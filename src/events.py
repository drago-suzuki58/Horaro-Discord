from loguru import logger
import pandas as pd
from typing import Optional

import src.env as env

def add_event(url: str, notice: int, server: int, channel: int) -> None:
    df = pd.read_csv(env.EVENTS)

    new_event = pd.DataFrame({
        "url": [url],
        "notice": [notice],
        "server": [server],
        "channel": [channel]
    })
    new_df = pd.concat([new_event])

    df = pd.concat([df, new_df], ignore_index=True)
    df.to_csv(env.EVENTS, index=False)
    logger.info(f"Added new event: {url}")
    return

def remove_event(url) -> None:
    df = pd.read_csv(env.EVENTS)

    df = df[df["url"] != url]
    df.to_csv(env.EVENTS, index=False)
    logger.info(f"Removed event: {url}")
    return

def update_event(old_url: str, new_url: Optional[str] = None, notice: Optional[int] = None, server: Optional[int] = None, channel: Optional[int] = None) -> None:
    df = pd.read_csv(env.EVENTS)

    if new_url is not None:
        df.loc[df["url"] == old_url, "url"] = new_url
    if notice is not None:
        df.loc[df["url"] == old_url, "notice"] = notice
    if server is not None:
        df.loc[df["url"] == old_url, "server"] = server
    if channel is not None:
        df.loc[df["url"] == old_url, "channel"] = channel

    df.to_csv(env.EVENTS, index=False)
    logger.info(f"Updated event: {old_url}")
    return

def get_events() -> pd.DataFrame:
    return pd.read_csv(env.EVENTS)

def get_events_server(server: int) -> pd.DataFrame:
    df = pd.read_csv(env.EVENTS)
    return df[df["server"] == server]

def get_events_channel(channel: int) -> pd.DataFrame:
    df = pd.read_csv(env.EVENTS)
    return df[df["channel"] == channel]

# test code
#if __name__ == '__main__':
#    add_event("https://example.com/abc/abc", 10, 123, 123)
#    remove_event("https://example.com/abc/abc")
#    update_event("https://example.com/abc/abc", new_url"https://example.com/def/def", notice=20, server=456, channel=456)
#    logger.info("Finished")
