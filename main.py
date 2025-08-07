import discord
from discord import app_commands
from discord.ext import tasks
import os, random, json, asyncio
from datetime import datetime, timedelta

intents = discord.Intents.all()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

DATA_FILE = os.getenv("VOLUME_PATH", ".") + "/economy.json"

MAX_BET = 250_000
BASE_COOLDOWN = 40 * 60
INVESTMENT_UPDATE_INTERVAL = 120

CRYPTOCURRENCIES = {
    "bitcoin": {"price": 50000, "desc": "BTC - Most popular crypto"},
    "ethereum": {"price": 3200, "desc": "ETH - Smart contracts"},
    "dogecoin": {"price": 0.3, "desc": "DOGE - Meme coin"},
    "litecoin": {"price": 180, "desc": "LTC - Faster Bitcoin"},
    "ripple": {"price": 1, "desc": "XRP - Bank payments"},
}

JOBS = {
    "hacker": {"emoji": "🧑‍💻", "base_pay": 1.2},
    "trader": {"emoji": "📈", "base_pay": 1.1},
    "miner": {"emoji": "⛏️", "base_pay": 1.0},
}

ACHIEVEMENTS = {
    "first_daily": {"desc": "Claim your first daily reward", "condition": lambda d,u: d[u].get("daily") is not None, "reward": 500},
    "first_work": {"desc": "Work for the first time", "condition": lambda d,u: d[u].get("work") is not None, "reward": 500},
    "own_bitcoin": {"desc": "Own at least 1 bitcoin", "condition": lambda d,u: d[u]["inv"].get("bitcoin", 0) >= 1, "reward": 1000},
    "level_5": {"desc": "Reach level 5", "condition": lambda d,u: d[u]["lvl"] >= 5, "reward": 1500},
}

LOOTBOX_ITEMS = [
    {"type": "crypto", "item": "bitcoin", "min": 1, "max": 1},
    {"type": "crypto", "item": "ethereum", "min": 1, "max": 3},
    {"type": "crypto", "item": "dogecoin", "min": 50, "max": 200},
    {"type": "booster", "item": "work_boost", "duration": 3600},
]

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
            "boosters": {},
            "cooldowns": {},
            "daily_quests": {"claimed": False, "quests": []},
            "investments": {},
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
        base = int(base * 0.5)
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

@tasks.loop(hours=1)
async def update_crypto_prices():
    for crypto in CRYPTOCURRENCIES:
        base_price = CRYPTOCURRENCIES[crypto]["price"]
        change_percent = random.uniform(-0.05, 0.05)
        new_price = base_price * (1 + change_percent)
        CRYPTOCURRENCIES[crypto]["price"] = round(max(new_price, 0.01), 2)

@tasks.loop(seconds=INVESTMENT_UPDATE_INTERVAL)
async def investment_price_fluctuation():
    for crypto in CRYPTOCURRENCIES:
        change_percent = random.uniform(-0.03, 0.03)
        new_price = CRYPTOCURRENCIES[crypto]["price"] * (1 + change_percent)
        CRYPTOCURRENCIES[crypto]["price"] = round(max(new_price, 0.01), 2)

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
    try:
        await tree.sync()
        print("✅ Slash commands globally synced.")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

# --- Economy commands ---

