import discord
from discord.ext import commands, tasks
import os, random, json
from datetime import datetime

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
DATA = "economy.json"
MAX_BET = 250_000
CD = 2400  # 40 min cooldown seconds

# Shop with cryptocurrencies that update hourly
CRYPTOCURRENCIES = {
    "Bitcoin": {"symbol": "BTC", "price": 40000, "desc": "Popular crypto"},
    "Ethereum": {"symbol": "ETH", "price": 3000, "desc": "Smart contract platform"},
    "Dogecoin": {"symbol": "DOGE", "price": 0.2, "desc": "Meme coin"},
    "Solana": {"symbol": "SOL", "price": 150, "desc": "Fast blockchain"},
    "Cardano": {"symbol": "ADA", "price": 1.5, "desc": "Proof of stake"},
}

def load():
    try:
        with open(DATA) as f:
            return json.load(f)
    except:
        return {}

def save(data):
    with open(DATA, "w") as f:
        json.dump(data, f, indent=2)

def ensure(data, uid):
    if uid not in data:
        data[uid] = {"bal": 1000, "exp": 0, "lvl": 1, "daily": None, "work": None, "inv": {}}

def cd_left(last):
    if not last:
        return 0
    diff = (datetime.utcnow() - datetime.fromisoformat(last)).total_seconds()
    return max(0, CD - diff)

def add_exp(user, amt):
    user["exp"] += amt
    while user["exp"] >= 1000:
        user["exp"] -= 1000
        user["lvl"] += 1

@tasks.loop(hours=1)
async def update_crypto_prices():
    for c in CRYPTOCURRENCIES:
        base = CRYPTOCURRENCIES[c]["price"]
        # Randomly fluctuate price +-5%
        change = base * random.uniform(-0.05, 0.05)
        new_price = max(0.01, base + change)
        CRYPTOCURRENCIES[c]["price"] = round(new_price, 2)
    print("Updated crypto prices:", {k: v["price"] for k,v in CRYPTOCURRENCIES.items()})

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} - Ready!")
    update_crypto_prices.start()

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
    left = cd_left(data[uid]["daily"])
    if left:
        await ctx.send(f"🕒 Wait {int(left//60)}m {int(left%60)}s for daily.")
        return
    reward = random.randint(1500, 3500)
    data[uid]["bal"] += reward
    data[uid]["daily"] = datetime.utcnow().isoformat()
    add_exp(data[uid], 60)
    save(data)
    await ctx.send(f"✅ Daily +{reward} coins, +60 EXP")

@bot.command()
async def work(ctx):
    data = load()
    uid = str(ctx.author.id)
    ensure(data, uid)
    left = cd_left(data[uid]["work"])
    if left:
        await ctx.send(f"🕒 Wait {int(left//60)}m {int(left%60)}s for work.")
        return
    reward = random.randint(1100, 2500)
    data[uid]["bal"] += reward
    data[uid]["work"] = datetime.utcnow().isoformat()
    add_exp(data[uid], 45)
    save(data)
    await ctx.send(f"💼 Work +{reward} coins, +45 EXP")

@bot.command()
async def shop(ctx):
    msg = "**🪙 Crypto Shop (prices update hourly):**\n"
    for c,v in CRYPTOCURRENCIES.items():
        price = v["price"]
        msg += f"`{v['symbol']}`: {price} coins — {v['desc']}\n"
    await ctx.send(msg)

@bot.command()
async def buy(ctx, symbol: str):
    data = load()
    uid = str(ctx.author.id)
    symbol = symbol.upper()
    ensure(data, uid)
    # Find crypto by symbol
    item = None
    for c,v in CRYPTOCURRENCIES.items():
        if v["symbol"] == symbol:
            item = c
            break
    if not item:
        await ctx.send("❌ Crypto not found.")
        return
    cost = CRYPTOCURRENCIES[item]["price"]
    if data[uid]["bal"] < cost:
        await ctx.send("❌ Not enough coins.")
        return
    data[uid]["bal"] -= cost
    inv = data[uid]["inv"]
    inv[item] = inv.get(item, 0) + 1
    add_exp(data[uid], 20)
    save(data)
    await ctx.send(f"✅ Bought 1 {item} ({symbol}) for {cost} coins")

@bot.command()
async def sell(ctx, symbol: str):
    data = load()
    uid = str(ctx.author.id)
    symbol = symbol.upper()
    ensure(data, uid)
    inv = data[uid]["inv"]
    item = None
    for c,v in CRYPTOCURRENCIES.items():
        if v["symbol"] == symbol:
            item = c
            break
    if not item or item not in inv or inv[item] < 1:
        await ctx.send("❌ You don't own this crypto.")
        return
    price = int(CRYPTOCURRENCIES[item]["price"] * 0.6)
    inv[item] -= 1
    data[uid]["bal"] += price
    save(data)
    await ctx.send(f"✅ Sold 1 {item} ({symbol}) for {price} coins")

