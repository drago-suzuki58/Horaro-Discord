from loguru import logger
import discord
from discord.app_commands import describe
from datetime import timedelta

import src.env as env
import src.fetch_json as fetch_json
import src.events as events

class Confirm(discord.ui.View):
    def __init__(self, url: str):
        super().__init__()
        self.url = url

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        events.remove_event(self.url)
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

        guild_id = interaction.guild_id if interaction.guild_id is not None else -1 # If the interaction is not in a guild, set the guild_id to -1
        server_events = events.get_events_server(guild_id)
        data = fetch_json.fetch_jsons(server_events["url"].tolist())
        fetch_json.save_jsons(data, env.CACHE_DIR)

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

        guild_id = interaction.guild_id if interaction.guild_id is not None else -1
        channel_id = interaction.channel_id if interaction.channel_id is not None else -1

        server_events = events.get_events_multiple(url=url, server=guild_id)
        if len(server_events) > 0:
            await message.edit(content="Event already exists.")
            return

        data = fetch_json.fetch_json(url)
        if data:
            fetch_json.save_json(data, env.CACHE_DIR)
            events.add_event(url, notice, guild_id, channel_id)
            logger.debug(f"{interaction.guild_id} - Added event with URL: {url}")
            await message.edit(content="Added the event successfully!")
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
        view = Confirm(url)
        await interaction.response.send_message("Are you sure you want to remove the event?", view=view)

    @tree.command(
        name="list_events",
        description="List all events",
    )
    async def list_events(interaction: discord.Interaction):
        await interaction.response.defer()
        message = await interaction.followup.send("Listing events...", wait=True)

        guild_id = interaction.guild_id if interaction.guild_id is not None else -1
        server_events = events.get_events_server(guild_id)

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

        events.update_event(url, notice=notice)
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

        events.update_event(url, channel=channel)
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

        events.update_event(old_url, new_url=new_url)
        logger.debug(f"{interaction.guild_id} - Changed URL for event with URL: {old_url}")
        await message.edit(content="URL changed successfully!")

    @tree.command(
        name="create_server_event",
        description="Create a server event from a schedule",
    )
    @describe(
        url="URL of the event",
        description="Description of the event",
    )
    async def create_server_event(interaction: discord.Interaction, url: str, description: str=""):
        await interaction.response.defer()
        message = await interaction.followup.send("Creating event...", wait=True)

        guild_id = interaction.guild_id if interaction.guild_id is not None else -1

        if guild_id == -1:
            await message.edit(content="This command can only be used in a server.")
            return

        server_events = events.get_events_multiple(url=url, server=guild_id)
        if not server_events.empty:
            server_event = server_events.iloc[0]
        else:
            await message.edit(content="Event not found in this server. Please add the event first.")
            return
        data = fetch_json.get_json(server_event["url"])
        if data is None:
            await message.edit(content="Failed to fetch the event data. Please check the URL and try again.")
            return

        start_time = discord.utils.parse_time(data["schedule"]["start"])
        scheduled_t = discord.utils.parse_time(data["schedule"]["items"][-1]["scheduled"])
        end_time = scheduled_t + timedelta(seconds=data["schedule"]["items"][-1]["length_t"])

        try:
            scheduled_event = await interaction.guild.create_scheduled_event( # type: ignore
                name=data["schedule"]["name"],
                description=description,
                start_time=start_time,
                end_time=end_time,
                entity_type=discord.EntityType.external,
                privacy_level=discord.PrivacyLevel.guild_only,
                location=server_event["url"],
            )
            logger.debug(f"Created scheduled event: {scheduled_event.name}")
            await message.edit(content=f"Scheduled event '{scheduled_event.name}' created successfully!")
        except Exception as e:
            logger.error(f"Failed to create scheduled event: {e}")
            await message.edit(content=f"Failed to create scheduled event: {e}")

    logger.info("Commands set up successfully!")
