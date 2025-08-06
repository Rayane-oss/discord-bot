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
MAX_BET = 250_000
COOLDOWN_TIME = 2400  # 40 minutes in seconds

# -------------------- UTILS --------------------
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
    user_id = str(user_id)
    if user_id not in data:
        data[user_id] = {
            "balance": 1000,
            "last_daily": None,
            "last_work": None,
            "exp": 0,
            "level": 1,
            "inventory": {}
        }

def add_exp(data, user_id, amount):
    user = data[str(user_id)]
    user["exp"] += amount
    while user["exp"] >= 1000:
        user["exp"] -= 1000
        user["level"] += 1

# -------------------- SHOP --------------------
SHOP_ITEMS = {
    "sword": {"price": 500, "desc": "A shiny sword."},
    "shield": {"price": 300, "desc": "A sturdy shield."},
    "potion": {"price": 150, "desc": "Heals you."}
}

@tasks.loop(hours=1)
async def update_prices():
    for item in SHOP_ITEMS:
        base = SHOP_ITEMS[item]["price"]
        fluctuation = random.randint(-50, 100)
        SHOP_ITEMS[item]["price"] = max(50, base + fluctuation)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    update_prices.start()

# -------------------- ECONOMY --------------------
@bot.command()
async def bal(ctx):
    data = load_data()
    user_id = ctx.author.id
    ensure_user(data, user_id)
    user = data[str(user_id)]
    await ctx.send(f"💰 Balance: {user['balance']} coins | Level: {user['level']} | EXP: {user['exp']}/1000")

