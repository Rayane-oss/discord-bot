import discord
from discord.ext import commands
import os

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} - Ready!")

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")

if __name__ == "__main__":
    token = os.environ.get("TOKEN")
    if not token:
        print("ERROR: TOKEN env var missing!")
    else:
        bot.run(token)
