import sys
import tempfile
import unittest
import json
from pathlib import Path
from types import SimpleNamespace

from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).parent / "src"))

from course_classification import (
    build_classifications,
    classify,
    classification_counts,
    format_course,
    load_classifications,
    review_csv,
    save_classifications,
    select_subgroup,
    sidecar_path,
    viewer_subgroup,
)


class CourseClassificationTests(unittest.TestCase):
    def test_lecture_uses_microphone_and_keeps_prefix_other_classes_keep_books(self):
        from html import escape
        for subject, glyph in (("c. Matematică", "🎙️"), ("sem. Matematică", "📖"),
                               ("AM", "📖"), ("lab. AM", "🌕")):
            raw = f"{subject}\nExemplu A.\n101"
            item = classify(raw)
            self.assertEqual(item["status"], "classified")
            output = format_course(raw, {raw: item})
            self.assertIn(glyph, output)
            if not subject.startswith("lab."):
                self.assertIn(subject, output)
            else:
                self.assertIn("🌕 lab. AM", output)
                self.assertNotIn("📖", output)
                self.assertNotIn("🎙️", output)
            self.assertEqual(format_course(raw, {raw: item}, emoji=False), escape(raw))
        combined = "1) c. AM\nExemplu A.\n101\n2) sem. AM\nExemplu B.\n102"
        output = format_course(combined, {combined: classify(combined)})
        self.assertIn("🎙️ 1) c. AM", output)
        self.assertIn("📖 2) sem. AM", output)
        unknown = "c. ambiguous"
        self.assertEqual(format_course(unknown, {unknown: classify(unknown)}), unknown)

    def test_sidecar_schema_rejects_whole_map_including_raw_and_nested_entries(self):
        import copy
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "schedule.xlsx"
            Workbook().save(path)
            raw = "1) lab. Algebra\nExample A.\n101\n2) lab. Logic\nSample B.\n102"
            valid = {raw: classify(raw), "unknown": classify("unknown")}
            save_classifications(path, valid, sidecar_path(path))
            self.assertEqual(load_classifications(path), valid)
            payload = json.loads(sidecar_path(path).read_text())
            broken = [[], {"xlsx_sha256": 1, "classes": valid},
                      {"xlsx_sha256": payload["xlsx_sha256"], "classes": []}]
            for field, value in (("teachers", [1]), ("rooms", "101"), ("status", []),
                                 ("subject", None), ("review_required", "yes"), ("raw", "other"), ("lab", True)):
                item = copy.deepcopy(payload)
                item["classes"]["unknown"][field] = value
                broken.append(item)
            for field, value in (("subject", ""), ("teachers", [None]), ("raw", "wrong nested raw")):
                item = copy.deepcopy(payload)
                item["classes"][raw]["entries"][0][field] = value
                broken.append(item)
            for item in broken:
                with self.subTest(item=item):
                    sidecar_path(path).write_text(json.dumps(item))
                    with self.assertLogs(level="WARNING"):
                        self.assertEqual(load_classifications(path), {})
            sidecar_path(path).unlink()
            self.assertEqual(load_classifications(path), {})

    def test_review_counts_never_sum_none(self):
        labels = {
            "normal": {"status": "classified"},
            "teacher flag": {"status": "classified", "review_required": True},
            "raw": {"status": "needs_review"},
            "unknown": {"status": "unclassified"},
        }
        self.assertEqual(classification_counts(labels),
                         {"classified": 1, "needs_review": 2, "unclassified": 1})

    def test_multiple_teachers_and_room_are_preserved(self):
        raw = "DAS\nPoștaru A.\nZaica M.\n113"
        item = classify(raw)
        self.assertEqual(item["status"], "classified")
        self.assertEqual(item["teachers"], ["Poștaru A.", "Zaica M."])
        self.assertEqual(item["rooms"], ["113"])
        self.assertEqual(item["subject"], "DAS")
        self.assertEqual(format_course(raw, {raw: item}).count("🧑‍🏫"), 2)

    def test_room_before_teachers_and_multiroom(self):
        english = classify("L. Engleză\n107/601\nTintiuc C.\nPușcașu A.")
        self.assertEqual(english["status"], "classified")
        self.assertEqual(english["rooms"], ["107/601"])
        self.assertEqual(english["teachers"], ["Tintiuc C.", "Pușcașu A."])
        self.assertEqual(classify("APA\nPerevoznic V.\n110\n112")["rooms"], ["110", "112"])
        whole = classify("Lab.\nCDE\nLitra D.\n406")
        self.assertEqual(whole["subject"], "CDE")
        self.assertEqual(whole["lab"], "whole")

    def test_lab_known_halls_and_ambiguous_lines(self):
        self.assertEqual(classify("c. Fizică\nRusu S.\n6-2 Henri Coandă")["status"], "classified")
        self.assertEqual(classify("c. PAD\nBolea P./ Brînză M.\nImunoTehnomed")["teachers"], ["Bolea P.", "Brînză M."])
        for raw in ("L. Engleză\n202\nL. Engleză\n718", "AM\nDohotaru L.\n720\nALGA\n720"):
            with self.subTest(raw=raw):
                self.assertEqual(classify(raw)["status"], "needs_review")
                self.assertEqual(format_course(raw, {raw: classify(raw)}), raw)
        for text in ("Activități individuale/ în grup", "Educație fizică", "Ed. fizică"):
            item = classify(text)
            self.assertEqual(item["status"], "classified")
            self.assertEqual(item["subject"], text)
            self.assertEqual(item["teachers"], [])
            self.assertEqual(item["rooms"], [])
        self.assertEqual(classify("Unknown isolated text")["status"], "unclassified")

    def test_ambiguous_subgroups_keep_all_lines(self):
        raw = "1) lab. 0.5 gr ASR\nSeniușin A.\n114\n2) lab. 0.5 gr IP\nSpatari A.\n224"
        self.assertEqual(classify(raw)["status"], "classified")
        self.assertEqual(format_course(raw, {raw: classify(raw)}).count("📖"), 2)
        self.assertEqual(classify(select_subgroup(raw, 1))["status"], "classified")
        self.assertEqual(classify(select_subgroup(raw, 2))["status"], "classified")
        self.assertEqual(select_subgroup("lab. 0.5 gr.\nRC\nBonta E.\n114", 2), "")
        shared = "lab. 0.5 gr.\n1) CDE\nChiriac M.\n\nA03\n2) MS\nLitra D.\n422"
        first = select_subgroup(shared, 1)
        second = select_subgroup(shared, 2)
        self.assertIn("1) CDE", first)
        self.assertNotIn("2) MS", first)
        self.assertIn("2) MS", second)
        self.assertNotIn("1) CDE", second)
        self.assertEqual(classify(first)["status"], "classified")
        self.assertEqual(classify(second)["status"], "classified")
        self.assertEqual(select_subgroup(shared, 0), shared)
        combined = classify(shared)
        self.assertEqual(combined["status"], "classified")
        self.assertEqual([entry["teachers"] for entry in combined["entries"]], [["Chiriac M."], ["Litra D."]])
        self.assertEqual([entry["rooms"] for entry in combined["entries"]], [["A03"], ["422"]])

    def test_incomplete_or_extra_numbered_class_stays_raw(self):
        # A sibling entry without a room is still a usable class: subject + teacher.
        missing_room = classify("1) lab. ASR\nSeniușin A.\n114\n2) lab. IP\nSpatari A.")
        self.assertEqual(missing_room["status"], "classified")
        self.assertEqual(missing_room["entries"][1]["rooms"], [])
        for raw in (
            "1) lab. ASR\nSeniușin A.\n114\n2) lab. IP\nSpatari A.\n224\n3) lab. SCR\nCazac A.\n526",
            "1) lab. ASR\nSeniușin A.\n114\n2) lab. IP\nSpatari A.\n224\nextra text",
        ):
            with self.subTest(raw=raw):
                item = classify(raw)
                self.assertEqual(item["status"], "needs_review")
                self.assertEqual(format_course(raw, {raw: item}), raw)

    def test_untrusted_html_is_escaped(self):
        raw = "<b>Subject</b>\nTeacher A.\n113"
        self.assertIn("&lt;b&gt;Subject&lt;/b&gt;", format_course(raw, {raw: classify(raw)}))

    def test_sidecar_must_match_xlsx(self):
        with tempfile.TemporaryDirectory() as directory:
            xlsx = Path(directory) / "orar2.xlsx"
            xlsx.write_bytes(b"schedule 1")
            raw = "DAS\nPoștaru A.\n113"
            save_classifications(xlsx, {raw: classify(raw)}, sidecar_path(xlsx))
            self.assertIn(raw, load_classifications(xlsx))
            xlsx.write_bytes(b"schedule 2")
            self.assertEqual(load_classifications(xlsx), {})

    def test_review_csv_quotes_multiline_raw(self):
        row = (1, "TI-261", "Luni", "8.00-9.30", "odd", 0, "needs_review", "A, B\nC", "ambiguous")
        data = review_csv([row, row]).decode("utf-8-sig")
        self.assertEqual(data.count("TI-261"), 1)
        self.assertIn('"A, B\nC"', data)
        self.assertIn("'=HYPERLINK", review_csv([(*row[:7], '=HYPERLINK("url")', row[-1])]).decode("utf-8-sig"))

    def test_review_week_matches_runtime_iso_week_parity(self):
        book = Workbook()
        sheet = book.active
        sheet["C2"] = "Unknown A"
        sheet["C3"] = "Unknown B"
        _, review = build_classifications(sheet, ["TI-261"], 1, ["Luni"] * 5, ["8.00-9.30"] * 7)
        self.assertEqual({row[7]: row[4] for row in review},
                         {"Unknown A": "ISO-even", "Unknown B": "ISO-odd"})

    def test_source_cell_boundaries_veto_composite_field_labels(self):
        raw = "DAS\nPoștaru A.\n113"
        book = Workbook()
        sheet = book.active
        sheet["C2"] = raw
        block = SimpleNamespace(group="TI-261", day="Luni", time="8.00-9.30",
                                values=[SimpleNamespace(value=raw)])
        labels, review = build_classifications(sheet, ["TI-261"], 1,
                                               ["Luni"] * 5, ["8.00-9.30"] * 7, [block])
        self.assertEqual(labels[raw]["status"], "needs_review")
        self.assertEqual(format_course(raw, labels), raw)
        self.assertTrue(review)
        block.values = [SimpleNamespace(value=value) for value in raw.splitlines()]
        labels, _ = build_classifications(sheet, ["TI-261"], 1,
                                          ["Luni"] * 5, ["8.00-9.30"] * 7, [block])
        self.assertEqual(labels[raw]["status"], "classified")

    def test_numbered_entries_require_source_backing(self):
        raw = "1) lab. ASR\nSeniușin A.\n114\n2) lab. IP\nSpatari A.\n224"
        book = Workbook()
        book.active["C2"] = raw
        block = SimpleNamespace(group="CR-231", day="Luni", time="8.00-9.30",
                                values=[SimpleNamespace(value=raw, merged_range=None)])
        labels, review = build_classifications(book.active, ["CR-231"], 4,
                                                ["Luni"] * 5, ["8.00-9.30"] * 7, [block])
        self.assertEqual(labels[raw]["status"], "needs_review")
        self.assertEqual(format_course(raw, labels), raw)
        self.assertTrue(review)
        block.values[0].merged_range = "C2:C13"
        labels, review = build_classifications(book.active, ["CR-231"], 4,
                                                ["Luni"] * 5, ["8.00-9.30"] * 7, [block])
        self.assertEqual(labels[raw]["status"], "classified")
        self.assertEqual(review, [])

    def test_numbered_output_escapes_user_html(self):
        raw = "1) lab. <b>ASR</b>\nSeniușin A.\n114\n2) lab. IP\nSpatari A.\n224"
        self.assertIn("&lt;b&gt;ASR&lt;/b&gt;", format_course(raw, {raw: classify(raw)}))

    def test_teacher_list_from_one_source_cell_is_safe(self):
        raw = "SO\nReițman P. / Dumitrașcu M.\n1-101/100"
        book = Workbook()
        sheet = book.active
        sheet["C2"] = raw
        block = SimpleNamespace(group="FAF-241", day="Luni", time="8.00-9.30",
                                values=[SimpleNamespace(value=value) for value in raw.splitlines()])
        labels, review = build_classifications(sheet, ["FAF-241"], 3,
                                               ["Luni"] * 5, ["8.00-9.30"] * 7, [block])
        self.assertEqual(labels[raw]["status"], "classified")
        self.assertEqual(labels[raw]["teachers"], ["Reițman P.", "Dumitrașcu M."])
        self.assertEqual(review, [])

    def test_cross_timeslot_evidence_requires_matching_resolved_pair(self):
        raw = "Lab. 0.5 gr.\nIoT\nLitra D.\nA01"
        book = Workbook()
        sheet = book.active
        sheet["C2"] = raw
        first = SimpleNamespace(group="TI-232", day="Luni", time="8.00-9.30",
                                values=[SimpleNamespace(value="Lab. 0.5 gr."), SimpleNamespace(value="IoT")])
        second = SimpleNamespace(group="TI-232", day="Luni", time="9.45-11.15",
                                 values=[SimpleNamespace(value="Litra D."), SimpleNamespace(value="A01")])
        pairs = [SimpleNamespace(group="TI-232", day="Luni", time=block.time, odd_text=raw,
                                 even_text=raw, status="auto", review_flags=["cross-timeslot source fragments joined"])
                 for block in (first, second)]
        labels, _ = build_classifications(sheet, ["TI-232"], 4, ["Luni"] * 5,
                                          ["8.00-9.30"] * 7, [first, second], pairs)
        self.assertEqual(labels[raw]["status"], "classified")
        pairs[1].odd_text = "different"
        labels, _ = build_classifications(sheet, ["TI-232"], 4, ["Luni"] * 5,
                                          ["8.00-9.30"] * 7, [first, second], pairs)
        self.assertEqual(labels[raw]["status"], "needs_review")

    def test_complete_merged_three_line_class_is_classified(self):
        raw = "lab. 0.5 gr. CDE\nLitra D.\nA03"
        book = Workbook()
        sheet = book.active
        sheet["C2"] = raw
        block = SimpleNamespace(group="TI-262", day="Luni", time="8.00-9.30",
                                values=[SimpleNamespace(value=raw, merged_range="C2:C13")])
        labels, review = build_classifications(sheet, ["TI-262"], 1,
                                               ["Luni"] * 5, ["8.00-9.30"] * 7, [block])
        self.assertEqual(labels[raw]["status"], "classified")
        self.assertEqual(review, [])

    def test_teacher_only_text_never_becomes_subject_and_room(self):
        self.assertEqual(classify("Popescu I.\n101")["status"], "needs_review")
        self.assertEqual(classify("DAS\nL. Engleză\n113")["status"], "needs_review")
        self.assertEqual(classify("L. Engleză\n202")["status"], "classified")

    def test_literal_teacher_names_classified_without_telegram_warning(self):
        for raw, subject, teachers, room in (
            ("L. Engleză\n203/601\nDutoaL., Nicolai F.", "L. Engleză", ["DutoaL.", "Nicolai F."], "203/601"),
            ("CDE\nBîrnaz\n524", "CDE", ["Bîrnaz"], "524"),
        ):
            with self.subTest(raw=raw):
                item = classify(raw)
                self.assertEqual(item["status"], "classified")
                self.assertTrue(item["review_required"])
                self.assertEqual((item["subject"], item["teachers"], item["rooms"]),
                                 (subject, teachers, [room]))
                rendered = format_course(raw, {raw: item})
                self.assertNotIn("Verify teacher name", rendered)
                self.assertEqual(rendered, "\n".join(
                    [f"📖 {subject}"] + [f"🧑‍🏫 {name}" for name in teachers] + [f"🏫 {room}"]))
                with tempfile.TemporaryDirectory() as directory:
                    xlsx = Path(directory) / "orar.xlsx"
                    xlsx.write_bytes(b"test schedule")
                    save_classifications(xlsx, {raw: item}, sidecar_path(xlsx))
                    stored = json.loads(sidecar_path(xlsx).read_text(encoding="utf-8"))["classes"][raw]
                    self.assertTrue(stored["review_required"])
                    self.assertIn("verify teacher", stored["reason"])
                self.assertEqual(classify(raw + "\nnew text")["status"], "needs_review")
        combined = classify("1) lab. 0.5 gr ASR\nSeniușin A.\n114\n2) lab. 0.5 gr IP\nSpatari A.\n224")
        self.assertEqual([entry["teachers"] for entry in combined["entries"]],
                         [["Seniușin A."], ["Spatari A."]])

    def test_physical_education_takes_any_teacher_and_room_mix(self):
        for raw, teachers, rooms in (
            ("Educație fizică", [], []),
            ("Ed. Fizică\nVerghizova O.", ["Verghizova O."], []),
            ("Ed. fizică\nNicora S.", ["Nicora S."], []),
            ("Ed. Fizică\nSala sportivă", [], ["Sala sportivă"]),
            ("Ed. Fizică\nVerghizova O.\nSala sportivă", ["Verghizova O."], ["Sala sportivă"]),
            ("Ed. Fizică\nVerghizova O.\nCaraus A.\nSala sportivă",
             ["Verghizova O.", "Caraus A."], ["Sala sportivă"]),
            ("Ed. Fizică\n112\n113", [], ["112", "113"]),
        ):
            with self.subTest(raw=raw):
                item = classify(raw)
                self.assertEqual(item["status"], "classified")
                self.assertEqual((item["teachers"], item["rooms"]), (teachers, rooms))
        self.assertEqual(classify("Ed. Fizică\nnot a person 42")["status"], "needs_review")

    def test_subject_with_room_and_teacher_does_not_look_like_a_person(self):
        self.assertEqual(classify("Criptografie\nZaica M.\nD01-03")["status"], "classified")
        self.assertEqual(classify("Fizica\nRusu S.\n201")["status"], "classified")
        inline = classify("c. Programarea Concurentă și Distribuită\nRotaru L. 614")
        self.assertEqual((inline["status"], inline["teachers"], inline["rooms"]),
                         ("classified", ["Rotaru L."], ["614"]))
        # A real person line in the subject position still needs review.
        self.assertEqual(classify("Popescu I.\n101")["status"], "needs_review")


