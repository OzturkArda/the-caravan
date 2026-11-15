"""Addon: level-ups, loot, dungeon runs and recipes (the data behind Phase 4)."""

from caravan.luadata import parse_savedvariables, to_lua
from caravan.schema import snapshot_from_savedvariables

from .addon_harness import Client, run, to_py

T0 = 1794800000  # GetServerTime() at stub time 0


def link(item_id, name, colour="ff0070dd"):
    return f"|c{colour}|Hitem:{item_id}::::::::14:::::|h[{name}]|h|r"


def grouped(*names):
    clients = [Client(n) for n in names]
    for c in clients:
        c.set_group(*[o for o in clients if o is not c])
    for c in clients:
        c.slash("addparty")
    run(clients, 20)
    return clients


def own_log(c):
    return to_py(c.g.TheCaravanDB.log[c.full_name])


def test_level_ups_are_logged_and_shared():
    a, b = grouped("Roland", "Brakka")
    a.W.player.level = 15
    a.fire("PLAYER_LEVEL_UP", 15)
    run([a, b], 10)
    assert [e["l"] for e in own_log(a)["lv"]] == [15]
    seen = b.member("Roland-Ironvale")
    assert seen["level"] == 15 and seen["lv"][0]["l"] == 15 and seen["lv"][0]["ts"] > T0


def test_notable_loot_is_logged():
    a = Client("Roland")
    a.W.itemQuality[2042] = 3
    a.fire("CHAT_MSG_LOOT", f"You receive loot: {link(2042, 'Staff of Westfall')}.")
    a.fire("CHAT_MSG_LOOT", f"You receive loot: {link(2589, 'Linen Cloth', 'ffffffff')}x3.")  # common
    a.fire("CHAT_MSG_LOOT", f"Brakka receives loot: {link(9999, 'Not Mine', 'ffa335ee')}.")
    a.fire("CHAT_MSG_LOOT", f"You receive item: {link(6630, 'Seedcloud Buckler', 'ffa335ee')}.")  # quality from colour
    loot = own_log(a)["loot"]
    assert [(e["n"], e["q"]) for e in loot] == [("Staff of Westfall", 3), ("Seedcloud Buckler", 4)]
    assert loot[0]["id"] == 2042 and a.errors == []


def test_secret_loot_text_is_skipped():
    a = Client("Roland")
    text = f"You receive loot: {link(2042, 'Staff of Westfall', 'ffa335ee')}."
    a.W.secret = text
    a.fire("CHAT_MSG_LOOT", text)
    assert own_log(a)["loot"] == {}
    assert a.errors == []


def enter_deadmines(c, with_journal=True):
    if with_journal:
        c.W.ej = c.lua.table_from({36: {"journalID": 63, "bosses": {
            1: {"name": "Rhahk'Zor", "encounterID": 1001},
            2: {"name": "Sneed", "encounterID": 1002},
            3: {"name": "Edwin VanCleef", "encounterID": 1003},
        }}}, recursive=True)
    c.W.instance = c.lua.table_from({"name": "The Deadmines", "kind": "party", "id": 36, "mapID": 36})
    c.fire("ZONE_CHANGED_NEW_AREA")


def leave(c):
    c.W.instance = None
    c.fire("ZONE_CHANGED_NEW_AREA")


def test_dungeon_run_with_bosses_and_clear():
    a = Client("Roland")
    enter_deadmines(a)
    a.fire("ENCOUNTER_END", 1001, "Rhahk'Zor", 1, 5, 1)
    a.fire("ENCOUNTER_END", 1002, "Sneed", 1, 5, 0)  # wipe
    a.W.advance(600)
    leave(a)  # ran out to repair
    a.W.advance(300)
    enter_deadmines(a)  # back within 30 minutes: same run
    a.fire("ENCOUNTER_END", 1002, "Sneed", 1, 5, 1)
    a.fire("ENCOUNTER_END", 1003, "Edwin VanCleef", 1, 5, 1)
    runs = own_log(a)["runs"]
    assert len(runs) == 1
    r = runs[0]
    assert r["n"] == "The Deadmines" and r["b"] == ["Rhahk'Zor", "Sneed", "Edwin VanCleef"]
    assert r["nb"] == 3 and r["done"] is True and r["te"] >= r["ts"] + 900
    leave(a)
    a.W.advance(3600)
    enter_deadmines(a)
    assert len(own_log(a)["runs"]) == 2
    assert a.errors == []


