"""What the bot works out from a game snapshot: level gaps, dungeons that fit,
who can craft what, and what happened during a session.

`members` is always the snapshot's {"Name-Realm": member} mapping
(see caravan.schema.member_from_lua).
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from .dungeons import DUNGEONS, Dungeon

Members = dict[str, dict[str, Any]]

STALE_DAYS = 30


def short(name: str) -> str:
    return name.split("-")[0]


def character_name(text: str, known: list[str]) -> str | None:
    """A typed character name as "Name-Realm", or None if it can't be told.

    `known` are the snapshot's member names, whose spelling wins. Without a
    realm, the name must match exactly one known character. WoW Forever names
    are "Name Surname", which the addon keys as "Name-Surname".
    """
    text = text.strip()
    if "-" not in text and " " in text:
        first, _, surname = text.partition(" ")
        surname = surname.replace(" ", "")
        text = f"{first}-{surname[:1].upper()}{surname[1:].lower()}"
    by_lower = {k.lower(): k for k in known}
    if "-" in text:
        if text.lower() in by_lower:
            return by_lower[text.lower()]
        name, _, realm = text.partition("-")
        name, realm = name.strip(), realm.replace(" ", "")
        if not name or not realm or " " in name or "-" in realm:
            return None
        return name[:1].upper() + name[1:].lower() + "-" + realm
    matches = [k for k in known if short(k).lower() == text.lower()]
    return matches[0] if len(matches) == 1 else None


def active_levels(members: Members, now: int, stale_days: int = STALE_DAYS) -> dict[str, int]:
    """{name: level} for members seen in the last `stale_days` (unknown age counts as active)."""
    cutoff = now - stale_days * 86400
    out = {}
    for name, m in members.items():
        level = m.get("level")
        updated = m.get("updated_at")
        if isinstance(level, int) and (updated is None or updated >= cutoff):
            out[name] = level
    return out


def group_faction(members: Members) -> str | None:
    counts = Counter(m.get("faction") for m in members.values() if m.get("faction") in ("Alliance", "Horde"))
    return counts.most_common(1)[0][0] if counts else None


# Level gaps -----------------------------------------------------------------


def level_gaps(levels: dict[str, int], threshold: int) -> dict[str, float]:
    """Members more than `threshold` levels above the median of everyone else."""
    if threshold <= 0 or len(levels) < 2:
        return {}
    out = {}
    for name, level in levels.items():
        gap = level - statistics.median(v for n, v in levels.items() if n != name)
        if gap > threshold:
            out[name] = gap
    return out


# Dungeons ---------------------------------------------------------------------


@dataclass(frozen=True)
class DungeonFit:
    dungeon: Dungeon
    under: tuple[str, ...]
    over: tuple[str, ...]

    @property
    def everyone(self) -> bool:
        return not self.under and not self.over


def suggest_dungeons(
    levels: dict[str, int], faction: str | None, dungeons: tuple[Dungeon, ...] = DUNGEONS, limit: int = 8,
) -> list[DungeonFit]:
    """Dungeons whose range overlaps the group's levels, best fits first."""
    if not levels:
        return []
    low, high = min(levels.values()), max(levels.values())
    fits = []
    for d in dungeons:
        if d.in_city and faction and d.territory != faction:
            continue
        if d.high < low or d.low > high:
            continue
        under = tuple(sorted(n for n, lv in levels.items() if lv < d.low))
        over = tuple(sorted(n for n, lv in levels.items() if lv > d.high))
        fits.append(DungeonFit(d, under, over))
    def rank(f: DungeonFit) -> tuple[int, bool, int, str]:
        far = bool(faction and f.dungeon.territory and f.dungeon.territory != faction)
        return len(f.under) + len(f.over), far, f.dungeon.low, f.dungeon.name

    fits.sort(key=rank)
    return fits[:limit]


# Crafting ------------------------------------------------------------------------


@dataclass(frozen=True)
class Crafter:
    member: str
    profession: str
    rank: int | None


@dataclass(frozen=True)
class RecipeMatch:
    name: str
    crafters: tuple[Crafter, ...]


