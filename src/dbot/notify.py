from loguru import logger
import discord
import asyncio
import datetime
import heapq

import src.dbot.bot as bot
import src.events as events
import src.fetch_json as fetch_json


event_queue = []

async def send_notification(server_id: int, channel_id: int, message: str):
    guild = bot.bot.get_guild(server_id)
    if guild is None:
        logger.error(f"Guild not found: {server_id}")
        return

    channel = guild.get_channel(channel_id)
    if channel is None:
        logger.error(f"Channel not found: {channel_id}")
        return

    if isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
        await channel.send(message)
    else:
        logger.error(f"Channel type not supported for sending messages: {type(channel).__name__}")

async def schedule_notifications():
    logger.debug("Scheduling notifications start...")
    events_info = await events.get_events()
    now = datetime.datetime.now(datetime.timezone.utc)

    for _, info in events_info.iterrows():
        event_data = await fetch_json.get_json(info['url'])
        if event_data is None:
            logger.debug(f"Failed to get event data: {info['url']}")
            continue

        items = event_data["schedule"]["items"]
        if not items:
            logger.debug(f"No items found in event data: {info['url']}")
            continue

        event_start_time_str = event_data["schedule"]["start"]
        if not event_start_time_str:
            logger.debug(f"No start time found in event data: {info['url']}")
            continue

        event_start_time = datetime.datetime.fromisoformat(event_start_time_str)
        monitor_start_time = event_start_time - datetime.timedelta(minutes=info['notice'] * 2)

        if now < monitor_start_time:
            logger.debug(f"Event not yet in monitoring range: {info['url']}")
            continue

        for item in items:
            scheduled_str = item.get("scheduled", None)
            if not scheduled_str:
                logger.debug(f"No scheduled time found in item: {item['data'][0]}")
                continue
            scheduled_time = datetime.datetime.fromisoformat(scheduled_str)
            notice_time = scheduled_time - datetime.timedelta(minutes=info["notice"])

            if now > scheduled_time:
                if scheduled_time + datetime.timedelta(seconds=item["length_t"]) > now:
                    logger.debug(f"Event already started: {item['data'][0]}")
                    await send_notification(
                        info["server"],
                        info["channel"],
                        f"{event_data['schedule']['name']}'s program has already started!"
                    )
                    continue
                else:
                    logger.debug(f"Event already finished: {item['data'][0]}")
                    continue

            if (scheduled_time - now).total_seconds() > 3600 * 6:
                logger.debug(f"Event too far in the future: {item['data'][0]}")
                continue

            if scheduled_time > now - datetime.timedelta(minutes=info["notice"]):
                logger.debug(f"Event has already passed notice time: {item['data'][0]}")
                await send_notification(
                    info["server"],
                    info["channel"],
                    f"{event_data['schedule']['name']}'s program has already started!"
                )
                continue

            logger.debug(f"Scheduled notification: {item['data'][0]} Notice time: {notice_time}")
            heapq.heappush(event_queue, (notice_time, {
                "server": info["server"],
                "channel": info["channel"],
                "message": f"{event_data['schedule']['name']}'s next program will start in {info['notice']} minutes!",
                "event_time": scheduled_time
            }))

async def process_event_queue():
    while True:
        if not event_queue or event_queue is []:
            await asyncio.sleep(60)
            continue

        notice_timestamp, notification_info = heapq.heappop(event_queue)
        notice_time = datetime.datetime.fromtimestamp(notice_timestamp, tz=datetime.timezone.utc)

        now = datetime.datetime.now(datetime.timezone.utc)
        wait_seconds = (notice_time - now).total_seconds()
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
        logger.debug(f"Sending notification: {notification_info['message']}")
        await send_notification(
            notification_info["server"],
            notification_info["channel"],
            notification_info["message"]
        )
