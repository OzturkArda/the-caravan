"""HTTP API the sync app talks to: snapshots in, schedule out."""

from __future__ import annotations

import hmac
import json
import logging
import time
from collections.abc import Awaitable, Callable

from aiohttp import web

from ..schema import validate_snapshot
from .db import Snapshot, Store

log = logging.getLogger(__name__)

SnapshotHook = Callable[[Snapshot, Snapshot | None], Awaitable[None]]


def create_app(
    store: Store,
    token: str,
    on_snapshot: SnapshotHook | None = None,
    clock: Callable[[], float] = time.time,
    reminders: tuple[int, ...] = (60, 15),
) -> web.Application:
    @web.middleware
    async def auth(request: web.Request, handler):
        if request.path != "/health":
            given = request.headers.get("Authorization", "")
            if not hmac.compare_digest(given.encode(), f"Bearer {token}".encode()):
                raise web.HTTPUnauthorized(text="bad or missing token")
        return await handler(request)

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    async def post_snapshot(request: web.Request) -> web.Response:
        try:
            payload = validate_snapshot(await request.json())
        except (json.JSONDecodeError, ValueError) as exc:
            raise web.HTTPBadRequest(text=str(exc)) from exc
        previous = store.latest_snapshot()
        snap = store.save_snapshot(payload, int(clock()))
        log.info("snapshot %s stored with %d members", snap.id, len(payload["members"]))
        if on_snapshot is not None:
            try:
                await on_snapshot(snap, previous)
            except Exception:
                log.exception("snapshot hook failed")
        return web.json_response({"stored": snap.id})

    async def get_schedule(_: web.Request) -> web.Response:
        return web.json_response(store.schedule_export(int(clock()), reminders))

    app = web.Application(middlewares=[auth], client_max_size=2 * 1024 * 1024)
    app.add_routes([
        web.get("/health", health),
        web.post("/snapshot", post_snapshot),
        web.get("/schedule", get_schedule),
    ])
    return app
