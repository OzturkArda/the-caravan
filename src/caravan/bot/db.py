"""SQLite storage for sessions, RSVPs, availability, game snapshots, crafting
orders, session recaps and level-gap alerts."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from ..schema import RSVP_STATUSES, SCHEMA_VERSION

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id      INTEGER PRIMARY KEY,
    display_name TEXT NOT NULL,
    tz           TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id     INTEGER NOT NULL,
    channel_id   INTEGER NOT NULL,
    message_id   INTEGER,
    event_id     INTEGER,
    title        TEXT NOT NULL,
    start_ts     INTEGER NOT NULL,
    duration_min INTEGER NOT NULL,
    created_by   INTEGER NOT NULL,
    cancelled    INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS rsvps (
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    user_id    INTEGER NOT NULL,
    status     TEXT NOT NULL CHECK (status IN ('going', 'late', 'out')),
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (session_id, user_id)
);
CREATE TABLE IF NOT EXISTS reminders_sent (
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    offset_min INTEGER NOT NULL,
    PRIMARY KEY (session_id, offset_min)
);
CREATE TABLE IF NOT EXISTS availability (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL,
    weekday   INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    start_min INTEGER NOT NULL CHECK (start_min BETWEEN 0 AND 1440),
    end_min   INTEGER NOT NULL CHECK (end_min BETWEEN 0 AND 1440)
);
CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at INTEGER NOT NULL,
    payload     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id   INTEGER NOT NULL,
    item         TEXT NOT NULL,
    quantity     INTEGER NOT NULL DEFAULT 1,
    note         TEXT,
    requested_by INTEGER NOT NULL,
    created_at   INTEGER NOT NULL,
    status       TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done', 'cancelled')),
    closed_by    INTEGER,
    closed_at    INTEGER
);
CREATE TABLE IF NOT EXISTS recaps (
    session_id INTEGER PRIMARY KEY REFERENCES sessions(id),
    message_id INTEGER,
    signature  TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS level_alerts (
    member     TEXT PRIMARY KEY,
    level      INTEGER NOT NULL,
    alerted_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS characters (
    name_key  TEXT PRIMARY KEY,      -- lower-case "name-realm"
    name      TEXT NOT NULL,         -- "Name-Realm"
    user_id   INTEGER NOT NULL,
    linked_at INTEGER NOT NULL
);
"""

# A game RSVP more than this far in the future (by the bot's clock) is ignored.
MAX_CLOCK_SKEW = 300


@dataclass(frozen=True)
class Session:
    id: int
    guild_id: int
    channel_id: int
    message_id: int | None
    event_id: int | None
    title: str
    start_ts: int
    duration_min: int
    created_by: int
    cancelled: bool

    @property
    def end_ts(self) -> int:
        return self.start_ts + self.duration_min * 60


@dataclass(frozen=True)
class Availability:
    id: int
    user_id: int
    weekday: int
    start_min: int
    end_min: int


@dataclass(frozen=True)
class Attendee:
    user_id: int
    display_name: str


@dataclass(frozen=True)
class Snapshot:
    id: int
    received_at: int
    payload: dict[str, Any]


@dataclass(frozen=True)
class Order:
    id: int
    channel_id: int
    item: str
    quantity: int
    note: str | None
    requested_by: int
    created_at: int
    status: str
    closed_by: int | None
    closed_at: int | None


@dataclass(frozen=True)
class LinkedCharacter:
    name: str
    user_id: int


@dataclass(frozen=True)
class GameRsvpResult:
    changed_sessions: set[int]   # sessions whose card needs refreshing
    unlinked: set[str]           # characters nobody has linked


@dataclass(frozen=True)
class RecapRecord:
    session_id: int
    message_id: int | None
    signature: str
    updated_at: int


def _session(row: sqlite3.Row) -> Session:
    return Session(
        id=row["id"], guild_id=row["guild_id"], channel_id=row["channel_id"],
        message_id=row["message_id"], event_id=row["event_id"], title=row["title"],
        start_ts=row["start_ts"], duration_min=row["duration_min"],
        created_by=row["created_by"], cancelled=bool(row["cancelled"]),
    )


