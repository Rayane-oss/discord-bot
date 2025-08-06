
import discord
from discord.ext import commands, tasks
import os
import random
import json
from datetime import datetime, timedelta
import asyncio

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "economy.json"
MAX_BET = 250000
COOLDOWN_TIME = 2400  # 40 minutes

SHOP_ITEMS = {
    "sword": {"price": 500, "desc": "Shiny sword"},
    "shield": {"price": 300, "desc": "Sturdy shield"},
    "potion": {"price": 150, "desc": "Healing potion"}
}

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
    uid = str(user_id)
    if uid not in data:
        data[uid] = {
            "balance": 1000,
            "exp": 0,
            "level": 1,
            "last_daily": None,
            "last_work": None,
            "inventory": {}
        }

def add_exp(data, user_id, amount):
    user = data[str(user_id)]
    user["exp"] += amount
    while user["exp"] >= 1000:
        user["exp"] -= 1000
        user["level"] += 1

@tasks.loop(hours=1)
async def update_prices():
    for item in SHOP_ITEMS:
        base = SHOP_ITEMS[item]["price"]
        SHOP_ITEMS[item]["price"] = max(50, base + random.randint(-75, 125))

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    update_prices.start()

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")

@bot.command(name="bal")
async def balance(ctx):
    data = load_data()
    ensure_user(data, ctx.author.id)
    user = data[str(ctx.author.id)]
    await ctx.send(f"💰 Balance: {user['balance']} | LVL: {user['level']} | EXP: {user['exp']}/1000")

@bot.command()
async def daily(ctx):
    data = load_data()
    ensure_user(data, ctx.author.id)
    now = datetime.utcnow()
    last = data[str(ctx.author.id)]["last_daily"]
    if last and (now - datetime.fromisoformat(last)).total_seconds() < COOLDOWN_TIME:
        mins = int(COOLDOWN_TIME - (now - datetime.fromisoformat(last)).total_seconds()) // 60
        await ctx.send(f"🕒 Cooldown. Wait {mins} minutes.")
        return
    reward = random.randint(1000, 3000)
    data[str(ctx.author.id)]["balance"] += reward
    data[str(ctx.author.id)]["last_daily"] = now.isoformat()
    add_exp(data, ctx.author.id, 60)
    save_data(data)
    await ctx.send(f"✅ You received {reward} coins and 60 EXP!")

@bot.command()
async def work(ctx):
    data = load_data()
    ensure_user(data, ctx.author.id)
    now = datetime.utcnow()
    last = data[str(ctx.author.id)]["last_work"]
    if last and (now - datetime.fromisoformat(last)).total_seconds() < COOLDOWN_TIME:
        mins = int(COOLDOWN_TIME - (now - datetime.fromisoformat(last)).total_seconds()) // 60
        await ctx.send(f"🕒 Cooldown. Wait {mins} minutes.")
        return
    reward = random.randint(900, 2200)
    data[str(ctx.author.id)]["balance"] += reward
    data[str(ctx.author.id)]["last_work"] = now.isoformat()
    add_exp(data, ctx.author.id, 45)
    save_data(data)
    await ctx.send(f"💼 You worked and earned {reward} coins + 45 EXP!")

@bot.command()
async def shop(ctx):
    msg = "**🛒 Shop:**\n"
    for item, val in SHOP_ITEMS.items():
        msg += f"`{item}` - {val['price']} | {val['desc']}\n"
    await ctx.send(msg)

@bot.command()
async def buy(ctx, item):
    item = item.lower()
    data = load_data()
    ensure_user(data, ctx.author.id)
    if item not in SHOP_ITEMS:
        await ctx.send("❌ Item not found.")
        return
    cost = SHOP_ITEMS[item]["price"]
    if data[str(ctx.author.id)]["balance"] < cost:
        await ctx.send("❌ Not enough coins.")
        return
    data[str(ctx.author.id)]["balance"] -= cost
    inv = data[str(ctx.author.id)]["inventory"]
    inv[item] = inv.get(item, 0) + 1
    add_exp(data, ctx.author.id, 20)
    save_data(data)
    await ctx.send(f"✅ Bought 1 {item} for {cost} coins!")

@bot.command()
async def sell(ctx, item):
    item = item.lower()
    data = load_data()
    ensure_user(data, ctx.author.id)
    inv = data[str(ctx.author.id)]["inventory"]
    if item not in inv or inv[item] == 0:
        await ctx.send("❌ You don’t own this item.")
        return
    resale = int(SHOP_ITEMS[item]["price"] * 0.6)
    data[str(ctx.author.id)]["balance"] += resale
    inv[item] -= 1
    save_data(data)
    await ctx.send(f"✅ Sold 1 {item} for {resale} coins.")

@bot.command()
async def inv(ctx):
    data = load_data()
    ensure_user(data, ctx.author.id)
    items = data[str(ctx.author.id)]["inventory"]
    msg = "**🎒 Inventory:**\n"
    if not items:
        msg += "Empty."
    else:
        for k, v in items.items():
            msg += f"{k} × {v}\n"
    await ctx.send(msg)

@bot.command(name="cf")
async def coinflip(ctx, amount: int, guess: str):
    data = load_data()
    ensure_user(data, ctx.author.id)
    guess = guess.lower()
    if guess not in ["heads", "tails"]:
        await ctx.send("❌ Choose heads or tails.")
        return
    if amount > MAX_BET or amount <= 0:
        await ctx.send("❌ Max bet is 250,000.")
        return
    if data[str(ctx.author.id)]["balance"] < amount:
        await ctx.send("❌ Not enough coins.")
        return
    result = random.choice(["heads", "tails"])
    if guess == result:
        win = int(amount * 0.9)
        data[str(ctx.author.id)]["balance"] += win
        add_exp(data, ctx.author.id, 30)
        await ctx.send(f"🎉 You won {win}! Result: {result}")
    else:
        data[str(ctx.author.id)]["balance"] -= amount
        add_exp(data, ctx.author.id, 10)
        await ctx.send(f"💀 You lost {amount}. Result: {result}")
    save_data(data)

bot.run(os.environ["TOKEN"])
