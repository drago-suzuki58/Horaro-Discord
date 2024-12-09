from loguru import logger
import asyncio
import aiohttp
import pandas as pd
import json
import os
from typing import Optional
from urllib.parse import urlparse

import src.env as env
import src.dbot.notify as notify

async def fetch_json(url: str) -> Optional[dict]:
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{url}.json") as response:
                if response.status == 404:
                    logger.error(f"404 Not Found: {url}.json")
                    return None
                response.raise_for_status()
                logger.debug(f"Fetched {url}.json")
                return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"Failed to fetch {url}.json: {e}")
            return None

async def fetch_jsons(urls: list[str]) -> list[dict]:
    jsons = []
    for url in urls:
        json_data = await fetch_json(url)
        if json_data:
            jsons.append(json_data)
        await asyncio.sleep(0.5)  # 0.5秒の遅延を挟む
    logger.debug(f"Fetched {len(jsons)} json files")
    return jsons

async def fetch_jsons_from_csv(csv_path: str) -> list[dict]:
    urls = pd.read_csv(csv_path)["url"].tolist()
    logger.debug(f"Fetching {len(urls)} json files")
    return await fetch_jsons(urls)


async def save_json(json_data: dict, base_dir: str) -> None:
    url_path = json_data["schedule"]["url"].lstrip("/") # URLの先頭のスラッシュを削除
    path = os.path.join(base_dir, f"{url_path}.json")
    logger.debug(f"Saving {path}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=4)
    return

async def save_jsons(json_datas: list[dict], base_dir: str) -> None:
    for json_data in json_datas:
        await save_json(json_data, base_dir)
    logger.debug(f"Saved {len(json_datas)} json files to {base_dir}")
    return


async def get_json(url: str) -> Optional[dict]:
    parsed_url = urlparse(url)
    url_path = parsed_url.path.lstrip("/")
    path = os.path.join(env.CACHE_DIR, f"{url_path}.json")
    if not os.path.exists(path):
        logger.debug(f"File not found: {path}")
        data = await fetch_json(url)
        if data:
            await save_json(data, env.CACHE_DIR)
            return data
        else:
            logger.error(f"File not found: {path}")
            return None
    else:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

async def get_jsons(urls: list[str]) -> list[dict]:
    jsons = []
    for u in urls:
        json_data = await get_json(u)
        if json_data:
            jsons.append(json_data)
    logger.debug(f"Got {len(jsons)} json files")
    return jsons

# test code
#if __name__ == '__main__':
#    json_datas = fetch_jsons_from_csv(env.EVENTS)
#    save_jsons(json_datas, env.CACHE_DIR)
#    logger.info("Finished")
