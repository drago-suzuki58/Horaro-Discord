from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    discord_token: str
    database_path: str
    log_level: str


def load_config() -> Config:
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise SystemExit("DISCORD_TOKEN is not set. Copy .env.example to .env and set the token.")
    return Config(
        discord_token=token,
        database_path=os.getenv("DATABASE_PATH") or "data/horaro-discord.db",
        log_level=(os.getenv("LOG_LEVEL") or "INFO").upper(),
    )
