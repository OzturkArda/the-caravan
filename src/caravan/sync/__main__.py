"""Run the Caravan sync app: python -m caravan.sync

Settings come from the environment, or from ~/.config/caravan/sync.env
(KEY=VALUE lines): CARAVAN_API_URL, CARAVAN_API_TOKEN, and optionally
CARAVAN_WOW_ROOT, CARAVAN_WOW_ACCOUNT, CARAVAN_SV_PATH.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from pathlib import Path

from .service import ApiClient, SyncService
from .wow import default_root, find_savedvariables, wow_is_running

DEFAULT_ENV_FILE = Path.home() / ".config" / "caravan" / "sync.env"


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync The Caravan addon data with the Discord bot")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--interval", type=float, default=5, help="seconds between file checks")
    parser.add_argument("--once", action="store_true", help="run one sync pass and exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    env = {**load_env_file(args.env_file), **os.environ}
    for key in ("CARAVAN_API_URL", "CARAVAN_API_TOKEN"):
        if not env.get(key):
            raise SystemExit(f"{key} is not set (environment or {args.env_file})")

    if env.get("CARAVAN_SV_PATH"):
        sv_path = Path(env["CARAVAN_SV_PATH"])
    else:
        root = Path(env.get("CARAVAN_WOW_ROOT") or default_root())
        sv_path = find_savedvariables(root, env.get("CARAVAN_WOW_ACCOUNT") or None)
    logging.info("watching %s", sv_path)

    service = SyncService(sv_path, ApiClient(env["CARAVAN_API_URL"], env["CARAVAN_API_TOKEN"]), wow_is_running)
    if args.once:
        service.tick()
        return
    while True:
        try:
            service.tick()
        except Exception:
            logging.exception("sync pass failed")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