@tree.command(name="balance", description="Check your balance")
async def balance(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    await interaction.response.send_message(f"💰 Wallet: {user['bal']}\nLevel: {user['lvl']} (EXP: {user['exp']})")
    save_data(data)

@tree.command(name="work", description="Work and earn coins")
async def work(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    now = datetime.utcnow()
    cooldown = get_work_cooldown(user)
    last_work = user.get("work")
    left = cooldown_left(last_work, cooldown)
    if left > 0:
        await interaction.response.send_message(f"⏳ You need to wait {int(left)} seconds before working again.")
        return
    earnings = random.randint(100, 500)
    user["bal"] += earnings
    user["work"] = now.isoformat()
    add_exp(user, 50)
    save_data(data)
    await interaction.response.send_message(f"🛠️ You worked and earned {earnings} coins!")

@tree.command(name="daily", description="Claim your daily reward")
async def daily(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    now = datetime.utcnow()
    last_daily = user.get("daily")
    if last_daily:
        diff = (now - datetime.fromisoformat(last_daily)).total_seconds()
        if diff < 24 * 3600:
            left = int(24 * 3600 - diff)
            await interaction.response.send_message(f"🕒 You can claim your daily reward in {left // 3600}h {(left // 60) % 60}m.")
            return
    reward = random.randint(1000, 2000)
    user["bal"] += reward
    user["daily"] = now.isoformat()
    add_exp(user, 100)
    save_data(data)
    await interaction.response.send_message(f"🎁 You claimed your daily reward of {reward} coins!")

@tree.command(name="deposit", description="Deposit coins")
@app_commands.describe(amount="Amount to deposit")
async def deposit(interaction: discord.Interaction, amount: int):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    if amount <= 0 or amount > user["bal"]:
        await interaction.response.send_message("❌ Invalid amount.")
        return
    user["bal"] -= amount
    user.setdefault("bank", 0)
    user["bank"] += amount
    save_data(data)
    await interaction.response.send_message(f"🏦 Deposited {amount} coins to your bank.")

@tree.command(name="withdraw", description="Withdraw coins")
@app_commands.describe(amount="Amount to withdraw")
async def withdraw(interaction: discord.Interaction, amount: int):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    if amount <= 0 or user.get("bank", 0) < amount:
        await interaction.response.send_message("❌ Invalid amount.")
        return
    user["bank"] -= amount
    user["bal"] += amount
    save_data(data)
    await interaction.response.send_message(f"💸 Withdrew {amount} coins from your bank.")

# --- Investment commands ---

@tree.command(name="invest", description="Invest coins into crypto")
@app_commands.describe(crypto="Crypto name", amount="Amount of coins")
async def invest(interaction: discord.Interaction, crypto: str, amount: int):
    crypto = crypto.lower()
    if crypto not in CRYPTOCURRENCIES:
        await interaction.response.send_message("❌ Unknown cryptocurrency.")
        return
    if amount <= 0:
        await interaction.response.send_message("❌ Amount must be positive.")
        return
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    if user["bal"] < amount:
        await interaction.response.send_message("❌ Not enough coins.")
        return
    price = CRYPTOCURRENCIES[crypto]["price"]
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
    await interaction.response.send_message(f"✅ Invested {amount} coins in {crypto} at price {price:.2f} coins.")

@tree.command(name="portfolio", description="Show your crypto portfolio")
async def portfolio(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    inv = user.get("investments", {})
    if not inv:
        await interaction.response.send_message("📉 You have no investments.")
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
        msg += f"• {crypto.capitalize()}: {amount} coins bought at {buy_price:.2f} - Current: {curr_price:.2f} - Value: {curr_value:.2f} - Profit: {profit_str}\n"
    msg += f"\nTotal portfolio value: {total_value:.2f}\nTotal profit/loss: {total_profit:.2f}"
    await interaction.response.send_message(msg)

@tree.command(name="sellinv", description="Sell your crypto investment")
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
        await interaction.response.send_message("❌ Not enough investment to sell.")
        return
    curr_price = CRYPTOCURRENCIES.get(crypto, {}).get("price", 0)
    if curr_price == 0:
        await interaction.response.send_message("❌ Crypto price unavailable.")
        return
    revenue = amount * curr_price
    inv[crypto]["amount"] -= amount
    if inv[crypto]["amount"] == 0:
        del inv[crypto]
    user["bal"] += int(revenue)
    save_data(data)
    await interaction.response.send_message(f"✅ Sold {amount} {crypto} for {int(revenue)} coins.")

# --- Daily Quests ---

@tree.command(name="dailyquests", description="View daily quests")
async def dailyquests(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    dq = user["daily_quests"]
    if not dq["quests"] or dq["claimed"]:
        quests = [
            {"task": "work", "desc": "Work once", "completed": False, "reward": 1000},
            {"task": "lootbox", "desc": "Open 1 lootbox", "completed": False, "reward": 1500},
            {"task": "slots", "desc": "Play slots once", "completed": False, "reward": 1200},
        ]
        dq["quests"] = quests
        dq["claimed"] = False
        save_data(data)
    msg = "**🎯 Daily Quests:**\n"
    for q in dq["quests"]:
        status = "✅ Completed" if q["completed"] else "❌ Not completed"
        msg += f"• {q['desc']} — {status} — Reward: {q['reward']} coins\n"
    if dq["claimed"]:
        msg += "\n✅ You already claimed today's quests reward."
    else:
        msg += "\nUse `/claimquests` to claim your reward if all quests completed."
    await interaction.response.send_message(msg)

@tree.command(name="claimquests", description="Claim daily quests reward")
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
    if not all(q["completed"] for q in dq["quests"]):
        await interaction.response.send_message("❌ You haven't completed all quests yet.")
        return
    total_reward = sum(q["reward"] for q in dq["quests"])
    user["bal"] += total_reward
    dq["claimed"] = True
    save_data(data)
    await interaction.response.send_message(f"✅ You claimed **{total_reward} coins** from daily quests!")

# --- Admin command example ---

@tree.command(name="resetcooldowns", description="Reset all cooldowns for all users (Admin only)")
async def resetcooldowns(interaction: discord.Interaction):
    try:
        owner_id = bot.owner_id or (await bot.application_info()).owner.id
    except:
        owner_id = None
    if interaction.user.id != owner_id:
        await interaction.response.send_message("❌ You are not authorized to use this command.")
        return
    data = load_data()
    for uid in data:
        data[uid]["cooldowns"] = {}
    save_data(data)
    await interaction.response.send_message("✅ All cooldowns have been reset.")

# You can continue to add your other commands here, fully implemented in the same style.

# --- Run bot ---
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    print("Error: DISCORD_BOT_TOKEN environment variable not set.")
else:
    bot.run(TOKEN)
