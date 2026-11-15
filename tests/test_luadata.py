import math

import pytest

from caravan.luadata import (
    LuaParseError, as_list, parse_savedvariables, parse_statements, read_savedvariables,
    replace_statement, to_lua,
)

# Written the way the WoW client writes SavedVariables.
WOW_FILE = (
    "\nTheCaravanDB = {\n"
    "[\"members\"] = {\n"
    "[\"Roland-Ironvale\"] = {\n"
    "[\"level\"] = 14,\n"
    "[\"ilvl\"] = 14.5,\n"
    "[\"name\"] = \"Roland\",\n"
    "[\"zone\"] = \"Dun Morogh \\\"North\\\"\\n\",\n"
    "[\"profs\"] = {\n"
    "{\n"
    "[\"name\"] = \"Mining\",\n"
    "[\"rank\"] = 52,\n"
    "}, -- [1]\n"
    "},\n"
    "[\"gear\"] = {\n"
    "},\n"
    "[\"ok\"] = true,\n"
    "},\n"
    "},\n"
    "}\n"
    "TheCaravanSchedule = nil\n"
)


def test_parses_wow_formatted_file():
    sv = parse_savedvariables(WOW_FILE)
    roland = sv["TheCaravanDB"]["members"]["Roland-Ironvale"]
    assert roland["level"] == 14 and roland["ilvl"] == 14.5 and roland["ok"] is True
    assert roland["zone"] == 'Dun Morogh "North"\n'
    assert roland["profs"] == [{"name": "Mining", "rank": 52}]
    assert roland["gear"] == {}
    assert sv["TheCaravanSchedule"] is None


def test_parses_lua_syntax_variants():
    sv = parse_savedvariables("X = { a = 1, 'two'; [3] = -0x10, n = 1e3, s = '\\65\\066', t = { }, }")
    assert sv["X"] == {"a": 1, 1: "two", 3: -16, "n": 1000.0, "s": "AB", "t": {}}


def test_decodes_utf8_and_byte_escapes():
    raw = 'N = "Æ\\195\\134"'.encode("utf-8").decode("latin-1")
    assert parse_savedvariables(raw)["N"] == "ÆÆ"


def test_reports_errors_with_line_numbers():
    with pytest.raises(LuaParseError, match="line 2"):
        parse_savedvariables('A = 1\nB = "unterminated\n')
    with pytest.raises(LuaParseError):
        parse_savedvariables("A = function() end")


def test_to_lua_round_trips():
    value = {"s": 'quote " back \\ nl \n tab \t Ævar', "n": -3, "f": 2.5, "b": False,
             "list": [1, "two", {"x": None}], "empty": {}, 7: "seven"}
    parsed = parse_savedvariables("V = " + to_lua(value))["V"]
    assert parsed["s"] == value["s"]
    assert parsed["list"][:2] == [1, "two"]
    assert parsed[7] == "seven" and parsed["b"] is False and parsed["f"] == 2.5


def test_to_lua_rejects_unwritable_values():
    with pytest.raises(ValueError):
        to_lua(math.inf)
    with pytest.raises(TypeError):
        to_lua({True: 1})
    with pytest.raises(TypeError):
        to_lua(object())


def test_replace_statement_keeps_other_bytes():
    text = WOW_FILE.replace("Roland", "Rólánd")
    raw = text.encode("utf-8").decode("latin-1")
    new = replace_statement(raw, "TheCaravanSchedule", {"sessions": [{"id": 1}]})
    db_end = parse_statements(raw)[0].end
    assert new[:db_end] == raw[:db_end]
    assert parse_savedvariables(new)["TheCaravanSchedule"] == {"sessions": [{"id": 1}]}


def test_replace_statement_appends_when_missing():
    new = replace_statement("A = 1", "B", [1, 2])
    assert parse_savedvariables(new) == {"A": 1, "B": [1, 2]}
    assert parse_savedvariables(replace_statement("", "B", 3)) == {"B": 3}


def test_as_list_normalises_arrays():
    assert as_list(None) == [] and as_list({}) == [] and as_list([1]) == [1]
    assert as_list({2: "b", 1: "a", "x": 0}) == ["a", "b"]
    assert as_list("nope") == []


def test_read_savedvariables(tmp_path):
    path = tmp_path / "TheCaravan.lua"
    path.write_bytes(WOW_FILE.encode("utf-8"))
    assert "TheCaravanDB" in read_savedvariables(path)
