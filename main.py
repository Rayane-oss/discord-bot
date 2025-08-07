import discord
from discord import app_commands
from discord.ext import tasks
import os, random, json, asyncio
from datetime import datetime, timedelta

intents = discord.Intents.all()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# Data file path for persistent storage (Railway volume or current dir fallback)
DATA_FILE = os.getenv("VOLUME_PATH", ".") + "/economy.json"

# Constants
MAX_BET = 250_000
BASE_COOLDOWN = 40 * 60  # 40 minutes cooldown (can be reduced by boosters)
INVESTMENT_UPDATE_INTERVAL = 120  # seconds

# Initial crypto shop list
CRYPTOCURRENCIES = {
    "bitcoin": {"price": 50000, "desc": "BTC - Most popular crypto"},
    "ethereum": {"price": 3200, "desc": "ETH - Smart contracts"},
    "dogecoin": {"price": 0.3, "desc": "DOGE - Meme coin"},
    "litecoin": {"price": 180, "desc": "LTC - Faster Bitcoin"},
    "ripple": {"price": 1, "desc": "XRP - Bank payments"},
}

# Job info (emoji, base pay multiplier)
JOBS = {
    "hacker": {"emoji": "🧑‍💻", "base_pay": 1.2},
    "trader": {"emoji": "📈", "base_pay": 1.1},
    "miner": {"emoji": "⛏️", "base_pay": 1.0},
}

# Achievements (easy to earn)
ACHIEVEMENTS = {
    "first_daily": {"desc": "Claim your first daily reward", "condition": lambda d,u: d[u].get("daily") is not None, "reward": 500},
    "first_work": {"desc": "Work for the first time", "condition": lambda d,u: d[u].get("work") is not None, "reward": 500},
    "own_bitcoin": {"desc": "Own at least 1 bitcoin", "condition": lambda d,u: d[u]["inv"].get("bitcoin", 0) >= 1, "reward": 1000},
    "level_5": {"desc": "Reach level 5", "condition": lambda d,u: d[u]["lvl"] >= 5, "reward": 1500},
}

# Lootbox items and boosters
LOOTBOX_ITEMS = [
    {"type": "crypto", "item": "bitcoin", "min": 1, "max": 1},
    {"type": "crypto", "item": "ethereum", "min": 1, "max": 3},
    {"type": "crypto", "item": "dogecoin", "min": 50, "max": 200},
    {"type": "booster", "item": "work_boost", "duration": 3600},  # 1 hour booster
]

# Helper functions for data handling

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
            "inv": {},
            "achievements": [],
            "job": None,
            "job_lvl": 1,
            "job_exp": 0,
            "boosters": {},  # e.g., {"work_boost": expiry_timestamp_iso}
            "cooldowns": {},  # generic cooldown dict (e.g. robbery)
            "daily_quests": {"claimed": False, "quests": []},
            "investments": {},  # {crypto: {"amount": int, "buy_price": float}}
        }

def cooldown_left(last_time, cooldown_sec):
    if not last_time:
        return 0
    delta = (datetime.utcnow() - datetime.fromisoformat(last_time)).total_seconds()
    return max(0, cooldown_sec - delta)

def add_exp(user, amount):
    user["exp"] += amount
    leveled_up = False
    while user["exp"] >= 1000:
        user["exp"] -= 1000
        user["lvl"] += 1
        leveled_up = True
    return leveled_up

def add_job_exp(user, amount):
    user["job_exp"] += amount
    leveled_up = False
    while user["job_exp"] >= 500:
        user["job_exp"] -= 500
        user["job_lvl"] += 1
        leveled_up = True
    return leveled_up

def has_booster(user, booster_name):
    if booster_name not in user.get("boosters", {}):
        return False
    expiry = datetime.fromisoformat(user["boosters"][booster_name])
    return expiry > datetime.utcnow()

def add_booster(user, booster_name, duration_sec):
    expiry = datetime.utcnow() + timedelta(seconds=duration_sec)
    user.setdefault("boosters", {})[booster_name] = expiry.isoformat()

def get_work_cooldown(user):
    base = BASE_COOLDOWN
    if has_booster(user, "work_boost"):
        base = int(base * 0.5)  # 50% cooldown reduction
    return base

def update_achievements(data, uid):
    user = data[uid]
    earned = []
    for key, ach in ACHIEVEMENTS.items():
        if key not in user["achievements"] and ach["condition"](data, uid):
            user["achievements"].append(key)
            user["bal"] += ach["reward"]
            earned.append((key, ach["desc"], ach["reward"]))
    return earned

