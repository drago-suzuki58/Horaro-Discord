from loguru import logger
import discord

def setup_commands(tree: discord.app_commands.CommandTree):
    logger.info("Setting up commands...")
    # TODO: Add some commands here
    @tree.command(
        name="hello",
        description="Says hello"
    )
    async def hello(interaction: discord.Interaction):
        await interaction.response.send_message('Hello, world!')

    logger.info("Commands set up successfully!")
