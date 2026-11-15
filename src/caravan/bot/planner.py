"""Find session times that suit the most people, from weekly availability."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .db import Availability
from .timeparse import zone


@dataclass(frozen=True)
class Suggestion:
    start: datetime
    user_ids: tuple[int, ...]


def _merge(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def free_intervals(
    rules: list[Availability], tz_name: str, start: datetime, end: datetime
) -> list[tuple[float, float]]:
    """One person's free time between start and end, as merged UTC epoch intervals.

    Rules are weekly wall-clock windows in the person's timezone. A window
    whose end is earlier than its start runs past midnight.
    """
    tz = zone(tz_name)
    day = start.astimezone(tz).date() - timedelta(days=1)
    last = end.astimezone(tz).date()
    out = []
    while day <= last:
        midnight = datetime(day.year, day.month, day.day, tzinfo=tz)
        for r in rules:
            if r.weekday != day.weekday():
                continue
            end_min = r.end_min if r.end_min > r.start_min else r.end_min + 1440
            a = (midnight + timedelta(minutes=r.start_min)).timestamp()
            b = (midnight + timedelta(minutes=end_min)).timestamp()
            out.append((a, b))
        day += timedelta(days=1)
    return _merge(out)


def suggest(
    rules: list[Availability],
    user_tzs: dict[int, str],
    default_tz: str,
    now: datetime,
    duration_min: int,
    days: int = 7,
    step_min: int = 30,
    top: int = 3,
) -> list[Suggestion]:
    """Best non-overlapping start times in the next `days`, most people first, then earliest."""
    by_user: dict[int, list[Availability]] = defaultdict(list)
    for r in rules:
        by_user[r.user_id].append(r)
    step = step_min * 60
    first = (int(now.timestamp()) // step + 1) * step
    horizon = now + timedelta(days=days)
    free = {
        uid: free_intervals(rs, user_tzs.get(uid, default_tz), now, horizon)
        for uid, rs in by_user.items()
    }
    length = duration_min * 60
    candidates = []
    t = first
    while t + length <= horizon.timestamp():
        users = tuple(sorted(
            uid for uid, ivs in free.items() if any(a <= t and t + length <= b for a, b in ivs)
        ))
        if users:
            candidates.append((t, users))
        t += step
    candidates.sort(key=lambda c: (-len(c[1]), c[0]))
    chosen: list[tuple[int, tuple[int, ...]]] = []
    for t, users in candidates:
        if all(abs(t - c) >= length for c, _ in chosen):
            chosen.append((t, users))
        if len(chosen) == top:
            break
    return [Suggestion(datetime.fromtimestamp(t, timezone.utc), users) for t, users in chosen]
