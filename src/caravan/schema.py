"""Data formats shared by the addon, the sync app and the bot.

Snapshot: the group's character data, read from the addon's SavedVariables
and posted to the bot. Schedule: upcoming sessions and RSVPs, served by the
bot and written into the SavedVariables file for the addon to show.
"""

from __future__ import annotations

import json
from typing import Any

from .luadata import as_list

SCHEMA_VERSION = 1
ADDON_NAME = "TheCaravan"
SV_FILENAME = f"{ADDON_NAME}.lua"
DB_VAR = "TheCaravanDB"
SCHEDULE_VAR = "TheCaravanSchedule"
RSVP_STATUSES = ("going", "late", "out")


def _num(v: Any) -> int | float | None:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _int(v: Any) -> int | None:
    n = _num(v)
    return int(n) if n is not None else None


def _str(v: Any, limit: int = 64) -> str | None:
    return v[:limit] if isinstance(v, str) else None


def _level_log(v: Any) -> list[dict[str, Any]]:
    out = []
    for e in as_list(v):
        if isinstance(e, dict) and _int(e.get("l")) is not None and _int(e.get("ts")) is not None:
            out.append({"level": _int(e["l"]), "at": _int(e["ts"])})
    return out


def _loot(v: Any) -> list[dict[str, Any]]:
    out = []
    for e in as_list(v):
        if isinstance(e, dict) and _int(e.get("id")) and _str(e.get("n")):
            out.append({"item_id": _int(e["id"]), "name": _str(e["n"]), "quality": _int(e.get("q")),
                        "at": _int(e.get("ts"))})
    return out


def _runs(v: Any) -> list[dict[str, Any]]:
    out = []
    for e in as_list(v):
        if isinstance(e, dict) and _str(e.get("n")) and _int(e.get("ts")) is not None:
            out.append({
                "instance": _str(e["n"]),
                "instance_id": _int(e.get("id")),
                "started_at": _int(e["ts"]),
                "ended_at": _int(e.get("te")),
                "bosses": [b for b in (_str(x) for x in as_list(e.get("b"))) if b],
                "boss_count": _int(e.get("nb")),
                "cleared": e.get("done") is True,
            })
    return out


def recipes_from_lua(entry: Any) -> dict[str, list[str]]:
    """{profession: [recipe names]} from one db.recipes entry."""
    profs = entry.get("p") if isinstance(entry, dict) else None
    if not isinstance(profs, dict):
        return {}
    return {
        prof[:64]: [n for n in (_str(x) for x in as_list(names)) if n]
        for prof, names in profs.items()
        if isinstance(prof, str)
    }


def member_from_lua(data: dict[str, Any], recipes: Any = None) -> dict[str, Any]:
    """Convert one member table written by the addon into snapshot form."""
    profs = []
    for p in as_list(data.get("profs")):
        if isinstance(p, dict) and _str(p.get("name")):
            profs.append({"name": _str(p["name"]), "rank": _int(p.get("rank")), "max": _int(p.get("max"))})
    gear = []
    for g in as_list(data.get("gear")):
        if isinstance(g, dict) and _int(g.get("id")):
            gear.append({"slot": _int(g.get("s")), "item_id": _int(g["id"]), "ilvl": _int(g.get("il"))})
    ilvl = _num(data.get("ilvl"))
    return {
        "name": _str(data.get("name")),
        "realm": _str(data.get("realm")),
        "class": _str(data.get("class")),
        "race": _str(data.get("race")),
        "faction": _str(data.get("faction"), 16),
        "level": _int(data.get("level")),
        "xp": _int(data.get("xp")),
        "xp_max": _int(data.get("xpMax")),
        "zone": _str(data.get("zone"), 128),
        "professions": profs,
        "ilvl": round(ilvl, 1) if ilvl is not None else None,
        "gear": gear,
        "recipes": recipes_from_lua(recipes),
        "level_log": _level_log(data.get("lv")),
        "loot": _loot(data.get("loot")),
        "runs": _runs(data.get("runs")),
        "updated_at": _int(data.get("ts")),
    }


def snapshot_from_savedvariables(sv: dict[str, Any], exported_at: int) -> dict[str, Any]:
    db = sv.get(DB_VAR)
    if not isinstance(db, dict):
        raise ValueError(f"{DB_VAR} not found in the SavedVariables file")
    members = db.get("members")
    if not isinstance(members, dict):
        members = {}
    recipes = db.get("recipes")
    if not isinstance(recipes, dict):
        recipes = {}
    return {
        "version": SCHEMA_VERSION,
        "exported_at": exported_at,
        "source": _str(db.get("lastCharacter")),
        "members": {
            name: member_from_lua(data, recipes.get(name))
            for name, data in members.items()
            if isinstance(name, str) and isinstance(data, dict)
        },
    }


def validate_snapshot(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError("snapshot must be a JSON object")
    if obj.get("version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported snapshot version {obj.get('version')!r}")
    if not isinstance(obj.get("members"), dict):
        raise ValueError("snapshot.members must be an object")
    if not isinstance(obj.get("exported_at"), int):
        raise ValueError("snapshot.exported_at must be an integer")
    return obj


def _canonical(value: Any) -> Any:
    """Lua has one table type, so empty and integer-keyed tables compare as lists."""
    if isinstance(value, dict):
        if not value or all(isinstance(k, int) and not isinstance(k, bool) for k in value):
            return [_canonical(v) for v in as_list(value)]
        return {str(k): _canonical(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_canonical(v) for v in value]
    return value


def schedule_signature(schedule: Any) -> str:
    """Identity of a schedule's content, ignoring when it was generated and
    which player's addon passed it on."""
    if not isinstance(schedule, dict):
        return "[]"
    content = {k: v for k, v in schedule.items() if k not in ("generated_at", "from")}
    content.setdefault("sessions", [])
    return json.dumps(_canonical(content), sort_keys=True, ensure_ascii=False)
