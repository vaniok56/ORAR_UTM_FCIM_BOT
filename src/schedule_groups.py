def extract_schedule_groups(schedule, min_column=3):
    values = next(
        schedule.iter_rows(
            min_row=1,
            max_row=1,
            min_col=min_column,
            values_only=True,
        ),
        (),
    )
    groups = []
    for value in values:
        if isinstance(value, str):
            value = value.strip()
        groups.append(value or None)

    while groups and groups[-1] is None:
        groups.pop()
    if None in groups:
        raise ValueError("Group headers must be contiguous")
    return groups


def normalize_schedule_version(value):
    if value is None:
        return "final"
    if isinstance(value, str):
        value = value.strip().lower()
        if value in {"", "final"}:
            return "final"
    if isinstance(value, bool) or isinstance(value, float) and not value.is_integer():
        raise ValueError(f"Invalid schedule version: {value}")

    try:
        version = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid schedule version: {value}") from error
    if not 0 <= version <= 99:
        raise ValueError(f"Invalid schedule version: {value}")
    return "final" if version == 0 else version
