from loguru import logger
import pandas as pd
import os
import random
from faker import Faker

EVENTS = "dev/events.csv"
fake = Faker()

def generate_events(n: int):
    urls = [f"{fake.url()}/{fake.slug()}/{fake.slug()}" for _ in range(n)]
    notices = [random.randint(1, 100) for _ in range(n)]
    servers = [random.randint(100000000000000000, 999999999999999999) for _ in range(n)]
    channels = [random.randint(100000000000000000, 999999999999999999) for _ in range(n)]

    df = pd.DataFrame({
        "url": urls,
        "notice": notices,
        "server": servers,
        "channel": channels
    })
    if os.path.exists(EVENTS):
        df.to_csv(EVENTS, mode='a', header=False, index=False)
    else:
        df.to_csv(EVENTS, index=False)
    logger.info(f"Generated {n} events")

# test code
if __name__ == '__main__':
    generate_events(100)
    logger.info("Finished")