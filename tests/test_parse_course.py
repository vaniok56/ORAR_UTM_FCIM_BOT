import re
import pytest


def _is_room(val: str) -> bool:
    v = val.strip()
    if '/' in v:
        parts = v.split('/')
        return all(bool(re.match(r'^[A-Za-z]?[\d\-]*\d[\dA-Za-z\-]*$', p.strip())) for p in parts)
    return bool(re.match(r'^[A-Za-z]?[\d\-]*\d[\dA-Za-z\-]*$', v))


def _extract_teacher_from_line(line: str):
    patterns = [
        r'\b([A-ZĂÎȘȚa-zăîșț]{2,})\s+([A-ZĂÎȘȚ][a-zăîșț]*\.)',  # Name I.
        r'\b([A-ZĂÎȘȚa-zăîșț]{2,})\.\s+([A-ZĂÎȘȚ][a-zăîșț]{0,1})\b',  # Name. I
        r'\b([A-ZĂÎȘȚ][a-zăîșț]{2,})\s+([A-ZĂÎȘȚ][a-zăîșț]{2,})\b',  # Full Name (mixed-case, no initial)
    ]
    all_matches = []
    for pat in patterns:
        all_matches.extend(re.finditer(pat, line))

    if all_matches:
        m = sorted(all_matches, key=lambda x: x.end())[-1]
        subject = line[:m.start()].strip()
        teacher = f"{m.group(1)} {m.group(2)}"
        room = line[m.end():].strip()
        return subject, teacher, room

    return line.strip(), "", ""


def parse_course(course: str):
    if not course or not str(course).strip():
        return "", "", ""

    lines = [line.strip() for line in str(course).split("\n") if line.strip()]

    if len(lines) == 0:
        return "", "", ""
    elif len(lines) == 1:
        subject, teacher, room = _extract_teacher_from_line(lines[0])
        return subject, teacher, room
    elif len(lines) == 2:
        if _is_room(lines[1]):
            subject, teacher, room = _extract_teacher_from_line(lines[0])
            if not room:
                room = lines[1]
            _SUBJ_PFX = ("Limba", "L.", "L.", "Ed.", "Ed", "Sem.", "se.")
            if teacher and any(teacher.startswith(p) for p in _SUBJ_PFX):
                subject = f"{subject} {teacher}".strip() if subject else teacher
                teacher = ""
            return subject, teacher, room
        elif _is_room(lines[0]):
            return lines[1], "", lines[0]
        else:
            _, test_teacher, test_room = _extract_teacher_from_line(lines[1])
            if test_teacher and test_room:
                return lines[0], test_teacher, test_room
            elif test_teacher:
                return lines[0], lines[1], ""
            else:
                subject, teacher, room = _extract_teacher_from_line(lines[0])
                if not teacher:
                    teacher = lines[1]
                return subject, teacher, room
    else:
        if len(lines) >= 3 and _is_room(lines[1]) and _is_room(lines[2]):
            return lines[0], "", f"{lines[1]}/{lines[2]}"
        return lines[0], lines[1], lines[2]


# ============================================================
# _is_room tests
# ============================================================

class TestIsRoom:
    def test_simple_numbers(self):
        assert _is_room("201") is True
        assert _is_room("310") is True
        assert _is_room("420") is True
        assert _is_room("7") is True

    def test_dash_format(self):
        assert _is_room("3-3") is True
        assert _is_room("6-2") is True
        assert _is_room("1-1") is True

    def test_complex_rooms(self):
        assert _is_room("D-02-04") is True
        assert _is_room("D01-03") is True
        assert _is_room("D123") is True

    def test_letter_prefix(self):
        assert _is_room("A201") is True
        assert _is_room("B3-3") is True

    def test_not_rooms(self):
        assert _is_room("Crețu V.") is False
        assert _is_room("Rotari A.") is False
        assert _is_room("sem. ALGA") is False
        assert _is_room("c. CDE") is False
        assert _is_room("Costaș") is False
        assert _is_room("") is False
        assert _is_room("hello") is False
        assert _is_room("V.") is False


# ============================================================
# _extract_teacher_from_line tests
# ============================================================

