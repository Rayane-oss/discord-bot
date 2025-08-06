import discord
from discord.ext import commands, tasks
import asyncio
import random
import sqlite3
from datetime import datetime, timedelta

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

DB_FILE = "economy.db"
MAX_BET = 250_000
CD_SECONDS = 40 * 60  # 40 minutes cooldown


# --- DB helper functions ---
def db_connect():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def create_tables():
    conn = db_connect()
    c = conn.cursor()
    # Users table
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        balance INTEGER DEFAULT 1000,
        exp INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        daily_cd TEXT,
        work_cd TEXT
    )""")
    # Inventory table
    c.execute("""CREATE TABLE IF NOT EXISTS inventory (
        user_id TEXT,
        item TEXT,
        amount INTEGER DEFAULT 0,
        PRIMARY KEY(user_id, item)
    )""")
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (str(user_id),))
    user = c.fetchone()
    if not user:
        c.execute("INSERT INTO users(user_id) VALUES (?)", (str(user_id),))
        conn.commit()
        c.execute("SELECT * FROM users WHERE user_id = ?", (str(user_id),))
        user = c.fetchone()
    conn.close()
    return user

def update_user(user_id, balance=None, exp=None, level=None, daily_cd=None, work_cd=None):
    conn = db_connect()
    c = conn.cursor()
    fields = []
    vals = []
    if balance is not None:
        fields.append("balance = ?")
        vals.append(balance)
    if exp is not None:
        fields.append("exp = ?")
        vals.append(exp)
    if level is not None:
        fields.append("level = ?")
        vals.append(level)
    if daily_cd is not None:
        fields.append("daily_cd = ?")
        vals.append(daily_cd)
    if work_cd is not None:
        fields.append("work_cd = ?")
        vals.append(work_cd)
    vals.append(str(user_id))
    if fields:
        c.execute(f"UPDATE users SET {', '.join(fields)} WHERE user_id = ?", vals)
        conn.commit()
    conn.close()

def get_inventory(user_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT item, amount FROM inventory WHERE user_id = ?", (str(user_id),))
    inv = {row["item"]: row["amount"] for row in c.fetchall()}
    conn.close()
    return inv

def add_item(user_id, item, amount=1):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT amount FROM inventory WHERE user_id = ? AND item = ?", (str(user_id), item))
    res = c.fetchone()
    if res:
        new_amt = res["amount"] + amount
        c.execute("UPDATE inventory SET amount = ? WHERE user_id = ? AND item = ?", (new_amt, str(user_id), item))
    else:
        c.execute("INSERT INTO inventory (user_id, item, amount) VALUES (?, ?, ?)", (str(user_id), item, amount))
    conn.commit()
    conn.close()

def remove_item(user_id, item, amount=1):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT amount FROM inventory WHERE user_id = ? AND item = ?", (str(user_id), item))
    res = c.fetchone()
    if not res or res["amount"] < amount:
        conn.close()
        return False
    new_amt = res["amount"] - amount
    if new_amt == 0:
        c.execute("DELETE FROM inventory WHERE user_id = ? AND item = ?", (str(user_id), item))
    else:
        c.execute("UPDATE inventory SET amount = ? WHERE user_id = ? AND item = ?", (new_amt, str(user_id), item))
    conn.commit()
    conn.close()
    return True


# --- Economy and Shop ---

# Cryptocurrencies that change prices every hour
CRYPTOCURRENCIES = {
    "BTC": {"base": 30000, "desc": "Bitcoin"},
    "ETH": {"base": 2000, "desc": "Ethereum"},
    "DOGE": {"base": 0.3, "desc": "Dogecoin"},
    "SOL": {"base": 25, "desc": "Solana"},
    "ADA": {"base": 1.2, "desc": "Cardano"},
}

# Current prices will be updated every hour
current_prices = {}

def update_prices():
    global current_prices
    new_prices = {}
    for sym, info in CRYPTOCURRENCIES.items():
        base = info["base"]
        # Random price variation ±10%
        change_percent = random.uniform(-0.1, 0.1)
        price = max(0.01, base * (1 + change_percent))
        new_prices[sym] = round(price, 2)
    current_prices = new_prices

def add_exp_and_level(user_id, add_exp):
    user = get_user(user_id)
    new_exp = user["exp"] + add_exp
    new_level = user["level"]
    while new_exp >= 1000:
        new_exp -= 1000
        new_level += 1
    update_user(user_id, exp=new_exp, level=new_level)

def cooldown_left(last_time_str):
    if not last_time_str:
        return 0
    last_time = datetime.fromisoformat(last_time_str)
    diff = datetime.utcnow() - last_time
    left = CD_SECONDS - diff.total_seconds()
    return max(0, left)


# Update prices every hour task
@tasks.loop(hours=1)
async def hourly_price_update():
    update_prices()
    print("🔄 Crypto prices updated:", current_prices)

@bot.event
async def on_ready():
    create_tables()
    update_prices()
    hourly_price_update.start()
    print(f"Bot ready as {bot.user}")



# --- Commands ---


@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")


@bot.command()
async def bal(ctx):
    user = get_user(ctx.author.id)
    await ctx.send(f"💰 Balance: {user['balance']} | Level: {user['level']} | EXP: {user['exp']}/1000")


@bot.command()
async def daily(ctx):
    user = get_user(ctx.author.id)
    left = cooldown_left(user["daily_cd"])
    if left > 0:
        await ctx.send(f"🕒 Wait {int(left // 60)}m {int(left % 60)}s to claim daily reward.")
        return
    reward = random.randint(1500, 3500)
    new_balance = user["balance"] + reward
    update_user(ctx.author.id, balance=new_balance, daily_cd=datetime.utcnow().isoformat())
    add_exp_and_level(ctx.author.id, 60)
    await ctx.send(f"✅ You claimed your daily {reward} coins and earned +60 EXP.")


@bot.command()
async def work(ctx):
    user = get_user(ctx.author.id)
    left = cooldown_left(user["work_cd"])
    if left > 0:
        await ctx.send(f"🕒 Wait {int(left // 60)}m {int(left % 60)}s to work again.")
        return
    reward = random.randint(1100, 2500)
    new_balance = user["balance"] + reward
    update_user(ctx.author.id, balance=new_balance, work_cd=datetime.utcnow().isoformat())
    add_exp_and_level(ctx.author.id, 45)
    await ctx.send(f"💼 You worked and earned {reward} coins and +45 EXP.")


@bot.command()
async def shop(ctx):
    msg = "**🪙 Crypto Shop (prices update hourly):**\n"
    for sym, price in current_prices.items():
        desc = CRYPTOCURRENCIES[sym]["desc"]
        msg += f"`{sym}`: {price} coins — {desc}\n"
    await ctx.send(msg)


@bot.command()
async def buy(ctx, symbol: str):
    symbol = symbol.upper()
    if symbol not in current_prices:
        await ctx.send("❌ Invalid crypto symbol.")
        return
    user = get_user(ctx.author.id)
    price = current_prices[symbol]
    if user["balance"] < price:
        await ctx.send("❌ Not enough coins to buy.")
        return
    new_balance = user["balance"] - price
    update_user(ctx.author.id, balance=new_balance)
    add_item(ctx.author.id, symbol, 1)
    add_exp_and_level(ctx.author.id, 20)
    await ctx.send(f"✅ Bought 1 {symbol} for {price} coins.")


@bot.command()
async def sell(ctx, symbol: str):
    symbol = symbol.upper()
    user = get_user(ctx.author.id)
    inv = get_inventory(ctx.author.id)
    if symbol not in inv or inv[symbol] < 1:
        await ctx.send("❌ You don't own this crypto.")
        return
    price = current_prices.get(symbol, 0)
    sell_price = int(price * 0.6)
    success = remove_item(ctx.author.id, symbol, 1)
    if not success:
        await ctx.send("❌ Could not sell the item.")
        return
    new_balance = user["balance"] + sell_price
    update_user(ctx.author.id, balance=new_balance)
    await ctx.send(f"✅ Sold 1 {symbol} for {sell_price} coins.")


@bot.command()
async def inv(ctx):
    inv = get_inventory(ctx.author.id)
    if not inv:
        await ctx.send("🎒 Your inventory is empty.")
        return
    msg = "**🎒 Your Inventory:**\n"
    for item, amount in inv.items():
        if amount > 0:
            msg += f"{item} x{amount}\n"
    await ctx.send(msg)


@bot.command(name="cf")
async def coinflip(ctx, amount: int, guess: str):
    guess = guess.lower()
    if guess not in ["heads", "tails"]:
        await ctx.send("❌ Guess 'heads' or 'tails'.")
        return
    if amount <= 0 or amount > MAX_BET:
        await ctx.send(f"❌ Bet must be 1 to {MAX_BET} coins.")
        return
    user = get_user(ctx.author.id)
    if user["balance"] < amount:
        await ctx.send("❌ Not enough coins.")
        return

    result = random.choice(["heads", "tails"])
    if guess == result:
        win_amt = int(amount * 0.85)
        new_balance = user["balance"] + win_amt
        update_user(ctx.author.id, balance=new_balance)
        add_exp_and_level(ctx.author.id, 30)
        await ctx.send(f"🎉 You won {win_amt} coins! Result: {result}")
    else:
        new_balance = user["balance"] - amount
        update_user(ctx.author.id, balance=new_balance)
        add_exp_and_level(ctx.author.id, 10)
        await ctx.send(f"💀 You lost {amount} coins. Result: {result}")


# --- Blackjack with reactions ---
@bot.command(name="bj")
async def blackjack(ctx, bet: int):
    if bet <= 0 or bet > MAX_BET:
        await ctx.send(f"❌ Bet must be 1 to {MAX_BET} coins.")
        return
    user = get_user(ctx.author.id)
    if user["balance"] < bet:
        await ctx.send("❌ Not enough coins.")
        return

    def deal_card():
        cards = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11]
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

    def format_hand(hand):
        return ", ".join(str(c) for c in hand)

    embed = discord.Embed(title="Blackjack", description=f"Your hand: {format_hand(player)} (total {hand_value(player)})\nDealer shows: {dealer[0]}")
    game_msg = await ctx.send(embed=embed)

    HIT_EMOJI = "🖐️"
    STAND_EMOJI = "✋"

    await game_msg.add_reaction(HIT_EMOJI)
    await game_msg.add_reaction(STAND_EMOJI)

    def check(reaction, user):
        return user == ctx.author and reaction.message.id == game_msg.id and str(reaction.emoji) in [HIT_EMOJI, STAND_EMOJI]

    while True:
        try:
            reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send("⏰ Timeout! Game ended.")
            return

        if str(reaction.emoji) == HIT_EMOJI:
            player.append(deal_card())
            val = hand_value(player)
            embed.description = f"Your hand: {format_hand(player)} (total {val})\nDealer shows: {dealer[0]}"
            await game_msg.edit(embed=embed)
            await game_msg.remove_reaction(HIT_EMOJI, user)
            await game_msg.remove_reaction(STAND_EMOJI, user)
            await game_msg.add_reaction(HIT_EMOJI)
            await game_msg.add_reaction(STAND_EMOJI)
            if val > 21:
                new_balance = user["balance"] - bet
                update_user(ctx.author.id, balance=new_balance)
                add_exp_and_level(ctx.author.id, 10)
                await ctx.send("💥 Bust! You lose.")
                return
        else:
            # Stand - dealer plays
            break

    while hand_value(dealer) < 17:
        dealer.append(deal_card())

    p_val = hand_value(player)
    d_val = hand_value(dealer)

    embed.description = f"Your final hand: {format_hand(player)} (total {p_val})\nDealer's hand: {format_hand(dealer)} (total {d_val})"
    await game_msg.edit(embed=embed)

    if d_val > 21 or p_val > d_val:
        win_amt = int(bet * 1.8)
        new_balance = user["balance"] + win_amt
        update_user(ctx.author.id, balance=new_balance)
        add_exp_and_level(ctx.author.id, 50)
        await ctx.send(f"🎉 You win {win_amt} coins!")
    elif p_val == d_val:
        await ctx.send("🤝 Push! Bet returned.")
    else:
        new_balance = user["balance"] - bet
        update_user(ctx.author.id, balance=new_balance)
        add_exp_and_level(ctx.author.id, 10)
        await ctx.send("💀 You lose.")


# --- Cups game with reactions ---
@bot.command(name="cups")
async def cups(ctx, bet: int):
    if bet <= 0 or bet > MAX_BET:
        await ctx.send(f"❌ Bet must be 1 to {MAX_BET} coins.")
        return
    user = get_user(ctx.author.id)
    if user["balance"] < bet:
        await ctx.send("❌ Not enough coins.")
        return

    cups_emojis = ["1️⃣", "2️⃣", "3️⃣"]
    prize_cup = random.randint(0, 2)
    display = "🥤 🥤 🥤"
    msg = await ctx.send(f"Guess the cup with the prize! React with 1️⃣, 2️⃣, or 3️⃣:\n{display}")

    for emoji in cups_emojis:
        await msg.add_reaction(emoji)

    def check(reaction, user_check):
        return user_check == ctx.author and reaction.message.id == msg.id and str(reaction.emoji) in cups_emojis

    try:
        reaction, user_check = await bot.wait_for("reaction_add", timeout=30.0, check=check)
    except asyncio.TimeoutError:
        await ctx.send("⏰ Timeout! Game cancelled.")
        return

    guess = cups_emojis.index(str(reaction.emoji))

    # shuffle cups - simulate with random re-order (not shown to user)
    cups_positions = [0, 1, 2]
    random.shuffle(cups_positions)
    real_pos = cups_positions.index(prize_cup)

    if guess == real_pos:
        win_amt = int(bet * 2.5)
        new_balance = user["balance"] + win_amt
        update_user(ctx.author.id, balance=new_balance)
        add_exp_and_level(ctx.author.id, 50)
        await ctx.send(f"🎉 Correct! The prize was under cup {real_pos+1}. You won {win_amt} coins!")
    else:
        new_balance = user["balance"] - bet
        update_user(ctx.author.id, balance=new_balance)
        add_exp_and_level(ctx.author.id, 10)
        await ctx.send(f"💀 Wrong! The prize was under cup {real_pos+1}. You lost {bet} coins.")


import os
bot.run(os.environ["TOKEN"])
