import discord
from discord.ext import commands, tasks
import os, random, json
from datetime import datetime, timedelta

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "economy.json"
MAX_BET = 250_000
CD_SECONDS = 2400  # 40 minutes cooldown

# Initial crypto coins for shop
CRYPTOS = {
    "BTC": 20000,
    "ETH": 1500,
    "DOGE": 0.06,
    "ADA": 0.45,
    "SOL": 22,
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
            "bal": 1000,
            "exp": 0,
            "lvl": 1,
            "daily": None,
            "work": None,
            "inv": {}
        }

def cd_left(last_time):
    if not last_time:
        return 0
    diff = (datetime.utcnow() - datetime.fromisoformat(last_time)).total_seconds()
    return max(0, CD_SECONDS - diff)

def add_exp(user_data, amount):
    user_data["exp"] += amount
    while user_data["exp"] >= 1000:
        user_data["exp"] -= 1000
        user_data["lvl"] += 1

def update_crypto_prices():
    for k in CRYPTOS:
        base = CRYPTOS[k]
        change = random.uniform(-0.05, 0.07)  # -5% to +7%
        new_price = base * (1 + change)
        CRYPTOS[k] = round(max(new_price, 0.01), 2)

@tasks.loop(hours=1)
async def hourly_price_update():
    update_crypto_prices()
    print("Crypto prices updated:", CRYPTOS)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} - Ready!")
    hourly_price_update.start()

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")

@bot.command(aliases=["bal"])
async def balance(ctx):
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
    left = cd_left(data[uid]["daily"])
    if left > 0:
        await ctx.send(f"⏳ Wait {int(left//60)}m {int(left%60)}s for daily.")
        return
    reward = random.randint(1500, 3500)
    data[uid]["bal"] += reward
    data[uid]["daily"] = datetime.utcnow().isoformat()
    add_exp(data[uid], 60)
    save_data(data)
    await ctx.send(f"✅ Daily claimed: +{reward} coins, +60 EXP")

