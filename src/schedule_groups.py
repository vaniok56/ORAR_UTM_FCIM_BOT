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