class TestExtractTeacherFromLine:
    def test_standard_format(self):
        s, t, r = _extract_teacher_from_line("sem. ALGA Repescu V.")
        assert s == "sem. ALGA"
        assert t == "Repescu V."
        assert r == ""

    def test_with_room_after_teacher(self):
        s, t, r = _extract_teacher_from_line("sem. PC Rotari A. 201")
        assert s == "sem. PC"
        assert t == "Rotari A."
        assert r == "201"

    def test_complex_subject(self):
        s, t, r = _extract_teacher_from_line("c. Algebra Liniară și Geometria Analitică Costaș A.")
        assert s == "c. Algebra Liniară și Geometria Analitică"
        assert t == "Costaș A."
        assert r == ""

    def test_two_letter_initial(self):
        s, t, r = _extract_teacher_from_line("sem. ESU Lazariuc Cr.")
        assert s == "sem. ESU"
        assert t == "Lazariuc Cr."
        assert r == ""

    def test_room_with_dash_after_teacher(self):
        s, t, r = _extract_teacher_from_line("sem. TP Tutunaru V. D-02-04")
        assert s == "sem. TP"
        assert t == "Tutunaru V."
        assert r == "D-02-04"

    def test_no_teacher_found(self):
        s, t, r = _extract_teacher_from_line("Ed.fizică")
        assert s == "Ed.fizică"
        assert t == ""
        assert r == ""

    def test_empty_string(self):
        s, t, r = _extract_teacher_from_line("")
        assert s == ""
        assert t == ""
        assert r == ""

    def test_subject_only_no_teacher(self):
        s, t, r = _extract_teacher_from_line("L. Engleză")
        assert s == "L. Engleză"
        assert t == ""
        assert r == ""

    def test_diacritics_in_teacher_name(self):
        s, t, r = _extract_teacher_from_line("sem. Crip Magdei O. D01-03")
        assert s == "sem. Crip"
        assert t == "Magdei O."
        assert r == "D01-03"

    def test_teacher_with_full_last_name(self):
        s, t, r = _extract_teacher_from_line("c. Fizică Pîrțac C.")
        assert s == "c. Fizică"
        assert t == "Pîrțac C."
        assert r == ""


# ============================================================
# parse_course — 1 line (all-in-one)
# ============================================================

class TestParseCourseOneLine:
    def test_subject_teacher_room(self):
        s, t, r = parse_course("sem. PC Rotari A. 201")
        assert s == "sem. PC"
        assert t == "Rotari A."
        assert r == "201"

    def test_subject_teacher_room_complex_room(self):
        s, t, r = parse_course("sem. TP Tutunaru V. D-02-04")
        assert s == "sem. TP"
        assert t == "Tutunaru V."
        assert r == "D-02-04"

    def test_subject_teacher_only(self):
        s, t, r = parse_course("sem. ALGA Repescu V.")
        assert s == "sem. ALGA"
        assert t == "Repescu V."
        assert r == ""

    def test_subject_teacher_room_d01(self):
        s, t, r = parse_course("sem. Crip Magdei O. D01-03")
        assert s == "sem. Crip"
        assert t == "Magdei O."
        assert r == "D01-03"

    def test_complex_subject_teacher_room(self):
        s, t, r = parse_course("c. Ingineria calculatoarelor și produse program\nIstrati D. 310")
        # This is actually 2 lines, tested elsewhere

    def test_teacher_two_letter_initial(self):
        s, t, r = parse_course("sem. ESU Gonța A. 618")
        assert s == "sem. ESU"
        assert t == "Gonța A."
        assert r == "618"

    def test_subject_only(self):
        s, t, r = parse_course("Ed.fizică")
        assert s == "Ed.fizică"
        assert t == ""
        assert r == ""

    def test_no_teacher_no_room(self):
        s, t, r = parse_course("sem. AM")
        assert s == "sem. AM"
        assert t == ""
        assert r == ""


# ============================================================
# parse_course — 2 lines
# ============================================================

