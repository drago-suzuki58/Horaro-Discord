from loguru import logger
import discord
from discord.ext import tasks

import src.env as env
import src.fetch_json as fetch_json


def bot_setup(bot: discord.Client, tree: discord.app_commands.CommandTree):
    @bot.event
    async def on_ready():
        logger.info(f"Logged in as {bot.user}")
        await fetch_jsons()
        await tree.sync()
    
    @tasks.loop(hours=24)
    async def fetch_jsons():
        data = await fetch_json.fetch_jsons_from_csv(env.EVENTS)
        await fetch_json.save_jsons(data, env.CACHE_DIR)