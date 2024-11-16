from loguru import logger
import discord


def bot_setup(bot: discord.Client, tree: discord.app_commands.CommandTree):
    @bot.event
    async def on_ready():
        logger.info(f"Logged in as {bot.user}")
        await tree.sync()