from loguru import logger
import requests
import pandas as pd
import json
import os
from typing import Optional

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


def save_json(json_data: dict, base_dir: str):
    url_path = json_data["schedule"]["url"].lstrip("/") # URLの先頭のスラッシュを削除
    path = os.path.join(base_dir, f"{url_path}.json")
    logger.debug(f"Saving {path}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=4)

def save_jsons(json_datas: list[dict], base_dir: str):
    for json_data in json_datas:
        save_json(json_data, base_dir)
    logger.debug(f"Saved {len(json_datas)} json files to {base_dir}")

# test code
#if __name__ == '__main__':
#    json_datas = fetch_jsons_from_csv("events.csv")
#    save_jsons(json_datas, "/dev/cache/")
#    logger.info("Finished")
