"""Conservative class labels. Unknown layouts keep their original text."""

import csv
import hashlib
import io
import json
import re
from html import escape
from pathlib import Path


NAME = r"[^\W\d_]+(?:[-'][^\W\d_]+)*"
CAP = r"[A-ZĂÂÎȘȚ]"
# A printed surname starts with a capital and has lowercase letters, so short
# uppercase subjects such as CDE, DAS or AM never match as a person.
SURNAME = r"[A-ZĂÂÎȘȚ][a-zăâîșț]{1,}(?:[-'][a-zăâîșț]+)*"
# Standard form is "Surname I." or "Surname Ion"; the loose form also accepts a
# surname alone ("Bîrnaz") and a surname with a compact initial ("DutovaL."),
# both of which the dean does print. Loose matches are flagged for review.
STANDARD_TEACHER = re.compile(
    rf"(?:{NAME}\s+{CAP}(?:[a-zăâîșț]{{1,2}})?\.?(?:\s*{CAP}\.)?|{CAP}\.\s*{NAME})",
    re.UNICODE,
)
TEACHER = re.compile(
    rf"(?:{NAME}\s+{CAP}(?:[a-zăâîșț]{{1,2}})?\.?(?:\s*{CAP}\.)?|{SURNAME}\s?{CAP}\.|{SURNAME}|{CAP}\.\s*{NAME})",
    re.UNICODE,
)
ROOM_PATTERN = r"(?:[A-D]\s*-?\s*)?\d{1,3}(?:\s*[-/]\s*(?:[A-D]\s*-?\s*)?\d{1,3})*"
ROOM = re.compile(ROOM_PATTERN, re.I)
TEACHER_AND_ROOM = re.compile(rf"(.+?)\s+({ROOM_PATTERN})", re.I)
# Half-group lab marker: "lab.", optional course code, "0,5 gr." or "0.5 gr".
LAB_MARKER = re.compile(
    r"(?i)lab\.?\s*(?P<code>[A-Za-zĂÂÎȘȚăâîșț0-9\-]{1,12})?\s*0[.,]5\s*gr\.?\s*(?P<tail>[A-Za-zĂÂÎȘȚăâîșț0-9\-]{1,12})?\s*$"
)
# Whole-group lab: the same "lab." token without a group size, e.g. "lab. CDE".
PLAIN_LAB = re.compile(r"(?i)^(?:(?P<num>\d\))\s*)?lab(?:\.\s*|\s+|$)(?P<code>.*)$")
NAMED_ROOMS = {"Sala sportivă", "Tekwill", "ImunoTehnomed"}
# Physical education prints only the subject, or the subject with any mix of
# teachers and rooms (several of either, in any order).
PHYSICAL_SUBJECTS = {"educație fizică", "educația fizică", "educatie fizica", "ed. fizică", "ed. fizica"}
SINGLE_LINE_SUBJECTS = {"Activități individuale/ în grup", "Educație fizică", "Ed. fizică"}
HALL = re.compile(r"(?:Aula\s+)?[36]-[23]\s+(?:Amdaris|Henri Coandă)", re.I)


def is_room(line):
    return bool(ROOM.fullmatch(line) or HALL.fullmatch(line) or line in NAMED_ROOMS)


def teacher_names(line):
    if line.strip().casefold() == "l. engleză":
        return []
    names = [name.strip() for name in re.split(r"\s*[,;/]\s*", line)]
    return names if names and all(TEACHER.fullmatch(name) for name in names) else []


def teacher_names_and_rooms(line):
    """Split a single line printed as "Surname I. 614"."""
    match = TEACHER_AND_ROOM.fullmatch(line)
    if not match:
        return [], []
    names = teacher_names(match.group(1))
    return (names, [match.group(2).strip()]) if names else ([], [])


def flag_loose_teacher_names(result):
    """Keep non-standard names visible for review without changing the text."""
    loose = [name for name in result.get("teachers", []) if not STANDARD_TEACHER.fullmatch(name)]
    if loose:
        result.update(review_required=True, reason="verify teacher name spelling")
    return result