@bot.command()
async def work(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    left = cd_left(data[uid]["work"])
    if left > 0:
        await ctx.send(f"⏳ Wait {int(left//60)}m {int(left%60)}s before working again.")
        return
    reward = random.randint(1100, 2500)
    data[uid]["bal"] += reward
    data[uid]["work"] = datetime.utcnow().isoformat()
    add_exp(data[uid], 45)
    save_data(data)
    await ctx.send(f"💼 Work done: +{reward} coins, +45 EXP")

@bot.command()
async def shop(ctx):
    msg = "**🪙 Crypto Shop (prices update hourly):**\n"
    for coin, price in CRYPTOS.items():
        msg += f"`{coin}`: {price} coins\n"
    await ctx.send(msg)

@bot.command()
async def buy(ctx, coin: str, qty: int = 1):
    data = load_data()
    uid = str(ctx.author.id)
    coin = coin.upper()
    ensure_user(data, uid)
    if coin not in CRYPTOS:
        await ctx.send("❌ Crypto not found.")
        return
    cost = int(CRYPTOS[coin] * qty)
    if qty < 1:
        await ctx.send("❌ Quantity must be at least 1.")
        return
    if data[uid]["bal"] < cost:
        await ctx.send(f"❌ Not enough coins. Need {cost}, you have {data[uid]['bal']}.")
        return
    inv = data[uid]["inv"]
    inv[coin] = inv.get(coin, 0) + qty
    data[uid]["bal"] -= cost
    add_exp(data[uid], 20 * qty)
    save_data(data)
    await ctx.send(f"✅ Bought {qty} {coin} for {cost} coins.")

@bot.command()
async def sell(ctx, coin: str, qty: int = 1):
    data = load_data()
    uid = str(ctx.author.id)
    coin = coin.upper()
    ensure_user(data, uid)
    inv = data[uid]["inv"]
    if coin not in inv or inv[coin] < qty or qty < 1:
        await ctx.send("❌ You don't have enough of that crypto.")
        return
    price = int(CRYPTOS[coin] * qty * 0.6)
    inv[coin] -= qty
    if inv[coin] <= 0:
        del inv[coin]
    data[uid]["bal"] += price
    save_data(data)
    await ctx.send(f"✅ Sold {qty} {coin} for {price} coins.")

@bot.command(aliases=["inv"])
async def inventory(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    inv = data[uid]["inv"]
    if not inv:
        await ctx.send("🎒 Inventory empty.")
        return
    msg = "**🎒 Your Inventory:**\n"
    for c, q in inv.items():
        msg += f"{c} x{q}\n"
    await ctx.send(msg)

# --------- Gambling Commands ---------

@bot.command(aliases=["cf"])
async def coinflip(ctx, amount: int, guess: str):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    guess = guess.lower()
    if guess not in ["heads", "tails"]:
        await ctx.send("❌ Guess heads or tails.")
        return
    if amount < 1 or amount > MAX_BET:
        await ctx.send(f"❌ Bet must be between 1 and {MAX_BET}.")
        return
    if data[uid]["bal"] < amount:
        await ctx.send("❌ Not enough coins.")
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

@bot.command(aliases=["bj"])
async def blackjack(ctx, bet: int):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    if bet < 1 or bet > MAX_BET:
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
    await ctx.send(f"Your hand: {player} (total {hand_value(player)})\nDealer shows: {dealer[0]}")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["hit", "stand"]

    while True:
        await ctx.send("Type `hit` or `stand`.")
        try:
            msg = await bot.wait_for("message", timeout=30.0, check=check)
        except:
            await ctx.send("⏰ Timeout! Game ended.")
            return
        if msg.content.lower() == "hit":
            player.append(deal_card())
            val = hand_value(player)
            await ctx.send(f"You drew {player[-1]}. Total now {val}")
            if val > 21:
                data[uid]["bal"] -= bet
                add_exp(data[uid], 10)
                save_data(data)
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
    save_data(data)

@bot.command()
async def cups(ctx, bet: int):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    if bet < 1 or bet > MAX_BET:
        await ctx.send(f"❌ Bet must be between 1 and {MAX_BET}.")
        return
    if data[uid]["bal"] < bet:
        await ctx.send("❌ Not enough coins.")
        return

    cups = ["🥤", "🥤", "🥤"]
    prize_cup = random.randint(1, 3)
    display = " ".join([f"{i+1}" for i in range(3)]) + "\n" + " ".join(cups)
    await ctx.send(f"Cups game!\nGuess the cup with the prize (1-3):\n{display}")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content in ["1", "2", "3"]

    try:
        msg = await bot.wait_for("message", timeout=30.0, check=check)
    except:
        await ctx.send("⏰ Timeout! Game cancelled.")
        return

    guess = int(msg.content)
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

# Horse racing command

@bot.command()
async def hr(ctx, bet: int):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)

    if bet < 1 or bet > MAX_BET:
        await ctx.send(f"❌ Bet must be between 1 and {MAX_BET}.")
        return
    if data[uid]["bal"] < bet:
        await ctx.send("❌ Not enough coins.")
        return

    horses = ["🏇1", "🏇2", "🏇3", "🏇4"]
    positions = [0, 0, 0, 0]
    finish_line = 15

    msg = await ctx.send("🏁 Horse race starting! Get ready!")
    await ctx.sleep(2)

    winner = None
    while max(positions) < finish_line:
        await ctx.sleep(1)
        # advance random horse(s)
        for i in range(4):
            positions[i] += random.choice([0,1,1,2])  # biased to move 1 or 2 steps
        race_status = ""
        for i in range(4):
            race_status += f"{horses[i]}: " + "🏇" * positions[i] + "\n"
        await msg.edit(content=race_status)
    max_pos = max(positions)
    winners = [horses[i] for i,p in enumerate(positions) if p == max_pos]
    winner = random.choice(winners)

    if winner[-1] == "1":
        win_mult = 3
    elif winner[-1] == "2":
        win_mult = 2.5
    elif winner[-1] == "3":
        win_mult = 2
    else:
        win_mult = 1.5

    if winner == "🏇1":
        horse_num = 1
    elif winner == "🏇2":
        horse_num = 2
    elif winner == "🏇3":
        horse_num = 3
    else:
        horse_num = 4

    if winner == "🏇" + str(horse_num):
        if winner[-1] == str(horse_num):
            pass

    await ctx.send(f"🏆 Horse {horse_num} won!")
    if bet and winner[-1] == str(horse_num):
        win_amount = int(bet * win_mult)
        data[uid]["bal"] += win_amount
        add_exp(data[uid], 100)
        save_data(data)
        await ctx.send(f"🎉 You won {win_amount} coins!")
    else:
        data[uid]["bal"] -= bet
        add_exp(data[uid], 10)
        save_data(data)
        await ctx.send(f"💀 You lost {bet} coins.")

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
