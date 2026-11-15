"""The Discord side: slash commands, RSVP buttons, reminders, game-data posts
and the HTTP API."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone

import discord
from aiohttp import web
from discord import app_commands
from discord.ext import tasks

from . import render
from .api import create_app
from .config import Config
from .db import Session, Store
from .feed import GameFeed
from .game_commands import register_game_commands
from .planner import suggest
from .timeparse import WEEKDAYS, parse_clock, parse_when, search_timezones, weekday_index, zone

log = logging.getLogger(__name__)


def _now() -> int:
    return int(time.time())


class RSVPButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"caravan:rsvp:(?P<sid>\d+):(?P<status>going|late|out)",
):
    STYLES = {
        "going": discord.ButtonStyle.success,
        "late": discord.ButtonStyle.primary,
        "out": discord.ButtonStyle.secondary,
    }

    def __init__(self, session_id: int, status: str) -> None:
        super().__init__(
            discord.ui.Button(
                label=render.RSVP_LABELS[status],
                emoji=render.RSVP_EMOJI[status],
                style=self.STYLES[status],
                custom_id=f"caravan:rsvp:{session_id}:{status}",
            )
        )
        self.session_id = session_id
        self.status = status

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str], /):
        return cls(int(match["sid"]), match["status"])

    async def callback(self, interaction: discord.Interaction) -> None:
        bot: CaravanBot = interaction.client  # type: ignore[assignment]
        session = bot.store.get_session(self.session_id)
        if session is None or session.cancelled:
            await interaction.response.send_message("That session was cancelled.", ephemeral=True)
            return
        bot.store.upsert_user(interaction.user.id, interaction.user.display_name)
        bot.store.set_rsvp(session.id, interaction.user.id, self.status, _now())
        embed = render.session_embed(session, bot.store.rsvps(session.id))
        await interaction.response.edit_message(embed=embed, view=rsvp_view(session.id))


def rsvp_view(session_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for status in ("going", "late", "out"):
        view.add_item(RSVPButton(session_id, status))
    return view


class DiscordPoster:
    """Lets the game feed post and edit embeds without knowing about discord.py."""

    def __init__(self, bot: CaravanBot) -> None:
        self.bot = bot

    async def send(self, channel_id: int, embed: discord.Embed) -> int | None:
        channel = await self.bot.channel(channel_id)
        if channel is None:
            log.warning("can't post in channel %s", channel_id)
            return None
        try:
            return (await channel.send(embed=embed)).id
        except discord.HTTPException as exc:
            log.warning("posting in channel %s failed: %s", channel_id, exc)
            return None

    async def edit(self, channel_id: int, message_id: int, embed: discord.Embed) -> bool:
        channel = await self.bot.channel(channel_id)
        if channel is None:
            return False
        try:
            message = await channel.fetch_message(message_id)  # type: ignore[union-attr]
            await message.edit(embed=embed)
            return True
        except discord.HTTPException:
            return False


class CaravanBot(discord.Client):
    def __init__(self, config: Config, store: Store) -> None:
        super().__init__(intents=discord.Intents.default())
        self.config = config
        self.store = store
        self.tree = app_commands.CommandTree(self)
        self._runner: web.AppRunner | None = None
        self.feed = GameFeed(store, DiscordPoster(self), config.level_gap, config.alerts_channel)
        register_commands(self)
        register_game_commands(self)

    async def setup_hook(self) -> None:
        self.add_dynamic_items(RSVPButton)
        if self.config.guild_id:
            guild = discord.Object(id=self.config.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
        self.reminder_loop.start()
        self.recap_loop.start()
        app = create_app(self.store, self.config.api_token, on_snapshot=self.feed.on_snapshot)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        await web.TCPSite(self._runner, self.config.api_host, self.config.api_port).start()
        log.info("HTTP API listening on %s:%s", self.config.api_host, self.config.api_port)

    async def close(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
        await super().close()

    def tz_for(self, user_id: int) -> str:
        return self.store.user_tz(user_id) or self.config.group_tz

    async def channel(self, channel_id: int) -> discord.abc.Messageable | None:
        channel = self.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(channel_id)
            except discord.HTTPException:
                return None
        return channel if isinstance(channel, discord.abc.Messageable) else None

    async def refresh_session_message(self, session: Session) -> None:
        if session.message_id is None:
            return
        channel = await self.channel(session.channel_id)
        if channel is None:
            return
        try:
            message = await channel.fetch_message(session.message_id)  # type: ignore[union-attr]
            view = None if session.cancelled else rsvp_view(session.id)
            await message.edit(embed=render.session_embed(session, self.store.rsvps(session.id)), view=view)
        except discord.HTTPException:
            log.warning("couldn't update the message for session %s", session.id)

    @tasks.loop(seconds=60)
    async def reminder_loop(self) -> None:
        for session, offsets in self.store.due_reminders(_now(), self.config.reminder_offsets):
            channel = await self.channel(session.channel_id)
            if channel is not None:
                jump = (
                    f"https://discord.com/channels/{session.guild_id}/{session.channel_id}/{session.message_id}"
                    if session.message_id else None
                )
                text = render.reminder_text(session, self.store.rsvps(session.id), jump)
                try:
                    await channel.send(text, allowed_mentions=discord.AllowedMentions(users=True))
                except discord.HTTPException:
                    log.exception("reminder for session %s failed", session.id)
                    continue
            self.store.mark_reminded(session.id, offsets)

    @reminder_loop.before_loop
    async def _wait_ready(self) -> None:
        await self.wait_until_ready()

    @tasks.loop(minutes=5)
    async def recap_loop(self) -> None:
        try:
            await self.feed.tick()
        except Exception:
            log.exception("recap check failed")

    @recap_loop.before_loop
    async def _wait_ready_recaps(self) -> None:
        await self.wait_until_ready()


def register_commands(bot: CaravanBot) -> None:
    store = bot.store
    cfg = bot.config

    session_group = app_commands.Group(name="session", description="Plan Caravan sessions")
    availability_group = app_commands.Group(name="availability", description="When you're free to play")
    timezone_group = app_commands.Group(name="timezone", description="Your timezone for times you type")

    @session_group.command(name="add", description="Schedule a session with RSVP buttons")
    @app_commands.describe(
        when='e.g. "fri 8pm", "tomorrow 7:30pm", "2026-11-21 19:00" (your timezone)',
        title="What the session is about",
        duration="Length in minutes",
    )
    async def session_add(
        interaction: discord.Interaction, when: str, title: str | None = None,
        duration: app_commands.Range[int, 15, 720] | None = None,
    ) -> None:
        store.upsert_user(interaction.user.id, interaction.user.display_name)
        tz = bot.tz_for(interaction.user.id)
        try:
            start = parse_when(when, tz, datetime.now(timezone.utc))
        except ValueError as exc:
            await interaction.response.send_message(f"⚠️ {exc}", ephemeral=True)
            return
        if interaction.guild is None:
            await interaction.response.send_message("Use this in the server, not in DMs.", ephemeral=True)
            return
        minutes = duration or cfg.default_duration_min
        channel_id = cfg.sessions_channel_id or interaction.channel_id
        channel = await bot.channel(channel_id) if channel_id else None
        if channel is None:
            await interaction.response.send_message("I can't post in the sessions channel.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=channel_id != interaction.channel_id, thinking=True)
        session = store.create_session(
            guild_id=interaction.guild.id, channel_id=channel_id, title=title or "Caravan session",
            start_ts=int(start.timestamp()), duration_min=minutes, created_by=interaction.user.id,
        )
        store.set_rsvp(session.id, interaction.user.id, "going", _now())
        message = await channel.send(
            embed=render.session_embed(session, store.rsvps(session.id)), view=rsvp_view(session.id)
        )
        store.set_session_message(session.id, message.id)
        try:
            event = await interaction.guild.create_scheduled_event(
                name=session.title[:100],
                start_time=start,
                end_time=start + timedelta(minutes=minutes),
                entity_type=discord.EntityType.external,
                privacy_level=discord.PrivacyLevel.guild_only,
                location="Azeroth (WoW Forever)",
                description=f"Caravan session #{session.id}. RSVP: {message.jump_url}",
            )
            store.set_session_event(session.id, event.id)
        except discord.HTTPException as exc:
            log.warning("couldn't create a scheduled event: %s", exc)
        await interaction.followup.send(
            f"Scheduled **{session.title}** for {render.ts(session.start_ts)} → {message.jump_url}"
        )

    @session_group.command(name="list", description="Upcoming sessions")
    async def session_list(interaction: discord.Interaction) -> None:
        sessions = store.upcoming_sessions(_now())
        if not sessions:
            await interaction.response.send_message("Nothing scheduled. Add one with `/session add`.")
            return
        lines = [render.session_line(s, store.rsvps(s.id)) for s in sessions]
        await interaction.response.send_message("\n".join(lines))

    @session_group.command(name="cancel", description="Cancel a session")
    @app_commands.describe(session_id="The number shown as Session #N")
    async def session_cancel(interaction: discord.Interaction, session_id: int) -> None:
        if not store.cancel_session(session_id):
            await interaction.response.send_message(f"No active session #{session_id}.", ephemeral=True)
            return
        session = store.get_session(session_id)
        assert session is not None
        await interaction.response.send_message(f"Cancelled **{session.title}** (#{session.id}).")
        await bot.refresh_session_message(session)
        if session.event_id and interaction.guild is not None:
            try:
                event = await interaction.guild.fetch_scheduled_event(session.event_id)
                await event.delete()
            except discord.HTTPException as exc:
                log.warning("couldn't delete scheduled event %s: %s", session.event_id, exc)

    @session_group.command(name="suggest", description="Find the time that suits the most people")
    @app_commands.describe(duration="Length in minutes", days="How many days ahead to look")
    async def session_suggest(
        interaction: discord.Interaction,
        duration: app_commands.Range[int, 30, 720] | None = None,
        days: app_commands.Range[int, 1, 14] = 7,
    ) -> None:
        minutes = duration or cfg.default_duration_min
        rules = store.availability()
        result = suggest(rules, store.user_tzs(), cfg.group_tz, datetime.now(timezone.utc), minutes, days)
        total = len({r.user_id for r in rules})
        await interaction.response.send_message(
            render.suggestions_text(result, store.display_names(), total, minutes)
        )

    day_choices = [app_commands.Choice(name=d, value=d) for d in WEEKDAYS]

    @availability_group.command(name="add", description="Add a weekly window when you can play")
    @app_commands.describe(day="Day of the week", start="e.g. 19:00 or 7pm", end="e.g. 23:00; earlier than start means past midnight")
    @app_commands.choices(day=day_choices)
    async def availability_add(interaction: discord.Interaction, day: app_commands.Choice[str], start: str, end: str) -> None:
        store.upsert_user(interaction.user.id, interaction.user.display_name)
        try:
            a, b = parse_clock(start), parse_clock(end)
            store.add_availability(interaction.user.id, weekday_index(day.value), a, b)
        except ValueError as exc:
            await interaction.response.send_message(f"⚠️ {exc}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Added {day.value} {render.clock(a)}–{render.clock(b)} ({bot.tz_for(interaction.user.id)}).",
            ephemeral=True,
        )

    @availability_group.command(name="clear", description="Remove all your availability windows")
    async def availability_clear(interaction: discord.Interaction) -> None:
        n = store.clear_availability(interaction.user.id)
        await interaction.response.send_message(f"Removed {n} window(s).", ephemeral=True)

    @availability_group.command(name="show", description="Show availability for you or everyone")
    @app_commands.describe(member="Leave empty to see everyone")
    async def availability_show(interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        rules = store.availability(member.id if member else None)
        text = render.availability_lines(rules, store.display_names(), store.user_tzs(), cfg.group_tz)
        await interaction.response.send_message(text, ephemeral=True)

    @timezone_group.command(name="set", description="Set your timezone, e.g. Australia/Melbourne")
    async def timezone_set(interaction: discord.Interaction, tz: str) -> None:
        try:
            zone(tz)
        except ValueError as exc:
            await interaction.response.send_message(f"⚠️ {exc}", ephemeral=True)
            return
        store.set_user_tz(interaction.user.id, interaction.user.display_name, tz)
        await interaction.response.send_message(f"Your timezone is now {tz}.", ephemeral=True)

    @timezone_set.autocomplete("tz")
    async def _tz_autocomplete(_: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return [app_commands.Choice(name=n, value=n) for n in search_timezones(current)]

    @timezone_group.command(name="show", description="Show the timezone used for your times")
    async def timezone_show(interaction: discord.Interaction) -> None:
        own = store.user_tz(interaction.user.id)
        text = own or f"{cfg.group_tz} (the group default; change it with `/timezone set`)"
        await interaction.response.send_message(f"Your timezone: {text}", ephemeral=True)

    @app_commands.command(name="group", description="Everyone's characters, from the latest game snapshot")
    async def group(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=render.group_embed(store.latest_snapshot()))

    bot.tree.add_command(session_group)
    bot.tree.add_command(availability_group)
    bot.tree.add_command(timezone_group)
    bot.tree.add_command(group)
