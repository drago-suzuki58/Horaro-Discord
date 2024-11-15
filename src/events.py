from loguru import logger
import pandas as pd
from typing import Optional

EVENTS = "events.csv"

def add_event(url: str, notice: int, server: int, channel: int):
    df = pd.read_csv(EVENTS)

    new_event = pd.DataFrame({
        "url": [url],
        "notice": [notice],
        "server": [server],
        "channel": [channel]
    })
    new_df = pd.concat([new_event])

    df = pd.concat([df, new_df], ignore_index=True)
    df.to_csv(EVENTS, index=False)
    logger.info(f"Added new event: {url}")

def remove_event(url):
    df = pd.read_csv(EVENTS)

    df = df[df["url"] != url]
    df.to_csv(EVENTS, index=False)
    logger.info(f"Removed event: {url}")

def update_event(old_url: str, new_url: Optional[str] = None, notice: Optional[int] = None, server: Optional[int] = None, channel: Optional[int] = None):
    df = pd.read_csv(EVENTS)

    if new_url is not None:
        df.loc[df["url"] == old_url, "url"] = new_url
    if notice is not None:
        df.loc[df["url"] == old_url, "notice"] = notice
    if server is not None:
        df.loc[df["url"] == old_url, "server"] = server
    if channel is not None:
        df.loc[df["url"] == old_url, "channel"] = channel

    df.to_csv(EVENTS, index=False)
    logger.info(f"Updated event: {old_url}")

def get_events():
    return pd.read_csv(EVENTS)

def get_events_server(server: int):
    df = pd.read_csv(EVENTS)
    return df[df["server"] == server]

def get_events_channel(channel: int):
    df = pd.read_csv(EVENTS)
    return df[df["channel"] == channel]

# test code
#if __name__ == '__main__':
#    add_event("https://example.com/abc/abc", 10, 123, 123)
#    remove_event("https://example.com/abc/abc")
#    update_event("https://example.com/abc/abc", new_url"https://example.com/def/def", notice=20, server=456, channel=456)
#    logger.info("Finished")
