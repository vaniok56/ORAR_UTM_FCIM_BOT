import ast
import asyncio
import datetime
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from test_upload_status import setUpModule, tearDownModule


class EmojiSettingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        import handlers.db as db
        import functions
        from localization import get_text, get_week_days, load_locales, SUPPORTED_LANGS
        from telethon.tl.custom import Button
        from telethon.errors import MessageNotModifiedError
        load_locales()
        self.runtime, self.db = functions, db
        self.text = get_text
        functions.clear_schedule_caches()
        # Load handler functions without starting Telegram or connecting MySQL.
        tree = ast.parse(Path("src/script.py").read_text())
        names = {"emoji_button", "emoji_command", "emoji_callback", "send_notification",
                 "send_schedule_tomorrow", "oree"}
        nodes = [node for node in tree.body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
        for node in nodes:
            node.decorator_list = []
        self.namespace = {
            "db": db, "Button": Button, "get_text": get_text,
            "emoji_preview": functions.emoji_preview,
            "format_id": functions.format_id, "is_rate_limited": Mock(return_value=False),
            "_get_sender_id_and_lang": AsyncMock(return_value=(42, "en")),
            "send_logs": Mock(), "MessageNotModifiedError": MessageNotModifiedError,
            "client": SimpleNamespace(send_message=AsyncMock()), "noti_send": 0,
            "print_next_course": functions.print_next_course,
            "format_hours": functions.format_hours, "get_week_days": get_week_days,
            "DEFAULT_LANG": "en", "SUPPORTED_LANGS": SUPPORTED_LANGS,
            "datetime": datetime, "moldova_tz": db.moldova_tz,
            "bulk_send_shift_earlier": datetime.timedelta(minutes=1), "bulk_send_interval": 0,
        }
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "src/script.py", "exec"), self.namespace)

    def event(self, data=b"emoji:42:1"):
        return SimpleNamespace(sender_id=42, is_private=True, data=data,
                               edit=AsyncMock(), answer=AsyncMock(), respond=AsyncMock())

    async def test_command_and_button_switch_both_states_and_keep_owner(self):
        event = self.event()
        with patch.object(self.db, "is_user_exists", return_value=True), \
                patch.object(self.db, "get_user_emoji", return_value=False), \
                patch.object(self.db, "set_user_emoji") as save:
            await self.namespace["emoji_command"](event)
            self.assertTrue(event.respond.call_args.args[0].startswith("Emoji OFF ❌"))
            self.assertEqual(event.respond.call_args.kwargs["buttons"][0][0].type.data, b"emoji:42:1")
            for target in (1, 0):
                event.data = f"emoji:42:{target}".encode()
                await self.namespace["emoji_callback"](event)
                save.assert_called_with("U42", bool(target))
                edited = event.edit.call_args
                label = self.text("en", "emoji_on" if target else "emoji_off")
                self.assertTrue(edited.args[0].startswith(label))
                self.assertEqual(edited.kwargs["buttons"][0][0].text, label)
                self.assertEqual(edited.kwargs["buttons"][0][0].type.data, f"emoji:42:{1-target}".encode())

    async def test_foreign_click_and_failed_save_cannot_edit(self):
        event = self.event(b"emoji:99:1")
        with patch.object(self.db, "set_user_emoji") as save:
            await self.namespace["emoji_callback"](event)
            save.assert_not_called()
            event.edit.assert_not_called()
        event = self.event()
        with patch.object(self.db, "is_user_exists", return_value=True), \
                patch.object(self.db, "set_user_emoji", side_effect=RuntimeError("offline")):
            await self.namespace["emoji_callback"](event)
            event.edit.assert_not_called()
            self.assertTrue(event.answer.call_args.kwargs["alert"])

    async def test_unregistered_user_and_duplicate_callback(self):
        event = self.event()
        with patch.object(self.db, "is_user_exists", return_value=False):
            await self.namespace["emoji_command"](event)
            self.assertIn("/start", event.respond.call_args.args[0])
        event = self.event()
        event.edit.side_effect = self.namespace["MessageNotModifiedError"](request=None)
        with patch.object(self.db, "is_user_exists", return_value=True), \
                patch.object(self.db, "set_user_emoji"):
            await self.namespace["emoji_callback"](event)
            self.assertEqual(event.answer.call_args.args[0], "Emoji ON ✅")

    def test_preview_and_hours_all_languages(self):
        for lang in ("ro", "ru", "en"):
            on = self.runtime.emoji_preview(lang, True)
            off = self.runtime.emoji_preview(lang, False)
            self.assertNotIn("06.10.2026", off)
            self.assertNotIn("{date}", off)
            self.assertNotIn("{day}", off)
            for glyph in ("🎙️", "📖", "🧑‍🏫", "🏫", "🌓", "🕗", "⏳"):
                self.assertIn(glyph, on)
                self.assertNotIn(glyph, off)
            self.assertIn("c. Algebra liniară și geometria analitică", on)
            self.assertIn("sem. ALGA", on)
            self.assertIn("c. Algebra liniară și geometria analitică", off)
            self.assertIn("🏫 3-3", on)
            self.assertIn("202", off)
            self.assertIn("2) lab. CDE 0.5 gr.", off)
            self.assertNotIn("🌗", on)
            self.assertEqual(on.count("lab. 0.5 gr."), 1)
            self.assertEqual(on.count("<b>"), 3)
            self.assertEqual(on.count("⏳"), 1)
            self.assertIn("#2 ⏳", on)
            if lang == "ro":
                self.assertTrue(on.startswith("Emoji pornite ✅\n\nAfișează emoji în orar, /hours și notificări.\nExemplu:\n"))
            self.assertNotIn("\n Time:", off)
            for glyph in ("🕗", "🍽️", "☕"):
                self.assertIn(glyph, self.runtime.format_hours(lang, emoji=True))
                self.assertNotIn(glyph, self.runtime.format_hours(lang, emoji=False))

    async def test_failed_preference_read_still_delivers_raw_reminder(self):
        self.namespace["print_next_course"] = Mock(return_value="raw schedule")
        with patch.object(self.db, "locate_field", return_value=1), \
                patch.object(self.db, "get_db_connection", side_effect=RuntimeError("offline")):
            self.assertTrue(await self.namespace["send_notification"](
                42, (1, "SAMPLE", 0, 1, 0, "en", 1)))
        self.namespace["print_next_course"].assert_called_once_with(
            1, "SAMPLE", 0, 1, 0, "en", study_year=1, emoji=False)
        self.namespace["client"].send_message.assert_awaited_once()

    async def test_settings_read_failure_does_not_claim_saved_state(self):
        event = self.event()
        with patch.object(self.db, "is_user_exists", return_value=True), \
                patch.object(self.db, "get_db_connection", side_effect=RuntimeError("offline")):
            await self.namespace["emoji_command"](event)
        self.assertEqual(event.respond.call_args.args[0], self.text("en", "emoji_error"))
        self.assertNotIn("buttons", event.respond.call_args.kwargs)

    async def test_hours_preference_read_failure_still_sends_without_emojis(self):
        client = AsyncMock()
        self.namespace.update(client=client,
                              functions=SimpleNamespace(messages=SimpleNamespace(SetTypingRequest=Mock())),
                              types=SimpleNamespace(SendMessageTypingAction=Mock()))
        with patch.object(self.db, "get_db_connection", side_effect=RuntimeError("offline")):
            await self.namespace["oree"](self.event())
        client.send_message.assert_awaited_once()
        text = client.send_message.call_args.args[1]
        self.assertIn(self.text("en", "hours_title"), text)
        for glyph in ("🕗", "🍽️", "☕"):
            self.assertNotIn(glyph, text)

    async def test_tomorrow_preference_read_failure_still_delivers_raw_schedule(self):
        import pandas as pd
        users = pd.DataFrame([{"SENDER": "U42", "group_n": "SAMPLE", "ban": 0,
                               "noti": 1, "subgrupa": 0, "lang": "en", "year_s": 1}])
        self.namespace.update(pd=pd, print_day=Mock(return_value="raw schedule"),
                              asyncio=SimpleNamespace(sleep=AsyncMock(
                                  side_effect=[None, None, asyncio.CancelledError()])))
        with patch.object(self.db, "get_app_setting", return_value="0"), \
                patch.object(self.db, "get_all_users", return_value=users), \
                patch.object(self.db, "get_db_connection", side_effect=RuntimeError("offline")), \
                self.assertRaises(asyncio.CancelledError):
            await self.namespace["send_schedule_tomorrow"]()
        self.assertFalse(self.namespace["print_day"].call_args.kwargs["emoji"])
        self.namespace["client"].send_message.assert_awaited_once()
        self.assertIn("raw schedule", self.namespace["client"].send_message.call_args.args[1])

    async def test_schedule_caches_and_reminders_use_current_preference(self):
        from course_classification import classify
        raw = "Matematică\nExemplu A.\n101"
        sheet = object()
        with patch.object(self.runtime, "get_schedule_and_groups", return_value=(sheet, ["SAMPLE"])), \
                patch.object(self.runtime, "get_daily_courses", return_value=[(1, raw)]), \
                patch.dict(self.runtime.classifications_by_schedule, {id(sheet): {raw: classify(raw)}}):
            for enabled in (True, False, True, False):
                for output in (
                    self.runtime.print_day(1, "SAMPLE", 0, 0, "en", 1, emoji=enabled),
                    self.runtime.print_sapt(0, "SAMPLE", 0, "en", emoji=enabled),
                    self.runtime.print_next_course(1, "SAMPLE", 0, 1, 0, "en", emoji=enabled),
                ):
                    self.assertEqual("📖" in output, enabled)
                    self.assertEqual("🕗" in output, enabled)
                    self.assertIn(raw if not enabled else "Matematică", output)
            # The reminder was prepared earlier; reread preference at delivery.
            with patch.object(self.db, "locate_field", return_value=1), \
                    patch.object(self.db, "get_user_emoji", return_value=False):
                await self.namespace["send_notification"](42, (1, "SAMPLE", 0, 1, 0, "en", 1))
                text = self.namespace["client"].send_message.call_args.args[1]
                self.assertNotIn("📖", text)
                self.assertNotIn("🕗", text)


if __name__ == "__main__":
    unittest.main()