if __name__ == "__main__":
    unittest.main()


class HalfLabTests(unittest.TestCase):
    SHAPES = (
        ("Lab. 0.5 gr.\nIoT\nLitra D.\nA01", "IoT"),
        ("Lab. 0.5 gr\nIoT\nLitra D.\nA01", "IoT"),
        ("Lab. 0.5 gr. IoT\nMaslova T.\nA01", "IoT"),
        ("lab. 0.5 gr. CDE\nLitra D.\nA03", "CDE"),
        ("lab. 0.5 gr TVLSIN\nTrofim V.\n426", "TVLSIN"),
        ("lab. 0.5 gr PSÎ\nSpatari A.\n224", "PSÎ"),
        ("lab. PADM 0.5 gr.\nBîrnaz A.\n427", "PADM"),
        ("lab. 0.5 gr.\nAFU\nBrînză M.\nȚugulea V.\n419", "AFU"),
    )

    def test_marker_splits_from_subject_in_every_observed_shape(self):
        for raw, expected_subject in self.SHAPES:
            with self.subTest(raw=raw):
                item = classify(raw)
                self.assertEqual(item["status"], "classified")
                self.assertEqual(item["lab"], "0.5")
                self.assertEqual(item["subject"], expected_subject)
                self.assertNotIn("0.5", item["subject"])
                self.assertTrue(item["teachers"] and item["rooms"])

    def test_glyph_marks_the_subgroup_a_class_is_for(self):
        raw, _ = self.SHAPES[0]
        labels = {raw: classify(raw)}
        # 🌗 is subgroup 1, 🌓 is subgroup 2, and a selected subgroup is constant.
        self.assertTrue(format_course(raw, labels, 1, False).startswith("🌗 Lab. 0.5 gr.\n📖 IoT"))
        self.assertTrue(format_course(raw, labels, 1, True).startswith("🌗 Lab. 0.5 gr."))
        self.assertTrue(format_course(raw, labels, 2, False).startswith("🌓 Lab. 0.5 gr."))
        self.assertTrue(format_course(raw, labels, 2, True).startswith("🌓 Lab. 0.5 gr."))
        # Combined view: single class belongs to half 1 on ISO-even weeks, half 2 on ISO-odd.
        self.assertTrue(format_course(raw, labels, 0, False).startswith("🌗 Lab. 0.5 gr."))
        self.assertTrue(format_course(raw, labels, 0, True).startswith("🌓 Lab. 0.5 gr."))
        self.assertTrue(format_course(raw, labels).startswith("🌗 Lab. 0.5 gr."))

    def test_numbered_pair_glyphs_follow_the_week_in_the_combined_view(self):
        raw = "1) lab. 0.5 gr ASR\nSeniușin A.\n114\n2) lab. 0.5 gr IP\nSpatari A.\n224"
        labels = {raw: classify(raw)}
        odd = format_course(raw, labels, 0, False)
        even = format_course(raw, labels, 0, True)
        self.assertIn("🌗 lab. 0.5 gr.\n📖 1) ASR", odd)
        self.assertIn("🌓 lab. 0.5 gr.\n📖 2) IP", odd)
        self.assertIn("🌓 lab. 0.5 gr.\n📖 1) ASR", even)
        self.assertIn("🌗 lab. 0.5 gr.\n📖 2) IP", even)

    def test_attending_half_alternates_on_odd_iso_weeks(self):
        self.assertEqual(viewer_subgroup(1, False), 1)
        self.assertEqual(viewer_subgroup(2, False), 2)
        self.assertEqual(viewer_subgroup(1, True), 2)
        self.assertEqual(viewer_subgroup(2, True), 1)
        self.assertEqual(viewer_subgroup(0, True), 0)
        self.assertEqual(viewer_subgroup("bad", True), 0)

    def test_numbered_halves_keep_numbers_and_inherit_the_marker(self):
        for raw, subjects in (
            ("lab. 0.5 gr.\n1) CDE\nChiriac M.\nA03\n2) MS\nLitra D.\n422", ["1) CDE", "2) MS"]),
            ("1) lab. 0.5 gr ASR\nSeniușin A.\n114\n2) lab. 0.5 gr IP\nSpatari A.\n224", ["1) ASR", "2) IP"]),
        ):
            with self.subTest(raw=raw):
                item = classify(raw)
                self.assertEqual(item["status"], "classified")
                self.assertEqual([entry["subject"] for entry in item["entries"]], subjects)
                self.assertTrue(all(entry.get("lab") == "0.5" for entry in item["entries"]))
                rendered = format_course(raw, {raw: item}, 1, False)
                self.assertEqual(rendered.count("🌗 lab. 0.5 gr."), 2)

    def test_marker_without_a_class_stays_raw(self):
        for raw in ("lab. 0.5 gr.", "1) lab. 0.5 gr."):
            with self.subTest(raw=raw):
                item = classify(raw)
                self.assertEqual(item["status"], "needs_review")
                self.assertEqual(format_course(raw, {raw: item}), raw)


