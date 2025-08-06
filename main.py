import discord
from discord.ext import commands, tasks
import os, random, json
from datetime import datetime, timedelta

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

DATA_FILE = "economy.json"
MAX_BET = 250_000
COOLDOWN_SEC = 2400  # 40 minutes cooldown

# Initial crypto coins with base prices
CRYPTOS = {
    "BTC": 30000,
    "ETH": 2000,
    "SOL": 30,
    "ADA": 1,
    "DOGE": 0.1,
    "MATIC": 1.5,
}

def load_data():
    try:
        with open(DATA_FILE) as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def ensure_user(data, uid):
    if uid not in data:
        data[uid] = {
            "bal": 1000,
            "exp": 0,
            "lvl": 1,
            "daily": None,
            "work": None,
            "inv": {},
        }

def cooldown_left(last_time):
    if not last_time:
        return 0
    diff = (datetime.utcnow() - datetime.fromisoformat(last_time)).total_seconds()
    return max(0, COOLDOWN_SEC - diff)

def add_exp(user, amount):
    user["exp"] += amount
    while user["exp"] >= 1000:
        user["exp"] -= 1000
        user["lvl"] += 1

# Prices dict updated every hour, start as copy of CRYPTOS base prices
prices = CRYPTOS.copy()

@tasks.loop(hours=1)
async def update_crypto_prices():
    global prices
    for coin in prices:
        base = CRYPTOS[coin]
        # fluctuate by ±10%
        change_percent = random.uniform(-0.1, 0.1)
        new_price = max(0.01, base * (1 + change_percent))
        prices[coin] = round(new_price, 2)
    print("Crypto prices updated:", prices)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} - Ready!")
    update_crypto_prices.start()

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")

@bot.command(name="bal")
async def balance(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]
    await ctx.send(f"💰 Balance: {user['bal']} | Level: {user['lvl']} | EXP: {user['exp']}/1000")

