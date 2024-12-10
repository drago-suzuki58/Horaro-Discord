from loguru import logger
import asyncio
import aiofiles
import io
import pandas as pd
from typing import Optional

import src.env as env
import src.fetch_json as fetch_json

async def read_csv_async(file_path):
    loop = asyncio.get_event_loop()
    async with aiofiles.open(file_path, mode='r') as f:
        content = await f.read()
    df = await loop.run_in_executor(None, lambda: pd.read_csv(io.StringIO(content)))
    return df

async def to_csv_async(df, file_path):
    loop = asyncio.get_event_loop()
    csv_content = await loop.run_in_executor(None, lambda: df.to_csv(index=False))
    async with aiofiles.open(file_path, mode='w', newline='') as f:
        await f.write(csv_content)

async def add_event(url: str, notice: int, server: int, channel: int) -> None:
    df = await read_csv_async(env.EVENTS)

    new_event = pd.DataFrame({
        "url": [url],
        "notice": [notice],
        "server": [server],
        "channel": [channel]
    })

    df = pd.concat([df, new_event], ignore_index=True)
    await to_csv_async(df, env.EVENTS)
    logger.debug(f"Added new event: {url}")

async def remove_event(url) -> None:
    df = await read_csv_async(env.EVENTS)

    df = df[df["url"] != url]
    await to_csv_async(df, env.EVENTS)
    logger.debug(f"Removed event: {url}")

async def update_event(old_url: str, new_url: Optional[str] = None, notice: Optional[int] = None, server: Optional[int] = None, channel: Optional[int] = None) -> None:
    df = await read_csv_async(env.EVENTS)

    if new_url is not None:
        df.loc[df["url"] == old_url, "url"] = new_url
    if notice is not None:
        df.loc[df["url"] == old_url, "notice"] = notice
    if server is not None:
        df.loc[df["url"] == old_url, "server"] = server
    if channel is not None:
        df.loc[df["url"] == old_url, "channel"] = channel

    await to_csv_async(df, env.EVENTS)
    data = await fetch_json.fetch_json(new_url if new_url is not None else old_url)
    await fetch_json.save_json(data, env.CACHE_DIR) # type:ignore
    logger.info(f"Updated event: {old_url}")

async def get_events() -> pd.DataFrame:
    df = await read_csv_async(env.EVENTS)
    return df

async def get_events_url(url: str) -> pd.DataFrame:
    df = await read_csv_async(env.EVENTS)
    return df[df["url"] == url]

async def get_events_notice(notice: int) -> pd.DataFrame:
    df = await read_csv_async(env.EVENTS)
    return df[df["notice"] == notice]

async def get_events_server(server: int) -> pd.DataFrame:
    df = await read_csv_async(env.EVENTS)
    return df[df["server"] == server]

async def get_events_channel(channel: int) -> pd.DataFrame:
    df = await read_csv_async(env.EVENTS)
    return df[df["channel"] == channel]

async def get_events_multiple(url: Optional[str] = None, notice: Optional[int] = None, server: Optional[int] = None, channel: Optional[int] = None) -> pd.DataFrame:
    df = await read_csv_async(env.EVENTS)
    conditions = []
    if url is not None:
        conditions.append(df["url"] == url)
    if notice is not None:
        conditions.append(df["notice"] == notice)
    if server is not None:
        conditions.append(df["server"] == server)
    if channel is not None:
        conditions.append(df["channel"] == channel)

    if conditions:
        combined_conditions = conditions[0]
        for condition in conditions[1:]:
            combined_conditions &= condition
        return df[combined_conditions]
    return df

# test code
#if __name__ == '__main__':
#    add_event("https://example.com/abc/abc", 10, 123, 123)
#    remove_event("https://example.com/abc/abc")
#    update_event("https://example.com/abc/abc", new_url"https://example.com/def/def", notice=20, server=456, channel=456)
#    logger.info("Finished")