def select_subgroup(value, subgroup):
    text = str(value)
    if subgroup == 0:
        return text
    if "\n2)" in text and (text.startswith("1)") or "\n1)" in text):
        first, second = text.split("\n2)", 1)
        if subgroup == 1:
            return first
        prefix = text.split("\n1)", 1)[0] if "\n1)" in text else ""
        return (prefix + "\n" if prefix else "") + "2)" + second
    count = text.count("0.5") + text.count("0,5")
    if count == 1 and subgroup == 2:
        return ""
    return text


def mark_review_teacher_candidates(result, lines):
    """Preserve teacher-looking source lines without certifying their identity."""
    candidates = [line for line in lines[1:] if teacher_names(line)]
    if candidates:
        result["teacher_candidates"] = list(dict.fromkeys(candidates))
        result["reason"] += "; teacher text requires human review"
    return result


def parse_fields(fields):
    """Return (teachers, rooms) for a field tail, or None when it is ambiguous."""
    for room_count in (2, 1):
        for rooms, teacher_lines in ((fields[-room_count:], fields[:-room_count]), (fields[:room_count], fields[room_count:])):
            if not teacher_lines or not all(is_room(room) for room in rooms):
                continue
            parsed_names = [teacher_names(line) for line in teacher_lines]
            if not all(parsed_names):
                continue
            return [name for names in parsed_names for name in names], rooms
    # Forgiving pass: each remaining line is a room, a teacher, or "teacher room".
    teachers, rooms = [], []
    for line in fields:
        names, inline_rooms = teacher_names_and_rooms(line)
        if is_room(line):
            rooms.append(line)
        elif (spot := teacher_names(line)):
            teachers.extend(spot)
        elif names:
            teachers.extend(names)
            rooms.extend(inline_rooms)
        else:
            return None
    return (teachers, rooms) if (teachers or rooms) else None


def split_lab_half(line):
    """Split a half-group lab marker, e.g. "1) lab. PADM 0,5 gr. IoT".

    The dean writes 0,5 and 0.5, with or without the final dot, with the course
    code before or after the marker, and with an optional 1)/2) prefix.
    """
    numbered = re.match(r"^(\d\))\s*", line)
    number = numbered.group(1) if numbered else ""
    rest = line[numbered.end():] if numbered else line
    match = LAB_MARKER.fullmatch(rest.strip())
    if not match:
        return None
    code = " ".join(part for part in (match.group("code"), match.group("tail")) if part).strip()
    return {"number": number, "code": code}


def split_plain_lab(line):
    """Split the "lab." marker of a whole-group lab from its course code."""
    match = PLAIN_LAB.match(line)
    if not match:
        return None
    return {"number": match.group("num") or "", "code": match.group("code").strip()}


