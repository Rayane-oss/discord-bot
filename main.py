import discord
from discord.ext import commands
import os
import random
import json
from datetime import datetime, timedelta

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "economy.json"

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

@bot.command()
async def joke(ctx):
    jokes = [
        "Why don’t scientists trust atoms? Because they make up everything!",
        "I told my computer I needed a break, and it said 'No problem, I’ll go to sleep.'",
        "Why did the scarecrow win an award? Because he was outstanding in his field!"
    ]
    await ctx.send(random.choice(jokes))

@bot.command()
async def coinflip(ctx):
    outcome = random.choice(["Heads", "Tails"])
    await ctx.send(f"The coin landed on **{outcome}**!")

@bot.command()
async def roll(ctx, sides: int = 6):
    result = random.randint(1, sides)
    await ctx.send(f"🎲 You rolled a **{result}** on a {sides}-sided dice!")

@bot.command()
async def eightball(ctx, *, question):
    responses = [
        "It is certain.",
        "Without a doubt.",
        "You may rely on it.",
        "Ask again later.",
        "Better not tell you now.",
        "Don't count on it.",
        "My reply is no.",
        "Very doubtful."
    ]
    answer = random.choice(responses)
    await ctx.send(f"🎱 Question: {question}\nAnswer: {answer}")

@bot.command()
async def balance(ctx):
    data = load_data()
    user_id = ctx.author.id
    ensure_user(data, user_id)
    bal = data[str(user_id)]["balance"]
    await ctx.send(f"{ctx.author.mention}, your balance is **{bal} coins**.")

@bot.command()
async def daily(ctx):
    data = load_data()
    user_id = ctx.author.id
    ensure_user(data, user_id)
    last_daily = data[str(user_id)]["last_daily"]
    now = datetime.utcnow()

    if last_daily:
        last_daily_dt = datetime.fromisoformat(last_daily)
        if now - last_daily_dt < timedelta(hours=24):
            next_claim = last_daily_dt + timedelta(hours=24)
            remaining = next_claim - now
            hours, remainder = divmod(int(remaining.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            await ctx.send(f"⏳ You already claimed your daily reward. Try again in {hours}h {minutes}m.")
            return

    reward = random.randint(50, 150)
    data[str(user_id)]["balance"] += reward
    data[str(user_id)]["last_daily"] = now.isoformat()
    save_data(data)
    await ctx.send(f"🎉 {ctx.author.mention}, you claimed your daily reward of **{reward} coins**!")

@bot.command()
async def work(ctx):
    data = load_data()
    user_id = ctx.author.id
    ensure_user(data, user_id)
    earnings = random.randint(10, 100)
    data[str(user_id)]["balance"] += earnings
    save_data(data)
    jobs = [
        "programmed a bot",
        "delivered pizzas",
        "worked at a coffee shop",
        "cleaned a park",
        "wrote a blog post"
    ]
    job = random.choice(jobs)
    await ctx.send(f"💼 {ctx.author.mention}, you {job} and earned **{earnings} coins**.")

@bot.command()
async def shop(ctx):
    msg = "**Shop Items:**\n"
    for item, info in SHOP_ITEMS.items():
        msg += f"**{item}** - {info['price']} coins: {info['desc']}\n"
    await ctx.send(msg)

@bot.command()
async def buy(ctx, item_name: str):
    data = load_data()
    user_id = ctx.author.id
    ensure_user(data, user_id)
    item_name = item_name.lower()

    if item_name not in SHOP_ITEMS:
        await ctx.send(f"❌ Item `{item_name}` not found in the shop.")
        return

    price = SHOP_ITEMS[item_name]["price"]
    bal = data[str(user_id)]["balance"]

    if bal < price:
        await ctx.send(f"❌ You don't have enough coins to buy `{item_name}`. Your balance: {bal} coins.")
        return

    data[str(user_id)]["balance"] -= price
    inv = data[str(user_id)]["inventory"]
    inv[item_name] = inv.get(item_name, 0) + 1
    save_data(data)

    await ctx.send(f"✅ {ctx.author.mention} bought 1 **{item_name}**!")

@bot.command()
async def inventory(ctx):
    data = load_data()
    user_id = ctx.author.id
    ensure_user(data, user_id)
    inv = data[str(user_id)]["inventory"]

    if not inv:
        await ctx.send(f"{ctx.author.mention}, your inventory is empty.")
        return

    msg = f"👜 **{ctx.author.name}'s Inventory:**\n"
    for item, count in inv.items():
        msg += f"{item}: {count}\n"
    await ctx.send(msg)

@bot.command()
async def leaderboard(ctx):
    data = load_data()
    sorted_users = sorted(data.items(), key=lambda x: x[1]["balance"], reverse=True)
    msg = "**🏆 Leaderboard (Top 10 richest users):**\n"
    for i, (user_id, user_data) in enumerate(sorted_users[:10], 1):
        member = ctx.guild.get_member(int(user_id))
        name = member.name if member else f"User ID {user_id}"
        msg += f"{i}. {name} — {user_data['balance']} coins\n"
    await ctx.send(msg)

@bot.command()
async def gamble(ctx, amount: int):
    data = load_data()
    user_id = ctx.author.id
    ensure_user(data, user_id)
    bal = data[str(user_id)]["balance"]

    if amount <= 0:
        await ctx.send("❌ You must gamble a positive amount.")
        return

    if bal < amount:
        await ctx.send(f"❌ You don't have enough coins to gamble that amount. Your balance: {bal} coins.")
        return

    if random.choice([True, False]):
        winnings = amount
        data[str(user_id)]["balance"] += winnings
        await ctx.send(f"🎉 Congrats {ctx.author.mention}, you won **{winnings} coins**!")
    else:
        data[str(user_id)]["balance"] -= amount
        await ctx.send(f"😢 Sorry {ctx.author.mention}, you lost **{amount} coins**.")

    save_data(data)

bot.run(os.getenv("TOKEN"))