# --- Crypto price updater (every hour) ---
@tasks.loop(hours=1)
async def update_crypto_prices():
    for crypto in CRYPTOCURRENCIES:
        base_price = CRYPTOCURRENCIES[crypto]["price"]
        change_percent = random.uniform(-0.05, 0.05)
        new_price = base_price * (1 + change_percent)
        CRYPTOCURRENCIES[crypto]["price"] = round(max(new_price, 0.01), 2)

# --- Coin investment price fluctuations (every 2 minutes) ---
@tasks.loop(seconds=INVESTMENT_UPDATE_INTERVAL)
async def investment_price_fluctuation():
    for crypto in CRYPTOCURRENCIES:
        change_percent = random.uniform(-0.03, 0.03)
        new_price = CRYPTOCURRENCIES[crypto]["price"] * (1 + change_percent)
        CRYPTOCURRENCIES[crypto]["price"] = round(max(new_price, 0.01), 2)

# --- Smart news feature (random events) ---
@tasks.loop(minutes=10)
async def crypto_news_event():
    if random.random() < 0.3:
        crypto = random.choice(list(CRYPTOCURRENCIES.keys()))
        event_type = random.choice(["boost", "drop"])
        multiplier = random.uniform(1.1, 1.3) if event_type == "boost" else random.uniform(0.7, 0.9)
        old_price = CRYPTOCURRENCIES[crypto]["price"]
        new_price = max(0.01, old_price * multiplier)
        CRYPTOCURRENCIES[crypto]["price"] = round(new_price, 2)
        for guild in bot.guilds:
            channel = discord.utils.get(guild.text_channels, name="general")
            if channel:
                await channel.send(f"📢 Crypto news: {crypto.capitalize()} price just {'rose' if event_type == 'boost' else 'fell'} sharply! New price: {CRYPTOCURRENCIES[crypto]['price']} coins")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    update_crypto_prices.start()
    investment_price_fluctuation.start()
    crypto_news_event.start()
    await tree.sync(guild=None)  # Global sync to appear in all servers and DMs
    print("Slash commands globally synced.")

# --------------- Your existing slash commands here ... (unchanged) ---------------

# -- ADD NEW COMMANDS BELOW ---

