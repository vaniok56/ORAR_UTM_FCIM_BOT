from collections import Counter, defaultdict


def plan_year_migration(users, group_list):
    group_years = defaultdict(set)
    for year, specialties in group_list.items():
        for groups in specialties.values():
            for group in groups.values():
                group_years[group.strip().upper()].add(int(year))

    updates = []
    unknown = Counter()
    ambiguous = Counter()
    correct = 0
    no_group = 0

    for row in users.itertuples():
        original_group = str(row.group_n).strip()
        group = original_group.upper()

        if not group or group == "NONE":
            no_group += 1
            continue

        years = group_years.get(group)
        if not years:
            unknown[group] += 1
            continue
        if len(years) != 1:
            ambiguous[group] += 1
            continue

        target_year = next(iter(years))
        try:
            current_year = int(row.year_s)
        except (TypeError, ValueError):
            current_year = None

        if current_year == target_year:
            correct += 1
        else:
            updates.append((target_year, row.SENDER, original_group))

    return {
        "updates": updates,
        "correct": correct,
        "no_group": no_group,
        "unknown": unknown,
        "ambiguous": ambiguous,
    }
