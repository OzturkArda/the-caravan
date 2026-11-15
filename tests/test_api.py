import pytest
from aiohttp.test_utils import TestClient, TestServer

from caravan.bot.api import create_app
from caravan.bot.db import Store

TOKEN = "s3cret"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
SNAP = {"version": 1, "exported_at": 5, "members": {"Roland-Ironvale": {"level": 14}}}


@pytest.fixture
async def setup():
    store = Store(":memory:")
    hook_calls = []

    async def hook(snap, previous):
        hook_calls.append((snap.id, previous.id if previous else None))

    app = create_app(store, TOKEN, on_snapshot=hook, clock=lambda: 1_800_000_000)
    async with TestClient(TestServer(app)) as client:
        yield client, store, hook_calls
    store.close()


async def test_health_needs_no_token(setup):
    client, _, _ = setup
    resp = await client.get("/health")
    assert resp.status == 200 and (await resp.json()) == {"ok": True}


async def test_token_required(setup):
    client, _, _ = setup
    assert (await client.get("/schedule")).status == 401
    assert (await client.get("/schedule", headers={"Authorization": "Bearer nope"})).status == 401


async def test_snapshot_stored_and_hook_called(setup):
    client, store, hook_calls = setup
    resp = await client.post("/snapshot", json=SNAP, headers=AUTH)
    assert resp.status == 200
    await client.post("/snapshot", json=SNAP, headers=AUTH)
    assert store.latest_snapshot().payload == SNAP
    assert hook_calls == [(1, None), (2, 1)]


async def test_bad_snapshot_rejected(setup):
    client, store, _ = setup
    assert (await client.post("/snapshot", json={"version": 9}, headers=AUTH)).status == 400
    assert (await client.post("/snapshot", data="not json", headers=AUTH)).status == 400
    assert store.latest_snapshot() is None


async def test_schedule(setup):
    client, store, _ = setup
    store.create_session(guild_id=1, channel_id=2, title="Run", start_ts=1_800_003_600,
                         duration_min=60, created_by=1)
    data = await (await client.get("/schedule", headers=AUTH)).json()
    assert data["generated_at"] == 1_800_000_000 and data["sessions"][0]["title"] == "Run"
