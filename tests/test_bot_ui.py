from datetime import datetime, timezone

import discord
import pytest

from caravan.bot import render
from caravan.bot.config import Config
from caravan.bot.db import Attendee, Availability, Session, Snapshot
from caravan.bot.discord_app import RSVPButton, rsvp_view
from caravan.bot.planner import Suggestion

SESSION = Session(id=3, guild_id=1, channel_id=2, message_id=None, event_id=None, title="Deadmines",
                  start_ts=1_800_000_000, duration_min=150, created_by=1, cancelled=False)
RSVPS = {"going": [Attendee(1, "Arda")], "late": [Attendee(2, "Bo")], "out": []}


def test_formatting_helpers():
    assert render.ts(5) == "<t:5:F>" and render.ts(5, "R") == "<t:5:R>"
    assert render.clock(1140) == "19:00" and render.clock(1440) == "00:00"
    assert render.duration(150) == "2h30" and render.duration(120) == "2h"


def test_session_embed():
    embed = render.session_embed(SESSION, RSVPS)
    assert "Deadmines" in embed.title and "<t:1800000000:F>" in embed.description
    assert [f.name for f in embed.fields] == ["✅ In (1)", "⏰ Late (1)", "❌ Out (0)"]
    assert embed.fields[0].value == "Arda" and embed.fields[2].value == "—"
    assert embed.footer.text == "Session #3"
    cancelled = render.session_embed(Session(**{**SESSION.__dict__, "cancelled": True}), RSVPS)
    assert "cancelled" in cancelled.title


def test_session_line_and_reminder():
    assert "2 coming" in render.session_line(SESSION, RSVPS)
    text = render.reminder_text(SESSION, RSVPS, "https://x")
    assert "<@1>" in text and "<@2>" in text and "https://x" in text
    assert "Nobody" in render.reminder_text(SESSION, {"going": [], "late": [], "out": []}, None)


def test_availability_and_suggestions_text():
    rules = [Availability(1, 10, 4, 1140, 60)]
    text = render.availability_lines(rules, {10: "Arda"}, {}, "Australia/Melbourne")
    assert "Arda" in text and "Friday 19:00–01:00" in text
    assert "No availability" in render.availability_lines([], {}, {}, "UTC")
    s = [Suggestion(datetime.fromtimestamp(1_800_000_000, timezone.utc), (10,))]
    assert "1/2: Arda" in render.suggestions_text(s, {10: "Arda"}, 2, 180)
    assert "No time works" in render.suggestions_text([], {}, 0, 180)


def test_group_embed():
    assert "No game data" in render.group_embed(None).description
    snap = Snapshot(1, 1_800_000_000, {"members": {
        "Bo-Ironvale": {"level": 9, "class": "MAGE", "race": "Gnome", "professions": []},
        "Roland-Ironvale": {"level": 14, "class": "WARRIOR", "race": "Human", "zone": "Elwynn Forest",
                            "ilvl": 14.5, "professions": [{"name": "Mining", "rank": 52}], "updated_at": 5},
    }})
    lines = render.group_embed(snap).description.splitlines()
    assert lines[0].startswith("**Roland** 14 Human Warrior · Elwynn Forest · iLvl 14.5 · Mining 52")
    assert lines[1].startswith("**Bo** 9 Gnome Mage")


def test_rsvp_buttons_round_trip_custom_ids():
    view = rsvp_view(7)
    ids = [item.item.custom_id for item in view.children]
    assert ids == ["caravan:rsvp:7:going", "caravan:rsvp:7:late", "caravan:rsvp:7:out"]
    match = RSVPButton.__discord_ui_compiled_template__.fullmatch(ids[1])
    assert match["sid"] == "7" and match["status"] == "late"


def test_config_from_env():
    cfg = Config.from_env({"DISCORD_TOKEN": "t", "CARAVAN_API_TOKEN": "a", "DISCORD_GUILD_ID": "42",
                           "REMINDER_OFFSETS": "15, 60,15", "GROUP_TZ": "Europe/Istanbul"})
    assert cfg.guild_id == 42 and cfg.reminder_offsets == (60, 15) and cfg.sessions_channel_id is None
    with pytest.raises(SystemExit):
        Config.from_env({"DISCORD_TOKEN": "t"})
    with pytest.raises(ValueError):
        Config.from_env({"DISCORD_TOKEN": "t", "CARAVAN_API_TOKEN": "a", "GROUP_TZ": "Nowhere/City"})


def test_phase4_commands_are_registered():
    from caravan.bot.db import Store
    from caravan.bot.discord_app import CaravanBot

    bot = CaravanBot(Config(discord_token="x", api_token="y"), Store(":memory:"))
    names = {c.qualified_name for c in bot.tree.walk_commands()}
    assert {"group", "dungeons", "craft", "order add", "order list", "order done", "order cancel"} <= names


def test_dungeons_embed():
    from caravan.bot.gamedata import suggest_dungeons

    levels = {"Roland-Ironvale": 19, "Bo-Ironvale": 13}
    embed = render.dungeons_embed(suggest_dungeons(levels, "Alliance"), levels, "Alliance", "Dungeons")
    assert embed.description.startswith("Roland 19 · Bo 13")
    assert "too low: Bo" in embed.description and "Ragefire" not in embed.description
    assert "in Horde territory" in embed.description and "range unconfirmed" in embed.description
    assert "No levels yet" in render.dungeons_embed([], {}, None, "Dungeons").description


