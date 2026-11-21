"""RSVPs made in the game: the snapshot format, /character and the bot's snapshot hook."""

import time

import discord

from caravan.bot.config import Config
from caravan.bot.db import Snapshot, Store
from caravan.bot.discord_app import CaravanBot
from caravan.bot.gamedata import character_name
from caravan.schema import rsvps_from_lua, snapshot_from_savedvariables, snapshot_rsvps

T0 = 1_800_000_000


def test_rsvps_from_lua_keeps_only_valid_entries():
    lua = {
        "Roland-Ironvale": [{"id": 3, "s": "going", "ts": 5}, {"id": "x", "s": "going", "ts": 5},
                            {"id": 4, "s": "maybe", "ts": 5}, "junk"],
        "Brakka-Ironvale": {1: {"id": 7, "s": "out", "ts": 6}},
        5: [{"id": 1, "s": "out", "ts": 1}],
    }
    assert rsvps_from_lua(lua) == [
        {"character": "Roland-Ironvale", "session_id": 3, "status": "going", "at": 5},
        {"character": "Brakka-Ironvale", "session_id": 7, "status": "out", "at": 6},
    ]
    assert rsvps_from_lua(None) == [] and rsvps_from_lua("x") == []


def test_snapshot_carries_rsvps():
    sv = {"TheCaravanDB": {"members": {}, "rsvps": {"Roland-Ironvale": [{"id": 3, "s": "late", "ts": 9}]}}}
    snap = snapshot_from_savedvariables(sv, exported_at=1)
    assert snap["rsvps"] == [{"character": "Roland-Ironvale", "session_id": 3, "status": "late", "at": 9}]
    assert snapshot_rsvps(snap) == snap["rsvps"]
    assert snapshot_rsvps({"rsvps": [{"character": "", "session_id": 1, "status": "going", "at": 1}, 5]}) == []
    assert snapshot_rsvps({"members": {}}) == []  # snapshots from older addons have none


def test_character_name():
    known = ["Roland-Ironvale", "Brakka-Ironvale", "Roland-Otherrealm"]
    assert character_name("brakka", known) == "Brakka-Ironvale"
    assert character_name("roland", known) is None  # two Rolands: the realm is needed
    assert character_name("roland-otherrealm", known) == "Roland-Otherrealm"
    assert character_name("dara-Ironvale", known) == "Dara-Ironvale"
    assert character_name("dara-Burning Blade", known) == "Dara-BurningBlade"
    assert character_name("dara", known) is None
    assert character_name("-x", known) is None and character_name("a b-c", known) is None
    # WoW Forever: "Name Surname", as the game shows it
    assert character_name("Roland Ironvale", known) == "Roland-Ironvale"
    assert character_name("sudo lock", known) == "Sudo-Lock"


class FakeUser:
    def __init__(self, user_id: int, name: str) -> None:
        self.id = user_id
        self.display_name = name


class FakeResponse:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bool]] = []

    async def send_message(self, content: str, *, ephemeral: bool = False, **_: object) -> None:
        self.sent.append((content, ephemeral))


class FakeInteraction:
    def __init__(self, user_id: int, name: str = "Arda", permissions: discord.Permissions | None = None) -> None:
        self.user = FakeUser(user_id, name)
        self.permissions = permissions or discord.Permissions.none()
        self.guild = None
        self.response = FakeResponse()


def make_bot() -> tuple[CaravanBot, Store]:
    store = Store(":memory:")
    store.save_snapshot({"version": 1, "exported_at": T0, "members": {"Roland-Ironvale": {"level": 15}}}, T0)
    return CaravanBot(Config(discord_token="x", api_token="y"), store), store


async def run_command(bot: CaravanBot, name: str, interaction: FakeInteraction, *args: object) -> str:
    command = bot.tree.get_command("character").get_command(name)
    await command.callback(interaction, *args)
    [(text, ephemeral)] = interaction.response.sent
    assert ephemeral
    return text


async def test_character_link_unlink_and_list():
    bot, store = make_bot()
    text = await run_command(bot, "link", FakeInteraction(10), "roland")
    assert text.startswith("Linked **Roland-Ironvale** to you.") and "isn't in the latest" not in text
    assert store.character_owner("Roland-Ironvale") == 10

    text = await run_command(bot, "link", FakeInteraction(20, "Bo"), "Roland-Ironvale")
    assert text == "**Roland-Ironvale** is linked to <@10>. They can `/character unlink` it first."
    assert store.character_owner("Roland-Ironvale") == 10

    text = await run_command(bot, "link", FakeInteraction(20, "Bo"), "Brakka-Ironvale")
    assert "isn't in the latest game snapshot" in text
    assert "Add the surname" in await run_command(bot, "link", FakeInteraction(20, "Bo"), "Nobody")

    listing = await run_command(bot, "list", FakeInteraction(30))
    assert listing.splitlines() == ["**Bo**: Brakka-Ironvale", "**Arda**: Roland-Ironvale"]

    assert "Only they or someone with Manage Server" in await run_command(bot, "unlink", FakeInteraction(20), "Roland")
    admin = FakeInteraction(30, permissions=discord.Permissions(manage_guild=True))
    assert await run_command(bot, "unlink", admin, "roland-ironvale") == "Unlinked **Roland-Ironvale**."
    assert "isn't linked" in await run_command(bot, "unlink", FakeInteraction(10), "Roland-Ironvale")


async def test_snapshot_hook_applies_rsvps_and_refreshes_cards():
    bot, store = make_bot()
    now = int(time.time())
    s = store.create_session(guild_id=1, channel_id=2, title="Run", start_ts=now + 3600, duration_min=60, created_by=10)
    store.upsert_user(10, "Arda")
    store.link_character("Roland-Ironvale", 10, now)
    refreshed, fed = [], []

    async def refresh(session):
        refreshed.append(session.id)

    async def feed(snapshot, previous):
        fed.append(snapshot.id)

    bot.refresh_session_message = refresh  # type: ignore[method-assign]
    bot.feed.on_snapshot = feed  # type: ignore[method-assign]
    payload = {"version": 1, "exported_at": now, "members": {},
               "rsvps": [{"character": "Roland-Ironvale", "session_id": s.id, "status": "late", "at": now - 5},
                         {"character": "Stranger-Ironvale", "session_id": s.id, "status": "going", "at": now - 5}]}
    await bot.on_snapshot(Snapshot(7, now, payload))
    assert refreshed == [s.id] and fed == [7]
    assert [a.display_name for a in store.rsvps(s.id)["late"]] == ["Arda"]
    await bot.on_snapshot(Snapshot(8, now, payload))  # the same entries again: no card edit
    assert refreshed == [s.id] and fed == [7, 8]
