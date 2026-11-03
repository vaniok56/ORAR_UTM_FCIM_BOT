import asyncio
import datetime
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
import bulk_delivery as bulk


class SettingsTests(unittest.TestCase):
    def test_estimate_and_validation(self):
        target = datetime.datetime(2026, 10, 30, 20, tzinfo=datetime.timezone.utc)
        self.assertAlmostEqual(bulk.estimated_batch_seconds(814), 39.072)
        self.assertAlmostEqual((target - bulk.centered_start(target, 814)).total_seconds(), 19.536)
        with self.assertRaises(ValueError):
            bulk.centered_start(target.replace(tzinfo=None), 1)
        dst_target = datetime.datetime(2026, 10, 25, 4, tzinfo=ZoneInfo('Europe/Chisinau'))
        with patch.object(bulk, 'BULK_SEND_RATE', 1 / 14400), \
                patch.object(bulk, 'BULK_EXTRA_SECONDS_PER_RECIPIENT', 0):
            dst_start = bulk.centered_start(dst_target, 1)
        self.assertEqual(dst_target.timestamp() - dst_start.timestamp(), 7200)
        self.assertNotEqual(dst_start.utcoffset(), dst_target.utcoffset())
        with patch.object(bulk, 'BULK_EXTRA_SECONDS_PER_RECIPIENT', 0.01):
            self.assertAlmostEqual(bulk.estimated_batch_seconds(230), 11.5)
        for value in (0, -1, math.inf, math.nan):
            with patch.object(bulk, 'BULK_SEND_RATE', value), self.assertRaises(ValueError):
                bulk.validate_settings(Mock())
        for value in (-1, math.inf, math.nan):
            with patch.object(bulk, 'BULK_EXTRA_SECONDS_PER_RECIPIENT', value), self.assertRaises(ValueError):
                bulk.validate_settings(Mock())
        for value in (0, 1.5, True):
            with patch.object(bulk, 'BULK_MAX_IN_FLIGHT', value), self.assertRaises(ValueError):
                bulk.validate_settings(Mock())
        for rate, calls in ((30, 0), (31, 1)):
            log = Mock()
            with patch.object(bulk, 'BULK_SEND_RATE', rate):
                bulk.validate_settings(log)
            self.assertEqual(log.call_count, calls)

    def test_gate_priority_pacing_pause_and_no_catchup(self):
        clock = Mock(return_value=10.0)
        with patch.object(bulk.asyncio, 'get_running_loop', return_value=Mock(time=clock)):
            gate = bulk.SendGate()
            first = gate.register(True)
            self.assertTrue(gate.try_start(first, True)[0])
            low = gate.register(True)
            high = gate.register(False)
            clock.return_value = 10.05
            self.assertFalse(gate.try_start(low, True)[0])
            self.assertTrue(gate.try_start(high, False)[0])
            gate.pause(4)
            clock.return_value = 11
            gate.pause(6)
            clock.return_value = 15
            self.assertFalse(gate.try_start(low, True)[0])
            clock.return_value = 17
            self.assertTrue(gate.try_start(low, True)[0])
            next_low = gate.register(True)
            self.assertAlmostEqual(gate.try_start(next_low, True)[1], 1 / bulk.BULK_SEND_RATE)
            gate.remove(next_low, True)

    def test_guard_is_checked_only_when_admitted_and_clock_is_refreshed(self):
        clock = Mock(return_value=10.0)
        with patch.object(bulk.asyncio, 'get_running_loop', return_value=Mock(time=clock)):
            gate = bulk.SendGate()
            gate.next_start = 11
            ticket = gate.register(True)
            guard = Mock(return_value=True)
            self.assertFalse(gate.try_start(ticket, True, guard)[0])
            guard.assert_not_called()
            clock.return_value = 11
            def slow_guard():
                clock.return_value = 12
                return True
            self.assertTrue(gate.try_start(ticket, True, slow_guard)[0])
            self.assertAlmostEqual(gate.next_start, 12 + 1 / bulk.BULK_SEND_RATE)


class BatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_batches_count_outcomes(self):
        async def send(item):
            return (True, False, None)[item % 3]

        log = Mock()
        tasks = [asyncio.create_task(bulk.run_bulk(list(range(12)), send, 'test', log)) for _ in range(2)]
        results = await asyncio.gather(*tasks)
        for result in results:
            self.assertEqual((result['sent'], result['skipped'], result['failed']), (4, 4, 4))
        self.assertEqual(log.call_count, 2)