def classify(raw):
    raw = str(raw)
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    result = {"status": "unclassified", "raw": raw, "subject": "", "teachers": [], "rooms": [], "reason": "unknown layout"}
    if not lines:
        return result
    if len(lines) == 1:
        if lines[0] in SINGLE_LINE_SUBJECTS or lines[0].casefold() in PHYSICAL_SUBJECTS:
            result.update(status="classified", subject=lines[0], reason="")
            return result
        if split_lab_half(lines[0]):
            result.update(status="needs_review", reason="half-group lab marker without a class")
            return mark_review_teacher_candidates(result, lines)
        result["reason"] = "single unstructured line"
        return result
    if lines[0].casefold() in PHYSICAL_SUBJECTS:
        teachers, rooms = [], []
        for line in lines[1:]:
            names = teacher_names(line)
            if is_room(line):
                rooms.append(line)
            elif names:
                teachers.extend(names)
            else:
                break
        else:
            result.update(status="classified", subject=lines[0], teachers=teachers, rooms=rooms, reason="")
            return flag_loose_teacher_names(result)
        result.update(status="needs_review", reason="physical education tail is not all teachers or rooms")
        return mark_review_teacher_candidates(result, lines)
    lab = split_lab_half(lines[0])
    if "\n2)" in raw and ("\n1)" in raw or raw.startswith("1)")):
        if ((raw.startswith("1)") or raw.count("\n1)") == 1) and raw.count("\n2)") == 1
                and not re.search(r"(?:^|\n)[3-9]\)", raw)):
            first, second = (classify(select_subgroup(raw, subgroup)) for subgroup in (1, 2))
            if all(entry["status"] == "classified" and not entry.get("review_required")
                   for entry in (first, second)):
                # One marker line can head a whole numbered pair, so the halves
                # that carry no marker of their own inherit it.
                if lab:
                    for entry in (first, second):
                        entry.setdefault("lab", "0.5")
                result.update(status="classified", entries=[first, second], reason="")
                return result
        result.update(status="needs_review", reason="multiple classes in one cell")
        return mark_review_teacher_candidates(result, lines)
    if lab:
        remaining = lines[1:]
        subject_parts = [f"{lab['number']} {lab['code']}".strip()] if lab["code"] else []
        while remaining and not is_room(remaining[0]) and not teacher_names(remaining[0]):
            subject_parts.append(remaining.pop(0))
        subject = "\n".join(part for part in subject_parts if part)
        parsed = parse_fields(remaining)
        if parsed and subject:
            result.update(status="classified", subject=subject, teachers=parsed[0], rooms=parsed[1],
                          lab="0.5", lab_source_line=lines[0], reason="")
            return flag_loose_teacher_names(result)
        result.update(status="needs_review", reason="half-group lab fields are incomplete")
        return mark_review_teacher_candidates(result, lines)
    # A whole-group lab carries the same "lab." token but no group size. The
    # token moves to the marker line, so the subject keeps only the code.
    whole_lab_line = None
    if not lab:
        plain = split_plain_lab(lines[0])
        if plain:
            whole_lab_line = lines[0]
            code = f"{plain['number']} {plain['code']}".strip()
            lines = ([code] + lines[1:]) if code else lines[1:]
            if not lines:
                result.update(status="needs_review", reason="lab marker without a class")
                return mark_review_teacher_candidates(result, [whole_lab_line])

    def whole_lab(entry):
        if whole_lab_line:
            entry.update(lab="whole", lab_source_line=whole_lab_line)
        return entry

    if (len(lines) == 2 and is_room(lines[1])
            and (not STANDARD_TEACHER.fullmatch(lines[0]) or lines[0].casefold() == "l. engleză")):
        result.update(status="classified", subject=lines[0], rooms=[lines[1]], reason="")
        return whole_lab(result)

    # Lab sheets can wrap a subject prefix and abbreviation onto two lines.
    subject_end = 2 if (
        len(lines) >= 4
        and re.fullmatch(r"(?i:lab\.)?(?:\s*0\.5\s*gr\.?)?", lines[0])
        and re.fullmatch(r"(?:[12]\)\s*)?[A-Z][A-Za-z0-9]{1,5}", lines[1])
    ) else 1
    subject = "\n".join(lines[:subject_end])
    if STANDARD_TEACHER.fullmatch(lines[0]) and not lines[0].startswith("L. "):
        result.update(status="needs_review", reason="subject resembles a teacher name")
        return mark_review_teacher_candidates(result, lines)
    fields = lines[subject_end:]
    parsed = parse_fields(fields)
    if parsed:
        result.update(status="classified", subject=subject, teachers=parsed[0], rooms=parsed[1], reason="")
        return flag_loose_teacher_names(whole_lab(result))
    result.update(status="needs_review", reason="field order or count is ambiguous")
    return mark_review_teacher_candidates(result, lines)


