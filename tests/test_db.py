import pytest

from caravan.bot.db import LinkedCharacter, Store

T0 = 1_800_000_000


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


def add(store, start=T0 + 3600, duration=120, title="Run"):
    return store.create_session(guild_id=1, channel_id=2, title=title, start_ts=start,
                                duration_min=duration, created_by=10)


def test_users_and_timezones(store):
    store.upsert_user(10, "Arda")
    store.upsert_user(10, "Arda B")
    assert store.display_names() == {10: "Arda B"}
    assert store.user_tz(10) is None and store.user_tz(99) is None
    store.set_user_tz(11, "Bo", "Europe/Istanbul")
    assert store.user_tz(11) == "Europe/Istanbul" and store.user_tzs() == {11: "Europe/Istanbul"}


def test_session_lifecycle(store):
    s = add(store)
    assert s.id == 1 and s.end_ts == s.start_ts + 7200 and not s.cancelled
    store.set_session_message(s.id, 555)
    store.set_session_event(s.id, 777)
    s = store.get_session(s.id)
    assert (s.message_id, s.event_id) == (555, 777)
    assert store.cancel_session(s.id) is True
    assert store.cancel_session(s.id) is False
    assert store.get_session(s.id).cancelled
    assert store.get_session(99) is None


def test_upcoming_sessions_include_running_and_skip_finished(store):
    add(store, start=T0 - 3 * 3600, duration=60, title="done")
    add(store, start=T0 - 1800, duration=60, title="running")
    add(store, start=T0 + 7200, title="later")
    cancelled = add(store, start=T0 + 3600, title="cancelled")
    store.cancel_session(cancelled.id)
    assert [s.title for s in store.upcoming_sessions(T0)] == ["running", "later"]


def test_rsvps_latest_choice_wins(store):
    s = add(store)
    store.upsert_user(10, "Arda")
    store.set_rsvp(s.id, 10, "going", T0)
    store.set_rsvp(s.id, 11, "late", T0)
    store.set_rsvp(s.id, 10, "out", T0 + 1)
    r = store.rsvps(s.id)
    assert [a.display_name for a in r["out"]] == ["Arda"]
    assert [a.display_name for a in r["late"]] == ["11"]
    assert r["going"] == []
    with pytest.raises(ValueError):
        store.set_rsvp(s.id, 10, "maybe", T0)


def test_due_reminders_send_once_and_skip_stale_offsets(store):
    s = add(store, start=T0 + 10 * 60)
    due = store.due_reminders(T0, (60, 15))
    assert due == [(s, [15, 60])]
    store.mark_reminded(s.id, [15, 60])
    assert store.due_reminders(T0, (60, 15)) == []
    later = add(store, start=T0 + 2 * 3600)
    assert store.due_reminders(T0, (60, 15)) == []
    assert store.due_reminders(T0 + 3600, (60, 15)) == [(later, [60])]


def test_availability(store):
    a = store.add_availability(10, 4, 19 * 60, 23 * 60)
    store.add_availability(11, 5, 20 * 60, 60)
    assert a.id == 1
    assert [r.user_id for r in store.availability()] == [10, 11]
    assert len(store.availability(10)) == 1
    with pytest.raises(ValueError):
        store.add_availability(10, 1, 600, 600)
    assert store.clear_availability(10) == 1
    assert store.availability(10) == []


def test_snapshots(store):
    assert store.latest_snapshot() is None
    store.save_snapshot({"members": {"A": 1}}, T0)
    snap = store.save_snapshot({"members": {"Ü": 2}}, T0 + 5)
    latest = store.latest_snapshot()
    assert latest.id == snap.id and latest.payload == {"members": {"Ü": 2}} and latest.received_at == T0 + 5


def test_schedule_export(store):
    s = add(store, title="Deadmines")
    store.upsert_user(10, "Arda")
    store.set_rsvp(s.id, 10, "going", T0)
    store.upsert_user(20, "Bo")
    store.link_character("Brakka-Ironvale", 20, T0)
    export = store.schedule_export(T0)
    assert export["version"] == 1 and export["generated_at"] == T0 and export["reminders"] == [60, 15]
    assert export["sessions"] == [{"id": s.id, "title": "Deadmines", "start": s.start_ts, "duration": 120,
                                   "going": ["Arda"], "late": [], "out": [], "rsvp": {"10": "going"}}]
    assert export["people"] == {"10": {"name": "Arda", "chars": []}, "20": {"name": "Bo", "chars": ["Brakka-Ironvale"]}}
    assert "sync" not in export
    store.save_snapshot({"version": 1, "exported_at": T0, "source": "Roland-Ironvale", "members": {}}, T0)
    assert store.schedule_export(T0)["sync"] == "Roland-Ironvale"


def test_character_links(store):
    store.link_character("Roland-Ironvale", 10, T0)
    assert store.character_owner("roland-ironvale") == 10
    store.link_character("ROLAND-Ironvale", 20, T0)  # same character, case-insensitive: moves to 20
    assert store.characters() == [LinkedCharacter("ROLAND-Ironvale", 20)]
    store.link_character("Brakka-Ironvale", 20, T0)
    assert [c.name for c in store.characters(20)] == ["Brakka-Ironvale", "ROLAND-Ironvale"]
    assert store.unlink_character("roland-ironvale") and not store.unlink_character("roland-ironvale")
    assert store.character_owner("Roland-Ironvale") is None


