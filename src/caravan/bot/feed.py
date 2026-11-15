"""Posts that come from game data rather than commands: level-gap alerts and
session recaps.

Recaps: once a session's scheduled end has passed and there is a snapshot
exported after the session started, the bot posts what happened between 30
minutes before the start and 3 hours after the scheduled end (or the next
session's start, if sooner): levels gained, dungeon runs and notable loot. The
addon timestamps each of these, so solo progress between sessions isn't
counted. Snapshots that arrive in the next 12 hours (Arda logs out late, or
/reloads again) edit the same post. A session with nothing to report gets no
post.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

import discord

from . import render
from .db import Session, Snapshot, Store
from .gamedata import active_levels, build_recap, level_gaps

log = logging.getLogger(__name__)

RECAP_LEAD = 30 * 60
RECAP_OVERRUN = 3 * 3600
RECAP_UPDATE_WINDOW = 12 * 3600


class Poster(Protocol):
    async def send(self, channel_id: int, embed: discord.Embed) -> int | None: ...

    async def edit(self, channel_id: int, message_id: int, embed: discord.Embed) -> bool: ...


class GameFeed:
    def __init__(
        self,
        store: Store,
        poster: Poster,
        level_gap: int,
        alerts_channel_id: int | None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.store = store
        self.poster = poster
        self.level_gap = level_gap
        self.alerts_channel_id = alerts_channel_id
        self.clock = clock

    async def on_snapshot(self, snapshot: Snapshot, previous: Snapshot | None = None) -> None:
        await self.check_level_gaps(snapshot)
        await self.update_recaps(snapshot)

    async def tick(self) -> None:
        """Called every few minutes: posts recaps for sessions that just ended."""
        snapshot = self.store.latest_snapshot()
        if snapshot is not None:
            await self.update_recaps(snapshot)

    # level gaps -----------------------------------------------------------------

    async def check_level_gaps(self, snapshot: Snapshot) -> None:
        if self.level_gap <= 0:
            return
        payload = snapshot.payload
        levels = active_levels(payload.get("members", {}), payload.get("exported_at") or snapshot.received_at)
        ahead = level_gaps(levels, self.level_gap)
        alerted = self.store.level_alerts()
        for member in alerted.keys() - ahead.keys():
            self.store.clear_level_alert(member)  # back with the group; a later gap alerts again
        for member, gap in sorted(ahead.items()):
            if member in alerted:
                continue
            if self.alerts_channel_id is None:
                log.info("%s is %s levels ahead, but no alerts channel is set", member, gap)
                continue
            embed = render.level_gap_embed(member, levels, gap, self.level_gap)
            if await self.poster.send(self.alerts_channel_id, embed) is not None:
                self.store.add_level_alert(member, levels[member], int(self.clock()))

    # session recaps -------------------------------------------------------------

    def recap_window(self, session: Session) -> tuple[int, int]:
        end = session.end_ts + RECAP_OVERRUN
        following = self.store.next_session_after(session.start_ts)
        if following is not None:
            end = max(session.end_ts, min(end, following.start_ts))
        return session.start_ts - RECAP_LEAD, end

    async def update_recaps(self, snapshot: Snapshot) -> None:
        now = int(self.clock())
        exported = snapshot.payload.get("exported_at") or snapshot.received_at
        members: dict[str, Any] = snapshot.payload.get("members", {})
        for session in self.store.sessions_ended_between(now - RECAP_UPDATE_WINDOW, now):
            if exported < session.start_ts:
                continue  # nothing from this session has reached the bot yet
            start, end = self.recap_window(session)
            recap = build_recap(members, start, end)
            if recap.empty:
                continue
            signature = recap.signature()
            existing = self.store.get_recap(session.id)
            if existing is not None and existing.signature == signature:
                continue
            embed = render.recap_embed(session, recap)
            if existing is not None and existing.message_id is not None:
                if await self.poster.edit(session.channel_id, existing.message_id, embed):
                    self.store.save_recap(session.id, existing.message_id, signature, now)
                    continue
            message_id = await self.poster.send(session.channel_id, embed)
            if message_id is not None:
                self.store.save_recap(session.id, message_id, signature, now)
                log.info("posted the recap for session %s", session.id)