def format_course(raw, classifications, subgroup=None, is_even=None):
    item = classifications.get(str(raw))
    if not item or item["status"] != "classified":
        return escape(str(raw))

    def half_glyph(entry_index):
        """🌗 marks subgroup 1, 🌓 marks subgroup 2.

        With a subgroup selected the glyph is that subgroup. In the combined
        view each entry carries the half that attends it this week, and the
        halves swap over on even ISO weeks.
        """
        if subgroup in (1, 2):
            half = subgroup
        else:
            half = (entry_index + 1) if not is_even else (2 - entry_index)
        return "🌗" if half == 1 else "🌓"

    def render(entry, entry_index):
        lines = []
        if entry.get("lab") == "0.5":
            lines.append(f"{half_glyph(entry_index)} Lab. 0.5 gr.")
        elif entry.get("lab"):
            lines.append("🌕 Lab.")
        lines.append("📖 " + escape(entry["subject"]))
        lines += ["🧑‍🏫 " + escape(name) for name in entry["teachers"]]
        lines += ["🏫 " + escape(room) for room in entry["rooms"]]
        return "\n".join(lines)

    return "\n\n".join(render(entry, index)
                        for index, entry in enumerate(item.get("entries", [item])))


def viewer_subgroup(subgrupa, is_even):
    """Half-group labs alternate: even ISO weeks the viewer sees the other half."""
    try:
        value = int(subgrupa)
    except (ValueError, TypeError):
        value = 0
    return 3 - value if (is_even and value) else value


def classification_counts(classifications):
    items = classifications.values()
    return {
        "classified": sum(item["status"] == "classified" and not bool(item.get("review_required")) for item in items),
        "needs_review": sum(item["status"] == "needs_review" or bool(item.get("review_required"))
                            for item in classifications.values()),
        "unclassified": sum(item["status"] == "unclassified" for item in classifications.values()),
    }


def sidecar_path(xlsx_path):
    return Path(xlsx_path).with_suffix(".classifications.json")