class WholeLabTests(unittest.TestCase):
    SHAPES = (
        ("lab. CDE\nLitra D.\nA03", "CDE"),
        ("Lab. CDE\nLitra D.\nA03", "CDE"),
        ("Lab.\nCDE\nLitra D.\n406", "CDE"),
        ("lab. BD1\nPopescu I.\n113", "BD1"),
        ("lab. CI 2\nRotaru L.\n614", "CI 2"),
        ("lab. SO\nReutov V.\n210", "SO"),
        ("Lab. Fizică\nRusu S.\n201", "Fizică"),
        ("1) lab. IP\nSpatari A.\n224", "1) IP"),
        ("2) lab. SCR\nMelnic V.\nA02", "2) SCR"),
    )

    def test_marker_moves_to_its_own_line_and_subject_keeps_the_code(self):
        for raw, subject in self.SHAPES:
            with self.subTest(raw=raw):
                item = classify(raw)
                self.assertEqual(item["status"], "classified")
                self.assertEqual(item["lab"], "whole")
                self.assertEqual(item["subject"], subject)
                self.assertNotIn("lab", item["subject"].casefold())
                rendered = format_course(raw, {raw: item}, 1, False)
                marker = "Lab." if raw.startswith("Lab.") else "lab."
                self.assertTrue(rendered.startswith(f"🌕 {marker} {subject}\n"), rendered)
                self.assertNotIn("📖", rendered)
                self.assertEqual(rendered.count("🌕"), 1)

    def test_half_labs_keep_their_marker_and_phase(self):
        for raw in ("Lab. 0.5 gr.\nIoT\nLitra D.\nA01", "lab. 0.5 gr. CDE\nLitra D.\nA03"):
            with self.subTest(raw=raw):
                item = classify(raw)
                self.assertEqual(item["lab"], "0.5")
                marker = raw.split()[0]
                self.assertTrue(format_course(raw, {raw: item}, 1, False).startswith(f"🌗 {marker} 0.5 gr."))

    def test_lab_spelling_and_case_are_preserved(self):
        for marker in ("lab.", "Lab.", "LAB.", "lab"):
            for half in ("", " 0.5 gr."):
                raw = f"2) {marker} IP{half}\nExemplu A.\n101"
                item = classify(raw)
                self.assertEqual(item["status"], "classified")
                rendered = format_course(raw, {raw: item}, 2, False)
                expected = f"🌓 {marker} 0.5 gr.\n📖 2) IP" if half else f"🌕 {marker} 2) IP"
                self.assertTrue(rendered.startswith(expected + "\n"), rendered)

    def test_compact_source_marker_keeps_case_and_subject_is_html_escaped(self):
        for marker in ("lab.", "Lab.", "LAB."):
            raw = f"{marker}PAE\nExemplu A.\n101"
            self.assertTrue(format_course(raw, {raw: classify(raw)}).startswith(f"🌕 {marker} PAE\n"))
        raw = "lab. A&B\nExemplu A.\n101"
        self.assertIn("🌕 lab. A&amp;B", format_course(raw, {raw: classify(raw)}))

    def test_non_lab_subjects_get_no_moon(self):
        for raw in ("c. Programarea declarativă\nBumbu T.\n104",
                    "Ed. Fizică\nVerghizova O.",
                    "SO\nReițman P.\n101",
                    "Elaborare raport\nPopescu I.\n220"):
            with self.subTest(raw=raw):
                item = classify(raw)
                rendered = format_course(raw, {raw: item}, 1, False)
                self.assertNotIn("🌕", rendered)
                self.assertNotIn("🌗", rendered)
                self.assertNotIn("🌓", rendered)

    def test_lab_word_inside_another_word_is_not_a_lab_marker(self):
        self.assertIsNone(classify("Elaborare\nPopescu I.\n220").get("lab"))
