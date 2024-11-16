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