@bot.command()
async def daily(ctx):
    data = load_data()
    user_id = ctx.author.id
    ensure_user(data, user_id)

    now = datetime.utcnow()
    last = data[str(user_id)]["last_daily"]
    if last:
        last_time = datetime.fromisoformat(last)
        if (now - last_time).total_seconds() < COOLDOWN_TIME:
            remain = COOLDOWN_TIME - (now - last_time).total_seconds()
            minutes = int(remain // 60)
            await ctx.send(f"🕒 Come back in {minutes} minutes for your daily reward.")
            return

    reward = random.randint(1000, 3000)
    data[str(user_id)]["balance"] += reward
    data[str(user_id)]["last_daily"] = now.isoformat()
    add_exp(data, user_id, 50)
    save_data(data)
    await ctx.send(f"✅ You claimed {reward} coins and 50 EXP!")

@bot.command()
async def work(ctx):
    data = load_data()
    user_id = ctx.author.id
    ensure_user(data, user_id)

    now = datetime.utcnow()
    last = data[str(user_id)]["last_work"]
    if last:
        last_time = datetime.fromisoformat(last)
        if (now - last_time).total_seconds() < COOLDOWN_TIME:
            remain = COOLDOWN_TIME - (now - last_time).total_seconds()
            minutes = int(remain // 60)
            await ctx.send(f"🕒 You’re tired. Try working again in {minutes} minutes.")
            return

    earnings = random.randint(750, 2000)
    data[str(user_id)]["balance"] += earnings
    data[str(user_id)]["last_work"] = now.isoformat()
    add_exp(data, user_id, 40)
    save_data(data)
    await ctx.send(f"💼 You worked and earned {earnings} coins + 40 EXP!")

@bot.command()
async def shop(ctx):
    msg = "**🛒 Shop:**\n"
    for item, details in SHOP_ITEMS.items():
        msg += f"**{item}** - {details['price']} coins | {details['desc']}\n"
    await ctx.send(msg)

@bot.command()
async def buy(ctx, item):
    item = item.lower()
    if item not in SHOP_ITEMS:
        await ctx.send("❌ Item not found.")
        return

    data = load_data()
    user_id = ctx.author.id
    ensure_user(data, user_id)

    price = SHOP_ITEMS[item]["price"]
    if data[str(user_id)]["balance"] < price:
        await ctx.send("❌ Not enough coins.")
        return

    data[str(user_id)]["balance"] -= price
    inventory = data[str(user_id)]["inventory"]
    inventory[item] = inventory.get(item, 0) + 1
    save_data(data)
    await ctx.send(f"✅ Bought 1 {item}!")

@bot.command()
async def sell(ctx, item):
    item = item.lower()
    data = load_data()
    user_id = ctx.author.id
    ensure_user(data, user_id)

    inventory = data[str(user_id)]["inventory"]
    if item not in inventory or inventory[item] == 0:
        await ctx.send("❌ You don’t own this item.")
        return

    price = SHOP_ITEMS[item]["price"]
    resale = int(price * 0.6)
    data[str(user_id)]["balance"] += resale
    inventory[item] -= 1
    save_data(data)
    await ctx.send(f"✅ Sold 1 {item} for {resale} coins.")

@bot.command()
async def inv(ctx):
    data = load_data()
    user_id = ctx.author.id
    ensure_user(data, user_id)
    inventory = data[str(user_id)]["inventory"]
    msg = "**🎒 Inventory:**\n"
    if not inventory:
        msg += "Empty."
    else:
        for item, amount in inventory.items():
            msg += f"{item}: {amount}\n"
    await ctx.send(msg)

# -------------------- GAMBLING --------------------
@bot.command(name="cf")
async def coinflip(ctx, amount: int, choice: str):
    data = load_data()
    user_id = ctx.author.id
    ensure_user(data, user_id)

    choice = choice.lower()
    if choice not in ["heads", "tails"]:
        await ctx.send("Choose 'heads' or 'tails'.")
        return

    if amount > MAX_BET:
        await ctx.send("❌ Max bet is 250,000.")
        return

    if data[str(user_id)]["balance"] < amount:
        await ctx.send("❌ Not enough coins.")
        return

    result = random.choice(["heads", "tails"])
    if result == choice:
        win = int(amount * 0.9)
        data[str(user_id)]["balance"] += win
        add_exp(data, user_id, 30)
        await ctx.send(f"🎉 It was {result}! You won {win} coins and 30 EXP.")
    else:
        data[str(user_id)]["balance"] -= amount
        add_exp(data, user_id, 10)
        await ctx.send(f"💀 It was {result}. You lost {amount} coins but got 10 EXP.")

    save_data(data)

@bot.command(name="plinko")
async def plinko(ctx, amount: int):
    data = load_data()
    user_id = ctx.author.id
    ensure_user(data, user_id)

    if amount > MAX_BET:
        await ctx.send("❌ Max bet is 250k.")
        return
    if data[str(user_id)]["balance"] < amount:
        await ctx.send("❌ Not enough coins.")
        return

    slots = [0, 1, 2, 3, 4, 5, 6]
    payout_chart = [0, 0.5, 0, 1, 0, 2, 0.3]
    chosen = random.choice(slots)
    multiplier = payout_chart[chosen]
    won = int(amount * multiplier)

    data[str(user_id)]["balance"] += won - amount
    add_exp(data, user_id, 40 if won > 0 else 15)
    msg = f"🎯 Slot: {chosen} | Multiplier: {multiplier}x\n"
    if won > 0:
        msg += f"✅ You won {won} coins!"
    else:
        msg += f"❌ You lost {amount} coins!"
    await ctx.send(msg)
    save_data(data)

@bot.command(name="cups")
async def cups(ctx):
    ball = random.randint(1, 3)
    await ctx.send("🥤 🥤 🥤\nPick a cup (1-3)!")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content in ["1", "2", "3"]

    try:
        guess = await bot.wait_for("message", check=check, timeout=15)
        guess_num = int(guess.content)
    except asyncio.TimeoutError:
        await ctx.send("⏰ You took too long.")
        return

    if guess_num == ball:
        await ctx.send("🎉 You guessed right! +20 EXP")
        data = load_data()
        ensure_user(data, ctx.author.id)
        add_exp(data, ctx.author.id, 20)
        save_data(data)
    else:
        await ctx.send(f"❌ Wrong! Ball was under cup {ball}. +5 EXP")
        data = load_data()
        ensure_user(data, ctx.author.id)
        add_exp(data, ctx.author.id, 5)
        save_data(data)

# -------------------- START --------------------
bot.run(os.environ["TOKEN"])