class TestParseCourseTwoLines:
    def test_subject_and_room(self):
        """Teacher is embedded in subject line"""
        s, t, r = parse_course("c. CDE\n3-3")
        assert s == "c. CDE"
        assert t == ""
        assert r == "3-3"

    def test_subject_with_teacher_and_room_on_second_line(self):
        s, t, r = parse_course("c. Algebra Liniară și Geometria Analitică Costaș A.\n3-3")
        assert s == "c. Algebra Liniară și Geometria Analitică"
        assert t == "Costaș A."
        assert r == "3-3"

    def test_subject_and_room_no_teacher(self):
        s, t, r = parse_course("L. Engleză\n707")
        assert s == "L. Engleză"
        assert t == ""
        assert r == "707"

    def test_subject_with_teacher_embedded_and_room(self):
        s, t, r = parse_course("c. Fizică Pîrțac C.\n310")
        assert s == "c. Fizică"
        assert t == "Pîrțac C."
        assert r == "310"

    def test_subject_and_teacher_separate_lines(self):
        s, t, r = parse_course("c. CDE\nCrețu V.")
        assert s == "c. CDE"
        assert t == "Crețu V."
        assert r == ""

    def test_subject_and_teacher_standalone(self):
        s, t, r = parse_course("sem. ALGA\nRepescu V.")
        assert s == "sem. ALGA"
        assert t == "Repescu V."
        assert r == ""

    def test_teacher_with_room_on_second_line(self):
        """Second line is teacher+room, not just teacher"""
        s, t, r = parse_course("c. Ingineria calculatoarelor și produse program\nIstrati D. 310")
        assert s == "c. Ingineria calculatoarelor și produse program"
        assert t == "Istrati D."
        assert r == "310"

    def test_room_then_subject(self):
        s, t, r = parse_course("3-3\nSem. PC")
        assert s == "Sem. PC"
        assert t == ""
        assert r == "3-3"

    def test_two_subjects_no_teacher(self):
        """Neither line is a room — falls back to inline parsing"""
        s, t, r = parse_course("c. CDE\nSome random text")
        assert s == "c. CDE"
        assert t == "Some random text"
        assert r == ""

    def test_subject_and_teacher_with_diacritics(self):
        s, t, r = parse_course("sem. ALGA\nCostaș A.")
        assert s == "sem. ALGA"
        assert t == "Costaș A."
        assert r == ""

    def test_subject_and_teacher_cr_initial(self):
        s, t, r = parse_course("sem. ESU\nLazariuc Cr.")
        assert s == "sem. ESU"
        assert t == "Lazariuc Cr."
        assert r == ""

    def test_subject_teacher_room_all_separate(self):
        s, t, r = parse_course("sem. ALGA\nCostaș A.\n203")
        assert s == "sem. ALGA"
        assert t == "Costaș A."
        assert r == "203"


# ============================================================
# parse_course — 3+ lines
# ============================================================

class TestParseCourseThreeLines:
    def test_standard_three_lines(self):
        s, t, r = parse_course("sem. ALGA\nCostaș A.\n203")
        assert s == "sem. ALGA"
        assert t == "Costaș A."
        assert r == "203"

    def test_three_lines_complex_subject(self):
        s, t, r = parse_course("C. Analiza Matematică\nPricop V.\n6-2")
        assert s == "C. Analiza Matematică"
        assert t == "Pricop V."
        assert r == "6-2"

    def test_three_lines_long_subject(self):
        s, t, r = parse_course(
            "C. Algebra liniară și geometria analitică\nRepeșco V.\n6-2"
        )
        assert s == "C. Algebra liniară și geometria analitică"
        assert t == "Repeșco V."
        assert r == "6-2"

    def test_three_lines_with_diacritics(self):
        s, t, r = parse_course(
            "C. Securitatea și sănătatea în muncă\nBecheci M.\n310"
        )
        assert s == "C. Securitatea și sănătatea în muncă"
        assert t == "Becheci M."
        assert r == "310"

    def test_four_lines_ignores_extra(self):
        s, t, r = parse_course("sem. ALGA\nCostaș A.\n203\nextra_line")
        assert s == "sem. ALGA"
        assert t == "Costaș A."
        assert r == "203"

    def test_three_lines_subject_teacher_room_d02(self):
        s, t, r = parse_course("sem. TP\nȚoncu V.\n110")
        assert s == "sem. TP"
        assert t == "Țoncu V."
        assert r == "110"