# Daily quests system
@tree.command(name="dailyquests", description="View and claim daily quests")
async def dailyquests(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    dq = user["daily_quests"]

    # If quests not set or reset, generate 3 simple quests
    if not dq["quests"] or dq["claimed"]:
        # Example quests: Work, Lootbox, Slots
        quests = [
            {"task": "work", "desc": "Work once", "completed": False, "reward": 1000},
            {"task": "lootbox", "desc": "Open 1 lootbox", "completed": False, "reward": 1500},
            {"task": "slots", "desc": "Play slots once", "completed": False, "reward": 1200},
        ]
        dq["quests"] = quests
        dq["claimed"] = False
        save_data(data)
    
    # Check completion status (for demo, we just mark completed manually here, you may link to events)
    msg = "**🎯 Daily Quests:**\n"
    for q in dq["quests"]:
        status = "✅ Completed" if q["completed"] else "❌ Not completed"
        msg += f"• {q['desc']} — {status} — Reward: {q['reward']} coins\n"

    if dq["claimed"]:
        msg += "\n✅ You already claimed today's quests reward."
    else:
        msg += "\nUse `/claimquests` to claim your reward if all quests completed."

    await interaction.response.send_message(msg)

# Claim daily quests reward
@tree.command(name="claimquests", description="Claim your daily quests reward if completed")
async def claimquests(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    dq = user["daily_quests"]

    if dq["claimed"]:
        await interaction.response.send_message("❌ You already claimed your daily quests reward today.")
        return

    if not dq["quests"]:
        await interaction.response.send_message("❌ No daily quests found. Use `/dailyquests` to generate them.")
        return

    # Check if all completed
    if not all(q["completed"] for q in dq["quests"]):
        await interaction.response.send_message("❌ You haven't completed all quests yet.")
        return

    total_reward = sum(q["reward"] for q in dq["quests"])
    user["bal"] += total_reward
    dq["claimed"] = True
    save_data(data)
    await interaction.response.send_message(f"✅ You claimed **{total_reward} coins** from daily quests!")

# Invest command: invest coins into cryptos, store buy price
@tree.command(name="invest", description="Invest coins into a cryptocurrency")
@app_commands.describe(crypto="Crypto name", amount="Amount of coins to invest")
async def invest(interaction: discord.Interaction, crypto: str, amount: int):
    crypto = crypto.lower()
    if crypto not in CRYPTOCURRENCIES:
        await interaction.response.send_message("❌ That crypto is not available.")
        return
    if amount <= 0:
        await interaction.response.send_message("❌ Amount must be positive.")
        return

    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]

    if user["bal"] < amount:
        await interaction.response.send_message("❌ You don't have enough coins to invest.")
        return

    price = CRYPTOCURRENCIES[crypto]["price"]
    # Store investment amount and buy price weighted average if already invested
    inv = user.setdefault("investments", {})
    if crypto in inv:
        total_amount = inv[crypto]["amount"] + amount
        total_cost = inv[crypto]["amount"] * inv[crypto]["buy_price"] + amount * price
        avg_price = total_cost / total_amount
        inv[crypto]["amount"] = total_amount
        inv[crypto]["buy_price"] = avg_price
    else:
        inv[crypto] = {"amount": amount, "buy_price": price}

    user["bal"] -= amount
    save_data(data)
    await interaction.response.send_message(f"✅ You invested **{amount} coins** in {crypto} at price {price} coins.")

# Check investments and their current value and profit/loss
@tree.command(name="portfolio", description="Check your crypto investments portfolio")
async def portfolio(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]

    inv = user.get("investments", {})
    if not inv:
        await interaction.response.send_message("📉 You have no active investments.")
        return

    msg = "**📈 Your Investments Portfolio:**\n"
    total_profit = 0
    total_value = 0
    for crypto, info in inv.items():
        curr_price = CRYPTOCURRENCIES.get(crypto, {}).get("price", 0)
        amount = info["amount"]
        buy_price = info["buy_price"]
        curr_value = amount * curr_price
        profit = curr_value - (amount * buy_price)
        total_profit += profit
        total_value += curr_value
        profit_str = f"+{profit:.2f}" if profit >= 0 else f"{profit:.2f}"
        msg += f"• {crypto.capitalize()}: {amount} coins bought at {buy_price:.2f} - Current price: {curr_price:.2f} - Value: {curr_value:.2f} coins - Profit: {profit_str} coins\n"

    msg += f"\nTotal portfolio value: {total_value:.2f} coins\nTotal profit/loss: {total_profit:.2f} coins"
    await interaction.response.send_message(msg)

# Sell investments command: sell amount of crypto investment at current price
@tree.command(name="sellinv", description="Sell part of your crypto investments")
@app_commands.describe(crypto="Crypto name", amount="Amount to sell")
async def sellinv(interaction: discord.Interaction, crypto: str, amount: int):
    crypto = crypto.lower()
    if amount <= 0:
        await interaction.response.send_message("❌ Amount must be positive.")
        return

    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    inv = user.get("investments", {})

    if crypto not in inv or inv[crypto]["amount"] < amount:
        await interaction.response.send_message("❌ You don't have that much investment to sell.")
        return

    curr_price = CRYPTOCURRENCIES.get(crypto, {}).get("price", 0)
    if curr_price == 0:
        await interaction.response.send_message("❌ Cannot sell now, crypto price unknown.")
        return

    revenue = amount * curr_price
    inv[crypto]["amount"] -= amount
    if inv[crypto]["amount"] == 0:
        del inv[crypto]

    user["bal"] += int(revenue)
    save_data(data)
    await interaction.response.send_message(f"✅ You sold **{amount} {crypto}** investment for **{int(revenue)} coins**.")

# Reset cooldowns command (admin only)
@tree.command(name="resetcooldowns", description="Reset all cooldowns for all users (Admin only)")
async def resetcooldowns(interaction: discord.Interaction):
    owner_id = bot.owner_id or bot.application.owner.id
    if interaction.user.id != owner_id:
        await interaction.response.send_message("❌ You are not authorized to use this command.")
        return
    data = load_data()
    for uid in data:
        data[uid]["cooldowns"] = {}
    save_data(data)
    await interaction.response.send_message("✅ All cooldowns have been reset.")

# You can add other admin commands as needed...

# -------------- END OF ADDITIONS --------------

# Run the bot
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    print("Error: DISCORD_BOT_TOKEN environment variable not set.")
else:
    bot.run(TOKEN)