def recipe_index(members: Members) -> dict[str, RecipeMatch]:
    """{lowercase recipe name: who knows it}."""
    found: dict[str, tuple[str, list[Crafter]]] = {}
    for member, m in sorted(members.items()):
        ranks = {p.get("name"): p.get("rank") for p in m.get("professions", []) if isinstance(p, dict)}
        for prof, names in (m.get("recipes") or {}).items():
            for recipe in names:
                key = recipe.casefold()
                entry = found.setdefault(key, (recipe, []))
                entry[1].append(Crafter(member, prof, ranks.get(prof)))
    return {k: RecipeMatch(name, tuple(crafters)) for k, (name, crafters) in found.items()}


def find_recipes(members: Members, query: str, limit: int = 10) -> list[RecipeMatch]:
    """Recipes matching `query`: an exact name, or every word of it."""
    index = recipe_index(members)
    q = query.casefold().strip()
    if not q:
        return []
    if q in index:
        return [index[q]]
    words = q.split()
    hits = [k for k in index if all(w in k for w in words)]
    hits.sort(key=lambda k: (not k.startswith(q), k))
    return [index[k] for k in hits[:limit]]


def recipe_names(members: Members, current: str, limit: int = 25) -> list[str]:
    """Recipe names for autocomplete."""
    return [m.name for m in find_recipes(members, current, limit)] if current.strip() else sorted(
        m.name for m in recipe_index(members).values()
    )[:limit]


def members_without_recipes(members: Members) -> list[str]:
    return sorted(short(n) for n, m in members.items() if not m.get("recipes"))


# Session recaps ---------------------------------------------------------------------


@dataclass(frozen=True)
class LevelGain:
    member: str
    start: int
    end: int


@dataclass(frozen=True)
class RunSummary:
    instance: str
    members: tuple[str, ...]
    bosses: tuple[str, ...]
    boss_count: int | None
    cleared: bool


@dataclass(frozen=True)
class LootItem:
    member: str
    name: str
    quality: int | None
    at: int | None


@dataclass(frozen=True)
class Recap:
    players: tuple[str, ...] = ()
    levels: tuple[LevelGain, ...] = ()
    runs: tuple[RunSummary, ...] = ()
    loot: tuple[LootItem, ...] = field(default=())

    @property
    def empty(self) -> bool:
        return not (self.levels or self.runs or self.loot)

    def signature(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


def _within(at: Any, start: int, end: int) -> bool:
    return isinstance(at, int) and start <= at <= end


def build_recap(members: Members, start: int, end: int, loot_limit: int = 15) -> Recap:
    """Levels gained, dungeon runs and notable loot with timestamps in [start, end]."""
    players: set[str] = set()
    levels = []
    runs: dict[str, dict[str, Any]] = {}
    loot = []
    for name, m in sorted(members.items()):
        who = short(name)
        if _within(m.get("updated_at"), start, end):
            players.add(who)
        ups = [e["level"] for e in m.get("level_log", []) if _within(e.get("at"), start, end)]
        if ups:
            levels.append(LevelGain(who, min(ups) - 1, max(ups)))
            players.add(who)
        for r in m.get("runs", []):
            began, ended = r.get("started_at"), r.get("ended_at") or r.get("started_at")
            if not (isinstance(began, int) and isinstance(ended, int) and began <= end and ended >= start):
                continue
            players.add(who)
            entry = runs.setdefault(r["instance"], {"members": [], "bosses": [], "count": None, "cleared": False})
            if who not in entry["members"]:
                entry["members"].append(who)
            entry["bosses"] += [b for b in r.get("bosses", []) if b not in entry["bosses"]]
            if r.get("boss_count"):
                entry["count"] = max(entry["count"] or 0, r["boss_count"])
            entry["cleared"] = entry["cleared"] or bool(r.get("cleared"))
        for item in m.get("loot", []):
            if _within(item.get("at"), start, end):
                loot.append(LootItem(who, item["name"], item.get("quality"), item.get("at")))
                players.add(who)
    loot.sort(key=lambda i: (-(i.quality or 0), i.at or 0, i.member))
    return Recap(
        players=tuple(sorted(players)),
        levels=tuple(sorted(levels, key=lambda g: (-(g.end - g.start), g.member))),
        runs=tuple(
            RunSummary(name, tuple(e["members"]), tuple(e["bosses"]), e["count"], e["cleared"])
            for name, e in runs.items()
        ),
        loot=tuple(loot[:loot_limit]),
    )