@bot.command()
async def daily(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    left = cooldown_left(data[uid]["daily"])
    if left > 0:
        await ctx.send(f"🕒 Wait {int(left//60)}m {int(left%60)}s for your daily reward.")
        return
    reward = random.randint(1500, 3500)
    data[uid]["bal"] += reward
    data[uid]["daily"] = datetime.utcnow().isoformat()
    add_exp(data[uid], 60)
    save_data(data)
    await ctx.send(f"✅ You received your daily {reward} coins and 60 EXP!")

@bot.command()
async def work(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    left = cooldown_left(data[uid]["work"])
    if left > 0:
        await ctx.send(f"🕒 Wait {int(left//60)}m {int(left%60)}s before working again.")
        return
    reward = random.randint(1100, 2500)
    data[uid]["bal"] += reward
    data[uid]["work"] = datetime.utcnow().isoformat()
    add_exp(data[uid], 45)
    save_data(data)
    await ctx.send(f"💼 You worked and earned {reward} coins and 45 EXP!")

@bot.command()
async def shop(ctx):
    msg = "**🪙 Crypto Shop (prices update hourly):**\n"
    for coin, price in prices.items():
        msg += f"`{coin}` : {price} coins\n"
    await ctx.send(msg)

@bot.command()
async def buy(ctx, coin: str, qty: int):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    coin = coin.upper()
    if coin not in prices:
        await ctx.send("❌ That cryptocurrency is not available.")
        return
    if qty <= 0:
        await ctx.send("❌ Quantity must be positive.")
        return
    cost = prices[coin] * qty
    if data[uid]["bal"] < cost:
        await ctx.send(f"❌ You need {cost} coins but only have {data[uid]['bal']}.")
        return
    data[uid]["bal"] -= cost
    inv = data[uid]["inv"]
    inv[coin] = inv.get(coin, 0) + qty
    add_exp(data[uid], 20 * qty)
    save_data(data)
    await ctx.send(f"✅ You bought {qty} {coin} for {cost} coins.")

@bot.command()
async def sell(ctx, coin: str, qty: int):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    coin = coin.upper()
    inv = data[uid]["inv"]
    if coin not in inv or inv[coin] < qty or qty <= 0:
        await ctx.send("❌ You don't have enough of that coin.")
        return
    price = prices[coin] * qty * 0.6  # 60% sellback price
    inv[coin] -= qty
    if inv[coin] == 0:
        del inv[coin]
    data[uid]["bal"] += int(price)
    save_data(data)
    await ctx.send(f"✅ Sold {qty} {coin} for {int(price)} coins.")

@bot.command(name="inv")
async def inventory(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    inv = data[uid]["inv"]
    if not inv:
        await ctx.send("🎒 Your inventory is empty.")
        return
    msg = "**🎒 Inventory:**\n"
    for coin, qty in inv.items():
        msg += f"{coin} x{qty}\n"
    await ctx.send(msg)

@bot.command(name="cf")
async def coinflip(ctx, amount: int, guess: str):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    guess = guess.lower()
    if guess not in ["heads", "tails"]:
        await ctx.send("❌ Guess must be 'heads' or 'tails'.")
        return
    if amount <= 0 or amount > MAX_BET:
        await ctx.send(f"❌ Bet amount must be between 1 and {MAX_BET}.")
        return
    if data[uid]["bal"] < amount:
        await ctx.send("❌ You don't have enough coins.")
        return
    result = random.choice(["heads", "tails"])
    if guess == result:
        win = int(amount * 0.85)
        data[uid]["bal"] += win
        add_exp(data[uid], 30)
        await ctx.send(f"🎉 You won {win} coins! Result: {result}")
    else:
        data[uid]["bal"] -= amount
        add_exp(data[uid], 10)
        await ctx.send(f"💀 You lost {amount} coins. Result: {result}")
    save_data(data)

# Reaction based blackjack game
@bot.command(name="bj")
async def blackjack(ctx, bet: int):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    if bet <= 0 or bet > MAX_BET:
        await ctx.send(f"❌ Bet must be between 1 and {MAX_BET}.")
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

    def hand_str(hand):
        return ", ".join(str(c) for c in hand)

    await ctx.send(f"Your hand: {hand_str(player)} (total {hand_value(player)})\nDealer shows: {dealer[0]}")

    msg = await ctx.send("React with 🖐️ to HIT or ✋ to STAND.")

    await msg.add_reaction("🖐️")  # hit
    await msg.add_reaction("✋")   # stand

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in ["🖐️", "✋"] and reaction.message.id == msg.id

    while True:
        try:
            reaction, user = await bot.wait_for("reaction_add", timeout=30.0, check=check)
        except:
            await ctx.send("⏰ Timeout! Game ended.")
            return

        if str(reaction.emoji) == "🖐️":
            player.append(deal_card())
            val = hand_value(player)
            await ctx.send(f"You drew {player[-1]}. Total now {val}.")
            if val > 21:
                data[uid]["bal"] -= bet
                add_exp(data[uid], 10)
                save_data(data)
                await ctx.send("💥 Bust! You lose.")
                return
        else:  # stand
            break

    while hand_value(dealer) < 17:
        dealer.append(deal_card())
    p_val = hand_value(player)
    d_val = hand_value(dealer)

    await ctx.send(f"Dealer's hand: {hand_str(dealer)} (total {d_val})")

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
    save_data(data)

# Reaction-based cups game
@bot.command(name="cups")
async def cups(ctx, bet: int):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    if bet <= 0 or bet > MAX_BET:
        await ctx.send(f"❌ Bet must be between 1 and {MAX_BET}.")
        return
    if data[uid]["bal"] < bet:
        await ctx.send("❌ Not enough coins.")
        return

    cups_list = ["🥤", "🥤", "🥤"]
    prize_cup = random.randint(1, 3)
    display = "Choose the cup with the prize (1-3):\n" + " ".join([str(i) for i in range(1, 4)]) + "\n" + " ".join(cups_list)
    msg = await ctx.send(display)

    emojis = ["1️⃣", "2️⃣", "3️⃣"]
    for e in emojis:
        await msg.add_reaction(e)

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in emojis and reaction.message.id == msg.id

    try:
        reaction, user = await bot.wait_for("reaction_add", timeout=30.0, check=check)
    except:
        await ctx.send("⏰ Timeout! Game cancelled.")
        return

    guess = emojis.index(str(reaction.emoji)) + 1
    # Shuffle cups and get new prize position
    positions = [1, 2, 3]
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
    save_data(data)

bot.run(os.getenv("TOKEN"))