def build_classifications(sheet, groups, year, days=None, times=None, source_blocks=None, source_pairs=None):
    source_by_slot = {(block.group, block.day.replace("ţ", "ț"), block.time): block
                      for block in source_blocks or ()}
    pairs_by_slot = {(pair.group, pair.day.replace("ţ", "ț"), pair.time): pair
                     for pair in source_pairs or ()}
    group_blocks = {}
    for block in source_blocks or ():
        group_blocks.setdefault((block.group, block.day.replace("ţ", "ț")), []).append(block)
    merged = {}
    for area in sheet.merged_cells.ranges:
        for row in range(max(2, area.min_row), min(sheet.max_row, area.max_row) + 1):
            for col in range(max(3, area.min_col), min(2 + len(groups), area.max_col) + 1):
                merged[row, col] = sheet.cell(area.min_row, area.min_col).value
    # Day and time live in columns 1 and 2. Read them from the sheet so a
    # six-day week works; the passed lists are only a fallback for bare tests.
    merged_any = {}
    for area in sheet.merged_cells.ranges:
        for row in range(max(1, area.min_row), min(sheet.max_row, area.max_row) + 1):
            for col in range(area.min_col, min(sheet.max_column, area.max_col) + 1):
                merged_any[row, col] = sheet.cell(area.min_row, area.min_col).value
    fallback_days = list(days or ())
    fallback_times = list(times or ())

    classifications = {}
    occurrences = []
    for row in range(2, sheet.max_row + 1):
        label = sheet.cell(row, 1).value or merged_any.get((row, 1))
        clock = sheet.cell(row, 2).value or merged_any.get((row, 2))
        day = str(label).strip() if label else (fallback_days[(row - 2) // 14] if fallback_days else "")
        time = str(clock).strip() if clock else (fallback_times[((row - 2) // 2) % len(fallback_times)]
                                                 if fallback_times else "")
        for col, group in enumerate(groups, start=3):
            value = sheet.cell(row, col).value or merged.get((row, col))
            if not isinstance(value, str) or not value.strip():
                continue
            for subgroup in (0, 1, 2):
                raw = select_subgroup(value, subgroup)
                if not raw.strip():
                    continue
                item = classifications.setdefault(raw, classify(raw))
                key = (group, day.replace("ţ", "ț"), time)
                source = source_by_slot.get(key)
                if source and item["status"] == "classified":
                    evidence = [source]
                    pair = pairs_by_slot.get(key)
                    if pair and any("cross-timeslot" in flag for flag in pair.review_flags):
                        adjacent = group_blocks[(group, day.replace("ţ", "ț"))]
                        index = adjacent.index(source)
                        for neighbor in adjacent[max(index - 1, 0):index] + adjacent[index + 1:index + 2]:
                            other = pairs_by_slot.get((group, day.replace("ţ", "ț"), neighbor.time))
                            if (other and other.status == pair.status == "auto"
                                    and (other.odd_text, other.even_text) == (pair.odd_text, pair.even_text)
                                    and any("cross-timeslot" in flag for flag in other.review_flags)):
                                evidence.append(neighbor)
                    whole_values = {str(value.value).strip().replace("0,5", "0.5")
                                    for block in evidence for value in block.values if value.value}
                    entries = item.get("entries", [item])
                    # A half-group lab keeps its marker out of the subject, so the
                    # untouched marker line is accepted as source evidence too.
                    subject_backed = all(
                        entry["subject"] in whole_values
                        or entry.get("lab_source_line") in whole_values
                        or ("\n" in entry["subject"]
                            and all(part in whole_values for part in entry["subject"].splitlines()))
                        for entry in entries
                    )
                    source_teachers, source_rooms = set(), set()
                    # Never rebind the outer `value` here: the next subgroup
                    # iteration still needs the original cell text.
                    for source_text in whole_values:
                        for line in str(source_text).splitlines():
                            if not line.strip():
                                continue
                            source_teachers.update(teacher_names(line))
                            names, inline_rooms = teacher_names_and_rooms(line)
                            source_teachers.update(names)
                            source_rooms.update(inline_rooms)
                            if is_room(line):
                                source_rooms.add(line.strip())
                    # A single vertically merged cell can itself contain a
                    # complete class, including two explicitly numbered entries.
                    def source_lines(text):
                        return [line.strip().replace("0,5", "0.5") for line in str(text).splitlines() if line.strip()]

                    merged_class = any(
                        getattr(source_value, "merged_range", None)
                        and source_lines(source_value.value) == source_lines(value)
                        for source_value in source.values if source_value.value
                    )
                    if not merged_class and (not subject_backed
                                             or any(not set(entry["teachers"]) <= source_teachers for entry in entries)
                                             or any(room not in source_rooms for entry in entries for room in entry["rooms"])):
                        item.update(status="needs_review", reason="field boundaries not confirmed by source cells",
                                    teacher_candidates=[teacher for entry in entries for teacher in entry["teachers"]],
                                    teachers=[], review_required=False)
                if item["status"] != "classified" or item.get("review_required"):
                    source_ref = (f"{source.values[0].coordinate}:{source.values[-1].coordinate}"
                                  if source and hasattr(source.values[0], "coordinate") else "")
                    occurrences.append((year, group, day, time, "ISO-odd" if row % 2 else "ISO-even", subgroup,
                                         "classified_review" if item.get("review_required") and item["status"] == "classified"
                                         else item["status"], raw, item["reason"], source_ref))
    return classifications, occurrences


def review_csv(occurrences, source_sha256=""):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(("year", "group", "day", "time", "week", "subgroup", "status", "raw", "reason", "source_cells", "source_sha256"))
    for row in dict.fromkeys(occurrences):
        row = (*row, "") if len(row) == 9 else row
        writer.writerow(("'" + cell if isinstance(cell, str) and cell.startswith(("=", "+", "-", "@", "\t", "\r")) else cell)
                        for cell in (*row, source_sha256))
    return output.getvalue().encode("utf-8-sig")


def save_classifications(xlsx_path, classifications, output_path, source_path=None):
    payload = {"xlsx_sha256": hashlib.sha256(Path(xlsx_path).read_bytes()).hexdigest(), "classes": classifications}
    if source_path:
        payload["source_sha256"] = hashlib.sha256(Path(source_path).read_bytes()).hexdigest()
    Path(output_path).write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def load_classifications(xlsx_path):
    try:
        payload = json.loads(sidecar_path(xlsx_path).read_text(encoding="utf-8"))
        if payload["xlsx_sha256"] == hashlib.sha256(Path(xlsx_path).read_bytes()).hexdigest():
            return payload["classes"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return {}
