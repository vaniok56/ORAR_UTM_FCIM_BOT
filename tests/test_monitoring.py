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
        from localization import load_locales
        load_locales()
        self.watch = version_watch
        self.fetch_original = version_watch.fetch
        self.values = {'fcim_owner_id': '42'}
        self.failed, self.hash, self.mapping = set(), 'a' * 64, MAPPING
        self.client = SimpleNamespace(send_message=AsyncMock())

        def claim(slot):
            if self.values.get('fcim_scheduled_slot', '') >= slot:
                return False
            self.values.update(fcim_scheduled_slot=slot, fcim_run='incomplete')
            return True

        def save(values):
            for key, value in values.items():
                assert len(key) <= 50
                assert value is None or len(value) <= 255
                self.values.pop(key, None) if value is None else self.values.update({key: value})

        def fetch(url, pdf=False):
            if 'source' in self.failed or url in self.failed:
                raise TimeoutError()
            return self.hash if pdf else PAGE if url == version_watch.LANDING else self.mapping

        store = SimpleNamespace(get_app_settings=lambda prefix: {k: v for k, v in self.values.items() if k.startswith(prefix)},
                                get_app_setting=lambda key, default=None, **kw: self.values.get(key, default),
                                set_app_settings=save, claim_watch_slot=claim)
        self.enterContext(patch.object(version_watch, 'db', store))
        self.fetch = self.enterContext(patch.object(version_watch, 'fetch', side_effect=fetch))

    async def poll(self, day, hour=18, minute=0, *, startup=False):
        return await self.watch.check(dt.datetime(2026, 10, day, hour, minute, tzinfo=self.watch.ZONE), startup=startup)

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

    async def test_pdf_buttons_are_direct_localized_cached_and_validated(self):
        await self.poll(20)
        self.failed.add('source')
        await self.poll(21)
        calls = self.fetch.call_count
        for lang, labels in {
            'ro': ['📄 Anul I', '📄 Anul II', '📄 Anul III', '📄 Anul IV'],
            'ru': ['📄 1 курс', '📄 2 курс', '📄 3 курс', '📄 4 курс'],
            'en': ['📄 Year I', '📄 Year II', '📄 Year III', '📄 Year IV'],
        }.items():
            rows = self.watch.pdf_buttons(lang)
            self.assertEqual([len(row) for row in rows], [2, 2])
            buttons = [button for row in rows for button in row]
            self.assertEqual([button.text for button in buttons], labels)
            self.assertEqual([button.type.url for button in buttons], list(URLS.values()))
        self.assertEqual(self.fetch.call_count, calls)
        for url in (None, 'https://other.example/file.pdf', URLS['Anul II']):
            self.values['fcim_url_1'] = url
            self.assertEqual(sum(map(len, self.watch.pdf_buttons('en'))), 3)
        with patch.object(self.watch.db, 'get_app_settings', side_effect=RuntimeError):
            self.assertEqual(self.watch.pdf_buttons('en'), [])

    async def test_last_successful_check_is_local_without_seconds_and_survives_failure(self):
        self.values['fcim_state_4'] = json.dumps({'ok': '2026-10-24T22:15:59+00:00'})
        now = dt.datetime(2026, 10, 25, 12, tzinfo=self.watch.ZONE)
        for lang, label in {'en': 'Last successful check', 'ro': 'Ultima verificare reușită',
                            'ru': 'Последняя успешная проверка'}.items():
            text = self.watch.version_text({1: 1, 2: 1, 3: 1, 4: 1}, now, lang=lang)
            self.assertIn(f'{label}: 25.10.2026 01:15', text)
            self.assertEqual(text.splitlines()[5], f'{label}: 25.10.2026 01:15')
            self.assertNotIn(':59', text)
        self.values['fcim_state_4'] = json.dumps({'ok': '2026-10-25T02:15:59+00:00', 'error': 'TimeoutError'})
        text = self.watch.version_text({4: 1}, now)
        self.assertIn('25.10.2026 04:15', text)
        self.assertIn('Web not checked yet', text)
        for value in ('bad', '2026-10-25T04:15:59'):
            self.values['fcim_state_4'] = json.dumps({'ok': value, 'error': 'TimeoutError'})
            self.assertIn('Last successful check: —', self.watch.version_text({4: 1}, now))

    async def test_version_handler_and_reply_keyboard_use_new_buttons(self):
        import functions
        from localization import get_text
        from telethon import Button, types
        tree = ast.parse(Path('src/script.py').read_text())
        nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and node.name == 'versionn']
        for node in nodes:
            node.decorator_list = []
        client = AsyncMock()
        scope = dict(Button=Button, types=types, get_text=get_text, build_bot_kb=functions.build_bot_kb,
                     client=client, _get_sender_id_and_lang=AsyncMock(return_value=(42, 'ru')),
                     is_rate_limited=lambda _: False, functions=SimpleNamespace(messages=SimpleNamespace(
                         SetTypingRequest=lambda **kw: None)), version_watch=self.watch,
                     get_local_schedule_versions=lambda: {1: 1, 2: 1, 3: 1, 4: 1},
                     latest_version='test', latest_date='test', send_logs=Mock(), format_id=str)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'src/script.py', 'exec'), scope)
        for lang, label in {'ro': 'Orar 🌐', 'ru': 'Расписание 🌐', 'en': 'Schedule 🌐'}.items():
            rows = functions.button_grid(scope['build_bot_kb'](lang), 2)
            self.assertEqual([button.text for button in rows[-1]], ['SIMU📚', label])
            self.assertEqual(rows[-1][1].type.url, 'https://fcim.utm.md/procesul-de-studii/orar')
        await self.poll(20)
        await scope['versionn'](SimpleNamespace())
        kwargs = client.send_message.call_args.kwargs
        self.assertEqual(kwargs['buttons'][0][0].text, '📄 1 курс')
        self.assertFalse(kwargs['link_preview'])
        self.assertIn('Последняя успешная проверка:', client.send_message.call_args.args[1])

    async def test_empty_outbox_does_not_require_owner(self):
        self.values.pop('fcim_owner_id')
        await self.watch.send_pending(self.client)
        self.client.send_message.assert_not_awaited()

    async def test_schedule_buttons_refresh_keyboard_but_slash_commands_do_not(self):
        import functions as runtime
        from localization import get_text, get_week_days
        from telethon import types
        handlers = [('azii', 'btn_today', '/today'), ('mainee', 'btn_tomorrow', '/tomorrow'),
                    ('sapt_curr', 'btn_current_week', '/curr_week'), ('sapt_viit', 'btn_next_week', '/next_week')]
        tree = ast.parse(Path('src/script.py').read_text())
        nodes = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef)
                 and n.name in {name for name, _, _ in handlers}]
        for node in nodes:
            node.decorator_list = []
        client = AsyncMock()
        scope = dict(client=client, datetime=dt, moldova_tz=runtime.moldova_tz,
                     _get_sender_id_and_lang=AsyncMock(), is_rate_limited=lambda _: False,
                     functions=SimpleNamespace(messages=SimpleNamespace(SetTypingRequest=lambda **kw: None)),
                     types=types, get_text=get_text, get_week_days=get_week_days, format_id=str,
                     current_pair_index=lambda: 0, print_day=Mock(), print_sapt=Mock(), send_logs=Mock(),
                     schedule_reply_buttons=runtime.schedule_reply_buttons,
                     db=SimpleNamespace(locate_field=lambda _, key: {'group_n': 'TEST', 'year_s': 1, 'subgrupa': 0}[key],
                                        get_user_emoji=lambda _: True))
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'src/script.py', 'exec'), scope)
        for lang in ('ro', 'ru', 'en'):
            scope['_get_sender_id_and_lang'].return_value = (42, lang)
            for name, key, command in handlers:
                for mode in ('schedule', 'empty', 'error'):
                    for render in (scope['print_day'], scope['print_sapt']):
                        render.return_value = '' if mode == 'empty' else 'schedule'
                        render.side_effect = ValueError('missing group') if mode == 'error' else None
                    for text in (command, command + '@testing_orar_bot', get_text(lang, key)):
                        with self.subTest(lang=lang, handler=name, mode=mode, text=text):
                            client.reset_mock()
                            await scope[name](SimpleNamespace(raw_text=text))
                            client.send_message.assert_awaited_once()
                            buttons = client.send_message.call_args.kwargs.get('buttons')
                            if text.startswith('/'):
                                self.assertIsNone(buttons)
                            else:
                                self.assertEqual([b.text for b in buttons[-1]], ['SIMU📚', get_text(lang, 'btn_web')])
        for code in ('ro', 'ru', 'en'):
            for key in runtime.SCHEDULE_BUTTON_KEYS:
                label = get_text(code, key)
                self.assertEqual(runtime.schedule_reply_buttons(label, 'ru')[-1][1].text, 'Расписание 🌐')
                self.assertIsNone(runtime.schedule_reply_buttons(label + ' extra', 'ru'))
        for text in ('/help', '/version', '', None):
            self.assertIsNone(runtime.schedule_reply_buttons(text, 'en'))

    async def test_group_selection_restores_shared_keyboard_with_website(self):
        import functions as runtime
        import handlers.group_handlers as group
        from localization import get_text
        self.assertIs(group.build_bot_kb, runtime.build_bot_kb)
        handlers = {}
        client = AsyncMock()
        client.on = Mock(side_effect=lambda _: lambda handler: handlers.setdefault(handler.__name__, handler))
        group.register_group_handlers(client, {}, {'1': {b'ti1': 'TI'}}, {'1': {'TI1': {b'1': 'TI-261'}}})
        event = SimpleNamespace(sender_id=42, message_id=1, data=b'group_pick_1', answer=AsyncMock())
        with patch.object(group, '_get_sender_id_and_lang', new=AsyncMock()) as sender, \
                patch.object(group, 'is_rate_limited', return_value=False), \
                patch.object(group.db, 'update_user_field'), patch.dict(group.temp_selection, clear=True):
            for lang in ('ro', 'ru', 'en'):
                sender.return_value = (42, lang)
                group.temp_selection[42] = dict(message_id=1, phase='group', speciality='TI', year='1')
                client.reset_mock()
                await handlers['group_callback'](event)
                buttons = client.send_message.call_args_list[0].kwargs['buttons']
                self.assertEqual([len(row) for row in buttons], [2, 2, 2])
                self.assertEqual([b.text for b in buttons[-1]], ['SIMU📚', get_text(lang, 'btn_web')])
                self.assertEqual(buttons[-1][1].type.url, 'https://fcim.utm.md/procesul-de-studii/orar')

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

    def test_twice_daily_schedule_boundaries_and_dst(self):
        for hour, minute, expected_day, expected_hour, expected_minute in (
                (0, 0, 20, 12, 30), (12, 29, 20, 12, 30), (12, 30, 20, 18, 0),
                (17, 59, 20, 18, 0), (18, 0, 21, 12, 30), (23, 59, 21, 12, 30)):
            now = dt.datetime(2026, 10, 20, hour, minute, tzinfo=self.watch.ZONE)
            target = self.watch.next_check(now)
            self.assertEqual((target.day, target.hour, target.minute), (expected_day, expected_hour, expected_minute))
            self.assertEqual(self.watch.next_check(now.astimezone(dt.timezone.utc)), target)
            self.assertLessEqual(self.watch.previous_check(now), now)
        for day in (dt.date(2026, 3, 28), dt.date(2026, 10, 24)):
            now = dt.datetime.combine(day, dt.time(19), self.watch.ZONE)
            target = self.watch.next_check(now)
            self.assertEqual((target.date(), target.hour, target.minute), (day + dt.timedelta(days=1), 12, 30))
            self.assertNotEqual(target.utcoffset(), now.utcoffset())

    async def test_restart_checks_do_not_consume_scheduled_slots(self):
        await self.poll(20, 10, startup=True)
        self.assertNotIn('fcim_scheduled_slot', self.values)
        self.assertTrue(await self.poll(20, 12, 30))
        self.assertFalse(await self.poll(20, 12, 30))
        self.assertTrue(await self.poll(20, 14, startup=True))
        self.assertEqual(self.values['fcim_scheduled_slot'], '2026-10-20T12:30')
        self.assertTrue(await self.poll(20))
        self.assertFalse(await self.poll(20))
        self.assertTrue(await self.poll(20, 20, startup=True))
        self.assertEqual(self.values['fcim_scheduled_slot'], '2026-10-20T18:00')
        self.assertEqual(self.fetch.call_count, 30)

    async def test_interrupted_slot_is_not_retried_but_restart_refreshes_it(self):
        self.values.update(fcim_scheduled_slot='2026-10-20T18:00', fcim_run='incomplete')
        self.assertFalse(await self.poll(20))
        self.fetch.assert_not_called()
        self.assertIn('Web check incomplete', self.watch.version_text({1: 4}))
        self.assertTrue(await self.poll(20, 19, startup=True))
        self.assertEqual(self.values['fcim_run'], 'complete')

    async def test_run_checks_on_every_start_even_after_previous_check(self):
        now = dt.datetime(2026, 10, 20, 14, tzinfo=self.watch.ZONE)
        await self.poll(20, 12, 30)
        self.fetch.reset_mock()
        for _ in range(2):
            clock = Mock(wraps=dt.datetime)
            clock.now.return_value = now
            with patch.object(self.watch, 'dt', SimpleNamespace(datetime=clock, timedelta=dt.timedelta, timezone=dt.timezone)), \
                    patch.object(self.watch.asyncio, 'sleep', side_effect=asyncio.CancelledError):
                with self.assertRaises(asyncio.CancelledError):
                    await self.watch.run(self.client)
        self.assertEqual(self.fetch.call_count, 12)
        self.assertEqual(self.values['fcim_scheduled_slot'], '2026-10-20T12:30')

    async def test_startup_crossing_a_slot_keeps_the_scheduled_check(self):
        for hour, minute in ((12, 29), (17, 59)):
            for failure in (None, RuntimeError('DB unavailable')):
                before = dt.datetime(2026, 10, 20, hour, minute, 59, tzinfo=self.watch.ZONE)
                after = before + dt.timedelta(seconds=6)
                clock = Mock(wraps=dt.datetime)
                clock.now.side_effect = [before, before, after, after, after]
                with patch.object(self.watch, 'dt', SimpleNamespace(datetime=clock, timedelta=dt.timedelta, timezone=dt.timezone)), \
                        patch.object(self.watch, 'check', new=AsyncMock(side_effect=[failure, None])) as check, \
                        patch.object(self.watch.asyncio, 'sleep', side_effect=asyncio.CancelledError):
                    with self.assertRaises(asyncio.CancelledError):
                        await self.watch.run(self.client)
                self.assertEqual(check.await_args_list[0].kwargs, {'startup': True})
                self.assertEqual(check.await_args_list[1].args, (after,))
                self.assertEqual(check.await_count, 2)

    async def test_startup_failures_do_not_advance_outage_but_success_recovers(self):
        await self.poll(19)
        self.failed.add('source')
        for hour in (8, 9, 10):
            await self.poll(20, hour, startup=True)
        self.assertEqual(json.loads(self.values['fcim_state_source'])['f'], 0)
        await self.poll(20, 12, 30)
        await self.poll(20, 13, startup=True)
        self.assertEqual(json.loads(self.values['fcim_state_source'])['f'], 1)
        self.assertFalse(any(k.startswith('fcim_notice_') for k in self.values))
        await self.poll(20)
        await self.watch.send_pending(self.client)
        self.assertEqual(self.client.send_message.await_count, 1)
        self.assertIn('two consecutive scheduled checks', self.client.send_message.call_args.args[1])
        self.failed.clear()
        await self.poll(20, 19, startup=True)
        await self.watch.send_pending(self.client)
        self.assertEqual(self.client.send_message.await_count, 2)
        self.assertIn('recovered', self.client.send_message.call_args.args[1])

    async def test_same_day_changes_keep_distinct_pending_links(self):
        await self.poll(20, 8, startup=True)
        now = dt.datetime(2026, 10, 20, 10, 0, 0, 100000, tzinfo=self.watch.ZONE)
        for version, micros in ((2, 100000), (3, 200000)):
            self.mapping = MAPPING.replace('anul_i_semestrul_i-1.pdf', f'anul_i_semestrul_i-{version}.pdf')
            await self.watch.check(now.replace(microsecond=micros), startup=True)
        self.assertEqual(sum(k.startswith('fcim_notice_') for k in self.values), 2)
        await self.watch.send_pending(self.client)
        self.assertEqual(self.client.send_message.await_count, 2)
        self.assertIn('anul_i_semestrul_i-2.pdf', self.client.send_message.call_args_list[0].args[1])
        self.assertIn('anul_i_semestrul_i-3.pdf', self.client.send_message.call_args_list[1].args[1])

    def test_notice_order_survives_repeated_dst_hour(self):
        first = dt.datetime(2026, 10, 25, 3, 45, tzinfo=self.watch.ZONE, fold=0)
        second = dt.datetime(2026, 10, 25, 3, 15, tzinfo=self.watch.ZONE, fold=1)
        keys = [self.watch.notice_key(at.isoformat(), 'source', 'recovery') for at in (first, second)]
        self.assertLess(keys[0], keys[1])
        self.assertTrue(all(len(key) <= 50 for key in keys))

    async def test_freshness_uses_latest_due_slot_not_just_date(self):
        await self.poll(20, 8, startup=True)
        def status(hour, minute=0):
            return self.watch.version_text({1: 1}, dt.datetime(2026, 10, 20, hour, minute, tzinfo=self.watch.ZONE))
        self.assertNotIn('stale', status(12, 29))
        self.assertIn('stale', status(12, 30))
        await self.poll(20, 12, 30)
        self.assertNotIn('stale', status(17, 59))
        self.assertIn('stale', status(18))
        await self.poll(20, 18, 1, startup=True)
        self.assertNotIn('stale', status(18, 2))

    def test_freshness_allows_five_minutes_early_but_keeps_later_checks_fresh(self):
        for day in (dt.date(2026, 10, 20), dt.date(2026, 10, 25)):
            for clock in self.watch.CHECK_TIMES:
                slot = dt.datetime.combine(day, clock, self.watch.ZONE)
                for seconds in (-301, -300, -1, 0, 300, 301, 3600):
                    at = slot + dt.timedelta(seconds=seconds)
                    now = max(slot, at) + dt.timedelta(seconds=1)
                    self.values['fcim_state_1'] = json.dumps({'ok': at.isoformat()})
                    self.values['fcim_url_1'] = URLS['Anul I']
                    with self.subTest(slot=slot, seconds=seconds):
                        text = self.watch.version_text({1: 1}, now)
                        self.assertEqual('Web check stale' in text, seconds < -300)

    async def test_startup_overlapping_slot_no_longer_reports_false_staleness(self):
        before = dt.datetime(2026, 10, 20, 12, 29, 50, tzinfo=self.watch.ZONE)
        await self.watch.check(before, startup=True)
        after = before + dt.timedelta(seconds=80)
        self.assertNotIn('Web check stale', self.watch.version_text({1: 1}, after))
        self.values['fcim_run'] = 'incomplete'
        self.assertIn('Web check incomplete', self.watch.version_text({1: 1}, after))

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
    def test_database_status_and_slot_claim_survive_cache_reload(self):
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
        self.assertTrue(db.claim_watch_slot('2026-10-20T12:30'))
        self.assertFalse(db.claim_watch_slot('2026-10-20T12:30'))
        self.assertTrue(db.claim_watch_slot('2026-10-20T18:00'))
        self.assertFalse(db.claim_watch_slot('2026-10-20T18:00'))
        self.assertFalse(db.claim_watch_slot('2026-10-20T12:30'))
        self.assertEqual(db.get_app_setting('fcim_scheduled_slot', strict=True), '2026-10-20T18:00')
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=8) as workers:
            self.assertEqual(sum(workers.map(db.claim_watch_slot, ['2026-10-21T12:30'] * 8)), 1)
        db.set_app_settings({'fcim_notice_test': 'pending'})
        self.assertEqual(db.get_app_settings('fcim_notice_'), {'fcim_notice_test': 'pending'})
