import discord
from discord.ext import commands, tasks
import os, random, json, asyncio
from datetime import datetime, timedelta

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

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
    print("Crypto prices updated:", {k: v['price'] for k, v in CRYPTOCURRENCIES.items()})

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
    # Random chance to boost or drop a crypto price drastically
    if random.random() < 0.3:
        crypto = random.choice(list(CRYPTOCURRENCIES.keys()))
        event_type = random.choice(["boost", "drop"])
        multiplier = random.uniform(1.1, 1.3) if event_type == "boost" else random.uniform(0.7, 0.9)
        old_price = CRYPTOCURRENCIES[crypto]["price"]
        new_price = max(0.01, old_price * multiplier)
        CRYPTOCURRENCIES[crypto]["price"] = round(new_price, 2)
        channel = discord.utils.get(bot.get_all_channels(), name="general")  # adjust channel name
        if channel:
            await channel.send(f"📢 Crypto news: {crypto.capitalize()} price just {'rose' if event_type == 'boost' else 'fell'} sharply! New price: {CRYPTOCURRENCIES[crypto]['price']} coins")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    update_crypto_prices.start()
    investment_price_fluctuation.start()
    crypto_news_event.start()

# ---------------- Economy commands ----------------

@bot.command()
async def bal(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]
    await ctx.send(f"💰 Balance: {user['bal']:,} | Level: {user['lvl']} | EXP: {user['exp']}/1000 | Job: {user['job'] or 'None'} Lv.{user.get('job_lvl',1)}")

@bot.command()
async def daily(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]
    left = cooldown_left(user["daily"], BASE_COOLDOWN)
    if left > 0:
        await ctx.send(f"🕒 You must wait {int(left // 60)}m {int(left % 60)}s for your daily reward.")
        return
    reward = random.randint(1500, 3500)
    user["bal"] += reward
    user["daily"] = datetime.utcnow().isoformat()
    add_exp(user, 60)
    earned_achievements = update_achievements(data, uid)
    save_data(data)
    msg = f"✅ You collected your daily reward: +{reward:,} coins, +60 EXP"
    for key, desc, rew in earned_achievements:
        msg += f"\n🏆 Achievement unlocked: {desc} (+{rew:,} coins)"
    await ctx.send(msg)

@bot.command()
async def work(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]
    cooldown = get_work_cooldown(user)
    left = cooldown_left(user["work"], cooldown)
    if left > 0:
        await ctx.send(f"🕒 You need to wait {int(left // 60)}m {int(left % 60)}s before working again.")
        return
    # Calculate pay based on job and level
    base_pay = random.randint(1100, 2500)
    job_mult = 1.0
    if user["job"] in JOBS:
        job_mult = JOBS[user["job"]]["base_pay"] + (user["job_lvl"] - 1) * 0.1
    pay = int(base_pay * job_mult)
    user["bal"] += pay
    user["work"] = datetime.utcnow().isoformat()
    add_exp(user, 45)
    add_job_exp(user, 30)
    earned_achievements = update_achievements(data, uid)
    save_data(data)
    msg = f"💼 You worked as {user['job'] or 'a freelancer'} and earned {pay:,} coins, +45 EXP"
    for key, desc, rew in earned_achievements:
        msg += f"\n🏆 Achievement unlocked: {desc} (+{rew:,} coins)"
    await ctx.send(msg)

@bot.command()
async def inv(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    inv = data[uid]["inv"]
    if not inv or all(v <= 0 for v in inv.values()):
        await ctx.send("🎒 Your inventory is empty.")
        return
    msg = "**🎒 Inventory:**\n"
    for item, amount in inv.items():
        if amount > 0:
            msg += f"{item} x{amount}\n"
    await ctx.send(msg)

@bot.command()
async def job(ctx, job_name: str = None):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]
    if job_name is None:
        if user["job"]:
            await ctx.send(f"👔 Your current job: {user['job']} {JOBS[user['job']]['emoji']} Lv.{user['job_lvl']}")
        else:
            await ctx.send(f"ℹ️ You don't have a job. Choose one with `!job <hacker/trader/miner>`")
        return
    job_name = job_name.lower()
    if job_name not in JOBS:
        await ctx.send("❌ Invalid job. Choose from: hacker, trader, miner.")
        return
    user["job"] = job_name
    user["job_lvl"] = 1
    user["job_exp"] = 0
    save_data(data)
    await ctx.send(f"✅ You started working as a {job_name} {JOBS[job_name]['emoji']}")

