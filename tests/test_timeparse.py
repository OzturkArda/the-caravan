from datetime import datetime, timezone

import pytest

from caravan.bot.timeparse import parse_clock, parse_when, search_timezones, weekday_index, zone

TZ = "Australia/Melbourne"
# Monday 16 Nov 2026, 10:00 in Melbourne (UTC+11)
NOW = datetime(2026, 11, 15, 23, 0, tzinfo=timezone.utc)


def local(dt):
    return dt.astimezone(zone(TZ)).strftime("%a %Y-%m-%d %H:%M")


@pytest.mark.parametrize("text,expected", [
    ("19:00", 1140), ("7pm", 1140), ("7:30pm", 1170), ("12am", 0), ("12pm", 720),
    ("19", 1140), ("24:00", 1440), ("midnight", 0), ("noon", 720), (" 9.15 ", 555),
])
def test_parse_clock(text, expected):
    assert parse_clock(text) == expected


@pytest.mark.parametrize("text", ["25:00", "13pm", "7:61", "soon", "24:30"])
def test_parse_clock_rejects(text):
    with pytest.raises(ValueError):
        parse_clock(text)


@pytest.mark.parametrize("text,expected", [
    ("8pm", "Mon 2026-11-16 20:00"),        # later today, not tomorrow
    ("9am", "Tue 2026-11-17 09:00"),        # already past today
    ("fri 8pm", "Fri 2026-11-20 20:00"),
    ("tomorrow 7:30pm", "Tue 2026-11-17 19:30"),
    ("2026-11-21 19:00", "Sat 2026-11-21 19:00"),
    ("21/11 19:00", "Sat 2026-11-21 19:00"),
])
def test_parse_when(text, expected):
    assert local(parse_when(text, TZ, NOW)) == expected


def test_parse_when_rejects_past_and_garbage():
    with pytest.raises(ValueError, match="past"):
        parse_when("2026-11-01 19:00", TZ, NOW)
    with pytest.raises(ValueError):
        parse_when("whenever", TZ, NOW)
    with pytest.raises(ValueError, match="timezone"):
        parse_when("8pm", "Mars/Olympus", NOW)


def test_weekday_index():
    assert weekday_index("Friday") == 4 and weekday_index("mon") == 0
    with pytest.raises(ValueError):
        weekday_index("Funday")


def test_search_timezones():
    assert "Australia/Melbourne" in search_timezones("melb")
    assert "America/New_York" in search_timezones("new york")
    assert len(search_timezones("")) == 25
