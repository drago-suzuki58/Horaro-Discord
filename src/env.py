from loguru import logger
from dotenv import load_dotenv
import os

load_dotenv()

logger.debug("Loading environment variables...")
# Discord
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN") or "YOUR_DISCORD_TOKEN"
