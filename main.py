import discord
from discord.ext import commands, tasks
import os, random, json, asyncio
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "economy.json"
MAX_BET = 250000
COOLDOWN = 2400  # 40 minutes

CRYPTO_LIST = {
    "btc": "₿",
    "eth": "Ξ",
    "sol": "◎",
    "doge": "Ð",
    "ltc": "Ł"
}
CRYPTO_SHOP = {}

# Load/save JSON
def load():
    try:
        with open(DATA_FILE) as f:
            return json.load(f)
    except:
        return {}

def save(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def ensure(data, uid):
    if uid not in data:
        data[uid] = {"bal": 1000, "exp": 0, "lvl": 1, "daily": None, "work": None, "inv": {}}

def cooldown_left(last):
    if not last: return 0
    elapsed = (datetime.utcnow() - datetime.fromisoformat(last)).total_seconds()
    return max(0, COOLDOWN - elapsed)

def add_exp(user, amount):
    user["exp"] += amount
    while user["exp"] >= 1000:
        user["exp"] -= 1000
        user["lvl"] += 1

# Crypto price updates
@tasks.loop(hours=1)
async def update_crypto():
    for coin in CRYPTO_LIST:
        CRYPTO_SHOP[coin] = random.randint(100, 800)
    print("Crypto prices updated:", CRYPTO_SHOP)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    update_crypto.start()

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")

@bot.command()
async def bal(ctx):
    data = load()
    uid = str(ctx.author.id)
    ensure(data, uid)
    u = data[uid]
    await ctx.send(f"💰 {u['bal']} | LVL: {u['lvl']} | EXP: {u['exp']}/1000")

@bot.command()
async def daily(ctx):
    data = load()
    uid = str(ctx.author.id)
    ensure(data, uid)
    left = cooldown_left(data[uid]["daily"])
    if left:
        await ctx.send(f"🕒 Wait {int(left//60)}m {int(left%60)}s for daily.")
        return
    amt = random.randint(1500, 3500)
    data[uid]["bal"] += amt
    data[uid]["daily"] = datetime.utcnow().isoformat()
    add_exp(data[uid], 60)
    save(data)
    await ctx.send(f"✅ Daily +{amt} coins, +60 EXP")

@bot.command()
async def work(ctx):
    data = load()
    uid = str(ctx.author.id)
    ensure(data, uid)
    left = cooldown_left(data[uid]["work"])
    if left:
        await ctx.send(f"🕒 Wait {int(left//60)}m {int(left%60)}s to work.")
        return
    amt = random.randint(1100, 2500)
    data[uid]["bal"] += amt
    data[uid]["work"] = datetime.utcnow().isoformat()
    add_exp(data[uid], 45)
    save(data)
    await ctx.send(f"💼 Work +{amt} coins, +45 EXP")

@bot.command()
async def shop(ctx):
    msg = "**🪙 Crypto Shop (prices update hourly):**\n"
    for coin, price in CRYPTO_SHOP.items():
        msg += f"`{coin}` {CRYPTO_LIST[coin]} — {price} coins\n"
    await ctx.send(msg)

@bot.command()
async def buy(ctx, item):
    data = load()
    uid = str(ctx.author.id)
    ensure(data, uid)
    item = item.lower()
    if item not in CRYPTO_SHOP:
        await ctx.send("❌ Item not found.")
        return
    cost = CRYPTO_SHOP[item]
    if data[uid]["bal"] < cost:
        await ctx.send("❌ Not enough coins.")
        return
    data[uid]["bal"] -= cost
    data[uid]["inv"][item] = data[uid]["inv"].get(item, 0) + 1
    add_exp(data[uid], 20)
    save(data)
    await ctx.send(f"✅ Bought 1 {item.upper()} for {cost} coins")

@bot.command()
async def sell(ctx, item):
    data = load()
    uid = str(ctx.author.id)
    ensure(data, uid)
    item = item.lower()
    inv = data[uid]["inv"]
    if item not in inv or inv[item] < 1:
        await ctx.send("❌ You don't own that.")
        return
    price = int(CRYPTO_SHOP[item] * 0.6)
    data[uid]["inv"][item] -= 1
    data[uid]["bal"] += price
    save(data)
    await ctx.send(f"✅ Sold 1 {item.upper()} for {price} coins")

@bot.command()
async def inv(ctx):
    data = load()
    uid = str(ctx.author.id)
    ensure(data, uid)
    items = data[uid]["inv"]
    if not items:
        await ctx.send("🎒 Inventory is empty.")
        return
    msg = "**🎒 Inventory:**\n"
    for item, amt in items.items():
        if amt > 0:
            msg += f"{item.upper()} x{amt}\n"
    await ctx.send(msg)

@bot.command(name="cf")
async def coinflip(ctx, amount: int, guess: str):
    data = load()
    uid = str(ctx.author.id)
    ensure(data, uid)
    guess = guess.lower()
    if guess not in ["heads", "tails"]:
        await ctx.send("❌ Guess `heads` or `tails`.")
        return
    if amount <= 0 or amount > MAX_BET:
        await ctx.send(f"❌ Bet must be 1–{MAX_BET}")
        return
    if data[uid]["bal"] < amount:
        await ctx.send("❌ Not enough coins.")
        return
    result = random.choice(["heads", "tails"])
    if result == guess:
        win = int(amount * 0.85)
        data[uid]["bal"] += win
        add_exp(data[uid], 30)
        await ctx.send(f"🎉 You won {win} coins! Result: `{result}`")
    else:
        data[uid]["bal"] -= amount
        add_exp(data[uid], 10)
        await ctx.send(f"💀 You lost {amount}. Result: `{result}`")
    save(data)

@bot.command(name="bj")
async def blackjack(ctx, bet: int):
    data = load()
    uid = str(ctx.author.id)
    ensure(data, uid)
    if bet <= 0 or bet > MAX_BET:
        await ctx.send(f"❌ Bet must be 1–{MAX_BET}")
        return
    if data[uid]["bal"] < bet:
        await ctx.send("❌ Not enough coins.")
        return

    def deal():
        return random.choice([2,3,4,5,6,7,8,9,10,10,10,10,11])
    
    def val(hand):
        v = sum(hand)
        aces = hand.count(11)
        while v > 21 and aces:
            v -= 10
            aces -= 1
        return v

    player = [deal(), deal()]
    dealer = [deal(), deal()]
    await ctx.send(f"Your cards: {player} (Total: {val(player)})\nDealer shows: {dealer[0]}")
    m = await ctx.send("⏱ React: ✅ = hit, ❌ = stand")
    await m.add_reaction("✅")
    await m.add_reaction("❌")

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == m.id

    while True:
        try:
            r, u = await bot.wait_for("reaction_add", timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send("⏰ Timeout. Game ended.")
            return
        if str(r.emoji) == "✅":
            player.append(deal())
            await ctx.send(f"You drew {player[-1]} (Total: {val(player)})")
            if val(player) > 21:
                data[uid]["bal"] -= bet
                add_exp(data[uid], 10)
                save(data)
                await ctx.send("💥 Bust! You lose.")
                return
        else:
            break

    while val(dealer) < 17:
        dealer.append(deal())
    await ctx.send(f"Dealer's cards: {dealer} (Total: {val(dealer)})")

    if val(dealer) > 21 or val(player) > val(dealer):
        win = int(bet * 1.8)
        data[uid]["bal"] += win
        add_exp(data[uid], 50)
        await ctx.send(f"🎉 You win {win} coins!")
    elif val(player) == val(dealer):
        await ctx.send("🤝 It's a tie.")
    else:
        data[uid]["bal"] -= bet
        add_exp(data[uid], 10)
        await ctx.send("💀 You lose.")
    save(data)

@bot.command(name="cups")
async def cups(ctx, bet: int):
    data = load()
    uid = str(ctx.author.id)
    ensure(data, uid)
    if bet <= 0 or bet > MAX_BET:
        await ctx.send(f"❌ Bet must be 1–{MAX_BET}")
        return
    if data[uid]["bal"] < bet:
        await ctx.send("❌ Not enough coins.")
        return

    msg = await ctx.send("🥤🥤🥤 Pick a cup: 1️⃣ 2️⃣ 3️⃣")
    for emoji in ["1️⃣", "2️⃣", "3️⃣"]:
        await msg.add_reaction(emoji)

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in ["1️⃣", "2️⃣", "3️⃣"] and reaction.message.id == msg.id

    try:
        r, u = await bot.wait_for("reaction_add", timeout=30.0, check=check)
    except:
        await ctx.send("⏰ Timeout!")
        return

    pick = ["1️⃣", "2️⃣", "3️⃣"].index(str(r.emoji)) + 1
    win_cup = random.randint(1, 3)

    if pick == win_cup:
        win = int(bet * 2.5)
        data[uid]["bal"] += win
        add_exp(data[uid], 50)
        await ctx.send(f"🎉 Correct! You won {win} coins.")
    else:
        data[uid]["bal"] -= bet
        add_exp(data[uid], 10)
        await ctx.send(f"💀 Wrong! Prize was in cup {win_cup}. You lost {bet} coins.")
    save(data)

# Run the bot with your token from environment
bot.run(os.getenv("TOKEN"))
