"""Turn what friends type ("fri 8pm", "tomorrow 7:30pm") into datetimes."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

import dateparser

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

_CLOCK = re.compile(r"^\s*(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?\s*$", re.IGNORECASE)


def parse_clock(text: str) -> int:
    """Minutes after midnight for "19:00", "7pm", "7:30pm", "19" or "24:00"."""
    t = text.strip().lower()
    if t == "midnight":
        return 0
    if t == "noon":
        return 12 * 60
    m = _CLOCK.match(t)
    if not m:
        raise ValueError(f"couldn't read {text!r} as a time; try 19:00 or 7pm")
    hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ampm:
        if not 1 <= hour <= 12:
            raise ValueError(f"{text!r} isn't a valid time")
        hour = hour % 12 + (12 if ampm == "pm" else 0)
    if minute > 59 or hour > 24 or (hour == 24 and minute):
        raise ValueError(f"{text!r} isn't a valid time")
    return hour * 60 + minute


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown timezone {name!r}") from exc


def parse_when(text: str, tz_name: str, now: datetime) -> datetime:
    """Parse a session start time in the given timezone; it must be in the future.

    `now` must be timezone-aware. A bare time ("8pm") means the next time the
    clock shows it: today if still ahead, otherwise tomorrow.
    """
    tz = zone(tz_name)
    local_now = now.astimezone(tz)
    try:
        minutes = parse_clock(text)
    except ValueError:
        minutes = None
    if minutes is not None:
        midnight = datetime(local_now.year, local_now.month, local_now.day, tzinfo=tz)
        result = midnight + timedelta(minutes=minutes)
        if result <= local_now:
            result += timedelta(days=1)
        return result
    parsed = dateparser.parse(
        text,
        settings={
            "PREFER_DATES_FROM": "future",
            "TIMEZONE": tz_name,
            "RETURN_AS_TIMEZONE_AWARE": True,
            "RELATIVE_BASE": local_now.replace(tzinfo=None),
            "DATE_ORDER": "DMY",
        },
    )
    if parsed is None:
        raise ValueError(f"couldn't read {text!r} as a date and time; try \"fri 8pm\" or \"2026-11-21 19:00\"")
    if parsed <= now:
        raise ValueError(f"{text!r} is in the past")
    return parsed


def weekday_index(name: str) -> int:
    key = name.strip().lower()[:3]
    for i, day in enumerate(WEEKDAYS):
        if day.lower().startswith(key):
            return i
    raise ValueError(f"unknown day {name!r}")


def search_timezones(query: str, limit: int = 25) -> list[str]:
    q = query.strip().lower().replace(" ", "_")
    names = sorted(available_timezones())
    hits = [n for n in names if q in n.lower()] if q else names
    return hits[:limit]