def test_craft_and_order_text():
    from caravan.bot.db import Order
    from caravan.bot.gamedata import Crafter, RecipeMatch

    match = RecipeMatch("Copper Bracers", (Crafter("Roland-Ironvale", "Blacksmithing", 52),))
    assert render.craft_text("copper", [match], ["Cy"]).splitlines() == [
        "**Copper Bracers**: Roland (Blacksmithing 52)",
        "-# No recipes yet from Cy: open each profession window once in game.",
    ]
    assert "Nobody in the group" in render.craft_text("mithril", [], [])
    order = Order(3, 2, "Copper Bracers", 2, "asap", 10, 0, "open", None, None)
    assert render.order_line(order, {10: "Bo"}, [match]) == (
        "**#3** 2× Copper Bracers for Bo (asap) · can craft: Roland (Blacksmithing 52)"
    )
    assert render.order_line(order, {}, []) == "**#3** 2× Copper Bracers for <@10> (asap)"


def test_recap_embed_shows_partial_runs():
    from caravan.bot.gamedata import LevelGain, LootItem, Recap, RunSummary

    recap = Recap(
        players=("Bo", "Roland"),
        levels=(LevelGain("Roland", 15, 17),),
        runs=(RunSummary("The Deadmines", ("Roland", "Bo"), ("Rhahk'Zor", "Sneed"), 6, False),
              RunSummary("Shadowfang Keep", ("Bo",), ("Rethilgore",), None, False),
              RunSummary("Wailing Caverns", ("Bo",), ("A", "B"), 4, True)),
        loot=(LootItem("Roland", "Cruel Barb", 4, 5),),
    )
    embed = render.recap_embed(SESSION, recap)
    fields = {f.name: f.value for f in embed.fields}
    assert "Played: Bo, Roland" in embed.description
    assert fields["🎉 Levels"] == "Roland 15 → 17"
    assert "**The Deadmines** · 2/6 bosses · Roland, Bo\n  down: Rhahk'Zor, Sneed" in fields["🏰 Dungeons"]
    assert "**Shadowfang Keep** · 1 boss · Bo" in fields["🏰 Dungeons"]
    assert "**Wailing Caverns** · cleared ✅ · Bo" in fields["🏰 Dungeons"]
    assert fields["💎 Loot"] == "🟣 Roland: [Cruel Barb]"


def test_level_gap_embed_and_config():
    embed = render.level_gap_embed("Roland-Ironvale", {"Roland-Ironvale": 20, "Bo-Ironvale": 15}, 5, 3)
    assert embed.title == "📈 Roland is pulling ahead" and embed.description.endswith("Bo 15")
    cfg = Config.from_env({"DISCORD_TOKEN": "t", "CARAVAN_API_TOKEN": "a", "SESSIONS_CHANNEL_ID": "9"})
    assert cfg.level_gap == 3 and cfg.alerts_channel == 9
    cfg = Config.from_env({"DISCORD_TOKEN": "t", "CARAVAN_API_TOKEN": "a", "SESSIONS_CHANNEL_ID": "9",
                           "ALERTS_CHANNEL_ID": "8", "LEVEL_GAP": "0"})
    assert cfg.level_gap == 0 and cfg.alerts_channel == 8


class _FakeResponse:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bool]] = []

    async def send_message(self, content: str, *, ephemeral: bool = False, **_: object) -> None:
        self.sent.append((content, ephemeral))


class _FakeInteraction:
    def __init__(self, user_id: int, permissions: discord.Permissions) -> None:
        self.user = discord.Object(id=user_id)
        self.permissions = permissions
        self.guild = None
        self.response = _FakeResponse()


@pytest.mark.parametrize(
    ("user_id", "permissions", "allowed"),
    [
        (10, discord.Permissions.none(), True),                       # the scheduler
        (20, discord.Permissions(manage_guild=True), True),           # Manage Server
        (20, discord.Permissions(administrator=True), True),          # Administrator
        (20, discord.Permissions.none(), False),                      # anyone else
        (20, discord.Permissions(manage_events=True), False),         # Manage Events isn't enough
    ],
)
async def test_session_cancel_is_limited_to_scheduler_and_admins(user_id, permissions, allowed):
    from caravan.bot.db import Store
    from caravan.bot.discord_app import CaravanBot, may_cancel

    store = Store(":memory:")
    bot = CaravanBot(Config(discord_token="x", api_token="y"), store)
    session = store.create_session(guild_id=1, channel_id=2, title="Deadmines", start_ts=1_800_000_000,
                                   duration_min=120, created_by=10)
    assert may_cancel(session, user_id, permissions) is allowed

    cancel = bot.tree.get_command("session").get_command("cancel")
    interaction = _FakeInteraction(user_id, permissions)
    await cancel.callback(interaction, session.id)

    [(text, ephemeral)] = interaction.response.sent
    assert store.get_session(session.id).cancelled is allowed
    if allowed:
        assert text == f"Cancelled **Deadmines** (#{session.id})." and not ephemeral
    else:
        assert text.startswith("Only <@10>, who scheduled session #") and ephemeral


async def test_session_cancel_unknown_or_already_cancelled():
    from caravan.bot.db import Store
    from caravan.bot.discord_app import CaravanBot

    store = Store(":memory:")
    bot = CaravanBot(Config(discord_token="x", api_token="y"), store)
    session = store.create_session(guild_id=1, channel_id=2, title="Deadmines", start_ts=1_800_000_000,
                                   duration_min=120, created_by=10)
    store.cancel_session(session.id)
    cancel = bot.tree.get_command("session").get_command("cancel")
    for session_id in (session.id, 999):
        interaction = _FakeInteraction(20, discord.Permissions.none())
        await cancel.callback(interaction, session_id)
        assert interaction.response.sent == [(f"No active session #{session_id}.", True)]
