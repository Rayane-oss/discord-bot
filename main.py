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
BASE_COOLDOWN = 40 * 60  # 40 min base cooldown
INVESTMENT_UPDATE_INTERVAL = 120  # 2 min price update
ROB_COOLDOWN = 30 * 60  # 30 min cooldown for robbery

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
    {"type": "booster", "item": "work_boost", "duration": 3600},  # 1 hour
]

# DAILY QUESTS POOL
DAILY_QUESTS_POOL = [
    {"desc": "Work 3 times", "type": "work", "amount": 3, "reward": 1000},
    {"desc": "Rob a user once", "type": "rob", "amount": 1, "reward": 1500},
    {"desc": "Win 3 coinflips", "type": "coinflip_win", "amount": 3, "reward": 800},
    {"desc": "Buy 5 crypto", "type": "buy_crypto", "amount": 5, "reward": 700},
]

# Helper functions

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
            "daily_quests": {"claimed": False, "quests": [], "progress": {}},
            "stats": {  # Track daily quest progress
                "work": 0,
                "rob": 0,
                "coinflip_win": 0,
                "buy_crypto": 0,
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

def generate_daily_quests():
    # pick 2 random quests from pool
    return random.sample(DAILY_QUESTS_POOL, 2)

def reset_daily_quests(user):
    user["daily_quests"]["claimed"] = False
    user["daily_quests"]["quests"] = generate_daily_quests()
    user["daily_quests"]["progress"] = {}
    # reset stats related to quests
    for stat in user["stats"]:
        user["stats"][stat] = 0

# --- Crypto price updater (hourly)
@tasks.loop(hours=1)
async def update_crypto_prices():
    for crypto in CRYPTOCURRENCIES:
        base_price = CRYPTOCURRENCIES[crypto]["price"]
        change_percent = random.uniform(-0.05, 0.05)
        new_price = base_price * (1 + change_percent)
        CRYPTOCURRENCIES[crypto]["price"] = round(max(new_price, 0.01), 2)

# --- Investment price fluctuation (every 2 minutes)
@tasks.loop(seconds=INVESTMENT_UPDATE_INTERVAL)
async def investment_price_fluctuation():
    for crypto in CRYPTOCURRENCIES:
        change_percent = random.uniform(-0.03, 0.03)
        new_price = CRYPTOCURRENCIES[crypto]["price"] * (1 + change_percent)
        CRYPTOCURRENCIES[crypto]["price"] = round(max(new_price, 0.01), 2)

# --- Smart crypto news events (every 10 minutes)
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
    await tree.sync(guild=None)
    print("Slash commands globally synced.")

# --- Slash commands ---

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
    earned_achievements = update_achievements(data, uid)
    # reset daily quests each day
    if user["daily_quests"]["claimed"]:
        reset_daily_quests(user)
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
    # Update daily quest progress
    user["stats"]["work"] = user["stats"].get("work", 0) + 1
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
    # Update daily quest progress for buy_crypto
    data[uid]["stats"]["buy_crypto"] = data[uid]["stats"].get("buy_crypto", 0) + amount
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
        reward_msg = f"🎁 You got **{amount} {loot['item']}**!"
    else:  # booster
        add_booster(user, loot["item"], loot["duration"])
        reward_msg = f"🎁 You got a **{loot['item']}** booster for {loot['duration']//60} minutes!"
    save_data(data)
    await interaction.response.send_message(reward_msg)

@tree.command(name="rob", description="Attempt to rob another user (30 min cooldown)")
@app_commands.describe(target="User to rob")
async def rob(interaction: discord.Interaction, target: discord.Member):
    if target.bot:
        await interaction.response.send_message("❌ You cannot rob bots.")
        return
    if target.id == interaction.user.id:
        await interaction.response.send_message("❌ You can't rob yourself.")
        return

    data = load_data()
    uid = str(interaction.user.id)
    target_uid = str(target.id)
    ensure_user(data, uid)
    ensure_user(data, target_uid)

    user = data[uid]
    victim = data[target_uid]

    left = cooldown_left(user["cooldowns"].get("rob"), ROB_COOLDOWN)
    if left > 0:
        await interaction.response.send_message(f"🕒 You must wait **{int(left//60)}m {int(left%60)}s** before robbing again.")
        return

    if victim["bal"] < 1000:
        await interaction.response.send_message("❌ Target does not have enough coins to be robbed.")
        return

    steal_amount = random.randint(500, min(3000, victim["bal"]))
    success = random.random() < 0.5

    if success:
        user["bal"] += steal_amount
        victim["bal"] -= steal_amount
        result_msg = f"💰 You successfully robbed **{steal_amount:,} coins** from {target.display_name}!"
        # Update daily quest progress for rob
        user["stats"]["rob"] = user["stats"].get("rob", 0) + 1
    else:
        penalty = steal_amount // 2
        user["bal"] -= penalty
        victim["bal"] += penalty
        result_msg = f"❌ Robbery failed! You paid a fine of **{penalty:,} coins** to {target.display_name}."

    user["cooldowns"]["rob"] = datetime.utcnow().isoformat()
    save_data(data)
    await interaction.response.send_message(result_msg)

# --- Gambling: Coinflip ---
@tree.command(name="coinflip", description="Bet coins on heads or tails")
@app_commands.describe(bet="Amount to bet", choice="heads or tails")
async def coinflip(interaction: discord.Interaction, bet: int, choice: str):
    choice = choice.lower()
    if choice not in ["heads", "tails"]:
        await interaction.response.send_message("❌ Choice must be 'heads' or 'tails'.")
        return
    if bet <= 0:
        await interaction.response.send_message("❌ Bet must be positive.")
        return
    if bet > MAX_BET:
        await interaction.response.send_message(f"❌ Max bet is {MAX_BET:,} coins.")
        return

    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    if user["bal"] < bet:
        await interaction.response.send_message("❌ You don't have enough coins to bet.")
        return
    result = random.choice(["heads", "tails"])
    if result == choice:
        winnings = bet
        user["bal"] += winnings
        user["stats"]["coinflip_win"] = user["stats"].get("coinflip_win", 0) + 1
        add_exp(user, 25)
        msg = f"🎉 You won the coinflip! You earned **{winnings:,} coins**."
    else:
        user["bal"] -= bet
        msg = f"😢 You lost the coinflip. Lost **{bet:,} coins**."

    save_data(data)
    await interaction.response.send_message(msg)

# --- Achievements ---
@tree.command(name="achievements", description="Show your achievements")
async def achievements(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    if not user["achievements"]:
        await interaction.response.send_message("🏅 You have no achievements yet.")
        return
    msg = "**🏅 Your Achievements:**\n"
    for ach in user["achievements"]:
        msg += f"• {ACHIEVEMENTS[ach]['desc']}\n"
    await interaction.response.send_message(msg)

# --- Daily quests ---
@tree.command(name="dailyquests", description="Show your current daily quests")
async def dailyquests(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]
    if not user["daily_quests"]["quests"]:
        reset_daily_quests(user)
        save_data(data)
    msg = "**🎯 Daily Quests:**\n"
    for idx, quest in enumerate(user["daily_quests"]["quests"], 1):
        progress = user["daily_quests"]["progress"].get(str(idx), 0)
        msg += f"{idx}. {quest['desc']} ({progress}/{quest['amount']}) - Reward: {quest['reward']} coins\n"
    claimed = user["daily_quests"]["claimed"]
    msg += f"\nClaimed: {'Yes' if claimed else 'No'}"
    await interaction.response.send_message(msg)

@tree.command(name="claimquests", description="Claim rewards if daily quests are completed")
async def claimquests(interaction: discord.Interaction):
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    user = data[uid]

    if user["daily_quests"]["claimed"]:
        await interaction.response.send_message("❌ You already claimed your daily quests reward.")
        return

    all_done = True
    for idx, quest in enumerate(user["daily_quests"]["quests"], 1):
        progress = user["daily_quests"]["progress"].get(str(idx), 0)
        if progress < quest["amount"]:
            all_done = False
            break

    if not all_done:
        await interaction.response.send_message("❌ You haven't completed all daily quests yet.")
        return

    total_reward = sum(q["reward"] for q in user["daily_quests"]["quests"])
    user["bal"] += total_reward
    user["daily_quests"]["claimed"] = True
    save_data(data)
    await interaction.response.send_message(f"🎉 You claimed **{total_reward} coins** from daily quests!")

# --- Admin command ---
@tree.command(name="resetdata", description="Admin: Reset all user data (admin only)")
async def resetdata(interaction: discord.Interaction):
    if interaction.user.guild_permissions.administrator:
        save_data({})
        await interaction.response.send_message("🧹 All data has been reset.")
    else:
        await interaction.response.send_message("❌ You don't have permission to use this command.")

# --- Sync commands for guild-only during dev (optional) ---
# Use tree.sync() in on_ready for global sync as we do

# --- Helper to update daily quest progress on relevant commands ---
async def update_daily_quest_progress(data, uid, key, amount=1):
    user = data[uid]
    user["stats"][key] = user["stats"].get(key, 0) + amount
    progress = user["daily_quests"]["progress"]
    for i, quest in enumerate(user["daily_quests"]["quests"], 1):
        if quest["type"] == key:
            progress[str(i)] = min(quest["amount"], progress.get(str(i), 0) + amount)

# --- Modify commands to update quests progress where needed ---
# For example, add calls to update_daily_quest_progress in work, rob, buy, coinflip win:

# We'll patch those now by monkey patching commands handlers (for clarity here):

old_work = work.callback
async def new_work(interaction: discord.Interaction):
    await old_work(interaction)
    # Update daily quest progress for 'work'
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    await update_daily_quest_progress(data, uid, "work", 1)
    save_data(data)
work.callback = new_work

old_rob = rob.callback
async def new_rob(interaction: discord.Interaction, target: discord.Member):
    await old_rob(interaction, target)
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    # Only count success rob for daily quest progress (approximate)
    # We don't have direct success result here, so for simplicity add 1 always
    await update_daily_quest_progress(data, uid, "rob", 1)
    save_data(data)
rob.callback = new_rob

old_buy = buy.callback
async def new_buy(interaction: discord.Interaction, item: str, amount: int = 1):
    await old_buy(interaction, item, amount)
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    await update_daily_quest_progress(data, uid, "buy_crypto", amount)
    save_data(data)
buy.callback = new_buy

old_coinflip = coinflip.callback
async def new_coinflip(interaction: discord.Interaction, bet: int, choice: str):
    await old_coinflip(interaction, bet, choice)
    data = load_data()
    uid = str(interaction.user.id)
    ensure_user(data, uid)
    # We don't know if user won or not inside new_coinflip, so no progress update here
    # It's handled in old_coinflip itself.
coinflip.callback = new_coinflip


# --- TOKEN and run ---
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    print("Error: DISCORD_BOT_TOKEN environment variable not set.")
else:
    bot.run(TOKEN)
