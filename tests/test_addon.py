from caravan.luadata import parse_savedvariables, to_lua
from caravan.schema import snapshot_from_savedvariables
from caravan.sync.service import write_schedule

from .addon_harness import ADDON_DIR, Client, load_order, run, to_py


def test_toc_lists_files_that_exist():
    files = load_order()
    assert files[-1].name == "Minimap.lua"
    assert all(p.exists() for p in files)


def test_toc_declares_forever_interface_and_saved_variables():
    toc = (ADDON_DIR / "TheCaravan.toc").read_text()
    assert "## Interface: 16001" in toc
    assert "## SavedVariables: TheCaravanDB, TheCaravanSchedule" in toc


def test_collects_own_character_on_login():
    a = Client("Roland")
    run([a], 6)
    me = a.member("Roland-Ironvale")
    assert me["level"] == 14 and me["class"] == "WARRIOR" and me["race"] == "Human"
    assert me["zone"] == "Elwynn Forest"
    assert [p["name"] for p in me["profs"]] == ["Mining", "Blacksmithing"]
    assert {g["id"] for g in me["gear"]} == {7413, 1292}
    assert me["ilvl"] == 14.5
    assert a.errors == []


def test_two_party_members_see_each_other():
    a, b = Client("Roland"), Client("Brakka")
    a.set_group(b)
    b.set_group(a)
    a.slash("add brakka")
    b.slash("addparty")
    run([a, b], 20)
    assert b.member("Roland-Ironvale")["level"] == 14
    assert a.member("Brakka-Ironvale")["profs"][0]["name"] == "Mining"
    assert a.errors == [] and b.errors == []


def test_level_up_reaches_the_group():
    a, b = Client("Roland"), Client("Brakka")
    a.set_group(b)
    b.set_group(a)
    a.slash("addparty")
    b.slash("addparty")
    run([a, b], 20)
    a.W.player.level = 15
    a.fire("PLAYER_LEVEL_UP", 15)
    run([a, b], 10)
    assert b.member("Roland-Ironvale")["level"] == 15


def test_data_from_players_not_on_the_list_is_ignored():
    a, b = Client("Roland"), Client("Stranger")
    a.set_group(b)
    b.set_group(a)
    b.slash("addparty")
    run([a, b], 20)
    assert to_py(a.g.TheCaravanDB.members["Stranger-Ironvale"]) is None
    assert to_py(a.addon.unlisted) == {"Stranger-Ironvale": True}


def test_no_messages_in_combat_until_it_ends():
    a, b = Client("Roland"), Client("Brakka")
    a.set_group(b)
    b.set_group(a)
    b.slash("addparty")
    a.W.inCombat = True
    run([a, b], 20)
    assert to_py(b.g.TheCaravanDB.members["Roland-Ironvale"]) is None
    a.W.inCombat = False
    a.fire("PLAYER_REGEN_ENABLED")
    run([a, b], 15)
    assert b.member("Roland-Ironvale")["level"] == 14


def test_newer_schema_is_ignored_with_one_warning():
    a = Client("Roland")
    a.slash("add Brakka")
    payload = a.addon.Serialize(a.addon, a.lua.table_from({"t": "DATA", "v": 99, "d": a.lua.table()}))
    for _ in range(2):
        a.fire("CHAT_MSG_ADDON", "TheCaravan", payload, "PARTY", "Brakka-Ironvale")
    warnings = [p for p in a.prints if "newer version" in p]
    assert len(warnings) == 1


def test_bad_member_payload_is_dropped():
    a = Client("Roland")
    assert a.call("SanitizeMember", "nonsense") is None
    clean = to_py(a.call("SanitizeMember", a.lua.table_from({"level": 3, "name": "x" * 500, "evil": "y"}, recursive=True)))
    assert clean["level"] == 3 and len(clean["name"]) == 64 and "evil" not in clean


def test_name_normalisation():
    a = Client("Roland")
    assert a.call("Normalize", "Brakka") == "Brakka-Ironvale"
    assert a.call("Normalize", "Brakka-Other") == "Brakka-Other"
    assert a.call("NormalizeInput", "  bRAKKA ") == "Brakka-Ironvale"
    assert a.call("Normalize", "") is None


def test_forever_name_normalisation():
    a = Client("Roland", surname="Ironvale")
    assert a.addon.selfName == "Roland-Ironvale"
    assert a.call("Normalize", "Sudo Lock") == "Sudo-Lock"  # how addon message senders arrive
    assert a.call("Normalize", "Sudo-Lock") == "Sudo-Lock"
    assert a.call("Normalize", "Sudo") == "Sudo"  # no surname, no realm to add
    assert a.call("NormalizeInput", "  sudo lock ") == "Sudo-Lock"
    assert a.call("NormalizeInput", "sudo-lock") == "Sudo-Lock"
    assert a.call("NormalizeInput", "sudo") == "Sudo"


