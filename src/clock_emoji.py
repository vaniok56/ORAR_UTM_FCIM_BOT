"""Time presentation helpers: clock faces and the current-pair marker.

Pure functions, no bot state, so they can be tested without Telegram, MySQL or
the schedule workbooks loaded.
"""

import datetime

import pytz

TZ = pytz.timezone("Europe/Chisinau")
PAIR_TIMES = ("8.00-9.30", "9.45-11.15", "11.30-13.00", "13.30-15.00",
              "15.15-16.45", "17.00-18.30", "18.45-20.15")

# Unicode ships one clock face per hour and per half hour, so a pair start gets
# the nearest face: :00-:14 the hour, :15-:44 half past, :45+ the next hour.
HOUR_FACES = "🕐🕑🕒🕓🕔🕕🕖🕗🕘🕙🕚🕛"   # index 0 is 1 o'clock
HALF_FACES = "🕜🕝🕞🕟🕠🕡🕢🕣🕤🕥🕦🕧"   # index 0 is half past 1


def clock_face(time_range):
    """Clock emoji for the start of a range like "8.00-9.30"."""
    try:
        start = str(time_range).split("-")[0].strip().replace(".", ":")
        hour, minute = (int(part) for part in start.split(":"))
    except (AttributeError, IndexError, ValueError):
        return "🕐"
    if minute <= 14:
        return HOUR_FACES[(hour - 1) % 12]
    if minute <= 44:
        return HALF_FACES[(hour - 1) % 12]
    return HOUR_FACES[hour % 12]


def pair_index_label(index, now_pair=None):
    """Append the hourglass to the pair in progress, or to the next one up."""
    return f"{index} ⏳" if now_pair and index == now_pair else index


def current_pair_index(now=None, times=PAIR_TIMES):
    """1-based index of the running pair, else the next one today, else 0."""
    moment = now or datetime.datetime.now(TZ)
    minutes = moment.hour * 60 + moment.minute
    upcoming = 0
    for index, slot in enumerate(times, start=1):
        try:
            start_text, end_text = str(slot).split("-")
            start_hour, start_minute = (int(part) for part in start_text.strip().split("."))
            end_hour, end_minute = (int(part) for part in end_text.strip().split("."))
        except (AttributeError, ValueError):
            continue
        start = start_hour * 60 + start_minute
        end = end_hour * 60 + end_minute
        if start <= minutes < end:
            return index
        if minutes < start and not upcoming:
            upcoming = index
    return upcoming
