import discord
from discord.ext import commands, tasks
import os, random, json, asyncio
from datetime import datetime, timedelta

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

DATA_FILE = os.getenv("VOLUME_PATH", ".") + "/economy.json"
MAX_BET = 250_000
COOLDOWN_SECONDS = 40 * 60

CRYPTOCURRENCIES = {
    "bitcoin": {"price": 50000, "desc": "BTC - Most popular crypto"},
    "ethereum": {"price": 3200, "desc": "ETH - Smart contracts"},
    "dogecoin": {"price": 0.3, "desc": "DOGE - Meme coin"},
    "litecoin": {"price": 180, "desc": "LTC - Faster Bitcoin"},
    "ripple": {"price": 1, "desc": "XRP - Bank payments"},
}

def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def ensure_user(data, uid):
    if uid not in data:
        data[uid] = {
            "bal": 1000, "exp": 0, "lvl": 1,
            "daily": None, "work": None, "inv": {}
        }

def cooldown_left(last_time):
    if not last_time: return 0
    delta = (datetime.utcnow() - datetime.fromisoformat(last_time)).total_seconds()
    return max(0, COOLDOWN_SECONDS - delta)

def add_exp(user, amount):
    user["exp"] += amount
    while user["exp"] >= 1000:
        user["exp"] -= 1000
        user["lvl"] += 1

@tasks.loop(hours=1)
async def update_crypto_prices():
    for crypto in CRYPTOCURRENCIES:
        base = CRYPTOCURRENCIES[crypto]["price"]
        new = base * (1 + random.uniform(-0.05, 0.05))
        CRYPTOCURRENCIES[crypto]["price"] = round(max(new, 0.01), 2)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    update_crypto_prices.start()

@bot.command()
async def bal(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    u = data[uid]
    await ctx.send(f"💰 Balance: {u['bal']} | Level: {u['lvl']} | EXP: {u['exp']}/1000")

@bot.command()
async def daily(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    left = cooldown_left(data[uid]["daily"])
    if left > 0:
        return await ctx.send(f"🕒 Wait {int(left//60)}m {int(left%60)}s for daily.")
    reward = random.randint(1500, 3500)
    data[uid]["bal"] += reward
    data[uid]["daily"] = datetime.utcnow().isoformat()
    add_exp(data[uid], 60)
    save_data(data)
    await ctx.send(f"✅ +{reward} coins, +60 EXP")

@bot.command()
async def work(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    left = cooldown_left(data[uid]["work"])
    if left > 0:
        return await ctx.send(f"🕒 Wait {int(left//60)}m {int(left%60)}s before working.")
    reward = random.randint(1100, 2500)
    data[uid]["bal"] += reward
    data[uid]["work"] = datetime.utcnow().isoformat()
    add_exp(data[uid], 45)
    save_data(data)
    await ctx.send(f"💼 You worked and earned {reward} coins, +45 EXP")

@bot.command()
async def shop(ctx):
    msg = "**🪙 Crypto Shop (changes hourly):**\n"
    for crypto, info in CRYPTOCURRENCIES.items():
        price = f"{info['price']:,}" if info["price"] >= 1 else str(info["price"])
        msg += f"`{crypto}`: {price} coins — {info['desc']}\n"
    await ctx.send(msg)

@bot.command()
async def buy(ctx, item: str, amount: int = 1):
    item = item.lower()
    if amount <= 0: return await ctx.send("❌ Invalid amount.")
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    if item not in CRYPTOCURRENCIES:
        return await ctx.send("❌ Item not in shop.")
    cost = int(CRYPTOCURRENCIES[item]["price"]) * amount
    if data[uid]["bal"] < cost:
        return await ctx.send(f"❌ Need {cost} coins.")
    data[uid]["bal"] -= cost
    inv = data[uid]["inv"]
    inv[item] = inv.get(item, 0) + amount
    add_exp(data[uid], 20 * amount)
    save_data(data)
    await ctx.send(f"✅ Bought {amount} {item} for {cost} coins.")

@bot.command()
async def inv(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    inv = data[uid]["inv"]
    if not inv: return await ctx.send("🎒 Inventory empty.")
    msg = "**🎒 Inventory:**\n" + "\n".join(f"{k} x{v}" for k,v in inv.items() if v > 0)
    await ctx.send(msg)

@bot.command()
async def sell(ctx, item: str, amount: int = 1):
    item = item.lower()
    if amount <= 0: return await ctx.send("❌ Invalid amount.")
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    inv = data[uid]["inv"]
    if item not in inv or inv[item] < amount:
        return await ctx.send("❌ You don't have enough.")
    price = int(CRYPTOCURRENCIES.get(item, {"price":0})["price"] * 0.6)
    total = price * amount
    inv[item] -= amount
    data[uid]["bal"] += total
    save_data(data)
    await ctx.send(f"✅ Sold {amount} {item} for {total} coins.")

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")

@bot.command()
async def help(ctx):
    cmds = [
        "`!bal` - Check balance",
        "`!daily` - Claim daily reward",
        "`!work` - Earn money by working",
        "`!shop` - View crypto shop",
        "`!buy <item> [amount]` - Buy crypto",
        "`!sell <item> [amount]` - Sell crypto",
        "`!inv` - Check your inventory",
        "`!ping` - Test bot",
    ]
    await ctx.send("**📜 Available Commands:**\n" + "\n".join(cmds))

if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN:
        print("❌ DISCORD_TOKEN not set.")
        exit(1)
    bot.run(TOKEN)