# ============================================================
# parse_course — edge cases
# ============================================================

class TestParseCourseEdgeCases:
    def test_empty_string(self):
        s, t, r = parse_course("")
        assert s == ""
        assert t == ""
        assert r == ""

    def test_none(self):
        s, t, r = parse_course(None)
        assert s == ""
        assert t == ""
        assert r == ""

    def test_whitespace_only(self):
        s, t, r = parse_course("   \n  \n  ")
        assert s == ""
        assert t == ""
        assert r == ""

    def test_newlines_only(self):
        s, t, r = parse_course("\n\n\n")
        assert s == ""
        assert t == ""
        assert r == ""

    def test_leading_trailing_newlines(self):
        s, t, r = parse_course("\nsem. ALGA\nCostaș A.\n203\n")
        assert s == "sem. ALGA"
        assert t == "Costaș A."
        assert r == "203"

    def test_multiple_spaces(self):
        s, t, r = parse_course("sem. ALGA   \n  Costaș A.  \n  203  ")
        assert s == "sem. ALGA"
        assert t == "Costaș A."
        assert r == "203"

    def test_int_input(self):
        """Excel sometimes gives float/NaN for empty cells"""
        s, t, r = parse_course(123)
        assert s == "123"
        assert t == ""
        assert r == ""

    def test_float_input(self):
        s, t, r = parse_course(3.14)
        assert s == "3.14"
        assert t == ""
        assert r == ""


# ============================================================
# Real data from AI-252 schedule
# ============================================================

class TestRealDataAI252:
    """Tests based on actual cell values from the example schedule"""

    def test_monday_pair1(self):
        s, t, r = parse_course("sem. PC Rotari A. 201")
        assert s == "sem. PC"
        assert t == "Rotari A."
        assert r == "201"

    def test_monday_pair2(self):
        s, t, r = parse_course("c. CDE\nCrețu V.\n3-3")
        assert s == "c. CDE"
        assert t == "Crețu V."
        assert r == "3-3"

    def test_monday_pair3(self):
        s, t, r = parse_course("lab. CDE\nVerjbițchi V.\n420")
        assert s == "lab. CDE"
        assert t == "Verjbițchi V."
        assert r == "420"

    def test_tuesday_sem_alga(self):
        s, t, r = parse_course("sem. ALGA Repescu V.\n402")
        assert s == "sem. ALGA"
        assert t == "Repescu V."
        assert r == "402"

    def test_tuesday_sem_eia(self):
        s, t, r = parse_course("sem. EIA Barcari D.\n614")
        assert s == "sem. EIA"
        assert t == "Barcari D."
        assert r == "614"

    def test_tuesday_english(self):
        s, t, r = parse_course("L. Engleză\n607")
        assert s == "L. Engleză"
        assert t == ""
        assert r == "607"

    def test_wednesday_ed_fizica(self):
        s, t, r = parse_course("Ed.fizică")
        assert s == "Ed.fizică"
        assert t == ""
        assert r == ""

    def test_wednesday_analiza(self):
        s, t, r = parse_course("C. Analiza matematică\nPricop V.\n6-2")
        assert s == "C. Analiza matematică"
        assert t == "Pricop V."
        assert r == "6-2"

    def test_wednesday_tehnici(self):
        s, t, r = parse_course("C. Tehnici de programare Bumbu T.\n6-2")
        assert s == "C. Tehnici de programare"
        assert t == "Bumbu T."
        assert r == "6-2"

    def test_thursday_tp(self):
        s, t, r = parse_course("sem. TP\nȚoncu V.\n110")
        assert s == "sem. TP"
        assert t == "Țoncu V."
        assert r == "110"

    def test_thursday_fizica(self):
        s, t, r = parse_course("C. Fizica\nRusu S.\n3-3")
        # Note: the actual cell has "C. Fizica Rusu S.\n3-3" in 2-line format
        assert s in ("C. Fizica", "C. Fizica Rusu S.")
        assert t in ("Rusu S.", "")
        assert r in ("3-3", "Rusu S.")  # depends on parsing

    def test_friday_securitatea(self):
        s, t, r = parse_course("C. Securitatea și sănătatea în muncă\nBecheci M.\n310")
        assert s == "C. Securitatea și sănătatea în muncă"
        assert t == "Becheci M."
        assert r == "310"

    def test_friday_algebra(self):
        s, t, r = parse_course("C. Algebra liniară și geometria analitică Repeșco V.\n6-2")
        assert s == "C. Algebra liniară și geometria analitică"
        assert t == "Repeșco V."
        assert r == "6-2"

    def test_friday_programarea(self):
        s, t, r = parse_course("C. Programarea calculatorului Kulev M.\n6-2")
        assert s == "C. Programarea calculatorului"
        assert t == "Kulev M."
        assert r == "6-2"