def test_run_without_encounter_journal_counts_bosses_only():
    a = Client("Roland")
    enter_deadmines(a, with_journal=False)
    a.fire("ENCOUNTER_END", 1003, "Edwin VanCleef", 1, 5, 1)
    r = own_log(a)["runs"][0]
    assert r["b"] == ["Edwin VanCleef"] and "nb" not in r and "done" not in r


def test_old_history_is_pruned_at_login():
    old = T0 - 30 * 86400
    a = Client("Roland")
    a.g.TheCaravanDB.log = a.lua.table_from(
        {"Roland-Ironvale": {"lv": {1: {"l": 5, "ts": old}, 2: {"l": 6, "ts": T0}}, "loot": {}, "runs": {}}},
        recursive=True,
    )
    a.fire("PLAYER_ENTERING_WORLD", True, False)
    assert [e["l"] for e in own_log(a)["lv"]] == [6]


def open_blacksmithing(c, linked=False):
    c.W.tradeskill = c.lua.table_from({"name": "Blacksmithing", "linked": linked, "recipes": {
        1: {"id": 2662, "name": "Copper Chain Pants"},
        2: {"id": 2663, "name": "Copper Bracers"},
        3: {"id": 3115, "name": "Rough Sharpening Stone"},
        4: {"id": 7408, "name": "Heavy Copper Maul", "learned": False},
        5: {"id": 9999, "name": "Copper Bracers Recraft", "isRecraft": True},
    }}, recursive=True)
    c.fire("TRADE_SKILL_SHOW")


def test_recipes_read_from_the_open_profession():
    a = Client("Roland")
    open_blacksmithing(a)
    a.W.advance(2)
    mine = to_py(a.g.TheCaravanDB.recipes["Roland-Ironvale"])
    assert mine["p"]["Blacksmithing"] == ["Copper Bracers", "Copper Chain Pants", "Rough Sharpening Stone"]
    assert mine["h"].startswith("3:")
    a.W.advance(5)
    assert a.member("Roland-Ironvale")["rh"] == mine["h"]


def test_someone_elses_linked_profession_is_ignored():
    a = Client("Roland")
    open_blacksmithing(a, linked=True)
    a.W.advance(2)
    assert to_py(a.g.TheCaravanDB.recipes["Roland-Ironvale"]) is None


def test_recipes_reach_the_group_on_request():
    a, b = grouped("Roland", "Brakka")
    open_blacksmithing(a)
    run([a, b], 40)
    got = to_py(b.g.TheCaravanDB.recipes["Roland-Ironvale"])
    assert got["p"]["Blacksmithing"] == ["Copper Bracers", "Copper Chain Pants", "Rough Sharpening Stone"]
    assert got["h"] == to_py(a.g.TheCaravanDB.recipes["Roland-Ironvale"])["h"]
    assert run([a, b], 120) == 0  # signatures match now, so nobody asks again
    assert b.errors == [] and a.errors == []


def test_history_and_recipes_round_trip_into_a_snapshot():
    a, b = grouped("Roland", "Brakka")
    open_blacksmithing(b)
    b.W.player.level = 15
    b.fire("PLAYER_LEVEL_UP", 15)
    b.W.itemQuality[2042] = 3
    b.fire("CHAT_MSG_LOOT", f"You receive loot: {link(2042, 'Staff of Westfall')}.")
    enter_deadmines(b)
    b.fire("ENCOUNTER_END", 1003, "Edwin VanCleef", 1, 5, 1)
    run([a, b], 60)
    sv_text = "TheCaravanDB = " + to_lua(to_py(a.g.TheCaravanDB)) + "\n"
    snap = snapshot_from_savedvariables(parse_savedvariables(sv_text), exported_at=1)
    brakka = snap["members"]["Brakka-Ironvale"]
    assert brakka["faction"] == "Alliance"
    assert [e["level"] for e in brakka["level_log"]] == [15]
    assert brakka["loot"][0]["name"] == "Staff of Westfall" and brakka["loot"][0]["quality"] == 3
    deadmines = brakka["runs"][0]
    assert deadmines["instance"] == "The Deadmines" and deadmines["bosses"] == ["Edwin VanCleef"]
    assert deadmines["cleared"] is True and deadmines["boss_count"] == 3
    assert brakka["recipes"] == {"Blacksmithing": ["Copper Bracers", "Copper Chain Pants", "Rough Sharpening Stone"]}
    assert snap["members"]["Roland-Ironvale"]["recipes"] == {}
