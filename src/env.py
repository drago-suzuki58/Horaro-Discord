from loguru import logger
from dotenv import load_dotenv
import os

load_dotenv()

logger.debug("Loading environment variables...")

# Discord
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or "YOUR_DISCORD_BOT_TOKEN"

# Files
CACHE_DIR = os.getenv("CACHE_DIR") or "./cache"
EVENTS = os.getenv("EVENTS") or "events.csv"

# Language
LANG = os.getenv("LANG") or "en"

# Periodic loop
FETCH_JSONS_INTERVAL = float(os.getenv("FETCH_JSONS_INTERVAL") or 24) # hours
SCHEDULE_NOTIFICATIONS_INTERVAL = float(os.getenv("SCHEDULE_NOTIFICATIONS_INTERVAL") or 6) # hours