@bot.command()
async def inv(ctx):
    data = load()
    uid = str(ctx.author.id)
    ensure(data, uid)
    inv = data[uid]["inv"]
    if not inv:
        await ctx.send("🎒 Inventory empty.")
        return
    msg = "**🎒 Inventory:**\n"
    for i,v in inv.items():
        if v>0:
            sym = CRYPTOCURRENCIES[i]["symbol"] if i in CRYPTOCURRENCIES else "?"
            msg += f"{i} ({sym}) x{v}\n"
    await ctx.send(msg)

@bot.command(name="cf")
async def coinflip(ctx, amount: int, guess: str):
    data = load()
    uid = str(ctx.author.id)
    ensure(data, uid)
    guess = guess.lower()
    if guess not in ["heads", "tails"]:
        await ctx.send("❌ Guess heads or tails.")
        return
    if amount <= 0 or amount > MAX_BET:
        await ctx.send(f"❌ Bet 1-{MAX_BET} coins.")
        return
    if data[uid]["bal"] < amount:
        await ctx.send("❌ Not enough coins.")
        return
    result = random.choice(["heads", "tails"])
    if guess == result:
        win = int(amount * 0.85)
        data[uid]["bal"] += win
        add_exp(data[uid], 30)
        await ctx.send(f"🎉 You won {win}! Result: {result}")
    else:
        data[uid]["bal"] -= amount
        add_exp(data[uid], 10)
        await ctx.send(f"💀 You lost {amount}. Result: {result}")
    save(data)

# BlackJack with reaction controls
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

    def deal_card():
        cards = [2,3,4,5,6,7,8,9,10,10,10,10,11]
        return random.choice(cards)

    def hand_value(hand):
        val = sum(hand)
        aces = hand.count(11)
        while val > 21 and aces:
            val -= 10
            aces -= 1
        return val

    player = [deal_card(), deal_card()]
    dealer = [deal_card(), deal_card()]

    msg = await ctx.send(
        f"Your hand: {player} (total {hand_value(player)})\nDealer shows: {dealer[0]}\n"
        "React with ▶️ to Hit or ⏹️ to Stand."
    )
    await msg.add_reaction("▶️")
    await msg.add_reaction("⏹️")

    def check(reaction, user):
        return (
            user == ctx.author
            and reaction.message.id == msg.id
            and str(reaction.emoji) in ["▶️", "⏹️"]
        )

    while True:
        try:
            reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=check)
        except:
            await ctx.send("⏰ Timeout! Game ended.")
            return

        if str(reaction.emoji) == "▶️":
            player.append(deal_card())
            val = hand_value(player)
            await ctx.send(f"You drew {player[-1]}. Total now {val}")
            if val > 21:
                data[uid]["bal"] -= bet
                add_exp(data[uid], 10)
                save(data)
                await ctx.send("💥 Bust! You lose.")
                return
        else:
            break

    while hand_value(dealer) < 17:
        dealer.append(deal_card())

    p_val = hand_value(player)
    d_val = hand_value(dealer)

    await ctx.send(f"Dealer's hand: {dealer} (total {d_val})")

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

# Cups game with reactions
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
    prize_cup = random.randint(1,3)
    display = " ".join([f"{i+1}" for i in range(3)]) + "\n" + " ".join(cups)
    msg = await ctx.send(f"Cups game!\nGuess the cup with the prize (1-3):\n{display}")

    emojis = ["1️⃣", "2️⃣", "3️⃣"]
    for e in emojis:
        await msg.add_reaction(e)

    def check(reaction, user):
        return (
            user == ctx.author
            and reaction.message.id == msg.id
            and str(reaction.emoji) in emojis
        )

    try:
        reaction, user = await bot.wait_for("reaction_add", timeout=30.0, check=check)
    except:
        await ctx.send("⏰ Timeout! Game cancelled.")
        return

    guess = emojis.index(str(reaction.emoji)) + 1
    positions = [1,2,3]
    random.shuffle(positions)
    real_pos = positions.index(prize_cup) + 1

    if guess == real_pos:
        win = int(bet * 2.5)
        data[uid]["bal"] += win
        add_exp(data[uid], 50)
        await ctx.send(f"🎉 Correct! You won {win} coins!")
    else:
        data[uid]["bal"] -= bet
        add_exp(data[uid], 10)
        await ctx.send(f"💀 Wrong! The prize was under cup {real_pos}. You lost {bet} coins.")
    save(data)

bot.run(os.getenv("DISCORD_TOKEN"))
