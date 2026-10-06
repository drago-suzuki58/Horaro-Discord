from __future__ import annotations

import asyncio
import contextlib
import logging

import aiohttp
import discord

from .bot import HoraroBot
from .config import load_config
from .store import Store


async def run() -> None:
    config = load_config()
    discord.utils.setup_logging(level=logging.getLevelNamesMapping()[config.log_level])
    store = Store(config.database_path)
    try:
        async with aiohttp.ClientSession() as session, HoraroBot(store, session) as bot:
            await bot.start(config.discord_token)
    finally:
        store.close()


def main() -> None:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run())


if __name__ == "__main__":
    main()
