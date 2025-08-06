import discord
from discord.ext import commands, tasks
import os, random, json, asyncio
from datetime import datetime, timedelta

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
DATA = "economy.json"
MAX_BET = 250_000
CD = 2400  # 40 minutes cooldown seconds

CRYPTO = {
    "btc": {"desc": "Bitcoin"},
    "eth": {"desc": "Ethereum"},
    "sol": {"desc": "Solana"},
    "doge": {"desc": "Dogecoin"},
    "xrp": {"desc": "Ripple"},
}

PRICES = {}

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
async def update_prices():
    for key in CRYPTO:
        PRICES[key] = random.randint(100, 2000)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    update_prices.start()

@bot.command()
async def shop(ctx):
    msg = "**🪙 Crypto Shop (prices update hourly):**
"
    for i, v in CRYPTO.items():
        msg += f"`{i}` ({v['desc']}): {PRICES[i]} coins
"
    await ctx.send(msg)

@bot.command()
async def buy(ctx, item):
    data = load()
    uid = str(ctx.author.id)
    item = item.lower()
    ensure(data, uid)
    if item not in PRICES:
        await ctx.send("❌ Invalid crypto.")
        return
    price = PRICES[item]
    if data[uid]["bal"] < price:
        await ctx.send("❌ Not enough coins.")
        return
    data[uid]["bal"] -= price
    inv = data[uid]["inv"]
    inv[item] = inv.get(item, 0) + 1
    add_exp(data[uid], 25)
    save(data)
    await ctx.send(f"✅ Bought 1 {item.upper()} for {price} coins")

@bot.command()
async def sell(ctx, item):
    data = load()
    uid = str(ctx.author.id)
    item = item.lower()
    ensure(data, uid)
    inv = data[uid]["inv"]
    if item not in inv or inv[item] < 1:
        await ctx.send("❌ You don't own this item.")
        return
    price = int(PRICES[item] * 0.6)
    inv[item] -= 1
    data[uid]["bal"] += price
    save(data)
    await ctx.send(f"✅ Sold 1 {item.upper()} for {price} coins")

@bot.command(name="cups")
async def cups(ctx, bet: int):
    data = load()
    uid = str(ctx.author.id)
    ensure(data, uid)
    if bet <= 0 or bet > MAX_BET:
        await ctx.send(f"❌ Bet 1-{MAX_BET} coins.")
        return
    if data[uid]["bal"] < bet:
        await ctx.send("❌ Not enough coins.")
        return

    cups = ["🥤", "🥤", "🥤"]
    prize = random.randint(0, 2)
    msg = await ctx.send("🎯 Guess the cup!
🥤 🥤 🥤")
    for emoji in ["1️⃣", "2️⃣", "3️⃣"]:
        await msg.add_reaction(emoji)

    def check(reaction, user):
        return user == ctx.author and reaction.message.id == msg.id and reaction.emoji in ["1️⃣", "2️⃣", "3️⃣"]

    try:
        reaction, _ = await bot.wait_for("reaction_add", timeout=30.0, check=check)
        guess = ["1️⃣", "2️⃣", "3️⃣"].index(reaction.emoji)
        if guess == prize:
            win = int(bet * 2.5)
            data[uid]["bal"] += win
            add_exp(data[uid], 50)
            await ctx.send(f"🎉 Correct! You won {win} coins!")
        else:
            data[uid]["bal"] -= bet
            add_exp(data[uid], 10)
            await ctx.send(f"💀 Wrong! The prize was under cup {prize+1}. You lost {bet} coins.")
        save(data)
    except asyncio.TimeoutError:
        await ctx.send("⏰ Timeout.")

@bot.command(name="bj")
async def blackjack(ctx, bet: int):
    data = load()
    uid = str(ctx.author.id)
    ensure(data, uid)
    if bet <= 0 or bet > MAX_BET:
        await ctx.send(f"❌ Bet 1-{MAX_BET} coins.")
        return
    if data[uid]["bal"] < bet:
        await ctx.send("❌ Not enough coins.")
        return

    def deal(): return random.choice([2,3,4,5,6,7,8,9,10,10,10,10,11])
    def total(hand):
        val = sum(hand)
        aces = hand.count(11)
        while val > 21 and aces:
            val -= 10
            aces -= 1
        return val

    player = [deal(), deal()]
    dealer = [deal(), deal()]

    msg = await ctx.send(f"🃏 You: {player} ({total(player)})
Dealer: [{dealer[0]}, ?]")
    for emoji in ["✅", "❌"]:  # ✅ = Hit, ❌ = Stand
        await msg.add_reaction(emoji)

    def check(r, u):
        return u == ctx.author and r.message.id == msg.id and r.emoji in ["✅", "❌"]

    while True:
        try:
            r, _ = await bot.wait_for("reaction_add", timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send("⏰ Timeout! Game cancelled.")
            return
        if r.emoji == "✅":
            player.append(deal())
            val = total(player)
            await ctx.send(f"🃏 You hit: {player} ({val})")
            if val > 21:
                data[uid]["bal"] -= bet
                add_exp(data[uid], 10)
                save(data)
                await ctx.send("💥 Bust! You lose.")
                return
        else:
            break

    while total(dealer) < 17:
        dealer.append(deal())
    p_val = total(player)
    d_val = total(dealer)
    await ctx.send(f"Dealer: {dealer} ({d_val})")
    if d_val > 21 or p_val > d_val:
        win = int(bet * 1.8)
        data[uid]["bal"] += win
        add_exp(data[uid], 50)
        await ctx.send(f"🎉 You win {win} coins!")
    elif p_val == d_val:
        await ctx.send("🤝 Push! Bet returned.")
    else:
        data[uid]["bal"] -= bet
        add_exp(data[uid], 10)
        await ctx.send("💀 You lose.")
    save(data)