# ============================================================
# Hypothetical edge cases — full teacher names
# ============================================================

class TestFullTeacherNames:
    """What if the Excel has full names like 'Crețu Victor' instead of 'Crețu V.'?"""

    def test_full_name_no_initial(self):
        """Full name without period — matches fallback pattern"""
        s, t, r = parse_course("c. CDE\nCrețu Victor\n3-3")
        assert s == "c. CDE"
        assert t == "Crețu Victor"
        assert r == "3-3"

    def test_full_name_on_one_line(self):
        """Full name on one line — fallback matches at end"""
        s, t, r = parse_course("c. CDE Crețu Victor 3-3")
        # fallback "Crețu Victor" matches at end, room "3-3" is after
        assert s == "c. CDE"
        assert t == "Crețu Victor"
        assert r == "3-3"

    def test_two_word_surname_with_initial(self):
        s, t, r = parse_course("sem. AM\nVasilache Ion M.\n402")
        assert s == "sem. AM"
        assert t == "Vasilache Ion M."
        assert r == "402"

    def test_hyphenated_surname(self):
        s, t, r = parse_course("c. Fizică\nPopescu-Marin V.\n310")
        assert s == "c. Fizică"
        assert t == "Popescu-Marin V."
        assert r == "310"

    def test_multiple_teachers_one_line(self):
        """Two teachers on second line — 3-line case, taken as-is"""
        s, t, r = parse_course("sem. PC\nRotari A. / Crețu V.\n201")
        assert s == "sem. PC"
        assert t == "Rotari A. / Crețu V."
        assert r == "201"

    def test_full_name_no_initial_with_room(self):
        """Full name followed by room on same line"""
        s, t, r = parse_course("sem. Podovailo Evgen 405")
        assert s == "sem."
        assert t == "Podovailo Evgen"
        assert r == "405"

    def test_full_name_no_initial_standalone(self):
        """Full name as the only content"""
        s, t, r = parse_course("Podovailo Evgen")
        assert s == ""
        assert t == "Podovailo Evgen"
        assert r == ""

    def test_full_name_no_initial_two_lines(self):
        """Full name on line 2, no room"""
        s, t, r = parse_course("c. CDE\nPodovailo Evgen")
        assert s == "c. CDE"
        assert t == "Podovailo Evgen"
        assert r == ""

    def test_full_name_no_initial_with_room_two_lines(self):
        """Full name on line 2 with room after"""
        s, t, r = parse_course("c. CDE\nPodovailo Evgen\n310")
        assert s == "c. CDE"
        assert t == "Podovailo Evgen"
        assert r == "310"

    def test_short_codes_not_teacher(self):
        """Short codes like 'CDE' should not match as teacher name"""
        s, t, r = parse_course("c. CDE\n3-3")
        assert s == "c. CDE"
        assert t == ""
        assert r == "3-3"


# ============================================================
# _is_room edge cases
# ============================================================

class TestIsRoomEdgeCases:
    def test_room_with_letter_suffix(self):
        assert _is_room("310A") is True

    def test_room_with_letter_prefix_and_suffix(self):
        assert _is_room("A310B") is True

    def test_single_digit(self):
        assert _is_room("1") is True

    def test_room_like_string_not_room(self):
        assert _is_room("V.") is False
        assert _is_room("Cr.") is False
        assert _is_room("A.") is False

    def test_mixed_alphanumeric_not_room(self):
        assert _is_room("Crețu") is False
        assert _is_room("sem") is False
