from loguru import logger
import discord

import src.env as env
from src.dbot.commands import setup_commands
from src.dbot.bot import bot_setup

intents = discord.Intents.default()

bot = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(bot)

if __name__ == "__main__":
    logger.add("log/file_{time}.log", rotation="1 week", enqueue=True)
    setup_commands(tree)
    bot_setup(bot, tree)

    try:
        logger.info("Starting bot...")
        bot.run(env.DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
