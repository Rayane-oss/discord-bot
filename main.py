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

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    update_crypto_prices.start()
    investment_price_fluctuation.start()
    try:
        await tree.sync()
        print("✅ Slash commands globally synced.")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

### ECONOMY COMMANDS ###

@tree.command(name="balance", description="Check your balance")
async def balance(interaction: discord.Interaction, member: discord.Member = None):
    data = load_data()
    uid = str(member.id if member else interaction.user.id)
    ensure_user(data, uid)
    bal = data[uid]["bal"]
    await interaction.response.send_message(f"{(member or interaction.user).display_name}'s balance: {bal} coins")

@tree.command(name="daily", description="Claim your daily reward")
async def daily(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    now = datetime.utcnow()
    last_daily = user["daily"]
    if last_daily:
        last_daily_dt = datetime.fromisoformat(last_daily)
        if (now - last_daily_dt).total_seconds() < 24*3600:
            remaining = 24*3600 - (now - last_daily_dt).total_seconds()
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            await interaction.response.send_message(f"⏳ You already claimed daily. Try again in {hours}h {minutes}m.")
            return
    reward = 1000
    user["bal"] += reward
    user["daily"] = now.isoformat()
    save_data(data)
    earned = update_achievements(data, uid)
    save_data(data)
    msg = f"🎉 You claimed your daily reward of {reward} coins."
    if earned:
        msg += "\nAchievements earned:\n" + "\n".join(f"- {desc} (+{rew} coins)" for _, desc, rew in earned)
    await interaction.response.send_message(msg)

@tree.command(name="work", description="Work to earn money")
async def work(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    now = datetime.utcnow()
    cd_sec = get_work_cooldown(user)
    last_work = user.get("work")
    if last_work:
        last_work_dt = datetime.fromisoformat(last_work)
        if (now - last_work_dt).total_seconds() < cd_sec:
            remaining = cd_sec - (now - last_work_dt).total_seconds()
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            await interaction.response.send_message(f"⏳ You are tired. Work again in {minutes}m {seconds}s.")
            return
    base_pay = 500
    multiplier = 1.0
    if user["job"] and user["job"] in JOBS:
        multiplier = JOBS[user["job"]]["base_pay"] + (user["job_lvl"] - 1) * 0.05
    earned = int(base_pay * multiplier)
    user["bal"] += earned
    user["work"] = now.isoformat()
    leveled = add_exp(user, 100)
    if user["job"]:
        job_leveled = add_job_exp(user, 50)
    else:
        job_leveled = False
    save_data(data)
    msg = f"💼 You worked and earned {earned} coins."
    if leveled:
        msg += f"\n🎉 You leveled up! Your level is now {user['lvl']}."
    if job_leveled:
        msg += f"\n🚀 Your job level increased to {user['job_lvl']}."
    earned_ach = update_achievements(data, uid)
    if earned_ach:
        save_data(data)
        msg += "\nAchievements earned:\n" + "\n".join(f"- {desc} (+{rew} coins)" for _, desc, rew in earned_ach)
    await interaction.response.send_message(msg)

@tree.command(name="rob", description="Rob another user")
@app_commands.describe(member="The member to rob")
async def rob(interaction: discord.Interaction, member: discord.Member):
    if member.id == interaction.user.id:
        await interaction.response.send_message("You can't rob yourself!")
        return
    data = load_data()
    uid = str(interaction.user.id)
    target_uid = str(member.id)
    ensure_user(data, uid)
    ensure_user(data, target_uid)
    user = data[uid]
    target = data[target_uid]

    now = datetime.utcnow()
    last_rob = user["cooldowns"].get("rob")
    if last_rob:
        last_rob_dt = datetime.fromisoformat(last_rob)
        if (now - last_rob_dt).total_seconds() < 3600:
            remaining = 3600 - (now - last_rob_dt).total_seconds()
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            await interaction.response.send_message(f"⏳ Rob cooldown: Try again in {minutes}m {seconds}s.")
            return

    if target["bal"] < 500:
        await interaction.response.send_message("Target doesn't have enough money to rob.")
        return

    success_chance = 0.5
    if random.random() < success_chance:
        amount = random.randint(100, min(1000, target["bal"]))
        user["bal"] += amount
        target["bal"] -= amount
        result = f"💰 You robbed {member.display_name} for {amount} coins!"
    else:
        penalty = random.randint(100, 500)
        user["bal"] = max(0, user["bal"] - penalty)
        result = f"🚨 Rob failed! You lost {penalty} coins as penalty."

    user["cooldowns"]["rob"] = now.isoformat()
    save_data(data)
    await interaction.response.send_message(result)

@tree.command(name="buy", description="Buy crypto from the shop")
@app_commands.describe(crypto="Crypto to buy", amount="Amount to buy")
async def buy(interaction: discord.Interaction, crypto: str, amount: int):
    crypto = crypto.lower()
    if crypto not in CRYPTOCURRENCIES:
        await interaction.response.send_message("That cryptocurrency is not available.")
        return
    if amount <= 0:
        await interaction.response.send_message("Amount must be positive.")
        return
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    price = CRYPTOCURRENCIES[crypto]["price"]
    total_cost = price * amount
    if user["bal"] < total_cost:
        await interaction.response.send_message(f"Insufficient funds. You need {total_cost} coins but have {user['bal']}.")
        return
    user["bal"] -= total_cost
    user["inv"][crypto] = user["inv"].get(crypto, 0) + amount
    save_data(data)
    await interaction.response.send_message(f"🛒 Bought {amount} {crypto} for {total_cost} coins.")

@tree.command(name="sell", description="Sell crypto from your inventory")
@app_commands.describe(crypto="Crypto to sell", amount="Amount to sell")
async def sell(interaction: discord.Interaction, crypto: str, amount: int):
    crypto = crypto.lower()
    if crypto not in CRYPTOCURRENCIES:
        await interaction.response.send_message("That cryptocurrency is not recognized.")
        return
    if amount <= 0:
        await interaction.response.send_message("Amount must be positive.")
        return
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    if user["inv"].get(crypto, 0) < amount:
        await interaction.response.send_message(f"You don't have enough {crypto} to sell.")
        return
    price = CRYPTOCURRENCIES[crypto]["price"]
    total_value = price * amount
    user["inv"][crypto] -= amount
    if user["inv"][crypto] == 0:
        del user["inv"][crypto]
    user["bal"] += total_value
    save_data(data)
    await interaction.response.send_message(f"💰 Sold {amount} {crypto} for {total_value} coins.")

### GAMBLING ###

@tree.command(name="coinflip", description="Flip a coin and bet coins")
@app_commands.describe(bet="Bet amount", choice="Choose heads or tails")
async def coinflip(interaction: discord.Interaction, bet: int, choice: str):
    choice = choice.lower()
    if choice not in ("heads", "tails"):
        await interaction.response.send_message("Choice must be 'heads' or 'tails'.")
        return
    if bet <= 0 or bet > MAX_BET:
        await interaction.response.send_message(f"Bet must be between 1 and {MAX_BET}.")
        return
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    if user["bal"] < bet:
        await interaction.response.send_message("You don't have enough coins for that bet.")
        return
    result = random.choice(["heads", "tails"])
    if result == choice:
        user["bal"] += bet
        outcome = f"You won! The coin landed on {result}."
    else:
        user["bal"] -= bet
        outcome = f"You lost! The coin landed on {result}."
    save_data(data)
    await interaction.response.send_message(outcome)

### JOB SYSTEM ###

@tree.command(name="job", description="View or select your job")
@app_commands.describe(job="Job to select (hacker, trader, miner)")
async def job(interaction: discord.Interaction, job: str = None):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    if job is None:
        current = user["job"]
        if current:
            await interaction.response.send_message(f"Your current job is {current} {JOBS[current]['emoji']}, level {user['job_lvl']}.")
        else:
            await interaction.response.send_message("You don't have a job yet. Use this command with a job name to select one.")
        return
    job = job.lower()
    if job not in JOBS:
        await interaction.response.send_message("Invalid job. Available jobs: hacker, trader, miner.")
        return
    user["job"] = job
    user["job_lvl"] = 1
    user["job_exp"] = 0
    save_data(data)
    await interaction.response.send_message(f"🎉 You started working as a {job} {JOBS[job]['emoji']}!")

### LOOTBOX ###

@tree.command(name="lootbox", description="Open a lootbox for random rewards")
async def lootbox(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    # Simple cooldown 1 hour
    now = datetime.utcnow()
    last_lb = user["cooldowns"].get("lootbox")
    if last_lb:
        last_lb_dt = datetime.fromisoformat(last_lb)
        if (now - last_lb_dt).total_seconds() < 3600:
            remaining = 3600 - (now - last_lb_dt).total_seconds()
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            await interaction.response.send_message(f"⏳ Lootbox cooldown: Try again in {minutes}m {seconds}s.")
            return
    reward = random.choice(LOOTBOX_ITEMS)
    msg = ""
    if reward["type"] == "crypto":
        amount = random.randint(reward["min"], reward["max"])
        user["inv"][reward["item"]] = user["inv"].get(reward["item"], 0) + amount
        msg = f"🎁 You got {amount} {reward['item']} from the lootbox!"
    elif reward["type"] == "booster":
        add_booster(user, reward["item"], reward["duration"])
        msg = f"🎁 You got a work booster for {reward['duration']//60} minutes!"
    user["cooldowns"]["lootbox"] = now.isoformat()
    save_data(data)
    await interaction.response.send_message(msg)

### INVESTMENTS ###

@tree.command(name="invest", description="Invest in a cryptocurrency")
@app_commands.describe(crypto="Crypto to invest in", amount="Amount of coins to invest")
async def invest(interaction: discord.Interaction, crypto: str, amount: int):
    crypto = crypto.lower()
    if crypto not in CRYPTOCURRENCIES:
        await interaction.response.send_message("Invalid cryptocurrency.")
        return
    if amount <= 0:
        await interaction.response.send_message("Amount must be positive.")
        return
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    if user["bal"] < amount:
        await interaction.response.send_message("Insufficient funds.")
        return
    # Deduct from balance, add to investments
    user["bal"] -= amount
    user["investments"][crypto] = user["investments"].get(crypto, 0) + amount
    save_data(data)
    await interaction.response.send_message(f"📈 Invested {amount} coins into {crypto}.")

@tree.command(name="portfolio", description="View your crypto investments")
async def portfolio(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    inv = user.get("investments", {})
    if not inv:
        await interaction.response.send_message("You have no investments.")
        return
    lines = []
    total_value = 0
    for c, amt in inv.items():
        price = CRYPTOCURRENCIES.get(c, {}).get("price", 0)
        val = amt * price
        total_value += val
        lines.append(f"{c.capitalize()}: {amt} coins worth {val:.2f}")
    lines.append(f"Total portfolio value: {total_value:.2f} coins")
    await interaction.response.send_message("\n".join(lines))

### ADMIN COMMANDS ###

@tree.command(name="addmoney", description="Add money to a user (Admin only)")
@app_commands.describe(member="Member to add money to", amount="Amount to add")
async def addmoney(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You don't have permission to use this command.")
        return
    if amount <= 0:
        await interaction.response.send_message("Amount must be positive.")
        return
    data = load_data()
    uid = str(member.id)
    ensure_user(data, uid)
    data[uid]["bal"] += amount
    save_data(data)
    await interaction.response.send_message(f"Added {amount} coins to {member.display_name}.")

@tree.command(name="removemoney", description="Remove money from a user (Admin only)")
@app_commands.describe(member="Member to remove money from", amount="Amount to remove")
async def removemoney(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You don't have permission to use this command.")
        return
    if amount <= 0:
        await interaction.response.send_message("Amount must be positive.")
        return
    data = load_data()
    uid = str(member.id)
    ensure_user(data, uid)
    data[uid]["bal"] = max(0, data[uid]["bal"] - amount)
    save_data(data)
    await interaction.response.send_message(f"Removed {amount} coins from {member.display_name}.")

@tree.command(name="resetcooldowns", description="Reset cooldowns for a user (Admin only)")
@app_commands.describe(member="Member to reset cooldowns for")
async def resetcooldowns(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You don't have permission to use this command.")
        return
    data = load_data()
    uid = str(member.id)
    ensure_user(data, uid)
    data[uid]["cooldowns"] = {}
    save_data(data)
    await interaction.response.send_message(f"Cooldowns reset for {member.display_name}.")

@tree.command(name="resetuser", description="Reset user data (Admin only)")
@app_commands.describe(member="Member to reset")
async def resetuser(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You don't have permission to use this command.")
        return
    data = load_data()
    uid = str(member.id)
    if uid in data:
        del data[uid]
        save_data(data)
        await interaction.response.send_message(f"Data reset for {member.display_name}.")
    else:
        await interaction.response.send_message("User has no data.")

### SHOP COMMAND ###

@tree.command(name="shop", description="Show available cryptos and prices")
async def shop(interaction: discord.Interaction):
    lines = []
    for c, info in CRYPTOCURRENCIES.items():
        lines.append(f"{c.capitalize()} - Price: {info['price']} coins - {info['desc']}")
    await interaction.response.send_message("\n".join(lines))

### DAILY QUESTS (simple example) ###

@tree.command(name="dailyquests", description="View and claim daily quests")
async def dailyquests(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]

    # For demo, a fixed simple daily quest: work 1 time and claim reward
    if user["daily_quests"]["claimed"]:
        await interaction.response.send_message("You already claimed your daily quests reward today. Come back tomorrow!")
        return

    # Check quest completion: worked today
    worked = False
    last_work = user.get("work")
    if last_work:
        last_work_dt = datetime.fromisoformat(last_work)
        if (datetime.utcnow() - last_work_dt).total_seconds() < 24*3600:
            worked = True

    if worked:
        reward = 1000
        user["bal"] += reward
        user["daily_quests"]["claimed"] = True
        save_data(data)
        await interaction.response.send_message(f"🎉 You completed your daily quest and earned {reward} coins!")
    else:
        await interaction.response.send_message("Daily quest: Work at least once in the last 24 hours to claim reward.")

# Final token run

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    print("Error: DISCORD_BOT_TOKEN environment variable not set.")
else:
    bot.run(TOKEN)
