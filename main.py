import discord
import os
import asyncio
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

class CapyWebhook(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.load_extension("cogs.webhook")
        print("Webhook cog loaded successfully.")

bot = CapyWebhook()
bot.run(os.getenv("DISCORD_TOKEN"))