from loguru import logger
import discord
from discord.app_commands import describe
from datetime import timedelta, datetime
import dateutil.parser
import pytz

import src.env as env
import src.events as events
import src.fetch_json as fetch_json
import src.dbot.notify as notify

class Confirm(discord.ui.View):
    def __init__(self, url: str):
        super().__init__()
        self.url = url

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await events.remove_event(self.url)
        logger.debug(f"{interaction.guild_id} - Removed event with URL: {self.url}")
        await interaction.response.edit_message(content="Removed the event successfully!", view=None)

    @discord.ui.button(label="No", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.debug(f"{interaction.guild_id} - Cancelled removal of event with URL: {self.url}")
        await interaction.response.edit_message(content="Event removal cancelled.", view=None)


def setup_commands(tree: discord.app_commands.CommandTree):
    logger.info("Setting up commands...")

    @tree.command(
        name="update_schedule",
        description="Update the Horaro schedule data",
    )
    async def update_schedule(interaction: discord.Interaction):
        await interaction.response.defer()
        message = await interaction.followup.send("Updating schedule...", wait=True)
        logger.debug(f"{interaction.guild_id} - update_schedule")

        guild_id = interaction.guild_id if interaction.guild_id is not None else -1 # If the interaction is not in a guild, set the guild_id to -1
        server_events = await events.get_events_server(guild_id)
        data = await fetch_json.fetch_jsons(server_events["url"].tolist())
        await fetch_json.save_jsons(data, env.CACHE_DIR)
        await notify.schedule_notifications()

        logger.debug(f"{interaction.guild_id} - Updated schedule data")
        await message.edit(content="Updated the schedule data successfully!")

    @tree.command(
        name="add_event",
        description="Add a new event to the list",
    )
    @describe(
        url="URL of the event",
        notice="How many minutes before to send the notification"
    )
    async def add_event(interaction: discord.Interaction, url: str, notice: int = 10):
        await interaction.response.defer()
        message = await interaction.followup.send("Adding event...", wait=True)
        logger.debug(f"{interaction.guild_id} - add_event")

        guild_id = interaction.guild_id if interaction.guild_id is not None else -1
        channel_id = interaction.channel_id if interaction.channel_id is not None else -1

        server_events = await events.get_events_multiple(url=url, server=guild_id)
        if len(server_events) > 0:
            await message.edit(content="Event already exists.")
            return

        data = await fetch_json.fetch_json(url)
        if data:
            await fetch_json.save_json(data, env.CACHE_DIR)
            await events.add_event(url, notice, guild_id, channel_id)
            await notify.schedule_notifications()

            embed = discord.Embed(
                title=data["schedule"]["name"],
                color=5872610,
                url=url,
                timestamp=dateutil.parser.parse(data["schedule"]["start"]),
                description=f"{data['schedule']['description']}"
                )

            logger.debug(f"{interaction.guild_id} - Added event with URL: {url}")
            await message.edit(content="Added the event successfully!", embed=embed)
        else:
            logger.warning(f"{interaction.guild_id} - Failed to fetch event data for URL: {url}")
            await message.edit(content="Failed to fetch the event data. Please check the URL and try again.")

    @tree.command(
        name="remove_event",
        description="Remove an event from the list",
    )
    @describe(
        url="URL of the event",
    )
    async def remove_event(interaction: discord.Interaction, url: str):
        logger.debug(f"{interaction.guild_id} - remove_event")
        view = Confirm(url)
        await interaction.response.send_message("Are you sure you want to remove the event?", view=view)

    @tree.command(
        name="list_events",
        description="List all events",
    )
    async def list_events(interaction: discord.Interaction):
        await interaction.response.defer()
        message = await interaction.followup.send("Listing events...", wait=True)
        logger.debug(f"{interaction.guild_id} - list_events")

        guild_id = interaction.guild_id if interaction.guild_id is not None else -1
        server_events = await events.get_events_server(guild_id)

        if len(server_events) > 0:
            embed = discord.Embed(title="Events List", color=4526227)
            for _, row in server_events.iterrows():
                channel_name = "Unknown Channel"
                if interaction.guild:
                    channel = interaction.guild.get_channel(row['channel'])
                    if channel:
                        channel_name = f"[#{channel.name}](https://discord.com/channels/{interaction.guild.id}/{channel.id})"
                    else:
                        channel_name = "Unknown Channel"
                embed.add_field(
                    name=row['url'],
                    value=f"Notice: {row['notice']} minutes\nChannel: {channel_name}",
                    inline=False
                )
            logger.debug(f"{interaction.guild_id} - Listed events: {len(embed.fields)}")
            await message.edit(content=None, embed=embed)
        else:
            await message.edit(content="No events found.")

    @tree.command(
        name="change_notice",
        description="Change the notice time for an event",
    )
    @describe(
        url="URL of the event",
        notice="New notice time in minutes"
    )
    async def change_notice(interaction: discord.Interaction, url: str, notice: int):
        await interaction.response.defer()
        message = await interaction.followup.send("Changing notice time...", wait=True)
        logger.debug(f"{interaction.guild_id} - change_notice")

        await events.update_event(url, notice=notice)
        logger.debug(f"{interaction.guild_id} - Changed notice time for event with URL: {url}")
        await message.edit(content="Notice time changed successfully!")

    @tree.command(
        name="change_channel",
        description="Change the channel for an event",
    )
    @describe(
        url="URL of the event",
        channel="New channel ID"
    )
    async def change_channel(interaction: discord.Interaction, url: str, channel: int):
        await interaction.response.defer()
        message = await interaction.followup.send("Changing channel...", wait=True)
        logger.debug(f"{interaction.guild_id} - change_channel")

        await events.update_event(url, channel=channel)
        logger.debug(f"{interaction.guild_id} - Changed channel for event with URL: {url}")
        await message.edit(content="Channel changed successfully!")

    @tree.command(
        name="change_url",
        description="Change the URL of an event",
    )
    @describe(
        old_url="Old URL of the event",
        new_url="New URL of the event"
    )
    async def change_url(interaction: discord.Interaction, old_url: str, new_url: str):
        await interaction.response.defer()
        message = await interaction.followup.send("Changing URL...", wait=True)
        logger.debug(f"{interaction.guild_id} - change_url")

        await events.update_event(old_url, new_url=new_url)
        logger.debug(f"{interaction.guild_id} - Changed URL for event with URL: {old_url}")
        await message.edit(content="URL changed successfully!")

    @tree.command(
        name="create_server_event",
        description="Create a server event from a schedule",
    )
    @describe(
        url="URL of the event",
    )
    async def create_server_event(interaction: discord.Interaction, url: str, description: str=""):
        await interaction.response.defer()
        message = await interaction.followup.send("Creating event...", wait=True)
        logger.debug(f"{interaction.guild_id} - create_server_event")

        guild_id = interaction.guild_id if interaction.guild_id is not None else -1

        if guild_id == -1:
            await message.edit(content="This command can only be used in a server.")
            return

        server_events = await events.get_events_multiple(url=url, server=guild_id)
        if not server_events.empty:
            server_event = server_events.iloc[0]
        else:
            await message.edit(content="Event not found in this server. Please add the event first.")
            return

        data = await fetch_json.get_json(server_event["url"])
        if data is None:
            await message.edit(content="Failed to get the event data. Please check the URL and try again.")
            return

        start_time = discord.utils.parse_time(data["schedule"]["start"])
        if len(data["schedule"]["items"]) == 0:
            end_time = start_time + timedelta(hours=1)
        else:
            scheduled_t = discord.utils.parse_time(data["schedule"]["items"][-1]["scheduled"])
            end_time = scheduled_t + timedelta(seconds=data["schedule"]["items"][-1]["length_t"])

        timezone = pytz.timezone(data["schedule"]["timezone"])
        now = datetime.now(tz=timezone)

        if start_time <= now or end_time <= now:
            await message.edit(content="Cannot schedule event in the past. Please check the event times.")
            return

        existing_events = await interaction.guild.fetch_scheduled_events() # type: ignore
        for existing_event in existing_events:
            if existing_event.name == data["schedule"]["name"]:
                await message.edit(content=f"Scheduled event with the name '{existing_event.name}' already exists.")
                return

        try:
            scheduled_event = await interaction.guild.create_scheduled_event( # type: ignore
                name=data["schedule"]["name"],
                description=data["schedule"]["description"],
                start_time=start_time,
                end_time=end_time,
                entity_type=discord.EntityType.external,
                privacy_level=discord.PrivacyLevel.guild_only,
                location=server_event["url"],
            )
            logger.debug(f"{interaction.guild_id} - Created scheduled event: {scheduled_event.name}")
            await message.edit(content=f"Scheduled event '{scheduled_event.name} created successfully!")
        except Exception as e:
            logger.error(f"Failed to create scheduled event: {e}")
            await message.edit(content=f"Failed to create scheduled event: {e}")

    @tree.command(
        name="create_server_event_all",
        description="Create all server events from the schedule",
    )
    async def create_server_event_all(interaction: discord.Interaction):
        await interaction.response.defer()
        message = await interaction.followup.send("Creating all events...", wait=True)
        logger.debug(f"{interaction.guild_id} - create_server_event_all")

        created_events = 0

        guild_id = interaction.guild_id if interaction.guild_id is not None else -1

        if guild_id == -1:
            await message.edit(content="This command can only be used in a server.")
            return

        server_events = await events.get_events_server(guild_id)
        if server_events.empty:
            logger.debug(f"{interaction.guild_id} - No events found in this server")
            await message.edit(content="No events found in this server. Please add events first.")
            return

        data = await fetch_json.get_jsons(server_events["url"].tolist())
        if data is None:
            logger.error(f"{interaction.guild_id} - Failed to get event data")
            await message.edit(content="Failed to get the event data. Please check the URL and try again.")
            return

        existing_events = await interaction.guild.fetch_scheduled_events() # type: ignore
        for event, server_event in zip(data, server_events.to_dict(orient="records")):
            try:
                start_time = discord.utils.parse_time(event["schedule"]["start"])
                if len(event["schedule"]["items"]) == 0:
                    end_time = start_time + timedelta(hours=1)
                else:
                    scheduled_t = discord.utils.parse_time(event["schedule"]["items"][-1]["scheduled"])
                    end_time = scheduled_t + timedelta(seconds=event["schedule"]["items"][-1]["length_t"])

                timezone = pytz.timezone(event["schedule"]["timezone"])
                now = datetime.now(tz=timezone)

                if start_time <= now or end_time <= now:
                    logger.debug(f"{interaction.guild_id} - Cannot schedule event in the past. Please check the event times.")
                    message = await message.edit(content=f"{message.content}\nCannot schedule event in the past. Please check the event times.")
                    continue

                event_exists = False
                for existing_event in existing_events:
                    if existing_event.name == event["schedule"]["name"]:
                        logger.debug(f"{interaction.guild_id} - Scheduled event with the name '{existing_event.name}' already exists")
                        message = await message.edit(content=f"{message.content}\nScheduled event with the name '{existing_event.name}' already exists.")
                        event_exists = True
                        break
                if event_exists:
                    continue

                scheduled_event = await interaction.guild.create_scheduled_event( # type: ignore
                    name=event["schedule"]["name"],
                    description=event["schedule"]["description"],
                    start_time=start_time,
                    end_time=end_time,
                    entity_type=discord.EntityType.external,
                    privacy_level=discord.PrivacyLevel.guild_only,
                    location=server_event["url"],
                )
                created_events += 1
                logger.debug(f"{interaction.guild_id} - Created scheduled event: {scheduled_event.name}")
            except Exception as e:
                logger.error(f"Failed to create scheduled event: {e}")
                message = await message.edit(content=f"{message.content}\nFailed to create scheduled event: {e}")
                continue

        if created_events == 0:
            logger.debug(f"{interaction.guild_id} - No events created")
            await message.edit(content="No events created.")
        else:
            logger.debug(f"{interaction.guild_id} - All scheduled events({created_events}) created successfully")
            await message.edit(content=f"All scheduled events({created_events}) created successfully!")

    @tree.command(
        name="get_now_program",
        description="Get the current program",
    )
    async def get_now_program(interaction: discord.Interaction):
        await interaction.response.defer()
        message = await interaction.followup.send("Getting the current program...", wait=True)
        logger.debug(f"{interaction.guild_id} - get_now_program")

        guild_id = interaction.guild_id if interaction.guild_id is not None else -1
        server_events = await events.get_events_server(guild_id)

        embeds = []

        if len(server_events) == 0:
            logger.debug(f"{interaction.guild_id} - No events found in this server")
            return

        for _, info in server_events.iterrows():
            event_data = await fetch_json.get_json(info["url"])
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

            event_start_time = dateutil.parser.parse(event_start_time_str)
            monitor_start_time = event_start_time - timedelta(minutes=info['notice'] * 2)
            timezone = pytz.timezone(event_data["schedule"]["timezone"])
            now = datetime.now(timezone)

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
                scheduled_time = dateutil.parser.parse(scheduled_str)

                if scheduled_time < now < scheduled_time + timedelta(seconds=item["length_t"]):
                    embed = discord.Embed(
                        title=event_data["schedule"]["name"],
                        color=5025616,
                        url=info["url"],
                        timestamp=scheduled_time,
                        description=f"{item['data'][0]}"
                    )
                    logger.debug(f"{interaction.guild_id} - Found current program: {item['data'][0]}")
                    embeds.append(embed)
                    continue
                else:
                    pass
        await message.edit(content=None, embeds=embeds if embeds else [])

    logger.info("Commands set up successfully!")
