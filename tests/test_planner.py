from datetime import datetime, timezone

from caravan.bot.db import Availability
from caravan.bot.planner import free_intervals, suggest
from caravan.bot.timeparse import zone

MEL = "Australia/Melbourne"
# Monday 16 Nov 2026 10:00 Melbourne
NOW = datetime(2026, 11, 15, 23, 0, tzinfo=timezone.utc)


def rule(uid, day, start, end):
    return Availability(0, uid, day, start * 60, end * 60)


def local(dt, tz=MEL):
    return dt.astimezone(zone(tz)).strftime("%a %H:%M")


def test_free_intervals_handle_midnight_crossing():
    ivs = free_intervals([rule(1, 4, 22, 2)], MEL, NOW, NOW.replace(day=22))
    assert len(ivs) == 1
    start, end = ivs[0]
    assert end - start == 4 * 3600
    assert local(datetime.fromtimestamp(start, timezone.utc)) == "Fri 22:00"


def test_free_intervals_merge_overlaps():
    ivs = free_intervals([rule(1, 4, 18, 21), rule(1, 4, 20, 23)], MEL, NOW, NOW.replace(day=22))
    assert len(ivs) == 1 and ivs[0][1] - ivs[0][0] == 5 * 3600


def test_suggest_prefers_most_people_then_earliest():
    rules = [
        rule(1, 2, 19, 23), rule(2, 2, 20, 23),           # Wed: two people 20-23
        rule(1, 4, 19, 23), rule(2, 4, 19, 23), rule(3, 4, 19, 23),  # Fri: everyone 19-23
    ]
    result = suggest(rules, {}, MEL, NOW, duration_min=180)
    assert local(result[0].start) == "Fri 19:00" and result[0].user_ids == (1, 2, 3)
    assert local(result[1].start) == "Wed 20:00" and result[1].user_ids == (1, 2)
    assert all(abs((a.start - b.start).total_seconds()) >= 3 * 3600 for a in result for b in result if a is not b)


def test_suggest_respects_each_persons_timezone():
    # 19:00-23:00 in Melbourne is 10:00-14:00 in Istanbul (UTC+3 vs UTC+11)
    rules = [rule(1, 4, 19, 23), rule(2, 4, 10, 14)]
    result = suggest(rules, {2: "Europe/Istanbul"}, MEL, NOW, duration_min=120)
    assert result[0].user_ids == (1, 2)
    assert local(result[0].start) == "Fri 19:00"


def test_suggest_with_nobody_free():
    assert suggest([], {}, MEL, NOW, duration_min=60) == []
    assert suggest([rule(1, 4, 19, 20)], {}, MEL, NOW, duration_min=120) == []
