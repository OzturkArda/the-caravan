"""Bot settings, read from environment variables (see deploy/bot.env.example)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from .timeparse import zone


def _opt_int(env: Mapping[str, str], key: str) -> int | None:
    raw = env.get(key, "").strip()
    return int(raw) if raw else None


@dataclass(frozen=True)
class Config:
    discord_token: str
    api_token: str
    guild_id: int | None = None
    sessions_channel_id: int | None = None
    api_host: str = "0.0.0.0"
    api_port: int = 8787
    db_path: str = "caravan.db"
    group_tz: str = "Australia/Melbourne"
    reminder_offsets: tuple[int, ...] = (60, 15)
    default_duration_min: int = 180
    level_gap: int = 3
    alerts_channel_id: int | None = None

    @property
    def alerts_channel(self) -> int | None:
        """Where level-gap alerts go: ALERTS_CHANNEL_ID, else the sessions channel."""
        return self.alerts_channel_id or self.sessions_channel_id

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Config:
        missing = [k for k in ("DISCORD_TOKEN", "CARAVAN_API_TOKEN") if not env.get(k)]
        if missing:
            raise SystemExit(f"missing required settings: {', '.join(missing)}")
        offsets = tuple(
            sorted({int(x) for x in env.get("REMINDER_OFFSETS", "60,15").split(",") if x.strip()}, reverse=True)
        )
        cfg = cls(
            discord_token=env["DISCORD_TOKEN"],
            api_token=env["CARAVAN_API_TOKEN"],
            guild_id=_opt_int(env, "DISCORD_GUILD_ID"),
            sessions_channel_id=_opt_int(env, "SESSIONS_CHANNEL_ID"),
            api_host=env.get("CARAVAN_API_HOST", "0.0.0.0"),
            api_port=int(env.get("CARAVAN_API_PORT", "8787")),
            db_path=env.get("CARAVAN_DB", "caravan.db"),
            group_tz=env.get("GROUP_TZ", "Australia/Melbourne"),
            reminder_offsets=offsets,
            default_duration_min=int(env.get("DEFAULT_DURATION_MIN", "180")),
            level_gap=int(env.get("LEVEL_GAP", "3") or "0"),
            alerts_channel_id=_opt_int(env, "ALERTS_CHANNEL_ID"),
        )
        zone(cfg.group_tz)  # fail fast on a typo
        return cfg
