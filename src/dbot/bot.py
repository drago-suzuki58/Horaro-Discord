from loguru import logger
import discord
from discord.ext import tasks
import asyncio

import src.env as env
import src.dbot.notify as notify
import src.fetch_json as fetch_json

intents = discord.Intents.default()

bot = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(bot)

initialize_fetch_jsons = False

def bot_setup(bot: discord.Client, tree: discord.app_commands.CommandTree):
    @bot.event
    async def on_ready():
        logger.info(f"Logged in as {bot.user}")

        fetch_jsons.start()
        while not initialize_fetch_jsons:
            await asyncio.sleep(1)
        schedule_notifications.start()
        asyncio.create_task(notify.process_event_queue())
        logger.info("Started tasks Successfully")

        await tree.sync()
        logger.info("Synced commands Successfully")

    @tasks.loop(hours=24)
    async def fetch_jsons():
        data = await fetch_json.fetch_jsons_from_csv(env.EVENTS)
        await fetch_json.save_jsons(data, env.CACHE_DIR)
        global initialize_fetch_jsons
        initialize_fetch_jsons = True

    @tasks.loop(hours=6)
    async def schedule_notifications():
        await notify.schedule_notifications()