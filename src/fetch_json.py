from loguru import logger
import requests
import pandas as pd
import json
import os
from urllib.parse import urlparse
from typing import Optional

import src.env as env

def fetch_json(url: str) -> Optional[dict]:
    try:
        response = requests.get(f"{url}.json")
        if response.status_code == 404:
            logger.error(f"404 Not Found: {url}.json")
            return None
        response.raise_for_status()
        logger.debug(f"Fetched {url}.json")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch {url}.json: {e}")
        return None

def fetch_jsons(url: list[str]) -> list[dict]:
    jsons = []
    for u in url:
        json_data = fetch_json(u)
        if json_data:
            jsons.append(json_data)
    logger.debug(f"Fetched {len(jsons)} json files")
    return jsons

def fetch_jsons_from_csv(csv_path: str) -> list[dict]:
    urls = pd.read_csv(csv_path)["url"].tolist()
    logger.debug(f"Fetching {len(urls)} json files")
    return fetch_jsons(urls)


def save_json(json_data: dict, base_dir: str) -> None:
    url_path = json_data["schedule"]["url"].lstrip("/") # URLの先頭のスラッシュを削除
    path = os.path.join(base_dir, f"{url_path}.json")
    logger.debug(f"Saving {path}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=4)
    return

def save_jsons(json_datas: list[dict], base_dir: str) -> None:
    for json_data in json_datas:
        save_json(json_data, base_dir)
    logger.debug(f"Saved {len(json_datas)} json files to {base_dir}")
    return


def get_json(url: str) -> Optional[dict]:
    parsed_url = urlparse(url)
    url_path = parsed_url.path.lstrip("/")
    path = os.path.join(env.CACHE_DIR, f"{url_path}.json")
    if not os.path.exists(path):
        logger.debug(f"File not found: {path}")
        data = fetch_json(url)
        if data:
            save_json(data, env.CACHE_DIR)
            return data
        else:
            logger.error(f"File not found: {path}")
            return None
    else:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

def get_jsons(urls: list[str]) -> list[dict]:
    jsons = []
    for u in urls:
        json_data = get_json(u)
        if json_data:
            jsons.append(json_data)
    logger.debug(f"Got {len(jsons)} json files")
    return jsons

# test code
#if __name__ == '__main__':
#    json_datas = fetch_jsons_from_csv(env.EVENTS)
#    save_jsons(json_datas, env.CACHE_DIR)
#    logger.info("Finished")
