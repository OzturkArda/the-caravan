"""The addon's schedule: in-game reminders and passing the schedule on to friends."""

import time

from .addon_harness import Client, run, to_py

NOW = 1794800000 + 100  # the fake client's server time at login


def schedule(start_in: int, generated_at: int = NOW, **extra):
    return {"version": 1, "generated_at": generated_at, **extra, "sessions": {
        1: {"id": 7, "title": "Deadmines run", "start": NOW + start_in, "duration": 120,
            "going": {1: "Arda"}, "late": {}, "out": {}},
    }}


def notices(a: Client) -> list[str]:
    return list(to_py(a.W.notices) or [])


def test_reminders_fire_60_and_15_minutes_before():
    a = Client("Roland", schedule=schedule(start_in=61 * 60))
    a.W.advance(59)
    assert notices(a) == []
    a.W.advance(2)
    clock = time.strftime("%H:%M", time.localtime(NOW + 61 * 60))  # the stub's date() is os.date
    assert notices(a) == [f"The Caravan: Deadmines run starts in 1 hour ({clock})."]
    assert any("Deadmines run" in p and "starts in 1 hour" in p for p in a.prints)
    a.W.advance(45 * 60)
    assert len(notices(a)) == 2 and "starts in 15 minutes" in notices(a)[1]
    assert to_py(a.W.sounds) == [8959, 8959]
    assert a.errors == []


def test_reminders_that_already_passed_are_skipped():
    a = Client("Roland", schedule=schedule(start_in=20 * 60))  # 60-minute reminder is in the past
    a.W.advance(30 * 60)
    assert len(notices(a)) == 1 and "15 minutes" in notices(a)[0]


def test_reminder_times_come_from_the_schedule():
    a = Client("Roland", schedule=schedule(start_in=40 * 60, reminders={1: 30}))
    a.W.advance(40 * 60)
    assert len(notices(a)) == 1 and "30 minutes" in notices(a)[0]


def test_reminders_can_be_turned_off_and_on():
    a = Client("Roland", schedule=schedule(start_in=61 * 60))
    a.slash("reminders")
    assert any(p.endswith("Session reminders off.") for p in a.prints)
    a.W.advance(61 * 60)
    assert notices(a) == []
    assert a.g.TheCaravanDB.reminders is False

    b = Client("Roland", schedule=schedule(start_in=61 * 60), db=to_py(a.g.TheCaravanDB))
    b.slash("reminders")
    assert any(p.endswith("Session reminders on.") for p in b.prints)
    b.W.advance(61)
    assert len(notices(b)) == 1
