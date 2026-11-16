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


def grouped(*clients: Client) -> None:
    for c in clients:
        c.set_group(*[o for o in clients if o is not c])
        c.slash("addparty")


def sched_messages(c: Client) -> list:
    out = []
    for msg in c.take_outbox():
        ok, data = c.addon.Deserialize(c.addon, msg.text)
        if ok and data.t == "SCHED":
            out.append(data)
    return out


def test_a_friend_without_the_sync_app_gets_the_schedule():
    a = Client("Roland", schedule=schedule(start_in=3 * 3600))
    b = Client("Brakka")
    grouped(a, b)
    run([a, b], 20)
    got = to_py(b.g.TheCaravanSchedule)
    assert got["generated_at"] == NOW and got["from"] == "Roland-Ironvale"
    assert got["sessions"][0]["title"] == "Deadmines run" and got["sessions"][0]["going"] == ["Arda"]
    assert any("Got the session list from Roland" in p for p in b.prints)
    assert to_py(a.g.TheCaravanSchedule).get("from") is None  # the sender's own copy is untouched
    b.slash("")
    b.call("ShowTab", "sessions")
    assert "via Roland" in b.g.TheCaravanFrame.footer.text
    b.W.advance(2 * 3600 + 1)  # the friend's addon now reminds too
    assert notices(b) and "1 hour" in notices(b)[0]
    assert a.errors == [] and b.errors == []


def test_an_older_schedule_never_replaces_a_newer_one():
    a = Client("Roland", schedule=schedule(start_in=3600, generated_at=NOW - 500))
    b = Client("Brakka", schedule=schedule(start_in=7200, generated_at=NOW - 100))
    grouped(a, b)
    run([a, b], 20)
    assert to_py(a.g.TheCaravanSchedule)["generated_at"] == NOW - 100  # Roland took Brakka's newer one
    assert to_py(b.g.TheCaravanSchedule)["generated_at"] == NOW - 100
    assert to_py(b.g.TheCaravanSchedule).get("from") is None


def test_schedule_from_someone_not_on_the_list_is_ignored():
    a = Client("Roland", schedule=schedule(start_in=3600))
    b = Client("Brakka")
    a.set_group(b)
    b.set_group(a)
    a.slash("addparty")  # only Roland lists Brakka
    run([a, b], 20)
    assert b.g.TheCaravanSchedule is None


def fake_data(a: Client, **envelope) -> str:
    msg = {"t": "DATA", "v": 1, "d": a.lua.table_from({"level": 9}), **envelope}
    return a.addon.Serialize(a.addon, a.lua.table_from(msg))


def test_older_addons_are_not_sent_the_schedule():
    a = Client("Roland", schedule=schedule(start_in=3600))
    a.slash("add Brakka")
    a.W.group = a.lua.table_from({1: a.lua.table_from({"name": "Brakka"})})
    a.W.advance(10)
    a.take_outbox()
    a.fire("CHAT_MSG_ADDON", "TheCaravan", fake_data(a), "PARTY", "Brakka-Ironvale")  # 0.2.0: no sg
    a.W.advance(5)
    assert sched_messages(a) == []
    a.fire("CHAT_MSG_ADDON", "TheCaravan", fake_data(a, sg=0), "PARTY", "Brakka-Ironvale")
    a.W.advance(5)
    assert len(sched_messages(a)) == 1


def test_a_pending_send_is_dropped_when_someone_else_sends_first():
    a = Client("Roland", schedule=schedule(start_in=3600))
    a.slash("add Brakka")
    a.W.group = a.lua.table_from({1: a.lua.table_from({"name": "Brakka"})})
    a.W.advance(10)
    a.take_outbox()
    a.call("QueueScheduleSend")
    assert a.addon.scheduleTimer
    same = a.addon.Serialize(a.addon, a.lua.table_from({"t": "SCHED", "v": 1, "s": a.g.TheCaravanSchedule}))
    a.fire("CHAT_MSG_ADDON", "TheCaravan", same, "PARTY", "Brakka-Ironvale")
    assert not a.addon.scheduleTimer
    a.W.advance(5)
    assert sched_messages(a) == []


def test_received_schedules_are_cleaned():
    a = Client("Roland")
    raw = a.lua.table_from({
        "generated_at": NOW, "evil": "x", "reminders": {1: 30, 2: "soon"},
        "sessions": {1: {"id": 1, "title": "T" * 500, "start": NOW + 60, "going": {1: "A", 2: 5}, "hack": 1},
                     2: {"title": "no id or start"}},
    }, recursive=True)
    clean = to_py(a.call("SanitizeSchedule", raw))
    assert set(clean) == {"version", "generated_at", "sessions", "reminders"}
    assert clean["reminders"] == [30]
    [s] = clean["sessions"]
    assert len(s["title"]) == 100 and s["going"] == ["A"] and "hack" not in s
    assert a.call("SanitizeSchedule", "nope") is None
