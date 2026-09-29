import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))


def bot_dependencies_installed():
    import importlib.util

    return all(importlib.util.find_spec(name) for name in ("pandas", "telethon"))


class VersionPolicyTests(unittest.TestCase):
    """A same or older revision warns instead of blocking publication."""

    def test_same_or_older_revision_is_warned_not_blocked(self):
        source = (Path(__file__).parent / "src" / "handlers" / "admin_handlers.py").read_text(encoding="utf-8")
        self.assertNotIn('await event.answer("Staged revision is not newer than the active schedule.", alert=True)',
                         source)
        # Warned once, when the batch is reviewed. The publish step only rechecks
        # that the active file is still the one that was reviewed.
        self.assertIn('item["version_warning"] = not newer', source)
        self.assertIn("⚠️ Warning: not newer than the active revision.", source)
        self.assertIn("⚠️ Warning: published a same/older revision.", source)


@unittest.skipUnless(
    bot_dependencies_installed(),
    "bot dependencies (pandas, telethon) are only installed in the container",
)
class BatchStatusMessageTests(unittest.TestCase):
    """Bulk uploads must reuse one status message instead of one per file."""

    class FakeMessage:
        def __init__(self, chat_id, text, buttons, log, editable=True):
            self.text = text
            self.buttons = buttons
            self.log = log
            self.editable = editable

        async def edit(self, text, buttons=None):
            if not self.editable:
                raise RuntimeError("message cannot be edited")
            self.log.append(("edit", text))
            self.text = text
            self.buttons = buttons
            return self

    class FakeClient:
        def __init__(self, log):
            self.log = log

        async def send_message(self, chat_id, text, buttons=None):
            self.log.append(("send", text))
            return BatchStatusMessageTests.FakeMessage(chat_id, text, buttons, self.log)

    def test_first_status_sends_then_edits_the_same_message(self):
        import asyncio
        from handlers.admin_handlers import update_batch_status

        log = []
        client = self.FakeClient(log)
        state = {"token": "abcd1234"}

        async def scenario():
            first = await update_batch_status(client, state, 42, "one")
            second = await update_batch_status(client, state, 42, "two")
            third = await update_batch_status(client, state, 42, "three")
            return first, second, third

        first, second, third = asyncio.run(scenario())
        self.assertIs(first, second)
        self.assertIs(second, third)
        self.assertEqual([kind for kind, _ in log], ["send", "edit", "edit"])
        self.assertEqual(state["status_message"].text, "three")

    def test_uneditable_status_falls_back_to_a_new_message(self):
        import asyncio
        from handlers.admin_handlers import update_batch_status

        log = []
        client = self.FakeClient(log)
        state = {"token": "abcd1234"}

        async def scenario():
            await update_batch_status(client, state, 42, "one")
            state["status_message"].editable = False
            await update_batch_status(client, state, 42, "two")
            await update_batch_status(client, state, 42, "three")

        asyncio.run(scenario())
        self.assertEqual([kind for kind, _ in log], ["send", "send", "edit"])

    def test_progress_line_lists_staged_files(self):
        from handlers.admin_handlers import batch_progress_line

        self.assertEqual(batch_progress_line({"years": {}}), "no files staged yet")
        self.assertEqual(
            batch_progress_line({"years": {2: {"xlsx": "x", "pdf": "p"}, 1: {"xlsx": "x"}}}),
            "Year 1: XLSX, Year 2: XLSX PDF",
        )

    def test_stale_stages_are_purged_and_fresh_ones_kept(self):
        from handlers.admin_handlers import purge_stale_stages

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stale, fresh = root / "stale-batch", root / "fresh-batch"
            for path in (stale, fresh):
                path.mkdir()
                (path / "dean.xlsx").write_bytes(b"x")
            long_ago = time.time() - 3600
            os.utime(stale, (long_ago, long_ago))

            purge_stale_stages(root)

            self.assertFalse(stale.exists())
            self.assertTrue(fresh.exists())
