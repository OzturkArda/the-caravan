"""Run the Caravan Discord bot: python -m caravan.bot"""

from __future__ import annotations

import logging

from .config import Config
from .db import Store
from .discord_app import CaravanBot


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = Config.from_env()
    store = Store(config.db_path)
    bot = CaravanBot(config, store)
    bot.run(config.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
