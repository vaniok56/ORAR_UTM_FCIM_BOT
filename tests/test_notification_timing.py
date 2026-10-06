import datetime
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@unittest.skipUnless(
    all(importlib.util.find_spec(name) for name in ("pandas", "telethon")),
    "bot dependencies are only installed in the container",
)
class NotificationTimingTests(unittest.TestCase):
    def test_notification_slot_is_selected_only_before_its_send_time(self):
        import handlers.db  # Load functions through the same import order as the bot.
        import functions

        class FixedDateTime(datetime.datetime):
            instant = None

            @classmethod
            def now(cls, tz=None):
                return tz.localize(cls.instant)

        with patch.object(functions.datetime, "datetime", FixedDateTime):
            FixedDateTime.instant = datetime.datetime(2026, 9, 30, 11, 13, 59, 500000)
            self.assertEqual(functions.get_next_course_time()[1], 3)

            FixedDateTime.instant = datetime.datetime(2026, 9, 30, 11, 14, 0, 500000)
            self.assertEqual(functions.get_next_course_time()[1], 4)
