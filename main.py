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
            "daily_quests": {
                "claimed": False,
                "quests": [
                    # Example quests, you can randomize quests on daily reset if you want
                    {"type": "work", "amount": 5},
                    {"type": "rob", "amount": 3},
                    {"type": "buy", "amount": 10},
                    {"type": "coinflip", "amount": 10},
                ],
                "progress": {}
            },
            "stats": {
                "work": 0,
                "rob": 0,
                "buy": 0,
                "coinflip": 0,
            },
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

def update_daily_quest_progress(user, action_type, amount=1):
    if "daily_quests" not in user:
        return
    quests = user["daily_quests"].get("quests", [])
    progress = user["daily_quests"].setdefault("progress", {})
    for i, quest in enumerate(quests, 1):
        if quest["type"] == action_type:
            current = progress.get(str(i), 0)
            progress[str(i)] = min(quest["amount"], current + amount)

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

# --------------- Slash commands -------------------

@tree.command(name="bal", description="Check your balance and level")
async def bal(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    msg = (
        f"💰 **Balance:** `{user['bal']:,}`\n"
        f"🎖️ **Level:** `{user['lvl']}` (EXP: `{user['exp']}/1000`)\n"
        f"👔 **Job:** `{user['job'] or 'None'}` (Lv. `{user.get('job_lvl',1)}`)"
    )
    await interaction.response.send_message(msg)

@tree.command(name="daily", description="Claim your daily reward (cooldown)")
async def daily(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    left = cooldown_left(user["daily"], BASE_COOLDOWN)
    if left > 0:
        await interaction.response.send_message(f"🕒 You must wait **{int(left // 60)}m {int(left % 60)}s** for your daily reward.")
        return
    reward = random.randint(1500, 3500)
    user["bal"] += reward
    user["daily"] = datetime.utcnow().isoformat()
    add_exp(user, 60)
    update_daily_quest_progress(user, "daily", 1)
    earned_achievements = update_achievements(data, uid)
    save_data(data)
    msg = (
        f"✅ You collected your daily reward:\n"
        f"➤ +{reward:,} coins\n"
        f"➤ +60 EXP"
    )
    for key, desc, rew in earned_achievements:
        msg += f"\n\n🏆 **Achievement unlocked:**\n• {desc} (+{rew:,} coins)"
    await interaction.response.send_message(msg)

@tree.command(name="work", description="Work for coins (cooldown, can be boosted)")
async def work(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    cooldown = get_work_cooldown(user)
    left = cooldown_left(user["work"], cooldown)
    if left > 0:
        await interaction.response.send_message(f"🕒 You need to wait **{int(left // 60)}m {int(left % 60)}s** before working again.")
        return
    base_pay = random.randint(1100, 2500)
    job_mult = 1.0
    if user["job"] in JOBS:
        job_mult = JOBS[user["job"]]["base_pay"] + (user["job_lvl"] - 1) * 0.1
    pay = int(base_pay * job_mult)
    user["bal"] += pay
    user["work"] = datetime.utcnow().isoformat()
    add_exp(user, 45)
    add_job_exp(user, 30)
    update_daily_quest_progress(user, "work", 1)
    earned_achievements = update_achievements(data, uid)
    save_data(data)
    msg = (
        f"💼 You worked as **{user['job'] or 'a freelancer'}** and earned **{pay:,} coins**\n"
        f"➤ +45 EXP"
    )
    for key, desc, rew in earned_achievements:
        msg += f"\n\n🏆 **Achievement unlocked:**\n• {desc} (+{rew:,} coins)"
    await interaction.response.send_message(msg)

@tree.command(name="inv", description="Show your inventory")
async def inv(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    inv = data[uid]["inv"]
    if not inv or all(v <= 0 for v in inv.values()):
        await interaction.response.send_message("🎒 Your inventory is empty.")
        return
    msg = "**🎒 Inventory:**\n"
    for item, amount in inv.items():
        if amount > 0:
            msg += f"• {item.capitalize()} x{amount}\n"
    await interaction.response.send_message(msg)

@tree.command(name="job", description="Choose or view your job")
@app_commands.describe(job_name="Choose a job: hacker, trader, miner")
async def job(interaction: discord.Interaction, job_name: str = None):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    if job_name is None:
        if user["job"]:
            await interaction.response.send_message(
                f"👔 Your current job:\n"
                f"• {user['job'].capitalize()} {JOBS[user['job']]['emoji']} Lv. {user['job_lvl']}"
            )
        else:
            await interaction.response.send_message(f"ℹ️ You don't have a job.\nChoose one with `/job job_name:hacker|trader|miner`")
        return
    job_name = job_name.lower()
    if job_name not in JOBS:
        await interaction.response.send_message("❌ Invalid job. Choose from: hacker, trader, miner.")
        return
    user["job"] = job_name
    user["job_lvl"] = 1
    user["job_exp"] = 0
    save_data(data)
    await interaction.response.send_message(f"✅ You started working as a **{job_name.capitalize()}** {JOBS[job_name]['emoji']}")

@tree.command(name="shop", description="View crypto shop")
async def shop(interaction: discord.Interaction):
    msg = "**🪙 Crypto Shop (prices update hourly):**\n"
    for crypto, info in CRYPTOCURRENCIES.items():
        price_str = f"{info['price']:,}" if info['price'] >= 1 else f"{info['price']:.4f}"
        msg += f"• `{crypto}`: {price_str} coins — {info['desc']}\n"
    msg += "\nUse `/buy item amount` to purchase multiple."
    await interaction.response.send_message(msg)

@tree.command(name="buy", description="Buy crypto from the shop")
@app_commands.describe(item="Crypto to buy", amount="Amount to buy")
async def buy(interaction: discord.Interaction, item: str, amount: int = 1):
    if amount <= 0:
        await interaction.response.send_message("❌ Amount must be a positive number.")
        return
    data = load_data()
    uid = str(interaction.user.id)
    item = item.lower()
    ensure_user(data, uid)
    if item not in CRYPTOCURRENCIES:
        await interaction.response.send_message("❌ That crypto is not available in the shop.")
        return
    cost = int(CRYPTOCURRENCIES[item]["price"] * amount)
    if data[uid]["bal"] < cost:
        await interaction.response.send_message(f"❌ You don't have enough coins to buy {amount} {item}(s) ({cost:,} coins).")
        return
    data[uid]["bal"] -= cost
    inv = data[uid]["inv"]
    inv[item] = inv.get(item, 0) + amount
    add_exp(data[uid], 20 * amount)
    update_daily_quest_progress(data[uid], "buy", amount)
    save_data(data)
    await interaction.response.send_message(f"✅ You bought **{amount} {item}(s)** for **{cost:,} coins**.")

@tree.command(name="sell", description="Sell crypto from your inventory")
@app_commands.describe(item="Crypto to sell", amount="Amount to sell")
async def sell(interaction: discord.Interaction, item: str, amount: int = 1):
    if amount <= 0:
        await interaction.response.send_message("❌ Amount must be a positive number.")
        return
    data = load_data()
    uid = str(interaction.user.id)
    item = item.lower()
    ensure_user(data, uid)
    inv = data[uid]["inv"]
    if item not in inv or inv[item] < amount:
        await interaction.response.send_message("❌ You don't own that many items to sell.")
        return
    price = int(CRYPTOCURRENCIES.get(item, {"price":0})["price"] * 0.6 * amount)
    inv[item] -= amount
    data[uid]["bal"] += price
    save_data(data)
    await interaction.response.send_message(f"✅ You sold **{amount} {item}(s)** for **{price:,} coins**.")

@tree.command(name="lootbox", description="Buy and open a lootbox for random rewards (cost 5000 coins)")
async def lootbox(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    cost = 5000
    if user["bal"] < cost:
        await interaction.response.send_message(f"❌ You need **{cost:,} coins** to buy a lootbox.")
        return
    user["bal"] -= cost

    loot = random.choice(LOOTBOX_ITEMS)
    if loot["type"] == "crypto":
        amount = random.randint(loot["min"], loot["max"])
        user["inv"][loot["item"]] = user["inv"].get(loot["item"], 0) + amount
        msg = f"🎁 You opened a lootbox and got **{amount} {loot['item']}**!"
    else:
        add_booster(user, loot["item"], loot["duration"])
        msg = f"🎉 You opened a lootbox and got a **{loot['item']}** booster for {loot['duration']//60} minutes!"

    save_data(data)
    await interaction.response.send_message(msg)

@tree.command(name="rob", description="Rob another user (cooldown 20 minutes)")
@app_commands.describe(target="User to rob")
async def rob(interaction: discord.Interaction, target: discord.User):
    data = load_data()
    uid = str(interaction.user.id)
    target_uid = str(target.id)
    ensure_user(data, uid)
    ensure_user(data, target_uid)
    user = data[uid]
    target_user = data[target_uid]

    cooldown = 20 * 60
    left = cooldown_left(user["cooldowns"].get("rob"), cooldown)
    if left > 0:
        await interaction.response.send_message(f"🕒 You must wait **{int(left//60)}m {int(left%60)}s** before robbing again.")
        return
    if target.id == interaction.user.id:
        await interaction.response.send_message("❌ You cannot rob yourself.")
        return
    if target_user["bal"] < 500:
        await interaction.response.send_message("❌ Target has too little money to rob.")
        return
    success = random.random() < 0.5
    amount = random.randint(300, min(1500, target_user["bal"]))
    if success:
        user["bal"] += amount
        target_user["bal"] -= amount
        user["cooldowns"]["rob"] = datetime.utcnow().isoformat()
        update_daily_quest_progress(user, "rob", 1)
        save_data(data)
        await interaction.response.send_message(f"💰 Success! You robbed **{amount:,} coins** from {target.name}.")
    else:
        penalty = random.randint(150, 400)
        user["bal"] = max(0, user["bal"] - penalty)
        user["cooldowns"]["rob"] = datetime.utcnow().isoformat()
        save_data(data)
        await interaction.response.send_message(f"❌ You got caught and paid a penalty of **{penalty} coins**.")

@tree.command(name="coinflip", description="Coinflip gamble game")
@app_commands.describe(bet="Amount to bet", side="Choose heads or tails")
async def coinflip(interaction: discord.Interaction, bet: int, side: str):
    side = side.lower()
    if side not in ("heads", "tails"):
        await interaction.response.send_message("❌ Side must be 'heads' or 'tails'.")
        return
    if bet <= 0 or bet > MAX_BET:
        await interaction.response.send_message(f"❌ Bet must be between 1 and {MAX_BET}.")
        return

    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]

    if user["bal"] < bet:
        await interaction.response.send_message("❌ You don't have enough balance for that bet.")
        return

    flip = random.choice(["heads", "tails"])
    if flip == side:
        win_amount = bet
        user["bal"] += win_amount
        result_msg = f"🎉 You won! The coin landed on **{flip}**. You gained **{win_amount} coins**."
    else:
        user["bal"] -= bet
        result_msg = f"😞 You lost! The coin landed on **{flip}**. You lost **{bet} coins**."

    update_daily_quest_progress(user, "coinflip", 1)
    save_data(data)
    await interaction.response.send_message(result_msg)

@tree.command(name="quests", description="View your daily quests progress")
async def quests(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    if not user.get("daily_quests") or not user["daily_quests"].get("quests"):
        await interaction.response.send_message("❌ You have no active daily quests.")
        return
    msg = "**📋 Daily Quests:**\n"
    quests = user["daily_quests"]["quests"]
    progress = user["daily_quests"].get("progress", {})
    for i, q in enumerate(quests, 1):
        p = progress.get(str(i), 0)
        msg += f"• {q['type'].capitalize()}: {p}/{q['amount']}\n"
    await interaction.response.send_message(msg)

@tree.command(name="achievements", description="View your achievements")
async def achievements(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    if not user["achievements"]:
        await interaction.response.send_message("❌ You have no achievements yet.")
        return
    msg = "**🏆 Achievements:**\n"
    for ach in user["achievements"]:
        msg += f"• {ACHIEVEMENTS[ach]['desc']}\n"
    await interaction.response.send_message(msg)

@tree.command(name="help", description="Get help with commands")
async def help(interaction: discord.Interaction):
    msg = (
        "**🤖 Bot Commands:**\n"
        "/bal - Show your balance and level\n"
        "/daily - Claim your daily reward\n"
        "/work - Work for coins\n"
        "/job - View or choose your job\n"
        "/shop - View crypto shop\n"
        "/buy item amount - Buy crypto\n"
        "/sell item amount - Sell crypto\n"
        "/inv - View your inventory\n"
        "/lootbox - Buy and open a lootbox (5000 coins)\n"
        "/rob @user - Rob another user (20m cooldown)\n"
        "/coinflip bet side - Gamble coins on coinflip\n"
        "/quests - Show daily quests progress\n"
        "/achievements - Show your achievements\n"
    )
    await interaction.response.send_message(msg)

# ------------- End slash commands --------------

# Run the bot with environment token check (your preferred style)
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    print("Error: DISCORD_BOT_TOKEN environment variable not set.")
else:
    bot.run(TOKEN)