def game(character, session_id, status, at):
    return {"character": character, "session_id": session_id, "status": status, "at": at}


def test_game_rsvps_apply_as_the_linked_user_and_newest_wins(store):
    s = add(store, start=T0 + 3600, title="Deadmines")
    store.upsert_user(10, "Arda")
    store.link_character("Roland-Ironvale", 10, T0)
    store.set_rsvp(s.id, 10, "going", T0 + 100)  # clicked In on Discord

    older = store.apply_game_rsvps([game("Roland-Ironvale", s.id, "out", T0 + 50)], T0 + 200)
    assert older.changed_sessions == set() and [a.user_id for a in store.rsvps(s.id)["going"]] == [10]

    newer = store.apply_game_rsvps([game("Roland-Ironvale", s.id, "late", T0 + 150)], T0 + 200)
    assert newer.changed_sessions == {s.id} and [a.display_name for a in store.rsvps(s.id)["late"]] == ["Arda"]

    again = store.apply_game_rsvps([game("Roland-Ironvale", s.id, "late", T0 + 150)], T0 + 300)
    assert again.changed_sessions == set()  # re-uploading the same entry changes nothing

    store.set_rsvp(s.id, 10, "going", T0 + 400)  # a later Discord click beats the old game entry
    store.apply_game_rsvps([game("Roland-Ironvale", s.id, "late", T0 + 150)], T0 + 500)
    assert [a.user_id for a in store.rsvps(s.id)["going"]] == [10]


def test_game_rsvps_skip_unlinked_ended_cancelled_and_future(store):
    s = add(store, start=T0 + 3600, duration=60, title="Run")
    gone = add(store, start=T0 + 3600, title="Gone")
    store.cancel_session(gone.id)
    store.link_character("Roland-Ironvale", 10, T0)
    result = store.apply_game_rsvps([
        game("Stranger-Ironvale", s.id, "going", T0),
        game("Roland-Ironvale", gone.id, "going", T0),
        game("Roland-Ironvale", 999, "going", T0),
        game("Roland-Ironvale", s.id, "going", T0 + 10_000),  # clock far ahead of the bot's
    ], T0)
    assert result.unlinked == {"Stranger-Ironvale"} and result.changed_sessions == set()
    assert store.rsvps(s.id)["going"] == []
    ended = store.apply_game_rsvps([game("Roland-Ironvale", s.id, "going", T0)], T0 + 3600 + 3600)
    assert ended.changed_sessions == set()


def test_alts_of_one_player_count_once_newest_first(store):
    s = add(store, start=T0 + 3600, title="Run")
    store.link_character("Roland-Ironvale", 10, T0)
    store.link_character("Alt-Ironvale", 10, T0)
    store.apply_game_rsvps([game("Alt-Ironvale", s.id, "out", T0 + 20), game("Roland-Ironvale", s.id, "going", T0 + 10)], T0 + 30)
    assert [a.user_id for a in store.rsvps(s.id)["out"]] == [10] and store.rsvps(s.id)["going"] == []


def test_sessions_ended_between_and_next_session(store):
    a = add(store, start=T0, duration=60, title="a")
    b = add(store, start=T0 + 7200, duration=60, title="b")
    store.cancel_session(add(store, start=T0, duration=60, title="gone").id)
    assert [s.title for s in store.sessions_ended_between(T0, T0 + 3600)] == ["a"]
    assert [s.title for s in store.sessions_ended_between(T0, T0 + 3 * 3600)] == ["a", "b"]
    assert store.next_session_after(a.start_ts) == b and store.next_session_after(b.start_ts) is None


def test_orders(store):
    o = store.create_order(channel_id=2, item="Copper Bracers", quantity=2, note="for my alt",
                           requested_by=10, now_ts=T0)
    assert (o.id, o.status, o.quantity, o.note) == (1, "open", 2, "for my alt")
    store.create_order(channel_id=2, item="Linen Bag", quantity=1, note=None, requested_by=11, now_ts=T0)
    assert [x.item for x in store.open_orders()] == ["Copper Bracers", "Linen Bag"]
    assert store.close_order(o.id, "done", 11, T0 + 5) is True
    assert store.close_order(o.id, "cancelled", 10, T0 + 6) is False
    closed = store.get_order(o.id)
    assert (closed.status, closed.closed_by, closed.closed_at) == ("done", 11, T0 + 5)
    assert [x.item for x in store.open_orders()] == ["Linen Bag"]
    with pytest.raises(ValueError):
        store.close_order(2, "lost", 10, T0)


def test_recaps_and_level_alerts(store):
    s = add(store)
    assert store.get_recap(s.id) is None
    store.save_recap(s.id, None, "sig1", T0)
    store.save_recap(s.id, 99, "sig2", T0 + 1)
    r = store.get_recap(s.id)
    assert (r.message_id, r.signature, r.updated_at) == (99, "sig2", T0 + 1)
    store.add_level_alert("Roland-Ironvale", 20, T0)
    assert store.level_alerts() == {"Roland-Ironvale": 20}
    store.clear_level_alert("Roland-Ironvale")
    assert store.level_alerts() == {}
