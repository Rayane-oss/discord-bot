import discord
from discord.ext import commands
import os
import random
import json
from datetime import datetime, timedelta

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "economy.json"

# Load or create economy data
def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def ensure_user(data, user_id):
    if str(user_id) not in data:
        data[str(user_id)] = {
            "balance": 0,
            "last_daily": None,
            "inventory": {}
        }

# Simple shop items
SHOP_ITEMS = {
    "sword": {"price": 500, "desc": "A shiny sword to fight monsters."},
    "shield": {"price": 300, "desc": "A sturdy shield for protection."},
    "potion": {"price": 150, "desc": "Heals you during battles."}
}

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")

@bot.comman
