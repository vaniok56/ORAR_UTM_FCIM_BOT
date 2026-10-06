import asyncio
import logging
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def setUpModule():
    global sandbox, previous, modules
    sandbox = tempfile.TemporaryDirectory()
    root = Path(__file__).resolve().parent.parent
    modules = {name: module for name, module in sys.modules.items()
               if name in {"functions", "localization", "handlers"} or name.startswith("handlers.")}
    for name in modules:
        del sys.modules[name]
    previous = (Path.cwd(), sys.path[:], logging.getLogger().handlers[:],
                logging.getLogger().level, logging.Formatter.converter)
    shutil.copytree(root / "src", Path(sandbox.name) / "src", ignore=shutil.ignore_patterns("__pycache__", "dynamic_group_lists.py"))
    shutil.copytree(root / "locales", Path(sandbox.name) / "locales")
    Path(sandbox.name, "contributors.csv").write_text("user_id,orar\n")
    os.chdir(sandbox.name)
    sys.path.insert(0, str(Path(sandbox.name) / "src"))


def tearDownModule():
    for name in list(sys.modules):
        if name in {"functions", "localization", "handlers"} or name.startswith("handlers."):
            del sys.modules[name]
    sys.modules.update(modules)
    for handler in logging.getLogger().handlers:
        if handler not in previous[2]:
            handler.close()
    logging.getLogger().handlers[:] = previous[2]
    logging.getLogger().setLevel(previous[3])
    logging.Formatter.converter = previous[4]
    os.chdir(previous[0])
    sys.path[:] = previous[1]
    sandbox.cleanup()


class BatchStatusMessageTests(unittest.TestCase):
    def test_status_reuses_one_message_then_falls_back(self):
        from handlers.admin_handlers import update_batch_status

        class Message:
            def __init__(self, text, editable=True):
                self.text, self.editable = text, editable

            async def edit(self, text, **kwargs):
                if not self.editable:
                    raise RuntimeError("not editable")
                self.text = text
                return self

        class Client:
            def __init__(self):
                self.messages = []

            async def send_message(self, chat_id, text, **kwargs):
                message = Message(text)
                self.messages.append(message)
                return message

        async def check():
            client, state = Client(), {"token": "token"}
            first = await update_batch_status(client, state, 42, "one")
            self.assertIs(first, await update_batch_status(client, state, 42, "two"))
            first.editable = False
            self.assertIsNot(first, await update_batch_status(client, state, 42, "three"))

        asyncio.run(check())


class PublicationStateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        import handlers.admin_handlers as admin
        import functions
        from localization import load_locales
        load_locales()
        self.runtime, self.admin = functions, admin
        self.old_sheet, self.old_groups = functions.schedule2, functions.groups2
        self.old_sheet3, self.old_groups3 = functions.schedule3, functions.groups3
        self.old_classes = functions.classifications_by_schedule.copy()
        shutil.rmtree("schedules", ignore_errors=True)
        Path("schedules").mkdir()
        Path("src/dynamic_group_lists.py").unlink(missing_ok=True)
        self.handlers, self.specialties, self.groups = {}, {}, {}
        self.client = SimpleNamespace(on=lambda _: lambda handler: self.handlers.setdefault(handler.__name__, handler),
                                 send_message=AsyncMock(), send_file=AsyncMock())
        admin.register_admin_handlers(self.client, [], [], self.specialties, self.groups)
        handler = self.handlers["upload_publish"]
        self.batches = dict(zip(handler.__code__.co_freevars, (cell.cell_contents for cell in handler.__closure__)))["active_uploads"]
        from test_schedule_ingest import ScheduleIngestTests
        self.source = Path("source.xlsx")
        ScheduleIngestTests().dean_source(self.source)

    def tearDown(self):
        self.runtime.schedule2, self.runtime.groups2 = self.old_sheet, self.old_groups
        self.runtime.schedule3, self.runtime.groups3 = self.old_sheet3, self.old_groups3
        self.runtime.classifications_by_schedule.clear()
        self.runtime.classifications_by_schedule.update(self.old_classes)
        self.runtime.clear_schedule_caches()

    async def call(self, name, **values):
        event = SimpleNamespace(sender_id=int(self.admin.main_admin[1:]), is_private=True, id=1,
                                data=b"", text="", raw_text="", file=None, answer=AsyncMock(), reply=AsyncMock(),
                                get_sender=AsyncMock(return_value=SimpleNamespace(id=int(self.admin.main_admin[1:]))),
                                download_media=AsyncMock(side_effect=lambda path: shutil.copy2(self.source, path)))
        vars(event).update(values)
        event.raw_text = values.get("raw_text", event.text)
        await self.handlers[name](event)
        return event

    async def review(self):
        await self.call("update_schedule")
        await self.call("receive_dean_upload", file=SimpleNamespace(name="source.xlsx", size=self.source.stat().st_size))
        await self.call("receive_dean_upload", text="2=3")
        state = self.batches[int(self.admin.main_admin[1:])]
        await self.call("upload_review", data=f"upload_review_{state['token']}".encode())
        self.assertIn("prepared", state["years"][2])
        return state

    async def publish(self, state):
        return await self.call("upload_publish", data=f"upload_publish_{state['token']}_2".encode())

    async def test_publish_rejects_absent_then_appeared_and_changed_target(self):
        target = Path("schedules/orar2.xlsx")
        for existing in (False, True):
            if existing:
                await self.publish(await self.review())
            state = await self.review()
            self.assertEqual(state["years"][2]["target_hash"] is None, not existing)
            target.write_bytes(b"changed after review")
            event = await self.publish(state)
            self.assertIn("changed since review", event.answer.call_args.args[0])
            self.assertEqual(target.read_bytes(), b"changed after review")
            self.assertEqual(self.batches, {})
            self.assertFalse(state["stage"].exists())
            target.unlink()

    async def test_publication_failure_restores_files_and_ram(self):
        paths = [Path("schedules/orar2.xlsx"), Path("schedules/orar2.classifications.json"), Path("src/dynamic_group_lists.py")]
        for existing in (False, True):
            if existing:
                await self.publish(await self.review())
                self.assertTrue(all(path.is_file() for path in paths))
            before = {path: path.read_bytes() if path.exists() else None for path in paths}
            old_sheet, old_groups = self.runtime.schedule2, self.runtime.groups2[:]
            old_classes = self.runtime.classifications_by_schedule.copy()
            catalogs = self.specialties.copy(), self.groups.copy()
            source = self.runtime.openpyxl.load_workbook(self.source)
            source.active["E3"] = f"c. Revised {existing}"
            source.save(self.source)
            state = await self.review()
            original = self.admin.write_groups_to_json
            def fail_catalog():
                original()
                paths[2].write_bytes(b"forced partial catalog")
                raise RuntimeError("forced catalog failure")
            with patch.object(self.admin, "write_groups_to_json", side_effect=fail_catalog):
                await self.publish(state)
            self.assertEqual({path: path.read_bytes() if path.exists() else None for path in paths}, before)
            self.assertIs(self.runtime.schedule2, old_sheet)
            self.assertEqual(self.runtime.groups2, old_groups)
            self.assertEqual(self.runtime.classifications_by_schedule, old_classes)
            self.assertEqual((self.specialties, self.groups), catalogs)
            self.assertEqual(self.runtime.merged_cell_ranges, {})
            self.assertEqual(self.batches, {})

    def test_selected_year_wins_for_duplicate_group(self):
        for year in (2, 3):
            sheet = self.runtime.openpyxl.Workbook().active
            sheet.append([None, None, "TI-261"])
            sheet.append(["Luni", "8.00-9.30", f"Year{year}"])
            sheet.append([None, None, f"Year{year} lower"])
            sheet.merge_cells("B2:B3")
            self.runtime.activate_schedule(sheet, ["TI-261"], year)
        for year in (2, 3, 2):
            for text in (self.runtime.print_day(0, "TI-261", 0, 0, study_year=year),
                         self.runtime.print_sapt(0, "TI-261", 0, study_year=year),
                         self.runtime.print_next_course(0, "TI-261", 0, 1, 0, study_year=year)):
                self.assertIn(f"Year{year}", text)
                self.assertNotIn(f"Year{5-year}", text)
        with self.assertRaises(ValueError):
            self.runtime.get_schedule_and_groups("TI-261")

    async def test_old_group_menu_preserves_new_menu_context(self):
        import handlers.group_handlers as group
        group.register_group_handlers(self.client, {b"y2": "2"}, self.specialties, self.groups)
        sender = int(self.admin.main_admin[1:])
        current = {"message_id": 2, "phase": "year"}
        group.temp_selection[sender] = current
        with patch.object(group, "_get_lang", return_value="ro"):
            await self.call("year_callback", data=b"group_year_y2", message_id=1)
        self.assertIs(group.temp_selection.get(sender), current)
