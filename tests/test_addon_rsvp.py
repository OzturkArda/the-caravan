"""RSVPs clicked in the addon's Sessions tab."""

from caravan.bot.db import Store
from caravan.luadata import parse_savedvariables, to_lua
from caravan.schema import snapshot_from_savedvariables, snapshot_rsvps

from .addon_harness import Client, run, to_py

NOW = 1794800000 + 100


def schedule(generated_at: int = NOW - 10, **extra):
    return {
        "version": 1, "generated_at": generated_at, "reminders": [60, 15], "sync": "Roland-Ironvale",
        "people": {"10": {"name": "Xebeche", "chars": ["Roland-Ironvale"]},
                   "20": {"name": "Bo", "chars": ["Brakka-Ironvale"]},
                   "30": {"name": "Cy", "chars": []}},
        "sessions": [{"id": 1, "title": "In-game test", "start": NOW + 2 * 3600, "duration": 60,
                      "going": ["Xebeche"], "late": [], "out": ["Cy"], "rsvp": {"10": "going", "30": "out"}}],
        **extra,
    }


def grouped(*clients: Client) -> None:
    for c in clients:
        c.set_group(*[o for o in clients if o is not c])
        c.slash("addparty")


def sessions_tab(c: Client):
    c.slash("")
    c.call("ShowTab", "sessions")
    return c.g.TheCaravanFrame


def click(c: Client, status: str) -> None:
    f = c.g.TheCaravanFrame
    button = next(b for b in to_py_list(f.rows[1].buttons) if b.status == status)
    button.scripts.OnClick(button)


def to_py_list(t):
    return [t[i] for i in range(1, len(t) + 1)]


def test_sessions_tab_shows_character_names_and_buttons():
    a = Client("Roland", schedule=schedule())
    f = sessions_tab(a)
    row = f.rows[1]
    assert [row.cells[i].text for i in (2, 3, 4)] == ["In-game test", "Roland", "Cy"]  # Cy has no character linked
    buttons = to_py_list(row.buttons)
    assert [b.text for b in buttons] == ["In", "Late", "Out"] and all(b.shown for b in buttons)
    assert "count as your RSVP in Discord" in f.footer.text
    a.call("ShowTab", "group")
    assert not any(b.shown for b in to_py_list(row.buttons))
    assert a.errors == []


def test_clicking_records_the_answer_and_shows_it_as_not_synced_yet():
    a = Client("Roland", schedule=schedule())
    f = sessions_tab(a)
    click(a, "late")
    [entry] = to_py(a.g.TheCaravanDB.rsvps)["Roland-Ironvale"]
    assert entry["id"] == 1 and entry["s"] == "late" and entry["ts"] >= NOW
    assert f.rows[1].cells[3].text == "Roland* (late)"
    assert a.call("MyStatus", a.g.TheCaravanSchedule.sessions[1]) == ("late", True)
    assert "* Not in Discord yet. Discord gets it when you /reload or log out." in f.footer.text
    assert any("You're Late for" in p and "when you /reload or log out" in p for p in a.prints)
    click(a, "going")  # changing your mind replaces the answer
    assert len(to_py(a.g.TheCaravanDB.rsvps)["Roland-Ironvale"]) == 1


def test_a_newer_schedule_replaces_the_pending_marker():
    a = Client("Roland", schedule=schedule())
    sessions_tab(a)
    click(a, "out")
    later = a.lua.table_from(schedule(generated_at=NOW + 3600), recursive=True)
    later.sessions[1].rsvp["10"] = "out"
    assert a.call("AcceptSchedule", later)
    assert a.g.TheCaravanFrame.rows[1].cells[4].text == "Cy, Roland"


def test_an_unlinked_character_is_told_how_to_link():
    a = Client("Dara", schedule=schedule())
    f = sessions_tab(a)
    assert "/character link Dara-Ironvale" in f.footer.text
    click(a, "going")
    assert any("link this character there: /character link Dara-Ironvale" in p for p in a.prints)
    assert "Dara*" in f.rows[1].cells[3].text


def test_a_friends_click_reaches_discord_through_the_sync_players_snapshot():
    a = Client("Roland", schedule=schedule())
    b = Client("Brakka")
    grouped(a, b)
    run([a, b], 20)  # Brakka gets the session list from Roland
    f = sessions_tab(b)
    click(b, "late")
    assert any("once you've grouped with Roland and they /reload or log out" in p for p in b.prints)
    run([a, b], 10)
    assert to_py(a.g.TheCaravanDB.rsvps)["Brakka-Ironvale"][0]["s"] == "late"
    assert "Brakka* (late)" in f.rows[1].cells[3].text

    # Roland's /reload writes the file; the sync app turns it into a snapshot.
    sv = parse_savedvariables("TheCaravanDB = " + to_lua(to_py(a.g.TheCaravanDB)) + "\n")
    snap = snapshot_from_savedvariables(sv, exported_at=NOW + 60)
    store = Store(":memory:")
    session = store.create_session(guild_id=1, channel_id=2, title="In-game test", start_ts=NOW + 2 * 3600,
                                   duration_min=60, created_by=10)
    store.upsert_user(20, "Bo")
    store.link_character("Brakka-Ironvale", 20, NOW)
    result = store.apply_game_rsvps(snapshot_rsvps(snap), NOW + 60)
    assert result.changed_sessions == {session.id}
    assert [a.display_name for a in store.rsvps(session.id)["late"]] == ["Bo"]
    assert a.errors == [] and b.errors == []


def test_merging_keeps_the_newest_click_and_drops_junk():
    a = Client("Roland")
    a.g.TheCaravanDB.rsvps = a.lua.table_from({"Brakka-Ironvale": [{"id": 1, "s": "going", "ts": 50}]}, recursive=True)
    incoming = a.lua.table_from({
        "Brakka-Ironvale": [{"id": 1, "s": "out", "ts": 40}, {"id": 2, "s": "late", "ts": 60}],
        "NoRealm": [{"id": 1, "s": "going", "ts": 70}],
        "Dara-Ironvale": [{"id": 1, "s": "maybe", "ts": 70}, {"id": "x", "s": "going", "ts": 70}],
    }, recursive=True)
    assert a.call("MergeRsvps", incoming)
    merged = to_py(a.g.TheCaravanDB.rsvps)
    assert merged == {"Brakka-Ironvale": [{"id": 1, "s": "going", "ts": 50}, {"id": 2, "s": "late", "ts": 60}]}
    assert not a.call("MergeRsvps", incoming)  # nothing new the second time
    assert not a.call("MergeRsvps", "junk")


def test_answers_for_ended_sessions_are_pruned():
    old = schedule()
    old["sessions"][0]["start"] = NOW - 3 * 3600
    a = Client("Roland", schedule=old)
    a.g.TheCaravanDB.rsvps = a.lua.table_from(
        {"Roland-Ironvale": [{"id": 1, "s": "going", "ts": NOW - 4 * 3600}, {"id": 99, "s": "out", "ts": NOW}],
         "Old-Ironvale": [{"id": 5, "s": "out", "ts": NOW - 15 * 86400}]}, recursive=True)
    a.call("PruneRsvps")
    assert to_py(a.g.TheCaravanDB.rsvps) == {"Roland-Ironvale": [{"id": 99, "s": "out", "ts": NOW}]}


def test_no_reminder_for_a_session_you_are_out_of():
    a = Client("Roland", schedule=schedule())
    sessions_tab(a)
    click(a, "out")
    a.W.advance(2 * 3600)
    assert to_py(a.W.notices) in (None, [], {})
