import ast
import asyncio
import datetime
import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_backup_repeats_at_20_through_dst_and_recovers_from_failures(self):
        import pytz
        zone = pytz.timezone('Europe/Chisinau')
        node = next(n for n in ast.parse(Path('src/script.py').read_text()).body
                    if isinstance(n, ast.AsyncFunctionDef) and n.name == 'backup_database')
        for failure in ('dump', 'send', 'owner'):
            with self.subTest(failure=failure):
                clock = [zone.localize(datetime.datetime(2026, 3, 28, 19))]
                waits, attempts = [], []

                class Clock(datetime.datetime):
                    @classmethod
                    def now(cls, tz=None):
                        return clock[0].astimezone(tz) if tz else clock[0]

                async def sleep(seconds):
                    waits.append(seconds)
                    if len(waits) == 5:
                        raise asyncio.CancelledError
                    clock[0] = (clock[0].astimezone(datetime.timezone.utc) +
                                datetime.timedelta(seconds=seconds)).astimezone(zone)

                def owner(*args, **kwargs):
                    return 'bad' if failure == 'owner' and clock[0].day == 29 else '42'

                def dump(path):
                    attempts.append((clock[0], path))
                    return not (failure == 'dump' and clock[0].day == 29)

                async def send(*args, **kwargs):
                    if failure == 'send' and clock[0].day == 29:
                        raise OSError('send failed')

                db = SimpleNamespace(get_app_setting=Mock(side_effect=owner),
                                     create_mysql_backup=Mock(side_effect=dump), get_user_count=Mock(return_value=1))
                client = SimpleNamespace(send_file=AsyncMock(side_effect=send))
                logs = Mock()
                scope = {'datetime': SimpleNamespace(datetime=Clock, time=datetime.time, timedelta=datetime.timedelta),
                         'moldova_tz': zone, 'asyncio': SimpleNamespace(sleep=sleep), 'db': db,
                         'client': client, 'os': SimpleNamespace(makedirs=Mock()), 'send_logs': logs}
                exec(compile(ast.Module(body=[node], type_ignores=[]), 'src/script.py', 'exec'), scope)
                with self.assertRaises(asyncio.CancelledError):
                    await scope['backup_database']()
                self.assertEqual(waits[:4], [3600, 23 * 3600, 60, 24 * 3600 - 60])
                self.assertEqual([at.day for at, path in attempts], [28, 30] if failure == 'owner' else [28, 29, 30])
                self.assertTrue(all(at.hour == 20 and at.minute == 0 for at, path in attempts))
                self.assertEqual(client.send_file.await_count, 3 if failure == 'send' else 2)
                self.assertTrue(any('Error in database backup:' in call.args[0] for call in logs.call_args_list))

    def class_scheduler(self, clock, users, prepare, sleep, run, hours):
        import pytz
        from bulk_delivery import centered_start, estimated_batch_seconds, format_local_time
        source = ast.parse(Path('src/functions.py').read_text())
        next_course = next(n for n in source.body if isinstance(n, ast.FunctionDef)
                           and n.name == 'get_next_course_time')
        helper = {'datetime': datetime, 'moldova_tz': pytz.UTC, 'hours': hours}
        exec(compile(ast.Module(body=[next_course], type_ignores=[]), 'src/functions.py', 'exec'), helper)
        source = ast.parse(Path('src/script.py').read_text())
        scheduler = next(n for n in source.body if isinstance(n, ast.AsyncFunctionDef)
                         and n.name == 'send_curr_course_users')
        scope = {'datetime': SimpleNamespace(datetime=SimpleNamespace(now=lambda tz: clock[0])),
                 'moldova_tz': pytz.UTC, 'get_next_course_time': helper['get_next_course_time'],
                 'db': SimpleNamespace(get_all_users=lambda: list(users), get_app_setting=lambda *a: '0'),
                 'prepare_next_courses': prepare, 'send_logs': Mock(),
                 'asyncio': SimpleNamespace(sleep=sleep, create_task=asyncio.create_task, gather=asyncio.gather),
                 'centered_start': centered_start, 'estimated_batch_seconds': estimated_batch_seconds,
                 'format_local_time': format_local_time, 'run_bulk': run, 'send_notification': AsyncMock()}
        exec(compile(ast.Module(body=[scheduler], type_ignores=[]), 'src/script.py', 'exec'), scope)
        return scope

    async def test_empty_slot_waits_before_preparing_later_slot(self):
        clock = [datetime.datetime(2026, 10, 30, 7, tzinfo=datetime.timezone.utc)]
        users, sleeps = [], []
        prepared = []
        async def sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 1:
                users.append(42)
            clock[0] += datetime.timedelta(seconds=seconds)
            await asyncio.sleep(0)
            if len(sleeps) == 3:
                raise asyncio.CancelledError
        def prepare(day, parity, index, snapshot):
            prepared.append((index, len(snapshot)))
            return {42: 'course'} if index == 2 and snapshot else {}
        run = AsyncMock()
        scope = self.class_scheduler(clock, users, prepare, sleep, run, [['8.00-9.30'], ['9.45-11.15']])
        with self.assertRaises(asyncio.CancelledError):
            await scope['send_curr_course_users']()
        self.assertEqual(prepared[:2], [(1, 0), (2, 1)])
        self.assertEqual(sleeps[0], 45 * 60)
        self.assertEqual(run.await_count, 1)

    async def test_next_day_batches_start_in_order_without_waiting_for_delivery(self):
        clock = [datetime.datetime(2026, 10, 30, 18, 31, tzinfo=datetime.timezone.utc)]
        users, sleeps, started, finished = list(range(814)), [], [], []
        async def sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 3:
                await asyncio.sleep(0)
                raise asyncio.CancelledError
            clock[0] += datetime.timedelta(seconds=seconds)
            await asyncio.sleep(0)
        def prepare(day, parity, index, snapshot):
            return {user: 'course' for user in snapshot}
        async def run(items, send, kind, log, *, success_kind=None, estimate=None):
            started.append(estimate)
            try:
                await asyncio.Event().wait()
            finally:
                finished.append(clock[0])
        scope = self.class_scheduler(clock, users, prepare, sleep, run, [['8.00-9.30'], ['9.45-11.15']])
        with self.assertRaises(asyncio.CancelledError):
            await scope['send_curr_course_users']()
        self.assertEqual(started, [32.56, 32.56])
        planned = [call.args[0] for call in scope['send_logs'].call_args_list
                   if call.args[0].startswith('Next-class planned')]
        self.assertGreaterEqual(len(planned), 2)
        self.assertIn('target 09:45:00.000 | start 09:44:43.720', planned[0])
        self.assertIn('target 11:30:00.000 | start 11:29:43.720', planned[1])
        self.assertEqual(len(finished), 2)

    async def test_exact_start_runs_and_preparation_crossing_start_skips(self):
        from bulk_delivery import centered_start
        target = datetime.datetime(2026, 10, 30, 7, 45, tzinfo=datetime.timezone.utc)
        for late in (False, True):
            clock = [target - datetime.timedelta(seconds=1)]
            users, calls, sleeps = [42], [], []
            async def sleep(seconds):
                sleeps.append(seconds)
                clock[0] += datetime.timedelta(seconds=seconds)
                await asyncio.sleep(0)
                if len(sleeps) >= (1 if late else 2):
                    raise asyncio.CancelledError
            def prepare(day, parity, index, snapshot):
                calls.append(index)
                if len(calls) == 1:
                    clock[0] = target if late else centered_start(target, 1)
                    return {42: 'course'}
                return {}
            run = AsyncMock()
            scope = self.class_scheduler(clock, users, prepare, sleep, run, [['8.00-9.30']])
            with self.assertRaises(asyncio.CancelledError):
                await scope['send_curr_course_users']()
            self.assertEqual(run.await_count, 0 if late else 1)
            if late:
                self.assertTrue(any('calculated start already passed' in call.args[0]
                                    for call in scope['send_logs'].call_args_list))
            else:
                self.assertEqual(sleeps[0], 0)

    async def test_tomorrow_late_start_skips_today_and_uses_target_date(self):
        import pandas as pd
        import pytz
        from bulk_delivery import centered_start, estimated_batch_seconds, format_local_time
        node = next(n for n in ast.parse(Path('src/script.py').read_text()).body
                    if isinstance(n, ast.AsyncFunctionDef) and n.name == 'send_schedule_tomorrow')
        zone = pytz.timezone('Europe/Chisinau')
        now = zone.localize(datetime.datetime(2026, 12, 31, 19, 59, 59, 990000))
        class Clock(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return now
        logs = Mock()
        sleep = AsyncMock(side_effect=[None, __import__('asyncio').CancelledError()])
        async def run_now(items, send, *args, **kwargs):
            await send(items[0])
        run = AsyncMock(side_effect=run_now)
        centered_targets = []
        def record_centered(target, count):
            centered_targets.append(target)
            return centered_start(target, count)
        users = pd.DataFrame([{'SENDER': 'U42'}])
        scope = {'datetime': SimpleNamespace(datetime=Clock, timedelta=datetime.timedelta, time=datetime.time),
                 'moldova_tz': zone, 'db': SimpleNamespace(get_all_users=Mock(return_value=users),
                                                           get_app_setting=Mock(return_value='0')),
                 'reminder_eligible': lambda row: True, 'centered_start': record_centered,
                 'estimated_batch_seconds': estimated_batch_seconds, 'format_local_time': format_local_time,
                 'send_logs': logs,
                 'asyncio': SimpleNamespace(sleep=sleep), 'run_bulk': run,
                 'send_tomorrow_recipient': AsyncMock(return_value=True)}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'src/script.py', 'exec'), scope)
        with self.assertRaises(__import__('asyncio').CancelledError):
            await scope['send_schedule_tomorrow']()
        self.assertIn('calculated start already passed', logs.call_args_list[0].args[0])
        self.assertEqual(centered_targets[1].date(), datetime.date(2027, 1, 1))
        self.assertEqual(run.await_count, 1)
        scope['send_tomorrow_recipient'].assert_awaited_once_with(42, datetime.date(2027, 1, 2))


@unittest.skipUnless(all(importlib.util.find_spec(name) for name in ('pandas', 'telethon')),
                     'bot dependencies are only installed in the container')
class NotificationTimingTests(unittest.TestCase):
    def test_next_course_target_is_aware_and_advances_after_processing(self):
        import handlers.db
        import functions
        now = functions.moldova_tz.localize(datetime.datetime(2026, 9, 30, 11, 14, 0, 500000))
        index, target = functions.get_next_course_time(now)
        self.assertEqual(index, 3)
        self.assertEqual((target.hour, target.minute), (11, 15))
        self.assertIsNotNone(target.utcoffset())
        self.assertEqual(functions.get_next_course_time(now, target)[0], 4)
        self.assertEqual(functions.get_next_course_time(target + datetime.timedelta(seconds=1))[0], 4)
        evening = functions.moldova_tz.localize(datetime.datetime(2026, 10, 24, 20))
        index, tomorrow = functions.get_next_course_time(evening)
        self.assertEqual(index, 1)
        self.assertEqual(tomorrow.date(), datetime.date(2026, 10, 25))
        self.assertEqual((tomorrow.hour, tomorrow.minute), (7, 45))
        self.assertNotEqual(tomorrow.utcoffset(), evening.utcoffset())