# ------------- Shop with buying multiple amounts -----------------

@bot.command()
async def shop(ctx):
    msg = "**🪙 Crypto Shop (prices update hourly):**\n"
    for crypto, info in CRYPTOCURRENCIES.items():
        price_str = f"{info['price']:,}" if info['price'] >= 1 else str(info['price'])
        msg += f"`{crypto}`: {price_str} coins — {info['desc']}\n"
    msg += "\nUse `!buy <crypto> <amount>` to purchase multiple."
    await ctx.send(msg)

@bot.command()
async def buy(ctx, item: str, amount: int = 1):
    if amount <= 0:
        await ctx.send("❌ Amount must be a positive number.")
        return
    data = load_data()
    uid = str(ctx.author.id)
    item = item.lower()
    ensure_user(data, uid)
    if item not in CRYPTOCURRENCIES:
        await ctx.send("❌ That crypto is not available in the shop.")
        return
    cost = int(CRYPTOCURRENCIES[item]["price"] * amount)
    if data[uid]["bal"] < cost:
        await ctx.send(f"❌ You don't have enough coins to buy {amount} {item}(s) ({cost:,} coins).")
        return
    data[uid]["bal"] -= cost
    inv = data[uid]["inv"]
    inv[item] = inv.get(item, 0) + amount
    add_exp(data[uid], 20 * amount)
    save_data(data)
    await ctx.send(f"✅ You bought {amount} {item}(s) for {cost:,} coins.")

@bot.command()
async def sell(ctx, item: str, amount: int = 1):
    if amount <= 0:
        await ctx.send("❌ Amount must be a positive number.")
        return
    data = load_data()
    uid = str(ctx.author.id)
    item = item.lower()
    ensure_user(data, uid)
    inv = data[uid]["inv"]
    if item not in inv or inv[item] < amount:
        await ctx.send("❌ You don't own that many items to sell.")
        return
    price = int(CRYPTOCURRENCIES.get(item, {"price":0})["price"] * 0.6 * amount)
    inv[item] -= amount
    data[uid]["bal"] += price
    save_data(data)
    await ctx.send(f"✅ You sold {amount} {item}(s) for {price:,} coins.")

# -------- Lootbox command --------

@bot.command()
async def lootbox(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]
    cost = 5000
    if user["bal"] < cost:
        await ctx.send(f"❌ You need {cost:,} coins to buy a lootbox.")
        return
    user["bal"] -= cost

    # Randomly pick lootbox item
    loot = random.choice(LOOTBOX_ITEMS)
    if loot["type"] == "crypto":
        amount = random.randint(loot["min"], loot["max"])
        user["inv"][loot["item"]] = user["inv"].get(loot["item"], 0) + amount
        msg = f"🎁 You opened a lootbox and got {amount} {loot['item']}!"
    else:  # booster
        add_booster(user, loot["item"], loot["duration"])
        msg = f"🎁 You opened a lootbox and got a **{loot['item']}** booster active for {loot['duration']//60} minutes!"

    add_exp(user, 50)
    save_data(data)
    await ctx.send(msg)

# -------- Work cooldown boosters info --------

@bot.command()
async def boosters(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]
    msg = "**🎁 Your Active Boosters:**\n"
    now = datetime.utcnow()
    active = False
    for booster, expiry_str in user.get("boosters", {}).items():
        expiry = datetime.fromisoformat(expiry_str)
        if expiry > now:
            active = True
            remaining = expiry - now
            m, s = divmod(int(remaining.total_seconds()), 60)
            msg += f"{booster}: {m}m {s}s remaining\n"
    if not active:
        msg += "None"
    await ctx.send(msg)

# -------- Robbery system --------

