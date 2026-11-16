import pytest

from caravan.schema import (
    member_from_lua, schedule_signature, snapshot_from_savedvariables, validate_snapshot,
)


def test_member_from_lua_maps_and_cleans_fields():
    m = member_from_lua({
        "name": "Roland", "level": 14, "xpMax": 8000, "ilvl": 14.55, "ts": 99, "class": "WARRIOR",
        "profs": [{"name": "Mining", "rank": 52, "max": 75}, {"rank": 1}],
        "gear": {1: {"s": 1, "id": 7413, "il": 15}, 2: {"s": 2}},
        "level_bogus": True,
    })
    assert m["level"] == 14 and m["xp_max"] == 8000 and m["ilvl"] == 14.6 and m["updated_at"] == 99
    assert m["professions"] == [{"name": "Mining", "rank": 52, "max": 75}]
    assert m["gear"] == [{"slot": 1, "item_id": 7413, "ilvl": 15}]
    assert "level_bogus" not in m


def test_snapshot_from_savedvariables():
    sv = {"TheCaravanDB": {"lastCharacter": "Roland-Ironvale", "members": {"Roland-Ironvale": {"level": 3}}}}
    snap = snapshot_from_savedvariables(sv, exported_at=5)
    assert snap["version"] == 1 and snap["exported_at"] == 5 and snap["source"] == "Roland-Ironvale"
    assert snap["members"]["Roland-Ironvale"]["level"] == 3
    with pytest.raises(ValueError):
        snapshot_from_savedvariables({}, exported_at=5)
    assert snapshot_from_savedvariables({"TheCaravanDB": {"members": {}}}, 1)["members"] == {}


def test_validate_snapshot():
    good = {"version": 1, "exported_at": 1, "members": {}}
    assert validate_snapshot(good) is good
    for bad in ([], {"version": 2, "exported_at": 1, "members": {}}, {"version": 1, "exported_at": 1},
                {"version": 1, "exported_at": "x", "members": {}}):
        with pytest.raises(ValueError):
            validate_snapshot(bad)


def test_schedule_signature_ignores_generation_time():
    a = {"generated_at": 1, "sessions": [{"id": 1}]}
    b = {"generated_at": 2, "sessions": {1: {"id": 1}}}
    assert schedule_signature(a) == schedule_signature(b)
    assert schedule_signature(a) != schedule_signature({"sessions": []})
    assert schedule_signature(None) == "[]"
    relayed = {**a, "from": "Brakka-Ironvale"}
    assert schedule_signature(relayed) == schedule_signature(a)
    assert schedule_signature({**a, "reminders": [30]}) != schedule_signature({**a, "reminders": [60, 15]})
