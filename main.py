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
COOLDOWN_TIME = 2400  # 40 mins

SHOP_ITEMS = {
    "sword": {"price": 500, "desc": "Shiny sword"},
    "shield": {"price": 300, "desc": "Basic shield"},
    "potion": {"price": 150, "desc": "Healing potion"},
}

# ------------------ DATA FUNCTIONS ------------------ #
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

# ------------------ PRICE FLUCTUATION ------------------ #
@tasks.loop(hours=1)
async def update_shop_prices():
    for item in SHOP_ITEMS:
        fluctuation = random.randint(-75, 125)
        base = SHOP_ITEMS[item]["price"]
        new_price = max(50, base + fluctuation)
        SHOP_ITEMS[item]["price"] = new_price

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    update_shop_prices.start()

# ------------------ COMMANDS ------------------ #
@bot.command()
async def bal(ctx):
    data = load_data()
    ensure_user(data, ctx.author.id)
    user = data[str(ctx.author.id)]
    await ctx.send(f"💰 {ctx.author.mention} | Balance: {user['balance']} | LVL: {user['level']} | EXP: {user['exp']}/1000")

@bot.command()
async def daily(ctx):
    data = load_data()
    ensure_user(data, ctx.author.id)
    now = datetime.utcnow()
    last = data[str(ctx.author.id)]["last_daily"]

    if last and (now - datetime.fromisoformat(last)).total_seconds() < COOLDOWN_TIME:
        mins = int(COOLDOWN_TIME - (now - datetime.fromisoformat(last)).total_seconds()) // 60
        await ctx.send(f"🕒 Cooldown. Come back in {mins} minutes.")
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
        await ctx.send(f"🕒 Cooldown. Work again in {mins} minutes.")
        return

    earned = random.randint(900, 2200)
    data[str(ctx.author.id)]["balance"] += earned
    data[str(ctx.author.id)]["last_work"] = now.isoformat()
    add_exp(data, ctx.author.id, 45)
    save_data(data)
    await ctx.send(f"💼 You worked and earned {earned} coins + 45 EXP!")

@bot.command()
async def shop(ctx):
    msg = "**🛒 Current Shop Items:**\n"
    for item, val in SHOP_ITEMS.items():
        msg += f"`{item}` - {val['price']} coins | {val['desc']}\n"
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
        await ctx.send("❌ You don't have enough coins.")
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

# ------------------ GAMES ------------------ #
@bot.command(name="cf")
async def coinflip(ctx, amount: int, guess: str):
    data = load_data()
    ensure_user(data, ctx.author.id)
    guess = guess.lower()
    if guess not in ["heads", "tails"]:
        await ctx.send("❌ Choose heads or tails.")
        return
    if amount > MAX_BET:
        await ctx.send("❌ Max bet is 250k.")
        return
    if data[str(ctx.author.id)]["balance"] < amount:
        await ctx.send("❌ Not enough coins.")
        return

    result = random.choice(["heads", "tails"])
    if guess == result:
        winnings = int(amount * 0.9)
        data[str(ctx.author.id)]["balance"] += winnings
        add_exp(data, ctx.author.id, 30)
        await ctx.send(f"🎉 You won {winnings}! Result: {result}")
    else:
        data[str(ctx.author.id)]["balance"] -= amount
        add_exp(data, ctx.author.id, 10)
        await ctx.send(f"💀 You lost {amount}. Result: {result}")
    save_data(data)

@bot.command(name="bj")
async def blackjack(ctx, amount: int):
    data = load_data()
    ensure_user(data, ctx.author.id)

    if amount > MAX_BET or amount <= 0:
        await ctx.send("❌ Invalid bet amount.")
        return
    if data[str(ctx.author.id)]["balance"] < amount:
        await ctx.send("❌ Not enough coins.")
        return

    def draw():
        return random.choice([2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 11])

    def score(hand):
        total = sum(hand)
        aces = hand.count(11)
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total

    player = [draw(), draw()]
    dealer = [draw(), draw()]
    await ctx.send(f"🃏 Your hand: {player} ({score(player)})\nDealer shows: [{dealer[0]}, ?]")

    def check(m): return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["hit", "stand"]

    while True:
        await ctx.send("Type `hit` or `stand`.")
        try:
            move = await bot.wait_for("message", timeout=30, check=check)
        except asyncio.TimeoutError:
            await ctx.send("⏰ Timeout!")
            return
        if move.content.lower() == "hit":
            player.append(draw())
            await ctx.send(f"Your hand: {player} ({score(player)})")
            if score(player) > 21:
                data[str(ctx.author.id)]["balance"] -= amount
                add_exp(data, ctx.author.id, 15)
                await ctx.send("💥 Bust! You lose.")
                save_data(data)
                return
        else:
            break

    while score(dealer) < 17:
        dealer.append(draw())

    p, d = score(player), score(dealer)
    await ctx.send(f"🏁 Dealer's hand: {dealer} ({d})")

    if d > 21 or p > d:
        data[str(ctx.author.id)]["balance"] += amount
        add_exp(data, ctx.author.id, 50)
        await ctx.send("🎉 You win!")
    elif p == d:
        add_exp(data, ctx.author.id, 25)
        await ctx.send("🤝 It's a draw.")
    else:
        data[str(ctx.author.id)]["balance"] -= amount
        add_exp(data, ctx.author.id, 15)
        await ctx.send("😢 You lose.")

    save_data(data)

@bot.command()
async def plinko(ctx, amount: int):
    data = load_data()
    ensure_user(data, ctx.author.id)

    if amount > MAX_BET or amount <= 0:
        await ctx.send("❌ Invalid bet.")
        return
    if data[str(ctx.author.id)]["balance"] < amount:
        await ctx.send("❌ Not enough coins.")
        return

    slots = [0, 1, 2, 3, 4, 5]
    payout = [0, 0.5, 0, 1, 2, 0.3]
    slot = random.choice(slots)
    multi = payout[slot]
    won = int(amount * multi)

    data[str(ctx.author.id)]["balance"] += won - amount
    add_exp(data, ctx.author.id, 30 if won else 10)
    save_data(data)
    await ctx.send(f"🎯 Landed in slot {slot} | Multiplier: {multi}x\n{'✅ Won ' + str(won) if won else '❌ Lost all!'}")

@bot.command()
async def cups(ctx):
    ball = random.randint(1, 3)
    await ctx.send("🥤🥤🥤 Guess which cup (1–3)?")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content in ["1", "2", "3"]

    try:
        guess = await bot.wait_for("message", timeout=15, check=check)
        if int(guess.content) == ball:
            await ctx.send("🎉 Correct! You found the ball. +20 EXP")
            data = load_data()
            ensure_user(data, ctx.author.id)
            add_exp(data, ctx.author.id, 20)
            save_data(data)
        else:
            await ctx.send(f"😢 Wrong! It was cup {ball}. +5 EXP")
            data = load_data()
            ensure_user(data, ctx.author.id)
            add_exp(data, ctx.author.id, 5)
            save_data(data)
    except asyncio.TimeoutError:
        await ctx.send("⏰ Too slow!")