def test_forever_party_members_see_each_other():
    # The live client: surnames instead of realms, senders "Name Surname", own messages echoed back.
    a, b = Client("Roland", surname="Ironvale"), Client("Sudo", surname="Lock")
    a.set_group(b)
    b.set_group(a)
    a.slash("addparty")
    b.slash("addparty")
    run([a, b], 20, echo=True)
    assert to_py(a.call("RosterNames")) == ["Sudo-Lock"]
    assert to_py(b.call("RosterNames")) == ["Roland-Ironvale"]
    assert a.member("Sudo-Lock")["level"] == 14
    assert b.member("Roland-Ironvale")["level"] == 14
    assert to_py(a.addon.unlisted) == {} and to_py(b.addon.unlisted) == {}
    assert a.errors == [] and b.errors == []


def test_forever_friends_added_by_typed_name():
    a, b = Client("Roland", surname="Ironvale"), Client("Sudo", surname="Lock")
    a.set_group(b)
    b.set_group(a)
    a.slash("add sudo lock")
    b.slash("add Roland Ironvale")
    run([a, b], 20, echo=True)
    assert a.member("Sudo-Lock")["level"] == 14
    assert b.member("Roland-Ironvale")["level"] == 14


def test_roster_add_remove_and_list():
    a = Client("Roland")
    a.slash("add Brakka")
    a.slash("add Roland")  # yourself: ignored
    assert to_py(a.call("RosterNames")) == ["Brakka-Ironvale"]
    a.slash("remove brakka")
    assert to_py(a.call("RosterNames")) == {}


def test_upcoming_sessions_skip_finished_ones_and_sort():
    now = 1794800000 + 100
    schedule = {"version": 1, "generated_at": now, "sessions": {
        1: {"id": 2, "title": "Later", "start": now + 7200, "duration": 60},
        2: {"id": 1, "title": "Finished", "start": now - 7200, "duration": 60},
        3: {"id": 3, "title": "Running", "start": now - 600, "duration": 60},
    }}
    a = Client("Roland", schedule=schedule)
    titles = [s["title"] for s in to_py(a.call("UpcomingSessions"))]
    assert titles == ["Running", "Later"]


def test_login_announces_a_session_within_a_day():
    now = 1794800000 + 100
    schedule = {"sessions": {1: {"title": "Deadmines run", "start": now + 3 * 3600, "duration": 120}}}
    a = Client("Roland", schedule=schedule)
    run([a], 12)
    assert any("Deadmines run" in p and "in 2h" in p for p in a.prints)


def test_window_renders_both_tabs_without_errors():
    now = 1794800000 + 100
    schedule = {"generated_at": now, "sessions": {1: {"title": "Raid night", "start": now + 600, "duration": 120,
                                                      "going": {1: "Arda"}, "late": {1: "Bo"}, "out": {}}}}
    a = Client("Roland", schedule=schedule)
    a.slash("add Brakka")
    run([a], 6)
    a.slash("")
    a.call("ShowTab", "sessions")
    a.call("ShowTab", "group")
    a.slash("")
    assert a.errors == []


def test_saved_data_round_trips_into_a_snapshot():
    a, b = Client("Roland"), Client("Brakka")
    a.set_group(b)
    b.set_group(a)
    a.slash("addparty")
    b.slash("addparty")
    run([a, b], 20)
    sv_text = "TheCaravanDB = " + to_lua(to_py(a.g.TheCaravanDB)) + "\n"
    snap = snapshot_from_savedvariables(parse_savedvariables(sv_text), exported_at=1)
    assert snap["source"] == "Roland-Ironvale"
    assert set(snap["members"]) == {"Roland-Ironvale", "Brakka-Ironvale"}
    brakka = snap["members"]["Brakka-Ironvale"]
    assert brakka["level"] == 14 and brakka["class"] == "WARRIOR"
    assert brakka["professions"][0] == {"name": "Mining", "rank": 52, "max": 75}
    assert {"slot": 1, "item_id": 7413, "ilvl": 15} in brakka["gear"]


def test_addon_loads_the_file_the_sync_app_writes(tmp_path):
    now = 1794800000 + 100
    path = tmp_path / "TheCaravan.lua"
    path.write_text('TheCaravanDB = {\n["roster"] = {\n["bo-ironvale"] = "Bo-Ironvale",\n},\n}\n')
    write_schedule(path, {"version": 1, "generated_at": now, "sessions": [
        {"id": 4, "title": 'Ragefire "RFC" run', "start": now + 3600, "duration": 90,
         "going": ["Árda"], "late": [], "out": []}]})
    a = Client("Roland", sv_text=path.read_bytes().decode("latin-1"))
    sessions = to_py(a.call("UpcomingSessions"))
    assert sessions[0]["title"] == 'Ragefire "RFC" run'
    assert sessions[0]["going"] == ["Árda".encode("utf-8").decode("latin-1")]  # raw UTF-8 bytes, as WoW sees them
    assert to_py(a.call("RosterNames")) == ["Bo-Ironvale"]
