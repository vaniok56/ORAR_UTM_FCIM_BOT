import ast
import asyncio
import datetime as dt
import json
import os
import unittest
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from test_upload_status import setUpModule, tearDownModule

PAGE = '<tr><td>Orar Semestrul de TOAMNĂ</td><td><a href="/orar-sectia-zi-2/">Secţia zi</a></td></tr>'
URLS = {f'Anul {year}': f'https://fcim.utm.md/wp-content/uploads/sites/24/2026/10/anul_{year.lower()}_semestrul_{semester}-1.pdf'
        for year, semester in zip(('I', 'II', 'III', 'IV'), ('i', 'iii', 'v', 'vii'))}
MAPPING = '<script>window.ORAR_FCIM_EXCEL = ' + json.dumps(URLS) + ';</script>'


class MonitoringTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        import version_watch
        self.watch = version_watch
        self.fetch_original = version_watch.fetch
        self.values = {'fcim_owner_id': '42'}
        self.failed, self.hash, self.mapping = set(), 'a' * 64, MAPPING
        self.client = SimpleNamespace(send_message=AsyncMock())

        def claim(date):
            if self.values.get('fcim_attempt_date', '') >= date:
                return False
            self.values.update(fcim_attempt_date=date, fcim_run='incomplete')
            return True

        def save(values):
            for key, value in values.items():
                assert value is None or len(value) <= 255
                self.values.pop(key, None) if value is None else self.values.update({key: value})

        def fetch(url, pdf=False):
            if 'source' in self.failed or url in self.failed:
                raise TimeoutError()
            return self.hash if pdf else PAGE if url == version_watch.LANDING else self.mapping

        store = SimpleNamespace(get_app_settings=lambda prefix: {k: v for k, v in self.values.items() if k.startswith(prefix)},
                                get_app_setting=lambda key, default=None, **kw: self.values.get(key, default),
                                set_app_settings=save, claim_watch_date=claim)
        self.enterContext(patch.object(version_watch, 'db', store))
        self.fetch = self.enterContext(patch.object(version_watch, 'fetch', side_effect=fetch))

    async def poll(self, day):
        return await self.watch.check(dt.datetime(2026, 10, day, 18, tzinfo=self.watch.ZONE))

    def test_source_validation_and_download_limits(self):
        self.assertEqual(self.watch.interactive_url(PAGE), 'https://fcim.utm.md/orar-sectia-zi-2/')
        self.assertEqual(set(self.watch.pdf_mapping(MAPPING)), {1, 2, 3, 4})
        for page in ('', PAGE.replace('orar-sectia-zi-2/', 'master/'), PAGE.replace('</td></tr>', '<a href="/other/">Other</a></td></tr>')):
            with self.assertRaises(ValueError):
                self.watch.interactive_url(page)
        for page in (MAPPING.replace('Anul IV', 'Anul I'), MAPPING.replace('Anul IV', 'Master'),
                     MAPPING.replace('fcim.utm.md', 'other.example'), MAPPING.replace('.pdf', '.html'),
                     MAPPING.replace('ORAR_FCIM_EXCEL', 'moved'), MAPPING + MAPPING):
            with self.assertRaises(ValueError):
                self.watch.pdf_mapping(page)
        response = Mock(status_code=200, headers={'Content-Type': 'application/pdf'})
        response.__enter__, response.__exit__ = Mock(return_value=response), Mock(return_value=False)
        with patch.object(self.watch.requests, 'get', return_value=response) as get:
            for chunks, valid in (([b'%PDF-test'], True), ([b'HTML'], False), ([b'x' * (20 * 1024 * 1024 + 1)], False)):
                response.iter_content.return_value = chunks
                if valid:
                    self.assertEqual(len(self.fetch_original(next(iter(URLS.values())), pdf=True)), 64)
                else:
                    with self.assertRaises(ValueError):
                        self.fetch_original(next(iter(URLS.values())), pdf=True)
            self.assertFalse(get.call_args.kwargs['allow_redirects'])
            response.status_code = 302
            with self.assertRaises(ValueError):
                self.fetch_original(next(iter(URLS.values())), pdf=True)

    async def test_baseline_changes_retries_and_cached_status(self):
        self.assertIn('not checked yet', self.watch.version_text({1: 4}))
        await self.poll(20)
        await self.poll(21)
        self.assertFalse(any(k.startswith('fcim_notice_') for k in self.values))
        self.assertIn('1: v4 / v1 ❌', self.watch.version_text({1: 4}, dt.datetime(2026, 10, 21, 19, tzinfo=self.watch.ZONE)))
        self.assertIn('1: v1 / v1 ✅', self.watch.version_text({1: 1}, dt.datetime(2026, 10, 21, 19, tzinfo=self.watch.ZONE)))
        self.hash = 'b' * 64
        await self.poll(22)
        calls = self.fetch.call_count
        self.assertFalse(await self.poll(22))
        self.client.send_message.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            await self.watch.send_pending(self.client)
        self.client.send_message.side_effect = None
        await self.watch.send_pending(self.client)
        self.assertEqual(self.client.send_message.await_count, 5)  # One failed attempt, then four year notices.
        self.assertEqual(self.client.send_message.call_args.args[0], 42)
        self.assertEqual(self.fetch.call_count, calls)
        self.assertIn('stale', self.watch.version_text({1: 4}, dt.datetime(2026, 10, 24, 19, tzinfo=self.watch.ZONE)))
        self.mapping = MAPPING.replace('anul_i_semestrul_i-1.pdf', 'anul_i_semestrul_i-2.pdf')
        await self.poll(23)
        self.assertEqual(sum(k.startswith('fcim_notice_') for k in self.values), 1)

    async def test_check_waits_for_pending_notice_sender(self):
        url = next(iter(URLS.values()))
        self.values['fcim_notice_2026-10-20_1_change'] = json.dumps(
            {'source': '1', 'kind': 'change', 'at': '2026-10-20T18:00:00+03:00'})
        self.values['fcim_link_2026-10-20_1_change'] = url
        started, release = asyncio.Event(), asyncio.Event()

        async def send(*args, **kwargs):
            started.set()
            await release.wait()
            return 'sent'
        self.client.send_message.side_effect = send
        sender = asyncio.create_task(self.watch.send_pending(self.client))
        await started.wait()
        checker = asyncio.create_task(self.poll(20))
        await asyncio.sleep(0)
        self.assertFalse(checker.done())
        self.assertFalse(self.fetch.called)
        release.set()
        await sender
        self.assertTrue(await checker)
        self.assertTrue(self.fetch.called)

    async def test_empty_outbox_does_not_require_owner(self):
        self.values.pop('fcim_owner_id')
        await self.watch.send_pending(self.client)
        self.client.send_message.assert_not_awaited()

    async def test_outage_threshold_suppression_and_recovery(self):
        await self.poll(20)
        self.failed.add(URLS['Anul II'])
        await self.poll(21)
        self.assertFalse(any(k.startswith('fcim_notice_') for k in self.values))
        await self.poll(22)
        await self.watch.send_pending(self.client)
        await self.poll(23)
        await self.watch.send_pending(self.client)
        self.assertEqual(self.client.send_message.await_count, 1)
        self.assertEqual(self.values['fcim_hash_2'], 'a' * 64)
        self.failed.clear()
        await self.poll(24)
        await self.watch.send_pending(self.client)
        self.assertIn('recovered', self.client.send_message.call_args.args[1])
        self.assertEqual(self.client.send_message.await_count, 2)
        self.failed.add('source')
        await self.poll(25)
        await self.poll(26)
        self.assertEqual(sum(k.startswith('fcim_notice_') for k in self.values), 1)
        self.failed.clear()
        await self.poll(27)
        self.assertFalse(any(k.startswith('fcim_notice_') for k in self.values))

    async def test_daily_schedule_dst_and_no_startup_or_interrupted_retry(self):
        before = dt.datetime(2026, 10, 20, 17, 59, tzinfo=self.watch.ZONE)
        self.assertEqual(self.watch.next_check(before).day, 20)
        self.assertEqual(self.watch.next_check(before.replace(hour=18)).day, 21)
        for day in (dt.date(2026, 3, 28), dt.date(2026, 10, 24)):
            now = dt.datetime.combine(day, dt.time(19), self.watch.ZONE)
            target = self.watch.next_check(now)
            self.assertEqual((target.date(), target.hour), (day + dt.timedelta(days=1), 18))
            self.assertNotEqual(target.utcoffset(), now.utcoffset())
        with patch.object(self.watch.asyncio, 'sleep', side_effect=asyncio.CancelledError):
            with self.assertRaises(asyncio.CancelledError):
                await self.watch.run(self.client)
        self.fetch.assert_not_called()
        self.values.update(fcim_attempt_date='2026-10-20', fcim_run='incomplete')
        self.assertFalse(await self.poll(20))
        self.fetch.assert_not_called()
        self.assertIn('Web check interrupted', self.watch.version_text({1: 4}))

    async def test_delivery_outcomes_returns_guards_and_media(self):
        from telethon import TelegramClient, utils
        from telethon.errors import UserIsBlockedError, InputUserDeactivatedError, UserDeactivatedError
        import handlers.db as db
        user = {'delivery_status': 'unknown', 'noti': 0}

        def save(sender, status, only_blocked=False):
            if not only_blocked or user['delivery_status'] == 'blocked':
                user['delivery_status'] = status

        tree = ast.parse(Path('src/script.py').read_text())
        names = {'record_delivery', 'delivery_event', 'track_send', 'DeliveryClient'}
        nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name in names]
        scope = dict(db=db, asyncio=asyncio, datetime=dt, utils=utils, TelegramClient=TelegramClient,
                     format_id=lambda sender: f'U{sender}', send_logs=Mock(), delivery_locks=defaultdict(asyncio.Lock),
                     delivery_active=set(), delivery_events={}, UserIsBlockedError=UserIsBlockedError,
                     InputUserDeactivatedError=InputUserDeactivatedError, UserDeactivatedError=UserDeactivatedError)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'src/script.py', 'exec'), scope)
        with patch.object(db, 'set_delivery_status', side_effect=save), patch.object(db, 'has_interaction_since', return_value=False):
            for error, expected in ((UserIsBlockedError(None), 'blocked'), (InputUserDeactivatedError(None), 'deleted'), (TimeoutError(), 'unknown')):
                user['delivery_status'] = 'unknown'
                with self.assertRaises(type(error)):
                    await scope['track_send'](42, AsyncMock(side_effect=error))
                self.assertEqual(user['delivery_status'], expected)
            await scope['delivery_event'](42, dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=1), True)
            await scope['delivery_event'](42, dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=2))
            self.assertEqual(user, {'delivery_status': 'unknown', 'noti': 0})
            operation = AsyncMock()
            self.assertIsNone(await scope['track_send'](42, operation, lambda: False))
            operation.assert_not_awaited()
            client = scope['DeliveryClient'](None, 12345, '0' * 32)

            async def nested(entity, *args, **kwargs):
                return await client.send_file(entity, 'file')
            with patch.object(TelegramClient, 'send_message', side_effect=nested), \
                    patch.object(TelegramClient, 'send_file', new=AsyncMock(return_value='sent')):
                self.assertEqual(await client.send_message(42, 'text'), 'sent')
            self.assertEqual(user['delivery_status'], 'delivered')

    async def test_reminder_prepared_selection_must_still_match(self):
        import handlers.db as db
        tree = ast.parse(Path('src/script.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'send_notification')
        fresh = {'group_n': 'TI-251', 'year_s': 1, 'subgrupa': 0, 'lang': 'en',
                 'noti': 1, 'ban': 0, 'delivery_status': 'unknown'}
        client = SimpleNamespace(send_message=AsyncMock(return_value='sent'))
        scope = {'db': db, 'client': client, 'send_logs': Mock(), 'noti_send': 0,
                 'format_id': lambda sender: f'U{sender}', 'reminder_eligible': lambda *a, **k: True,
                 'print_next_course': Mock(return_value='X'), 'get_text': lambda *a, **k: 'text',
                 'SUPPORTED_LANGS': {'en'}, 'DEFAULT_LANG': 'en'}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'src/script.py', 'exec'), scope)
        with patch.object(db, 'get_user_for_delivery', return_value=fresh), \
                patch.object(db, 'get_user_emoji', return_value=False):
            self.assertFalse(await scope['send_notification'](42, (0, 'TI-299', 0, 0, 0, 'en', 1)))
            client.send_message.assert_not_awaited()
            self.assertTrue(await scope['send_notification'](42, (0, 'TI-251', 0, 0, 0, 'en', 1)))
            client.send_message.assert_awaited_once()

    def test_reminder_eligibility_preserves_overlapping_exclusions(self):
        import functions
        user = dict(noti=1, ban=0, group_n='TI-251', year_s=1, subgrupa=0, delivery_status='unknown')
        with patch.object(functions, 'get_schedule_and_groups') as resolve:
            self.assertTrue(functions.reminder_eligible(user))
            for changes in ({'noti': 0}, {'ban': 1}, {'delivery_status': 'blocked'}, {'delivery_status': 'deleted'}):
                self.assertFalse(functions.reminder_eligible(dict(user, **changes)))
            self.assertFalse(functions.reminder_eligible(dict(user, group_n='TI-252'), selection=user))
            resolve.side_effect = ValueError('invalid group')
            self.assertFalse(functions.reminder_eligible(user))

    @unittest.skipUnless(os.environ.get('MYSQL_HOST') == 'orar_review_mysql' and os.environ.get('ORAR_ISOLATED_TEST') == '1', 'isolated MySQL only')
    def test_database_status_and_daily_claim_survive_cache_reload(self):
        import handlers.db as db
        self.assertTrue(db.initialize_mysql_connection())
        self.assertRegex(db.get_app_setting('fcim_owner_id', None, strict=True) or '', r'^\d+$')
        db.add_new_user('U900001')
        self.assertEqual(db.get_user_for_delivery('U900001')['delivery_status'], 'unknown')
        for status in db.DELIVERY_STATUSES:
            db.set_delivery_status('U900001', status)
            self.assertEqual(db.get_user_for_delivery('U900001')['noti'], 0)
            self.assertEqual(db.locate_field('U900001', 'delivery_status'), status)
        db.user_data_cache.clear()
        db.load_user_cache()
        self.assertEqual(db.locate_field('U900001', 'delivery_status'), 'deleted')
        self.assertTrue(db.claim_watch_date('2026-10-20'))
        self.assertFalse(db.claim_watch_date('2026-10-20'))
        db.set_app_settings({'fcim_notice_test': 'pending'})
        self.assertEqual(db.get_app_settings('fcim_notice_'), {'fcim_notice_test': 'pending'})
