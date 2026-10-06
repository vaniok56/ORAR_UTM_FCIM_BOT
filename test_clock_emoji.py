import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))


class ClockEmojiTests(unittest.TestCase):
    def test_clock_face_follows_the_standard_rounding(self):
        from clock_emoji import clock_face

        self.assertEqual([clock_face(t) for t in
                          ("8.00-9.30", "9.45-11.15", "11.30-13.00", "13.30-15.00",
                           "15.15-16.45", "17.00-18.30", "18.45-20.15")],
                         ["🕗", "🕙", "🕦", "🕜", "🕞", "🕔", "🕖"])
        self.assertEqual(clock_face("8.14-9.30"), "🕗")
        self.assertEqual(clock_face("8.15-9.30"), "🕣")
        self.assertEqual(clock_face("12.45-14.00"), "🕐")
        self.assertEqual(clock_face("nonsense"), "🕐")

    def test_current_pair_marks_the_running_pair_then_the_next(self):
        import datetime
        import pytz
        from clock_emoji import current_pair_index

        tz = pytz.timezone("Europe/Chisinau")

        def pair(hour, minute):
            return current_pair_index(tz.localize(datetime.datetime(2026, 9, 29, hour, minute)))

        self.assertEqual(pair(7, 30), 1)     # before the first pair -> the next one
        self.assertEqual(pair(8, 0), 1)      # running
        self.assertEqual(pair(9, 29), 1)     # still running
        self.assertEqual(pair(9, 35), 2)     # in the break -> the next pair
        self.assertEqual(pair(12, 10), 3)    # running
        self.assertEqual(pair(15, 20), 5)    # running
        self.assertEqual(pair(18, 50), 7)    # running
        self.assertEqual(pair(20, 30), 0)    # day finished -> no marker

    def test_hourglass_only_on_the_marked_pair(self):
        from clock_emoji import pair_index_label

        self.assertEqual(pair_index_label(4, 4), "4 ⏳")
        self.assertEqual(pair_index_label(3, 4), 3)
        self.assertEqual(pair_index_label(4, None), 4)
        self.assertEqual(pair_index_label(4, 0), 4)


class ClockLocaleTests(unittest.TestCase):
    """The clock face sits in front of the label, so every locale needs it."""

    def test_every_locale_puts_the_clock_before_the_time_label(self):
        import json
        from clock_emoji import clock_face

        locales = sorted(Path(__file__).parent.joinpath("locales").glob("*.json"))
        self.assertTrue(locales)
        for path in locales:
            with self.subTest(locale=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                for key in ("hour_label", "pair_format"):
                    self.assertIn("{clock}", data[key], f"{path.name}:{key} lacks {{clock}}")
                label = data["hour_label"].format(clock=clock_face("8.00-9.30") + " ", time="8.00-9.30")
                self.assertTrue(label.startswith("🕗 "), label)
                block = data["pair_format"].format(index=1, course="X", time="8.00-9.30",
                                                   clock=clock_face("8.00-9.30") + " ")
                self.assertIn("\n🕗 ", block)
