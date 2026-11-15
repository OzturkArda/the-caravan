import pytest

from caravan.bot.db import Store
from caravan.bot.feed import GameFeed

T0 = 1_800_000_000


class FakePoster:
    def __init__(self):
        self.sent = []  # (channel_id, embed)
        self.edits = []  # (channel_id, message_id, embed)
        self.fail_edits = False

    async def send(self, channel_id, embed):
        self.sent.append((channel_id, embed))
        return 1000 + len(self.sent)

    async def edit(self, channel_id, message_id, embed):
        if self.fail_edits:
            return False
        self.edits.append((channel_id, message_id, embed))
        return True


@pytest.fixture
def env():
    store = Store(":memory:")
    poster = FakePoster()
    clock = {"now": T0}
    feed = GameFeed(store, poster, level_gap=3, alerts_channel_id=77, clock=lambda: clock["now"])
    yield store, poster, feed, clock
    store.close()


def snapshot(store, members, exported_at):
    return store.save_snapshot({"version": 1, "exported_at": exported_at, "members": members}, exported_at)


def levels(**kw):
    return {f"{n}-Ironvale": {"level": lv, "updated_at": T0} for n, lv in kw.items()}


async def test_level_gap_alerts_once_per_crossing(env):
    store, poster, feed, _ = env
    await feed.on_snapshot(snapshot(store, levels(Roland=18, Bo=15, Cy=15), T0))
    assert poster.sent == []
    await feed.on_snapshot(snapshot(store, levels(Roland=19, Bo=15, Cy=15), T0))
    assert len(poster.sent) == 1
    channel, embed = poster.sent[0]
    assert channel == 77 and "Roland" in embed.title and "level 19, 4 levels above" in embed.description
    await feed.on_snapshot(snapshot(store, levels(Roland=20, Bo=15, Cy=15), T0))
    assert len(poster.sent) == 1  # still ahead: no repeat
    await feed.on_snapshot(snapshot(store, levels(Roland=20, Bo=18, Cy=18), T0))
    assert store.level_alerts() == {}  # caught up
    await feed.on_snapshot(snapshot(store, levels(Roland=22, Bo=18, Cy=18), T0))
    assert len(poster.sent) == 2


async def test_level_gap_without_channel_or_disabled(env):
    store, poster, _, _ = env
    quiet = GameFeed(store, poster, level_gap=3, alerts_channel_id=None)
    await quiet.on_snapshot(snapshot(store, levels(Roland=30, Bo=15), T0))
    off = GameFeed(store, poster, level_gap=0, alerts_channel_id=77)
    await off.on_snapshot(snapshot(store, levels(Roland=30, Bo=15), T0))
    assert poster.sent == [] and store.level_alerts() == {}


def session_members(extra_loot=()):
    return {
        "Roland-Ironvale": {
            "level": 17, "updated_at": T0 + 3 * 3600,
            "level_log": [{"level": 17, "at": T0 + 3600}],
            "loot": [{"item_id": 2, "name": "Staff of Westfall", "quality": 3, "at": T0 + 1800}, *extra_loot],
            "runs": [],
        },
    }


async def test_recap_posts_after_the_session_and_edits_on_later_snapshots(env):
    store, poster, feed, clock = env
    feed.level_gap = 0
    s = store.create_session(guild_id=1, channel_id=55, title="Deadmines", start_ts=T0, duration_min=180,
                             created_by=1)
    clock["now"] = T0 + 2 * 3600  # still running
    await feed.on_snapshot(snapshot(store, session_members(), T0 + 2 * 3600))
    assert poster.sent == []
    clock["now"] = T0 + 3 * 3600 + 60  # scheduled end passed; the loop picks it up
    await feed.tick()
    assert len(poster.sent) == 1
    channel, embed = poster.sent[0]
    assert channel == 55 and "Deadmines" in embed.title
    fields = {f.name: f.value for f in embed.fields}
    assert fields["🎉 Levels"] == "Roland 16 → 17" and "Staff of Westfall" in fields["💎 Loot"]
    await feed.tick()
    assert len(poster.sent) == 1 and poster.edits == []  # nothing new
    clock["now"] = T0 + 5 * 3600  # Arda logs out late with more loot
    more = [{"item_id": 3, "name": "Cruel Barb", "quality": 4, "at": T0 + 4 * 3600}]
    await feed.on_snapshot(snapshot(store, session_members(more), T0 + 5 * 3600))
    assert len(poster.edits) == 1 and poster.edits[0][1] == 1001
    assert "Cruel Barb" in {f.name: f.value for f in poster.edits[0][2].fields}["💎 Loot"]
    assert store.get_recap(s.id).message_id == 1001


async def test_recap_reposts_when_the_old_message_is_gone(env):
    store, poster, feed, clock = env
    feed.level_gap = 0
    store.create_session(guild_id=1, channel_id=55, title="Run", start_ts=T0, duration_min=60, created_by=1)
    clock["now"] = T0 + 2 * 3600
    await feed.on_snapshot(snapshot(store, session_members(), T0 + 2 * 3600))
    poster.fail_edits = True
    more = [{"item_id": 3, "name": "Cruel Barb", "quality": 4, "at": T0 + 3000}]
    await feed.on_snapshot(snapshot(store, session_members(more), T0 + 2 * 3600 + 60))
    assert len(poster.sent) == 2


async def test_no_recap_without_fresh_data_or_activity(env):
    store, poster, feed, clock = env
    feed.level_gap = 0
    store.create_session(guild_id=1, channel_id=55, title="Run", start_ts=T0, duration_min=60, created_by=1)
    clock["now"] = T0 + 2 * 3600
    await feed.on_snapshot(snapshot(store, session_members(), T0 - 60))  # exported before the session
    await feed.on_snapshot(snapshot(store, levels(Roland=17), T0 + 2 * 3600))  # nothing happened
    clock["now"] = T0 + 20 * 3600  # too late to recap
    await feed.on_snapshot(snapshot(store, session_members(), T0 + 20 * 3600))
    assert poster.sent == []


async def test_recap_window_stops_at_the_next_session(env):
    store, _, feed, _ = env
    first = store.create_session(guild_id=1, channel_id=55, title="A", start_ts=T0, duration_min=60, created_by=1)
    store.create_session(guild_id=1, channel_id=55, title="B", start_ts=T0 + 2 * 3600, duration_min=60, created_by=1)
    assert feed.recap_window(first) == (T0 - 1800, T0 + 2 * 3600)
    lone = store.create_session(guild_id=1, channel_id=55, title="C", start_ts=T0 + 86400, duration_min=60,
                                created_by=1)
    assert feed.recap_window(lone) == (T0 + 86400 - 1800, T0 + 86400 + 3600 + 3 * 3600)