@bot.command()
async def rob(ctx, target: discord.Member):
    if target.bot:
        await ctx.send("❌ You can't rob bots.")
        return
    if target == ctx.author:
        await ctx.send("❌ You can't rob yourself.")
        return
    data = load_data()
    uid = str(ctx.author.id)
    tid = str(target.id)
    ensure_user(data, uid)
    ensure_user(data, tid)

    user = data[uid]
    target_user = data[tid]

    cooldown_key = "rob"
    left = cooldown_left(user["cooldowns"].get(cooldown_key), 1800)  # 30 min cooldown
    if left > 0:
        await ctx.send(f"🕒 You must wait {int(left // 60)}m {int(left % 60)}s before robbing again.")
        return

    if target_user["bal"] < 100:
        await ctx.send("❌ Target doesn't have enough money to rob.")
        return

    success_chance = 0.4
    if random.random() < success_chance:
        # Rob success: steal 10-30% of target's balance
        steal_amount = int(target_user["bal"] * random.uniform(0.1, 0.3))
        steal_amount = max(50, steal_amount)
        steal_amount = min(steal_amount, target_user["bal"])
        target_user["bal"] -= steal_amount
        user["bal"] += steal_amount
        user["cooldowns"][cooldown_key] = datetime.utcnow().isoformat()
        save_data(data)
        await ctx.send(f"💰 You robbed {target.display_name} and stole {steal_amount:,} coins!")
    else:
        # Rob fail: lose some money as penalty
        penalty = random.randint(100, 300)
        penalty = min(penalty, user["bal"])
        user["bal"] -= penalty
        user["cooldowns"][cooldown_key] = datetime.utcnow().isoformat()
        save_data(data)
        await ctx.send(f"❌ You got caught trying to rob {target.display_name}! You paid a penalty of {penalty:,} coins.")

# -------- Gambling: coinflip --------

@bot.command()
async def coinflip(ctx, bet: int, guess: str):
    guess = guess.lower()
    if bet <= 0 or bet > MAX_BET:
        await ctx.send(f"❌ Bet must be positive and at most {MAX_BET:,} coins.")
        return
    if guess not in ["heads", "tails"]:
        await ctx.send("❌ Guess must be 'heads' or 'tails'.")
        return
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]
    if user["bal"] < bet:
        await ctx.send("❌ You don't have enough coins for that bet.")
        return
    flip = random.choice(["heads", "tails"])
    if flip == guess:
        win = bet * 2
        user["bal"] += bet
        add_exp(user, 25)
        await ctx.send(f"🎉 You won! The coin landed on {flip}. You gained {bet:,} coins.")
    else:
        user["bal"] -= bet
        await ctx.send(f"😢 You lost! The coin landed on {flip}. You lost {bet:,} coins.")
    save_data(data)

# -------- Gambling: slots --------

@bot.command()
async def slots(ctx, bet: int):
    if bet <= 0 or bet > MAX_BET:
        await ctx.send(f"❌ Bet must be positive and at most {MAX_BET:,} coins.")
        return
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]
    if user["bal"] < bet:
        await ctx.send("❌ You don't have enough coins for that bet.")
        return
    symbols = ["🍒", "🍋", "🍊", "💎", "7️⃣"]
    result = [random.choice(symbols) for _ in range(3)]
    user["bal"] -= bet
    if result[0] == result[1] == result[2]:
        payout = bet * 5
        user["bal"] += payout
        add_exp(user, 50)
        await ctx.send(f"🎰 {' | '.join(result)}\nJackpot! You won {payout:,} coins!")
    elif len(set(result)) == 2:  # two symbols match
        payout = bet * 2
        user["bal"] += payout
        add_exp(user, 20)
        await ctx.send(f"🎰 {' | '.join(result)}\nNice! Two match. You won {payout:,} coins!")
    else:
        await ctx.send(f"🎰 {' | '.join(result)}\nNo luck this time. You lost {bet:,} coins.")
    save_data(data)

# -------- Gambling: cups (reaction buttons) --------
# For simplicity, will use text command cups with 3 cups and user picks a cup number 1-3

@bot.command()
async def cups(ctx, bet: int, choice: int):
    if bet <= 0 or bet > MAX_BET:
        await ctx.send(f"❌ Bet must be positive and at most {MAX_BET:,} coins.")
        return
    if choice not in [1, 2, 3]:
        await ctx.send("❌ Choose a cup number between 1 and 3.")
        return
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]
    if user["bal"] < bet:
        await ctx.send("❌ You don't have enough coins for that bet.")
        return
    user["bal"] -= bet
    winning_cup = random.randint(1, 3)
    if choice == winning_cup:
        payout = bet * 3
        user["bal"] += payout
        add_exp(user, 40)
        await ctx.send(f"🥤 You picked cup {choice}, and it was correct! You won {payout:,} coins.")
    else:
        await ctx.send(f"🥤 You picked cup {choice}, but the prize was under cup {winning_cup}. You lost {bet:,} coins.")
    save_data(data)

# -------- Achievements --------

