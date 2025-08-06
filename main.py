
import discord
from discord.ext import commands, tasks
import os, random, json
from datetime import datetime, timedelta

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
DATA = "economy.json"
MAX_BET = 250_000
CD = 2400  # 40 minutes cooldown

CRYPTOS = {
    "BTC": {"price": 30000, "desc": "Bitcoin"},
    "ETH": {"price": 2000, "desc": "Ethereum"},
    "DOGE": {"price": 0.1, "desc": "Dogecoin"},
    "XRP": {"price": 0.5, "desc": "Ripple"},
    "SOL": {"price": 25, "desc": "Solana"},
}

def load():
    try:
        with open(DATA) as f: return json.load(f)
    except: return {}

def save(data):
    with open(DATA, "w") as f: json.dump(data, f, indent=2)

def ensure(data, uid):
    if uid not in data:
        data[uid] = {"bal": 1000, "exp": 0, "lvl": 1, "daily": None, "work": None, "inv": {}}

def cd_left(last):
    if not last: return 0
    diff = (datetime.utcnow() - datetime.fromisoformat(last)).total_seconds()
    return max(0, CD - diff)

def add_exp(user, amt):
    user["exp"] += amt
    while user["exp"] >= 1000:
        user["exp"] -= 1000
        user["lvl"] += 1

@tasks.loop(hours=1)
async def update_crypto_prices():
    for sym in CRYPTOS:
        base = CRYPTOS[sym]["price"]
        fluctuation = base * random.uniform(-0.15, 0.25)
        CRYPTOS[sym]["price"] = round(max(0.01, base + fluctuation), 2)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    update_crypto_prices.start()

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")

@bot.command()
async def shop(ctx):
    msg = "**🪙 Crypto Shop (prices update hourly):**\n"
    for sym, data in CRYPTOS.items():
        msg += f"`{sym}`: ${data['price']} — {data['desc']}\n"
    await ctx.send(msg)
