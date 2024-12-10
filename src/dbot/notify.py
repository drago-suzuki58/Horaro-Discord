from loguru import logger
import discord
import asyncio
import datetime
import heapq
import pytz

import src.env as env
import src.dbot.bot as bot
import src.events as events
import src.fetch_json as fetch_json


event_queue = []
sent_notifications = set()

async def send_notification(server_id: int, channel_id: int, message: str, embed: discord.Embed):
    guild = bot.bot.get_guild(server_id)
    if guild is None:
        logger.error(f"Guild not found: {server_id}")
        return

    channel = guild.get_channel(channel_id)
    if channel is None:
        logger.error(f"Channel not found: {channel_id}")
        return

    if isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
        await channel.send(message, embed=embed)
    else:
        logger.error(f"Channel type not supported for sending messages: {type(channel).__name__}")

async def schedule_notifications():
    logger.debug("Scheduling notifications start...")
    events_info = await events.get_events()

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
        timezone = pytz.timezone(event_data["schedule"]["timezone"])
        now = datetime.datetime.now(timezone)

        if now < monitor_start_time:
            logger.debug(f"Event not yet in monitoring range: {info['url']}")
            continue

        logger.debug(f"Monitoring event: {info['url']} Start time: {event_start_time}")
        for item in items:
            scheduled_str = item.get("scheduled", None)
            if not scheduled_str:
                logger.debug(f"No scheduled time found in item: {item['data'][0]}")
                break
            else:
                pass
            scheduled_time = datetime.datetime.fromisoformat(scheduled_str)
            notice_time = scheduled_time - datetime.timedelta(minutes=info["notice"])
            
            notification_id = f"{info['server']}_{info['channel']}_{scheduled_time.timestamp()}"

            if now > scheduled_time:
                if scheduled_time + datetime.timedelta(seconds=item["length_t"]) > now:
                    if notification_id not in sent_notifications:
                        logger.debug(f"Program already started: {item['data'][0]}")
                        description = "\n".join([str(i) for i in item['data']])
                        embed = discord.Embed(title="Program detail", url=info["url"], color=5025616, description=description, timestamp=scheduled_time)
                        heapq.heappush(event_queue, (float(notice_time.timestamp()), {
                            "server": info["server"],
                            "channel": info["channel"],
                            "message": f"{event_data['schedule']['name']}'s next program is already started in {int((now - scheduled_time).total_seconds() / 60)} minutes ago!",
                            "embed": embed,
                            "event_time": scheduled_time,
                            "timezone": timezone
                        }))
                        sent_notifications.add(notification_id)
                    else:
                        logger.debug(f"Program notice already sent: {item['data'][0]}")
                        continue
                else:
                    logger.debug(f"Program are already finished: {item['data'][0]}")
                    continue
            else:
                pass

            if (scheduled_time - now).total_seconds() > 3600 * env.SCHEDULE_NOTIFICATIONS_INTERVAL:
                logger.debug(f"Event too far in the future: {item['data'][0]}")
                break
            else:
                pass

            if (scheduled_time < now and scheduled_time + datetime.timedelta(seconds=info["notice"]) > now):
                if notification_id not in sent_notifications:
                    logger.debug(f"Program notify deley: {item['data'][0]}")
                    description = "\n".join([str(i) for i in item['data']])
                    embed = discord.Embed(title="Program detail", url=info["url"], color=5025616, description=description, timestamp=scheduled_time)
                    time_diff = now.timestamp() - (scheduled_time - datetime.timedelta(minutes=info['notice'])).timestamp()
                    minutes_diff = int(time_diff / 60)
                    heapq.heappush(event_queue, (float(notice_time.timestamp()), {
                        "server": info["server"],
                        "channel": info["channel"],
                        "message": f"{event_data['schedule']['name']}'s next program will start in {minutes_diff} minutes!",
                        "embed": embed,
                        "event_time": scheduled_time,
                        "timezone": timezone
                    }))
                    sent_notifications.add(notification_id)
                    continue
                else:
                    logger.debug(f"Program notice already sent: {item['data'][0]}")
                    continue

            if not is_duplicate_event(event_queue, float(notice_time.timestamp()), info["server"], info["channel"], scheduled_time):
                if notification_id not in sent_notifications:
                    logger.debug(f"Scheduled notification: {item['data'][0]} Notice time: {notice_time}")

                    description = "\n".join([str(i) for i in item['data']])
                    embed = discord.Embed(title="Program detail", url=info["url"], color=5025616, description=description, timestamp=scheduled_time)
                    heapq.heappush(event_queue, (float(notice_time.timestamp()), {
                        "server": info["server"],
                        "channel": info["channel"],
                        "message": f"{event_data['schedule']['name']}'s next program will start in {info['notice']} minutes!",
                        "embed": embed,
                        "event_time": scheduled_time,
                        "timezone": timezone
                    }))
                    sent_notifications.add(notification_id)
                else:
                    logger.debug(f"Program notice already sent: {item['data'][0]}")
            else:
                logger.debug(f"Duplicate event found: {item['data'][0]}")

async def process_event_queue():
    while True:
        if not event_queue or event_queue is []:
            await asyncio.sleep(1)
            continue

        notice_timestamp, notification_info = heapq.heappop(event_queue)
        notice_time = datetime.datetime.fromtimestamp(notice_timestamp, tz=notification_info["timezone"])
        now = datetime.datetime.now(notification_info["timezone"])

        wait_seconds = (notice_time - now).total_seconds()
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
            logger.debug(f"Sending notification: {notification_info['message']}")
            await send_notification(
                notification_info["server"],
                notification_info["channel"],
                notification_info["message"],
                notification_info["embed"]
            )
        else:
            logger.debug(f"Sending notification delay: {notification_info['message']}")
            await send_notification(
                notification_info["server"],
                notification_info["channel"],
                notification_info["message"],
                notification_info["embed"]
            )

def is_duplicate_event(event_queue, notice_timestamp, server, channel, event_time):
    for event in event_queue:
        if (abs(event[0] - notice_timestamp) < 1.0 and
            event[1]["server"] == server and
            event[1]["channel"] == channel and
            event[1]["event_time"] == event_time):
            return True
    return False
