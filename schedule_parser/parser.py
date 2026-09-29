"""Lossless, review-first FCIM schedule extractor.

This module deliberately does not infer subject, teacher, or room from free
text. Current source workbooks use the same six-row area for both two classes
and multi-instructor classes. It emits source-backed blocks and review flags;
approved review decisions can later create normalized class records safely.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter, range_boundaries


DAY_NAMES = {"Luni", "Marți", "Marţi", "Miercuri", "Joi", "Vineri", "Sâmbătă", "Duminică"}
DAY_CANONICAL = {"Marți": "Marţi"}
TIME_RE = re.compile(r"^\d{1,2}\.\d{2}-\d{1,2}\.\d{2}$")
GROUP_RE = re.compile(r"^[A-ZĂÂÎȘŢȚ]{1,5}-\d{3}$")
BLOCK_ROWS = 6

DAY_COLORS = {
    "Luni": "DDEEFF",
    "Marți": "DDFFDD",
    "Marţi": "DDFFDD",
    "Miercuri": "FFFADD",
    "Joi": "FFE8DD",
    "Vineri": "F0DDFF",
    "Sâmbătă": "FFDDE8",
}
THIN = Side(style="thin")
MEDIUM = Side(style="medium")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


class LayoutError(ValueError):
    """Workbook does not match the known FCIM schedule layout."""


@dataclass(frozen=True)
class SourceValue:
    row: int
    column: int
    coordinate: str
    value: Optional[str]
    merged_range: Optional[str]
    bottom_border: Optional[str]
    top_border: Optional[str] = None


@dataclass(frozen=True)
class SourceSegment:
    start_offset: int
    end_offset: int
    values: list[SourceValue]


@dataclass(frozen=True)
class ScheduleBlock:
    group: str
    day: str
    time: str
    source_row: int
    source_column: int
    values: list[SourceValue]
    segments: list[SourceSegment]
    review_flags: list[str]


@dataclass(frozen=True)
class SchedulePair:
    group: str
    day: str
    time: str
    odd_text: Optional[str]
    even_text: Optional[str]
    status: str
    review_flags: list[str]


def _merged_lookup(ws):
    lookup = {}
    for merged in ws.merged_cells.ranges:
        for row in range(merged.min_row, merged.max_row + 1):
            for column in range(merged.min_col, merged.max_col + 1):
                lookup[(row, column)] = merged
    return lookup


def _source_value(ws, merged_lookup, row, column):
    merged = merged_lookup.get((row, column))
    origin = ws.cell(merged.min_row, merged.min_col) if merged else ws.cell(row, column)
    value = origin.value
    return SourceValue(
        row=row,
        column=column,
        coordinate=ws.cell(row, column).coordinate,
        value=str(value).strip() if value is not None else None,
        merged_range=str(merged) if merged else None,
        bottom_border=(ws.cell(row, column).border.bottom.style if ws.cell(row, column).border.bottom else None),
        top_border=(ws.cell(row, column).border.top.style if ws.cell(row, column).border.top else None),
    )


def _layout(ws):
    headers = []
    for row in ws.iter_rows():
        columns = [cell.column for cell in row if cell.value == "Grupele"]
        if columns:
            headers.extend((row[0].row, column) for column in columns)

    if not headers:
        raise LayoutError("Missing 'Grupele' header")

    # Known files can contain a second decorative 'Grupele' label. Select the
    # first header followed by at least one canonical group identifier.
    for header_row, group_label_col in headers:
        groups = []
        for column in range(group_label_col + 3, ws.max_column + 1):
            value = ws.cell(header_row, column).value
            identifiers = [part.strip() for part in str(value or "").splitlines() if part.strip()]
            if identifiers and all(GROUP_RE.fullmatch(identifier) for identifier in identifiers):
                groups.extend((column, identifier) for identifier in identifiers)
            elif groups:
                break
        if groups:
            identifiers = [identifier for _, identifier in groups]
            if len(set(identifiers)) != len(identifiers):
                raise LayoutError("Duplicate group identifier in header")
            return header_row, group_label_col, groups

    raise LayoutError("No canonical group identifiers after 'Grupele' header")


def _timeslots(ws, header_row, day_column, time_column):
    current_day = None
    timeslots = []
    for row in range(header_row + 1, ws.max_row + 1):
        day = ws.cell(row, day_column).value
        time = ws.cell(row, time_column).value
        if isinstance(day, str) and day.strip() in DAY_NAMES:
            current_day = DAY_CANONICAL.get(day.strip(), day.strip())
        if isinstance(time, str) and TIME_RE.fullmatch(time.strip()):
            if current_day is None:
                raise LayoutError(f"Timeslot at row {row} has no day")
            if row + BLOCK_ROWS - 1 > ws.max_row:
                raise LayoutError(f"Timeslot at row {row} is missing block rows")
            timeslots.append((row, current_day, time.strip()))

    if len(timeslots) == 0 or len(timeslots) % 7 != 0:
        raise LayoutError(f"Expected whole weeks of 7 timeslots per day; found {len(timeslots)}")
    keys = [(day.replace("ţ", "ț"), time) for _, day, time in timeslots]
    if len(set(keys)) != len(keys):
        raise LayoutError("Duplicate weekly timeslot")
    day_order = list(dict.fromkeys(day for _, day, _ in timeslots))
    if any(len([slot for slot in timeslots if slot[1] == day]) != 7 for day in day_order):
        raise LayoutError("Each weekday must contain exactly 7 timeslots")
    return timeslots


def _segments(values):
    """Split on visual bottom OR next-cell top borders; never infer from text count."""
    segments = []
    start = 0
    for offset, value in enumerate(values):
        same_merge = offset and value.merged_range and value.merged_range == values[offset - 1].merged_range
        same_next_merge = (offset + 1 < len(values) and value.merged_range
                           and value.merged_range == values[offset + 1].merged_range)
        if offset > start and not same_merge and value.top_border in {"medium", "thick"}:
            segments.append(SourceSegment(start, offset - 1, values[start:offset]))
            start = offset
        if not same_next_merge and value.bottom_border in {"medium", "thick"}:
            segments.append(SourceSegment(start, offset, values[start:offset + 1]))
            start = offset + 1
    if start < len(values):
        segments.append(SourceSegment(start, len(values) - 1, values[start:]))
    return segments


def _review_flags(values, segments):
    populated = [(index, value.value) for index, value in enumerate(values) if value.value]
    if not populated:
        return []

    offsets = [index for index, _ in populated]
    flags = []
    if len(populated) == 4 and offsets == [1, 2, 3, 4]:
        flags.append("four consecutive values cross pair boundary; may be multi-instructor class")
    if len(populated) not in {1, 3, 6} and not flags:
        flags.append("non-canonical populated-row pattern")
    if not values[-1].bottom_border and any(value.value for value in values):
        flags.append("missing final border; checked for cross-timeslot continuation")
    if len(segments) > 2:
        flags.append("more than two visual segments in one timeslot")
    return flags


def _clean_source_text(value):
    return "\n".join(
        line.strip()
        for line in value.replace("0,5", "0.5").splitlines()
        if line.strip()
    )


def _visible_values(values):
    result = []
    previous_merge = None
    for value in values:
        if not value.value:
            continue
        text = _clean_source_text(value.value)
        if value.merged_range and value.merged_range == previous_merge and result[-1] == text:
            continue
        result.append(text)
        previous_merge = value.merged_range
    return result


def _segment_text(segment):
    """Return visible source text, retaining order and only collapsing merge repeats."""
    return "\n".join(_visible_values(segment.values)) or None


def _block_lines(block):
    """Visible block text, collapsing only repeats from one merged cell."""
    return _visible_values(block.values)


def _populated_offsets(block):
    return [offset for offset, value in enumerate(block.values) if value.value]


def _has_nonempty_internal_divider(block):
    for offset in range(1, BLOCK_ROWS):
        upper, lower = block.values[offset - 1], block.values[offset]
        if upper.merged_range and upper.merged_range == lower.merged_range:
            continue
        if (upper.bottom_border in {"medium", "thick"} or lower.top_border in {"medium", "thick"}) and (
                any(value.value for value in block.values[:offset])
                and any(value.value for value in block.values[offset:])):
            return True
    return False


def resolve_pair(block: ScheduleBlock) -> SchedulePair:
    """Resolve only border-unambiguous odd/even display text.

    `auto` means display boundaries are guaranteed by source borders. It does
    not claim that free text has been normalized into subject/teacher/room.
    """
    segments = [segment for segment in block.segments if _segment_text(segment)]
    shape = tuple((segment.start_offset, segment.end_offset) for segment in segments)
    flags = list(block.review_flags)
    offsets = _populated_offsets(block)

    if not segments:
        return SchedulePair(block.group, block.day, block.time, None, None, "auto", flags)
    # Explicit source borders provide stronger parity evidence than a missing
    # final border, which can also describe formatting or a shared merge.
    if shape == ((0, 2), (3, 5)):
        return SchedulePair(
            block.group,
            block.day,
            block.time,
            _segment_text(segments[0]),
            _segment_text(segments[1]),
            "auto",
            flags,
        )
    if shape == ((0, 2),):
        return SchedulePair(block.group, block.day, block.time, _segment_text(segments[0]), None, "auto", flags)
    if shape == ((3, 5),):
        return SchedulePair(block.group, block.day, block.time, None, _segment_text(segments[0]), "auto", flags)

    if tuple(offsets) in {
        (0, 2, 4),
        (1, 2, 3),
        (1, 2, 4),
        (1, 3, 5),
        (2, 4),
        (1, 2, 3, 5),
        (1, 3, 4),
    }:
        text = "\n".join(_block_lines(block))
        return SchedulePair(block.group, block.day, block.time, text, text, "auto", flags)

    if "missing final border; checked for cross-timeslot continuation" in flags:
        # A single merged source cell already holds complete class text. The
        # missing border only describes duration, not a missing class field.
        lines = _block_lines(block)
        if len(lines) == 1:
            return SchedulePair(block.group, block.day, block.time, lines[0], lines[0], "auto", flags)
        if tuple(offsets) == (0, 1, 2):
            return SchedulePair(block.group, block.day, block.time, "\n".join(lines), None, "auto", flags)
        if tuple(offsets) == (0, 1, 2, 3, 4, 5) and len(lines) == 6:
            return SchedulePair(
                block.group,
                block.day,
                block.time,
                "\n".join(lines[:3]),
                "\n".join(lines[3:]),
                "auto",
                flags,
            )
        return SchedulePair(block.group, block.day, block.time, None, None, "review", flags)
    if shape == ((0, 5),):
        lines = _block_lines(block)
        if offsets and max(offsets) <= 2:
            return SchedulePair(block.group, block.day, block.time, "\n".join(lines), None, "auto", flags)
        if offsets and min(offsets) >= 3:
            return SchedulePair(block.group, block.day, block.time, None, "\n".join(lines), "auto", flags)
        if len(lines) == 6:
            # Known FCIM sheets occasionally omit the inner border between two
            # complete 3-row parity entries. Six distinct visual rows retain
            # that boundary even without a border.
            return SchedulePair(
                block.group,
                block.day,
                block.time,
                "\n".join(lines[:3]),
                "\n".join(lines[3:]),
                "auto",
                flags,
            )
        text = "\n".join(lines)
        return SchedulePair(block.group, block.day, block.time, text, text, "auto", flags)
    elif shape in {((0, 0), (1, 5)), ((0, 4), (5, 5))}:
        lines = _block_lines(block)
        if len(lines) <= 4:
            text = "\n".join(lines)
            return SchedulePair(block.group, block.day, block.time, text, text, "auto", flags)

    text = "\n".join(_block_lines(block)) or None
    return SchedulePair(block.group, block.day, block.time, text, text, "review", flags)


def resolve_pairs(blocks):
    pairs = [resolve_pair(block) for block in blocks]
    positions = {(block.group, block.source_row): index for index, block in enumerate(blocks)}
    times_by_group = {}
    for block in blocks:
        times_by_group.setdefault(block.group, []).append(block)

    for group_blocks in times_by_group.values():
        for current, following in zip(group_blocks, group_blocks[1:]):
            if (current.day != following.day or current.values[-1].bottom_border
                    or following.values[0].top_border in {"medium", "thick"}):
                continue
            current_offsets = _populated_offsets(current)
            following_offsets = _populated_offsets(following)
            if not current_offsets or not following_offsets:
                continue
            current_lines = _block_lines(current)
            following_lines = _block_lines(following)
            if (
                any(line.lstrip().startswith("1)") for line in current_lines)
                and any(line.lstrip().startswith("2)") for line in following_lines)
                and min(current_offsets) >= 2
                and not _has_nonempty_internal_divider(current)
                and not _has_nonempty_internal_divider(following)
            ):
                text = "\n".join(current_lines) + "\n\n" + "\n".join(following_lines)
                for block in (current, following):
                    index = positions[(block.group, block.source_row)]
                    pairs[index] = replace(
                        pairs[index],
                        odd_text=text,
                        even_text=text,
                        status="auto",
                        review_flags=list(dict.fromkeys([
                            *pairs[index].review_flags,
                            "numbered cross-timeslot entries joined from source fragments",
                        ])),
                )
                continue
            # Sparse trailing content can continue into the next slot's upper
            # half only when current starts at/after the midpoint. This covers
            # source fragments such as `lab. 0.5 gr. / AFU / teacher` followed
            # by `teacher / room`; do not join an upper-half class forward.
            if (pairs[positions[(current.group, current.source_row)]].status == "review"
                    and min(current_offsets) >= 2 and max(following_offsets) <= 2
                    and not _has_nonempty_internal_divider(current) and not _has_nonempty_internal_divider(following)):
                text = "\n".join(current_lines + following_lines)
                for block in (current, following):
                    index = positions[(block.group, block.source_row)]
                    pairs[index] = replace(
                        pairs[index], odd_text=text, even_text=text, status="auto",
                        review_flags=list(dict.fromkeys([
                            *pairs[index].review_flags,
                            "cross-timeslot source fragments joined",
                        ])),
                    )
                continue
            if (min(current_offsets) < 3 or max(following_offsets) > 2
                    or _has_nonempty_internal_divider(current) or _has_nonempty_internal_divider(following)):
                continue
            lines = _block_lines(current) + _block_lines(following)
            if len(lines) < 3:
                continue
            text = "\n".join(lines)
            merged_flags = ["cross-timeslot entry joined from source fragments"]
            for block in (current, following):
                index = positions[(block.group, block.source_row)]
                pairs[index] = replace(
                    pairs[index],
                    odd_text=text,
                    even_text=text,
                    status="auto",
                    review_flags=list(dict.fromkeys([*pairs[index].review_flags, *merged_flags])),
                )

    # Resolve complete centered entries only after continuation rules had a
    # chance to join genuine fragments with the following timeslot.
    for index, (block, pair) in enumerate(zip(blocks, pairs)):
        shape = tuple((segment.start_offset, segment.end_offset) for segment in block.segments)
        if (
            pair.status == "review"
            and tuple(_populated_offsets(block)) == (2, 3, 4)
            and shape == ((0, 5),)
            and "missing final border; checked for cross-timeslot continuation" in pair.review_flags
        ):
            text = "\n".join(_block_lines(block))
            pairs[index] = replace(
                pair,
                odd_text=text,
                even_text=text,
                status="auto",
                review_flags=list(dict.fromkeys([
                    *pair.review_flags,
                    "centered complete three-line entry treated as both weeks",
                ])),
            )
    return pairs


def parse_workbook(path: str | Path) -> list[ScheduleBlock]:
    """Extract every group/time block without mutating source workbook."""
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=False)
    if len(workbook.sheetnames) != 1:
        raise LayoutError("Expected exactly one worksheet")
    ws = workbook.active
    header_row, day_column, groups = _layout(ws)
    timeslots = _timeslots(ws, header_row, day_column, day_column + 1)
    merged = _merged_lookup(ws)

    blocks = []
    for row, day, time in timeslots:
        for column, group in groups:
            values = [_source_value(ws, merged, row + offset, column) for offset in range(BLOCK_ROWS)]
            segments = _segments(values)
            blocks.append(ScheduleBlock(
                group=group,
                day=day,
                time=time,
                source_row=row,
                source_column=column,
                values=values,
                segments=segments,
                review_flags=_review_flags(values, segments),
            ))
    return blocks


def write_json(blocks, path: str | Path):
    Path(path).write_text(json.dumps([asdict(block) for block in blocks], ensure_ascii=False, indent=2) + "\n")


def write_pairs_json(pairs, path: str | Path):
    Path(path).write_text(json.dumps([asdict(pair) for pair in pairs], ensure_ascii=False, indent=2) + "\n")


def write_review_workbook(blocks, path: str | Path):
    workbook = Workbook()
    ws = workbook.active
    ws.title = "Review"
    ws.append(["group", "day", "time", "source", "row 1", "row 2", "row 3", "row 4", "row 5", "row 6", "review flags"])
    for block in blocks:
        ws.append([
            block.group,
            block.day,
            block.time,
            f"{block.values[0].coordinate}:{block.values[-1].coordinate}",
            *[value.value for value in block.values],
            "; ".join(block.review_flags),
        ])
    ws.freeze_panes = "A2"
    for column in ws.columns:
        ws.column_dimensions[column[0].column_letter].width = 24
    workbook.save(path)


def _displayed_value(ws, row, column):
    value = ws.cell(row, column).value
    if value is not None:
        return str(value).strip()
    for merged in ws.merged_cells.ranges:
        if merged.min_row <= row <= merged.max_row and merged.min_col <= column <= merged.max_col:
            return str(ws.cell(merged.min_row, merged.min_col).value or "").strip()
    return ""


def write_candidate_review_workbook(blocks, reference_path: str | Path | None, path: str | Path):
    """Export warning blocks with optional non-authoritative prior-output hints."""
    pairs = resolve_pairs(blocks)
    groups = list(dict.fromkeys(block.group for block in blocks))
    times = list(dict.fromkeys((block.day, block.time, block.source_row) for block in blocks))
    reference = openpyxl.load_workbook(reference_path, data_only=True).active if reference_path else None
    if reference and (reference.max_row != len(times) * 2 + 1 or reference.max_column != len(groups) + 2):
        raise LayoutError("Reference workbook dimensions do not match source layout")
    if reference:
        reference_groups = [_displayed_value(reference, 1, column) for column in range(3, len(groups) + 3)]
        if reference_groups != groups:
            raise LayoutError("Reference workbook groups do not match source layout")
        for index, (day, time, _) in enumerate(times):
            row = 2 + index * 2
            if _displayed_value(reference, row, 1) != day or _displayed_value(reference, row, 2) != time:
                raise LayoutError("Reference workbook timeslots do not match source layout")

    workbook = Workbook()
    ws = workbook.active
    ws.title = "Review candidates"
    ws.append([
        "group", "day", "time", "source", "row 1", "row 2", "row 3", "row 4", "row 5", "row 6",
        "resolution status", "resolved odd", "resolved even", "old odd candidate", "old even candidate", "parser flags",
    ])
    for block, pair in zip(blocks, pairs):
        if pair.status != "review" and not pair.review_flags:
            continue
        group_index = groups.index(block.group)
        time_index = next(index for index, item in enumerate(times) if item[2] == block.source_row)
        ws.append([
            block.group,
            block.day,
            block.time,
            f"{block.values[0].coordinate}:{block.values[-1].coordinate}",
            *[value.value for value in block.values],
            "auto-warning" if pair.status == "auto" else pair.status,
            pair.odd_text,
            pair.even_text,
            _displayed_value(reference, 2 + time_index * 2, 3 + group_index) if reference else None,
            _displayed_value(reference, 3 + time_index * 2, 3 + group_index) if reference else None,
            "; ".join(pair.review_flags),
        ])
    ws.freeze_panes = "A2"
    for column in ws.columns:
        ws.column_dimensions[column[0].column_letter].width = 24
    workbook.save(path)


def _source_horizontal_ranges(block, group_columns):
    """Return group-index ranges backed by a horizontal source merge."""
    ranges = {0: set(), 1: set()}
    for offset, value in enumerate(block.values):
        if not value.merged_range:
            continue
        min_col, min_row, max_col, max_row = range_boundaries(value.merged_range)
        if min_col == max_col or not (min_row <= value.row <= max_row):
            continue
        covered = [index for index, column in enumerate(group_columns) if min_col <= column <= max_col]
        if len(covered) >= 2:
            ranges[offset // 3].add((min(covered), max(covered)))
    return ranges


def write_schedule_workbook(
    blocks,
    pairs,
    path: str | Path,
    version: int | None = None,
    generated_date: date | None = None,
):
    """Export auto-resolved parity values; unresolved cells are never guessed."""
    groups = list(dict.fromkeys(block.group for block in blocks))
    group_columns = [next(block.source_column for block in blocks if block.group == group) for group in groups]
    times = list(dict.fromkeys((block.day, block.time, block.source_row) for block in blocks))
    pair_index = {(pair.group, pair.day, pair.time): pair for pair in pairs}
    block_index = {(block.group, block.day, block.time): block for block in blocks}

    workbook = Workbook()
    ws = workbook.active
    ws.title = "Orar"
    ws.append([None, None, *groups])
    if version is not None:
        ws["A1"] = version
    if generated_date is not None:
        ws["B1"] = generated_date
        ws["B1"].number_format = "dd/mm/yyyy"
    header_font = Font(name="Arial", bold=True, size=9)
    header_alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    cell_font = Font(name="Arial", size=8)
    cell_alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    for column in range(1, len(groups) + 3):
        cell = ws.cell(1, column)
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = BORDER
        if column > 2:
            cell.fill = PatternFill("solid", fgColor="C8D8F0")
    ws.row_dimensions[1].height = 26

    day_rows = {}
    horizontal_ranges = {}
    last_day = None
    for time_index, (day, time, _) in enumerate(times):
        rows = []
        for parity in ("odd", "even"):
            row = [day if day != last_day and parity == "odd" else None, time if parity == "odd" else None]
            for group_index, group in enumerate(groups):
                pair = pair_index[(group, day, time)]
                value = pair.odd_text if parity == "odd" else pair.even_text
                row.append(value)
                source_ranges = _source_horizontal_ranges(block_index[(group, day, time)], group_columns)
                horizontal_ranges.setdefault((time_index, parity), set()).update(source_ranges[0 if parity == "odd" else 1])
            rows.append(row)
        ws.append(rows[0])
        ws.append(rows[1])
        top_row, bottom_row = ws.max_row - 1, ws.max_row
        day_rows.setdefault(day, []).extend((top_row, bottom_row))
        for row in (top_row, bottom_row):
            ws.row_dimensions[row].height = 26
            for column in range(1, len(groups) + 3):
                cell = ws.cell(row, column)
                cell.alignment = cell_alignment
                cell.border = BORDER
                cell.font = Font(name="Arial", bold=(column == 1), size=8) if column <= 2 else cell_font
                if column <= 2:
                    cell.fill = PatternFill("solid", fgColor=DAY_COLORS.get(day, "FFFFFF"))
        last_day = day

    claimed = set()
    for time_index, (day, time, _) in enumerate(times):
        top_row = 2 + time_index * 2
        bottom_row = top_row + 1
        odd_ranges = horizontal_ranges.get((time_index, "odd"), set())
        even_ranges = horizontal_ranges.get((time_index, "even"), set())
        for group_start, group_end in sorted(odd_ranges | even_ranges):
            first_column, last_column = group_start + 3, group_end + 3
            odd_values = [ws.cell(top_row, column).value for column in range(first_column, last_column + 1)]
            even_values = [ws.cell(bottom_row, column).value for column in range(first_column, last_column + 1)]
            odd_valid = (
                (group_start, group_end) in odd_ranges
                and all(odd_values)
                and len(set(odd_values)) == 1
            )
            even_valid = (
                (group_start, group_end) in even_ranges
                and all(even_values)
                and len(set(even_values)) == 1
            )
            if not odd_valid and not even_valid:
                continue
            cells = {(row, column) for row in (top_row, bottom_row) for column in range(first_column, last_column + 1)}
            if odd_valid and even_valid and odd_values[0] == even_values[0] and not cells & claimed:
                ws.merge_cells(start_row=top_row, start_column=first_column, end_row=bottom_row, end_column=last_column)
                claimed.update(cells)
            else:
                for row, valid in ((top_row, odd_valid), (bottom_row, even_valid)):
                    row_cells = {(row, column) for column in range(first_column, last_column + 1)}
                    if valid and not row_cells & claimed:
                        ws.merge_cells(start_row=row, start_column=first_column, end_row=row, end_column=last_column)
                        claimed.update(row_cells)

        for group_index in range(len(groups)):
            column = group_index + 3
            if (top_row, column) in claimed or (bottom_row, column) in claimed:
                continue
            if ws.cell(top_row, column).value == ws.cell(bottom_row, column).value:
                ws.merge_cells(start_row=top_row, start_column=column, end_row=bottom_row, end_column=column)

        ws.merge_cells(start_row=top_row, start_column=2, end_row=bottom_row, end_column=2)

    for day, rows in day_rows.items():
        if len(rows) > 1:
            ws.merge_cells(start_row=min(rows), start_column=1, end_row=max(rows), end_column=1)

    ordered_days = list(day_rows)
    for previous_day, next_day in zip(ordered_days, ordered_days[1:]):
        previous_row = max(day_rows[previous_day])
        next_row = min(day_rows[next_day])
        for column in range(1, len(groups) + 3):
            cell = ws.cell(previous_row, column)
            border = cell.border
            cell.border = Border(left=border.left, right=border.right, top=border.top, bottom=MEDIUM)
            cell = ws.cell(next_row, column)
            border = cell.border
            cell.border = Border(left=border.left, right=border.right, top=MEDIUM, bottom=border.bottom)

    ws.column_dimensions["A"].width = 9
    ws.column_dimensions["B"].width = 11
    for column in range(3, len(groups) + 3):
        ws.column_dimensions[get_column_letter(column)].width = 22
    workbook.save(path)


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("source")
    cli.add_argument("--json", required=True)
    cli.add_argument("--pairs-json")
    cli.add_argument("--review-xlsx")
    cli.add_argument("--reference-xlsx")
    cli.add_argument("--candidate-review-xlsx")
    cli.add_argument("--schedule-xlsx")
    args = cli.parse_args()
    blocks = parse_workbook(args.source)
    write_json(blocks, args.json)
    pairs = resolve_pairs(blocks)
    if args.pairs_json:
        write_pairs_json(pairs, args.pairs_json)
    if args.review_xlsx:
        write_review_workbook(blocks, args.review_xlsx)
    if args.candidate_review_xlsx:
        write_candidate_review_workbook(blocks, args.reference_xlsx, args.candidate_review_xlsx)
    if args.schedule_xlsx:
        write_schedule_workbook(blocks, pairs, args.schedule_xlsx)
    print(f"Extracted {len(blocks)} group/time blocks")


if __name__ == "__main__":
    main()
