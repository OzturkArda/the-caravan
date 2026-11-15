from caravan.bot.dungeons import BLIZZARD, DUNGEONS, REPORTED
from caravan.bot.gamedata import (
    active_levels, build_recap, find_recipes, group_faction, level_gaps, members_without_recipes, recipe_names,
    suggest_dungeons,
)

T0 = 1_800_000_000


def test_dungeon_table_is_sane():
    names = [d.name for d in DUNGEONS]
    assert len(names) == len(set(names)) == 35
    assert all(1 <= d.low <= d.high <= 60 and d.source in (BLIZZARD, REPORTED) for d in DUNGEONS)
    new = {d.name: (d.low, d.high) for d in DUNGEONS if d.source == BLIZZARD}
    assert len(new) == 9 and new["Hall of Thanes"] == (13, 18) and new["Excavation Site: Wetlands"] == (24, 29)


def test_active_levels_skip_stale_and_unknown():
    members = {
        "A-R": {"level": 20, "updated_at": T0},
        "B-R": {"level": 18, "updated_at": T0 - 40 * 86400},
        "C-R": {"level": 17},
        "D-R": {"level": None},
    }
    assert active_levels(members, T0) == {"A-R": 20, "C-R": 17}


def test_level_gaps_use_the_median_of_everyone_else():
    assert level_gaps({"A": 20, "B": 15, "C": 15}, 3) == {"A": 5}
    assert level_gaps({"A": 20, "B": 17, "C": 15}, 3) == {"A": 4}  # 20 - median(17, 15)
    assert level_gaps({"A": 18, "B": 17, "C": 15}, 3) == {}
    assert level_gaps({"A": 20, "B": 15}, 3) == {"A": 5}
    assert level_gaps({"A": 20}, 3) == {}
    assert level_gaps({"A": 20, "B": 10}, 0) == {}


def test_group_faction():
    assert group_faction({"a": {"faction": "Horde"}, "b": {"faction": "Horde"}, "c": {}}) == "Horde"
    assert group_faction({"a": {}}) is None


def test_dungeon_suggestions_rank_full_fits_first():
    fits = suggest_dungeons({"Roland": 19, "Bo": 17}, "Alliance")
    names = [f.dungeon.name for f in fits]
    assert names[0] == "Wailing Caverns" and fits[0].everyone  # 15-24, both in range
    assert "Ragefire Chasm" not in names  # inside Orgrimmar
    hall = next(f for f in fits if f.dungeon.name == "Hall of Thanes")
    assert hall.over == ("Roland",) and not hall.everyone
    assert all(f.dungeon.high >= 17 and f.dungeon.low <= 19 for f in fits)
    horde = [f.dungeon.name for f in suggest_dungeons({"x": 14}, "Horde", limit=20)]
    assert "Ragefire Chasm" in horde and "The Stockade" not in horde
    assert suggest_dungeons({}, None) == []


MEMBERS = {
    "Roland-Ironvale": {
        "professions": [{"name": "Blacksmithing", "rank": 52}],
        "recipes": {"Blacksmithing": ["Copper Bracers", "Copper Chain Pants", "Rough Sharpening Stone"]},
    },
    "Bo-Ironvale": {
        "professions": [{"name": "Tailoring", "rank": 70}],
        "recipes": {"Tailoring": ["Linen Bag", "Brown Linen Pants"], "Cooking": ["Copper Bracers"]},
    },
    "Cy-Ironvale": {"professions": []},
}


def test_find_recipes_exact_then_words():
    exact = find_recipes(MEMBERS, "copper bracers")
    assert len(exact) == 1 and exact[0].name == "Copper Bracers"
    assert [(c.member, c.profession, c.rank) for c in exact[0].crafters] == [
        ("Bo-Ironvale", "Cooking", None), ("Roland-Ironvale", "Blacksmithing", 52),
    ]
    assert [m.name for m in find_recipes(MEMBERS, "pants")] == ["Brown Linen Pants", "Copper Chain Pants"]
    assert [m.name for m in find_recipes(MEMBERS, "linen pa")] == ["Brown Linen Pants"]
    assert find_recipes(MEMBERS, "mithril") == [] and find_recipes(MEMBERS, "  ") == []


def test_recipe_names_and_missing_members():
    assert recipe_names(MEMBERS, "")[:2] == ["Brown Linen Pants", "Copper Bracers"]
    assert recipe_names(MEMBERS, "lin") == ["Linen Bag", "Brown Linen Pants"]
    assert members_without_recipes(MEMBERS) == ["Cy"]


def test_recap_counts_only_the_session_window():
    start, end = T0, T0 + 4 * 3600
    members = {
        "Roland-Ironvale": {
            "updated_at": end - 60,
            "level_log": [{"level": 15, "at": T0 - 86400}, {"level": 16, "at": T0 + 600}, {"level": 17, "at": T0 + 7200}],
            "loot": [
                {"item_id": 1, "name": "Old Sword", "quality": 4, "at": T0 - 86400},
                {"item_id": 2, "name": "Staff of Westfall", "quality": 3, "at": T0 + 3000},
                {"item_id": 3, "name": "Cruel Barb", "quality": 4, "at": T0 + 5000},
            ],
            "runs": [{"instance": "The Deadmines", "started_at": T0 + 1000, "ended_at": T0 + 6000,
                      "bosses": ["Rhahk'Zor", "Edwin VanCleef"], "boss_count": 6, "cleared": True}],
        },
        "Bo-Ironvale": {
            "updated_at": end - 120,
            "runs": [
                {"instance": "The Deadmines", "started_at": T0 + 1100, "ended_at": T0 + 6000,
                 "bosses": ["Rhahk'Zor", "Sneed"], "boss_count": 6, "cleared": False},
                {"instance": "Shadowfang Keep", "started_at": T0 + 7000, "ended_at": T0 + 9000,
                 "bosses": ["Rethilgore"], "boss_count": None, "cleared": False},
            ],
        },
        "Cy-Ironvale": {"updated_at": T0 - 5 * 86400, "level_log": [{"level": 30, "at": T0 - 5 * 86400}]},
    }
    recap = build_recap(members, start, end)
    assert recap.players == ("Bo", "Roland")
    assert [(g.member, g.start, g.end) for g in recap.levels] == [("Roland", 15, 17)]
    dm, sfk = recap.runs
    assert dm.instance == "The Deadmines" and dm.cleared and dm.boss_count == 6
    assert set(dm.members) == {"Roland", "Bo"} and set(dm.bosses) == {"Rhahk'Zor", "Edwin VanCleef", "Sneed"}
    assert sfk.members == ("Bo",) and sfk.boss_count is None and not sfk.cleared
    assert [i.name for i in recap.loot] == ["Cruel Barb", "Staff of Westfall"]
    assert not recap.empty
    assert recap.signature() == build_recap(members, start, end).signature()
    assert build_recap(members, T0 + 10 * 86400, T0 + 11 * 86400).empty