@bot.command()
async def achievements(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]
    if not user["achievements"]:
        await ctx.send("🏆 You have no achievements yet. Keep playing!")
        return
    msg = "**🏆 Your Achievements:**\n"
    for key in user["achievements"]:
        msg += f"- {ACHIEVEMENTS[key]['desc']}\n"
    await ctx.send(msg)

# -------- Daily quests (simple and rewarding) --------

@bot.command()
async def quest(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]
    if user["daily_quests"]["claimed"]:
        await ctx.send("✅ You already claimed your daily quest rewards. New quests come tomorrow.")
        return
    # If no quests or all completed, generate new quests
    if not user["daily_quests"]["quests"]:
        quests = [
            {"task": "work", "desc": "Work once", "done": False, "reward": 800},
            {"task": "rob", "desc": "Rob a player once", "done": False, "reward": 1200},
            {"task": "gamble", "desc": "Win 1 gamble game", "done": False, "reward": 1000},
        ]
        user["daily_quests"]["quests"] = quests
        user["daily_quests"]["claimed"] = False
        save_data(data)
    msg = "**🎯 Daily Quests:**\n"
    for i, q in enumerate(user["daily_quests"]["quests"], 1):
        status = "✅" if q["done"] else "❌"
        msg += f"{i}. {q['desc']} {status}\n"
    msg += "\nComplete quests and use `!claim` to get rewards."
    await ctx.send(msg)

@bot.command()
async def claim(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]
    if user["daily_quests"]["claimed"]:
        await ctx.send("❌ You already claimed your daily quests rewards.")
        return
    total_reward = 0
    for q in user["daily_quests"]["quests"]:
        if q["done"]:
            total_reward += q["reward"]
    if total_reward == 0:
        await ctx.send("❌ You haven't completed any quests yet.")
        return
    user["bal"] += total_reward
    user["daily_quests"]["claimed"] = True
    save_data(data)
    await ctx.send(f"🎉 You claimed {total_reward:,} coins from your daily quests!")

# You can add hooks or triggers on certain commands to mark quests as done, e.g. on work, rob, gamble commands,
# but for simplicity, user must manually mark them or it can be extended later.

# -------- Admin commands --------

@bot.command()
@commands.is_owner()
async def resetdata(ctx, user: discord.User = None):
    data = load_data()
    if user:
        uid = str(user.id)
        if uid in data:
            del data[uid]
            save_data(data)
            await ctx.send(f"✅ Data for {user} reset.")
        else:
            await ctx.send("❌ User data not found.")
    else:
        # Reset all data (careful!)
        save_data({})
        await ctx.send("✅ All data reset.")

@bot.command()
@commands.is_owner()
async def resetcd(ctx, user: discord.User = None):
    data = load_data()
    if user:
        uid = str(user.id)
        if uid in data:
            data[uid]["cooldowns"] = {}
            save_data(data)
            await ctx.send(f"✅ Cooldowns reset for {user}.")
        else:
            await ctx.send("❌ User data not found.")
    else:
        # Reset cooldowns for all users
        for uid in data:
            data[uid]["cooldowns"] = {}
        save_data(data)
        await ctx.send("✅ All cooldowns reset.")

# -------------- Help command --------------

@bot.command(name="help")
async def help_cmd(ctx):
    msg = """**📚 Bot Commands:**

**Economy:**
`!bal` - Check your balance and level
`!daily` - Claim daily reward (cooldown)
`!work` - Work for coins (cooldown, can be boosted)
`!inv` - Show your inventory
`!job [job]` - Choose/view your job (hacker, trader, miner)
`!shop` - View crypto shop
`!buy <crypto> <amount>` - Buy crypto
`!sell <crypto> <amount>` - Sell crypto

**Gambling (max bet 250,000):**
`!coinflip <bet> <heads/tails>`
`!slots <bet>`
`!cups <bet> <cup number (1-3)>`

**Other:**
`!lootbox` - Buy and open a lootbox for random rewards (cost 5000 coins)
`!boosters` - Show your active boosters
`!rob <user>` - Attempt to rob another user (30 min cooldown)
`!achievements` - View your achievements
`!quest` - View daily quests
`!claim` - Claim daily quests rewards

**Admin (owner only):**
`!resetdata [@user]` - Reset user or all data
`!resetcd [@user]` - Reset cooldowns for user or all

"""
    await ctx.send(msg)

# ------------- Run bot -------------

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    print("ERROR: DISCORD_BOT_TOKEN env variable not set!")
else:
    bot.run(TOKEN)