class Store:
    def __init__(self, path: str) -> None:
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(_SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # users -----------------------------------------------------------------

    def upsert_user(self, user_id: int, display_name: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO users (user_id, display_name) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET display_name = excluded.display_name",
                (user_id, display_name),
            )

    def set_user_tz(self, user_id: int, display_name: str, tz: str) -> None:
        self.upsert_user(user_id, display_name)
        with self.conn:
            self.conn.execute("UPDATE users SET tz = ? WHERE user_id = ?", (tz, user_id))

    def user_tz(self, user_id: int) -> str | None:
        row = self.conn.execute("SELECT tz FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return row["tz"] if row else None

    def user_tzs(self) -> dict[int, str]:
        rows = self.conn.execute("SELECT user_id, tz FROM users WHERE tz IS NOT NULL")
        return {r["user_id"]: r["tz"] for r in rows}

    def display_names(self) -> dict[int, str]:
        return {r["user_id"]: r["display_name"] for r in self.conn.execute("SELECT * FROM users")}

    # linked characters -----------------------------------------------------

    def character_owner(self, name: str) -> int | None:
        row = self.conn.execute("SELECT user_id FROM characters WHERE name_key = ?", (name.lower(),)).fetchone()
        return row["user_id"] if row else None

    def link_character(self, name: str, user_id: int, now_ts: int) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO characters (name_key, name, user_id, linked_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(name_key) DO UPDATE SET name = excluded.name, user_id = excluded.user_id, "
                "linked_at = excluded.linked_at",
                (name.lower(), name, user_id, now_ts),
            )

    def unlink_character(self, name: str) -> bool:
        with self.conn:
            cur = self.conn.execute("DELETE FROM characters WHERE name_key = ?", (name.lower(),))
        return cur.rowcount > 0

    def characters(self, user_id: int | None = None) -> list[LinkedCharacter]:
        sql = "SELECT name, user_id FROM characters"
        args: tuple[Any, ...] = ()
        if user_id is not None:
            sql += " WHERE user_id = ?"
            args = (user_id,)
        rows = self.conn.execute(sql + " ORDER BY name_key", args)
        return [LinkedCharacter(r["name"], r["user_id"]) for r in rows]

    # sessions --------------------------------------------------------------

    def create_session(
        self, *, guild_id: int, channel_id: int, title: str, start_ts: int,
        duration_min: int, created_by: int,
    ) -> Session:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO sessions (guild_id, channel_id, title, start_ts, duration_min, created_by) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (guild_id, channel_id, title, start_ts, duration_min, created_by),
            )
        session = self.get_session(cur.lastrowid or 0)
        assert session is not None
        return session

    def get_session(self, session_id: int) -> Session | None:
        row = self.conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return _session(row) if row else None

    def set_session_message(self, session_id: int, message_id: int) -> None:
        with self.conn:
            self.conn.execute("UPDATE sessions SET message_id = ? WHERE id = ?", (message_id, session_id))

    def set_session_event(self, session_id: int, event_id: int) -> None:
        with self.conn:
            self.conn.execute("UPDATE sessions SET event_id = ? WHERE id = ?", (event_id, session_id))

    def cancel_session(self, session_id: int) -> bool:
        with self.conn:
            cur = self.conn.execute(
                "UPDATE sessions SET cancelled = 1 WHERE id = ? AND cancelled = 0", (session_id,)
            )
        return cur.rowcount == 1

    def upcoming_sessions(self, now_ts: int, limit: int = 10) -> list[Session]:
        rows = self.conn.execute(
            "SELECT * FROM sessions WHERE cancelled = 0 AND start_ts + duration_min * 60 > ? "
            "ORDER BY start_ts LIMIT ?",
            (now_ts, limit),
        )
        return [_session(r) for r in rows]

    def sessions_ended_between(self, start_ts: int, end_ts: int) -> list[Session]:
        """Sessions (not cancelled) whose scheduled end is in [start_ts, end_ts]."""
        rows = self.conn.execute(
            "SELECT * FROM sessions WHERE cancelled = 0 AND start_ts + duration_min * 60 BETWEEN ? AND ? "
            "ORDER BY start_ts",
            (start_ts, end_ts),
        )
        return [_session(r) for r in rows]

    def next_session_after(self, ts: int) -> Session | None:
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE cancelled = 0 AND start_ts > ? ORDER BY start_ts LIMIT 1", (ts,)
        ).fetchone()
        return _session(row) if row else None

    # rsvps -----------------------------------------------------------------

    def set_rsvp(self, session_id: int, user_id: int, status: str, now_ts: int) -> None:
        if status not in RSVP_STATUSES:
            raise ValueError(f"unknown RSVP status {status!r}")
        with self.conn:
            self.conn.execute(
                "INSERT INTO rsvps (session_id, user_id, status, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(session_id, user_id) DO UPDATE SET status = excluded.status, "
                "updated_at = excluded.updated_at",
                (session_id, user_id, status, now_ts),
            )

    def rsvps(self, session_id: int) -> dict[str, list[Attendee]]:
        out: dict[str, list[Attendee]] = {s: [] for s in RSVP_STATUSES}
        rows = self.conn.execute(
            "SELECT r.user_id, r.status, COALESCE(u.display_name, CAST(r.user_id AS TEXT)) AS name "
            "FROM rsvps r LEFT JOIN users u ON u.user_id = r.user_id "
            "WHERE r.session_id = ? ORDER BY r.updated_at",
            (session_id,),
        )
        for r in rows:
            out[r["status"]].append(Attendee(r["user_id"], r["name"]))
        return out

    def apply_game_rsvps(self, entries: list[dict[str, Any]], now_ts: int) -> GameRsvpResult:
        """Apply RSVPs clicked in the addon, as the Discord user who linked each character.

        `entries` are snapshot RSVPs: {character, session_id, status, at}. An
        entry only replaces an RSVP that was set before it (in Discord or by an
        earlier entry), so re-uploading the same entries changes nothing.
        Sessions that were cancelled or have ended are left alone.
        """
        changed: set[int] = set()
        unlinked: set[str] = set()
        for e in sorted(entries, key=lambda e: e["at"]):
            owner = self.character_owner(e["character"])
            if owner is None:
                unlinked.add(e["character"])
                continue
            session = self.get_session(e["session_id"])
            if session is None or session.cancelled or session.end_ts <= now_ts or e["at"] > now_ts + MAX_CLOCK_SKEW:
                continue
            row = self.conn.execute(
                "SELECT status, updated_at FROM rsvps WHERE session_id = ? AND user_id = ?", (session.id, owner)
            ).fetchone()
            if row is not None and e["at"] <= row["updated_at"]:
                continue
            self.set_rsvp(session.id, owner, e["status"], e["at"])
            if row is None or row["status"] != e["status"]:
                changed.add(session.id)
        return GameRsvpResult(changed, unlinked)

    # reminders -------------------------------------------------------------

    def due_reminders(self, now_ts: int, offsets: tuple[int, ...]) -> list[tuple[Session, list[int]]]:
        """Sessions with reminders due now, each with every due-but-unsent offset.

        Callers send one reminder per session (for the smallest offset) and
        mark all returned offsets sent, so a bot that was down doesn't post a
        burst of stale reminders.
        """
        out = []
        for session in self.upcoming_sessions(now_ts, limit=100):
            if session.start_ts <= now_ts:
                continue
            sent = {
                r["offset_min"]
                for r in self.conn.execute(
                    "SELECT offset_min FROM reminders_sent WHERE session_id = ?", (session.id,)
                )
            }
            due = [o for o in offsets if o not in sent and session.start_ts - o * 60 <= now_ts]
            if due:
                out.append((session, sorted(due)))
        return out

    def mark_reminded(self, session_id: int, offsets: list[int]) -> None:
        with self.conn:
            self.conn.executemany(
                "INSERT OR IGNORE INTO reminders_sent (session_id, offset_min) VALUES (?, ?)",
                [(session_id, o) for o in offsets],
            )

    # availability ----------------------------------------------------------

    def add_availability(self, user_id: int, weekday: int, start_min: int, end_min: int) -> Availability:
        if start_min == end_min:
            raise ValueError("start and end are the same time")
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO availability (user_id, weekday, start_min, end_min) VALUES (?, ?, ?, ?)",
                (user_id, weekday, start_min, end_min),
            )
        return Availability(cur.lastrowid or 0, user_id, weekday, start_min, end_min)

    def clear_availability(self, user_id: int) -> int:
        with self.conn:
            cur = self.conn.execute("DELETE FROM availability WHERE user_id = ?", (user_id,))
        return cur.rowcount

    def availability(self, user_id: int | None = None) -> list[Availability]:
        if user_id is None:
            rows = self.conn.execute("SELECT * FROM availability ORDER BY user_id, weekday, start_min")
        else:
            rows = self.conn.execute(
                "SELECT * FROM availability WHERE user_id = ? ORDER BY weekday, start_min", (user_id,)
            )
        return [Availability(r["id"], r["user_id"], r["weekday"], r["start_min"], r["end_min"]) for r in rows]

    # snapshots -------------------------------------------------------------

    def save_snapshot(self, payload: dict[str, Any], received_at: int) -> Snapshot:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO snapshots (received_at, payload) VALUES (?, ?)",
                (received_at, json.dumps(payload, ensure_ascii=False)),
            )
        return Snapshot(cur.lastrowid or 0, received_at, payload)

    def latest_snapshot(self) -> Snapshot | None:
        row = self.conn.execute("SELECT * FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()
        return Snapshot(row["id"], row["received_at"], json.loads(row["payload"])) if row else None

    # schedule export ---------------------------------------------------------

    def schedule_export(self, now_ts: int, reminders: tuple[int, ...] = (60, 15)) -> dict[str, Any]:
        """The upcoming schedule in the format the sync app writes for the addon.

        `reminders` (minutes before the start) lets the addon remind at the
        same times as the bot.

        `people` maps Discord user ids (as strings: they don't fit a Lua
        number) to a display name and linked characters, and each session's
        `rsvp` maps the same ids to a status, so the addon can show character
        names and find its own player's answer. `going`/`late`/`out` keep the
        display names for addons before 0.3.0. `sync` is the character whose
        sync app sent the latest snapshot, i.e. whose /reload or logout takes
        in-game RSVPs to Discord.
        """
        names = self.display_names()
        chars: dict[int, list[str]] = {}
        for c in self.characters():
            chars.setdefault(c.user_id, []).append(c.name)
        people: dict[str, dict[str, Any]] = {}

        def person(user_id: int) -> str:
            key = str(user_id)
            if key not in people:
                people[key] = {"name": names.get(user_id, key), "chars": chars.get(user_id, [])}
            return key

        for user_id in chars:
            person(user_id)
        sessions = []
        for s in self.upcoming_sessions(now_ts, limit=20):
            rsvps = self.rsvps(s.id)
            sessions.append({
                "id": s.id,
                "title": s.title,
                "start": s.start_ts,
                "duration": s.duration_min,
                **{status: [a.display_name for a in rsvps[status]] for status in rsvps},
                "rsvp": {person(a.user_id): status for status in rsvps for a in rsvps[status]},
            })
        out: dict[str, Any] = {
            "version": SCHEMA_VERSION, "generated_at": now_ts, "reminders": list(reminders),
            "people": people, "sessions": sessions,
        }
        snap = self.latest_snapshot()
        source = snap.payload.get("source") if snap else None
        if isinstance(source, str):
            out["sync"] = source
        return out

    # crafting orders ---------------------------------------------------------

    def create_order(
        self, *, channel_id: int, item: str, quantity: int, note: str | None, requested_by: int, now_ts: int,
    ) -> Order:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO orders (channel_id, item, quantity, note, requested_by, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (channel_id, item, quantity, note, requested_by, now_ts),
            )
        order = self.get_order(cur.lastrowid or 0)
        assert order is not None
        return order

    def get_order(self, order_id: int) -> Order | None:
        row = self.conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        return Order(**dict(row)) if row else None

    def open_orders(self) -> list[Order]:
        rows = self.conn.execute("SELECT * FROM orders WHERE status = 'open' ORDER BY id")
        return [Order(**dict(r)) for r in rows]

    def close_order(self, order_id: int, status: str, user_id: int, now_ts: int) -> bool:
        if status not in ("done", "cancelled"):
            raise ValueError(f"unknown order status {status!r}")
        with self.conn:
            cur = self.conn.execute(
                "UPDATE orders SET status = ?, closed_by = ?, closed_at = ? WHERE id = ? AND status = 'open'",
                (status, user_id, now_ts, order_id),
            )
        return cur.rowcount == 1

    # session recaps ------------------------------------------------------------

    def get_recap(self, session_id: int) -> RecapRecord | None:
        row = self.conn.execute("SELECT * FROM recaps WHERE session_id = ?", (session_id,)).fetchone()
        return RecapRecord(**dict(row)) if row else None

    def save_recap(self, session_id: int, message_id: int | None, signature: str, now_ts: int) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO recaps (session_id, message_id, signature, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET message_id = excluded.message_id, "
                "signature = excluded.signature, updated_at = excluded.updated_at",
                (session_id, message_id, signature, now_ts),
            )

    # level-gap alerts ----------------------------------------------------------

    def level_alerts(self) -> dict[str, int]:
        """Members with an alert posted and still ahead: {member: level at the alert}."""
        return {r["member"]: r["level"] for r in self.conn.execute("SELECT * FROM level_alerts")}

    def add_level_alert(self, member: str, level: int, now_ts: int) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO level_alerts (member, level, alerted_at) VALUES (?, ?, ?)",
                (member, level, now_ts),
            )

    def clear_level_alert(self, member: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM level_alerts WHERE member = ?", (member,))
