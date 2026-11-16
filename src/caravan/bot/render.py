"""Discord message text and embeds."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import discord

from .db import Attendee, Availability, Order, Session, Snapshot
from .gamedata import DungeonFit, Recap, RecipeMatch, short
from .planner import Suggestion
from .timeparse import WEEKDAYS

CARAVAN_COLOUR = discord.Colour.from_rgb(201, 145, 64)
RSVP_LABELS = {"going": "In", "late": "Late", "out": "Out"}
RSVP_EMOJI = {"going": "✅", "late": "⏰", "out": "❌"}


def ts(epoch: int, style: str = "F") -> str:
    return f"<t:{epoch}:{style}>"


def clock(minutes: int) -> str:
    minutes %= 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def duration(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    if not h:
        return f"{m}m"
    return f"{h}h{m:02d}" if m else f"{h}h"


def session_embed(session: Session, rsvps: dict[str, list[Attendee]]) -> discord.Embed:
    title = f"🐫 {session.title}"
    if session.cancelled:
        title = f"~~{session.title}~~ (cancelled)"
    embed = discord.Embed(
        title=title,
        description=f"{ts(session.start_ts)} · {ts(session.start_ts, 'R')} · {duration(session.duration_min)}",
        colour=discord.Colour.dark_grey() if session.cancelled else CARAVAN_COLOUR,
    )
    for status in ("going", "late", "out"):
        people = rsvps.get(status, [])
        names = ", ".join(a.display_name for a in people) or "—"
        embed.add_field(name=f"{RSVP_EMOJI[status]} {RSVP_LABELS[status]} ({len(people)})", value=names, inline=True)
    embed.set_footer(text=f"Session #{session.id}")
    return embed


def session_line(session: Session, rsvps: dict[str, list[Attendee]]) -> str:
    going = len(rsvps["going"]) + len(rsvps["late"])
    return f"**#{session.id} {session.title}** · {ts(session.start_ts)} ({ts(session.start_ts, 'R')}) · {going} coming"


def reminder_text(session: Session, rsvps: dict[str, list[Attendee]], jump_url: str | None) -> str:
    mentions = " ".join(f"<@{a.user_id}>" for a in rsvps["going"] + rsvps["late"])
    link = f" ({jump_url})" if jump_url else ""
    text = f"⏰ **{session.title}** starts {ts(session.start_ts, 'R')}{link}."
    return f"{text} {mentions}" if mentions else f"{text} Nobody has RSVP'd yet."


def availability_lines(rules: list[Availability], names: dict[int, str], tzs: dict[int, str], default_tz: str) -> str:
    if not rules:
        return "No availability set yet. Use `/availability add`."
    lines = []
    current = None
    for r in rules:
        if r.user_id != current:
            current = r.user_id
            lines.append(f"**{names.get(r.user_id, r.user_id)}** ({tzs.get(r.user_id, default_tz)})")
        lines.append(f"  {WEEKDAYS[r.weekday]} {clock(r.start_min)}–{clock(r.end_min)}")
    return "\n".join(lines)


def suggestions_text(suggestions: list[Suggestion], names: dict[int, str], total: int, duration_min: int) -> str:
    if not suggestions:
        return "No time works for anyone yet. Ask everyone to add availability with `/availability add`."
    who_set = "1 person has" if total == 1 else f"{total} people have"
    lines = [f"Best {duration(duration_min)} windows ({who_set} set availability):"]
    for s in suggestions:
        epoch = int(s.start.timestamp())
        who = ", ".join(names.get(u, str(u)) for u in s.user_ids)
        lines.append(f"• {ts(epoch)} — {len(s.user_ids)}/{total}: {who}")
    lines.append("Book one with `/session add`.")
    return "\n".join(lines)


def _member_line(name: str, m: dict[str, Any]) -> str:
    cls = (m.get("class") or "").title()
    parts = [f"**{name.split('-')[0]}** {m.get('level', '?')} {m.get('race') or ''} {cls}".rstrip()]
    if m.get("zone"):
        parts.append(m["zone"])
    if m.get("ilvl") is not None:
        parts.append(f"iLvl {m['ilvl']}")
    profs = ", ".join(f"{p['name']} {p['rank']}" for p in m.get("professions", []) if p.get("name"))
    if profs:
        parts.append(profs)
    if m.get("updated_at"):
        parts.append(f"seen {ts(m['updated_at'], 'R')}")
    return " · ".join(parts)


def group_embed(snapshot: Snapshot | None) -> discord.Embed:
    embed = discord.Embed(title="🐫 The Caravan", colour=CARAVAN_COLOUR)
    if snapshot is None:
        embed.description = "No game data yet. It arrives after the sync app uploads a SavedVariables snapshot."
        return embed
    members = snapshot.payload.get("members", {})
    ordered = sorted(members.items(), key=lambda kv: (-(kv[1].get("level") or 0), kv[0]))
    embed.description = "\n".join(_member_line(n, m) for n, m in ordered) or "The snapshot has no members."
    embed.set_footer(text="Snapshot from the last logout or /reload")
    embed.timestamp = datetime.fromtimestamp(snapshot.received_at, timezone.utc)
    return embed


# Phase 4: game data ------------------------------------------------------------

QUALITY_EMOJI = {3: "🔵", 4: "🟣", 5: "🟠", 6: "🟡", 7: "🩵"}


def _fmt_level(value: float) -> str:
    return f"{value:g}"


def level_gap_embed(member: str, levels: dict[str, int], gap: float, threshold: int) -> discord.Embed:
    others = sorted(((n, lv) for n, lv in levels.items() if n != member), key=lambda kv: (-kv[1], kv[0]))
    embed = discord.Embed(
        title=f"📈 {short(member)} is pulling ahead",
        description=(
            f"**{short(member)}** is level {levels[member]}, {_fmt_level(gap)} levels above the rest of the "
            f"group (alert above {threshold}).\n"
            + " · ".join(f"{short(n)} {lv}" for n, lv in others)
        ),
        colour=CARAVAN_COLOUR,
    )
    embed.set_footer(text="From the latest game snapshot")
    return embed


def _dungeon_line(fit: DungeonFit, faction: str | None) -> str:
    d = fit.dungeon
    notes = []
    if d.territory and faction and d.territory != faction:
        notes.append(f"in {d.territory} territory")
    if d.players != 5:
        notes.append(f"{d.players} players")
    if d.source != "blizzard":
        notes.append("range unconfirmed")
    line = f"{'✅' if fit.everyone else '➖'} **{d.name}** {d.low}–{d.high} · {d.zone}"
    if notes:
        line += f" ({', '.join(notes)})"
    if fit.under:
        line += f"\n  too low: {', '.join(short(n) for n in fit.under)}"
    if fit.over:
        line += f"\n  too high: {', '.join(short(n) for n in fit.over)}"
    return line


def dungeons_embed(fits: list[DungeonFit], levels: dict[str, int], faction: str | None, title: str) -> discord.Embed:
    embed = discord.Embed(title=title, colour=CARAVAN_COLOUR)
    if not levels:
        embed.description = "No levels yet. They arrive with the first game snapshot, or pass `level`."
        return embed
    who = " · ".join(f"{short(n)} {lv}" for n, lv in sorted(levels.items(), key=lambda kv: (-kv[1], kv[0])))
    body = "\n".join(_dungeon_line(f, faction) for f in fits) or "No dungeon covers these levels."
    embed.description = f"{who}\n\n{body}"
    embed.set_footer(text="✅ everyone in range · ranges from Blizzard and Forever community sites")
    return embed


def crafters_text(match: RecipeMatch) -> str:
    return ", ".join(
        f"{short(c.member)} ({c.profession}{f' {c.rank}' if c.rank is not None else ''})" for c in match.crafters
    )


def craft_text(query: str, matches: list[RecipeMatch], without_recipes: list[str]) -> str:
    if matches:
        lines = [f"**{m.name}**: {crafters_text(m)}" for m in matches]
    else:
        lines = [f"Nobody in the group knows a recipe matching “{query}”."]
    if without_recipes:
        lines.append(
            f"-# No recipes yet from {', '.join(without_recipes)}: open each profession window once in game."
        )
    return "\n".join(lines)


def order_line(order: Order, names: dict[int, str], matches: list[RecipeMatch]) -> str:
    who = names.get(order.requested_by, f"<@{order.requested_by}>")
    text = f"**#{order.id}** {order.quantity}× {order.item} for {who}"
    if order.note:
        text += f" ({order.note})"
    exact = [m for m in matches if m.name.casefold() == order.item.casefold()]
    if exact:
        text += f" · can craft: {crafters_text(exact[0])}"
    return text


def recap_embed(session: Session, recap: Recap) -> discord.Embed:
    embed = discord.Embed(
        title=f"📜 Recap: {session.title}",
        description=f"{ts(session.start_ts)}" + (f"\nPlayed: {', '.join(recap.players)}" if recap.players else ""),
        colour=CARAVAN_COLOUR,
    )
    if recap.levels:
        embed.add_field(
            name="🎉 Levels",
            value="\n".join(f"{g.member} {g.start} → {g.end}" for g in recap.levels)[:1024],
            inline=False,
        )
    if recap.runs:
        lines = []
        for r in recap.runs:
            if r.cleared:
                state = "cleared ✅"
            elif r.boss_count:
                state = f"{len(r.bosses)}/{r.boss_count} bosses"
            else:
                state = f"{len(r.bosses)} boss{'es' if len(r.bosses) != 1 else ''}"
            line = f"**{r.instance}** · {state} · {', '.join(r.members)}"
            if r.bosses and not r.cleared:
                line += f"\n  down: {', '.join(r.bosses)}"
            lines.append(line)
        embed.add_field(name="🏰 Dungeons", value="\n".join(lines)[:1024], inline=False)
    if recap.loot:
        embed.add_field(
            name="💎 Loot",
            value="\n".join(
                f"{QUALITY_EMOJI.get(i.quality or 0, '▫️')} {i.member}: [{i.name}]" for i in recap.loot
            )[:1024],
            inline=False,
        )
    embed.set_footer(text=f"Session #{session.id} · from the game snapshot; updates if a later one arrives")
    return embed
