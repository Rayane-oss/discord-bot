import discord
from discord.ext import commands, tasks
import os, random, json, asyncio
from datetime import datetime, timedelta

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = os.getenv("VOLUME_PATH", ".") + "/economy.json"
MAX_BET = 250_000
WORK_COOLDOWN = 40 * 60  # seconds
ROB_COOLDOWN = 30 * 60
INVEST_UPDATE_INTERVAL = 120  # seconds

# Initial cryptos with base prices and descriptions
CRYPTOCURRENCIES = {
    "bitcoin": {"price": 50000, "desc": "BTC - Most popular crypto"},
    "ethereum": {"price": 3200, "desc": "ETH - Smart contracts"},
    "dogecoin": {"price": 0.3, "desc": "DOGE - Meme coin"},
    "litecoin": {"price": 180, "desc": "LTC - Faster Bitcoin"},
    "ripple": {"price": 1, "desc": "XRP - Bank payments"},
}

# Job definitions
JOBS = {
    "hacker": {"emoji": "🕵️‍♂️", "base_income": 1500},
    "trader": {"emoji": "💹", "base_income": 1300},
    "miner": {"emoji": "⛏️", "base_income": 1100},
}

# Achievements example (easy to earn)
ACHIEVEMENTS = {
    "first_work": {"desc": "Complete your first work", "exp": 100, "coins": 500},
    "reach_lvl_5": {"desc": "Reach level 5", "exp": 500, "coins": 2500},
    "buy_10_crypto": {"desc": "Buy 10 cryptos in total", "exp": 300, "coins": 1500},
}

# Daily quests example
DAILY_QUESTS = [
    {"desc": "Earn 3,000 coins today", "check": lambda u: u.get("coins_earned_today", 0) >= 3000, "reward_exp": 100, "reward_coins": 1000},
    {"desc": "Gain 100 EXP today", "check": lambda u: u.get("exp_gained_today", 0) >= 100, "reward_exp": 80, "reward_coins": 800},
]

# Load and save user data
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
            "rob": None,
            "inv": {},
            "job": None,
            "job_lvl": 1,
            "achievements": [],
            "coins_earned_today": 0,
            "exp_gained_today": 0,
            "daily_quest_completed": False,
            "work_booster": 0,  # number of boosters owned
            "investments": {},  # crypto: amount
        }

def cooldown_left(last_time, cd):
    if not last_time:
        return 0
    delta = (datetime.utcnow() - datetime.fromisoformat(last_time)).total_seconds()
    return max(0, cd - delta)

def add_exp(user, amount):
    user["exp"] += amount
    user["exp_gained_today"] = user.get("exp_gained_today", 0) + amount
    leveled_up = False
    while user["exp"] >= 1000:
        user["exp"] -= 1000
        user["lvl"] += 1
        leveled_up = True
    return leveled_up

def add_coins_earned_today(user, amount):
    user["coins_earned_today"] = user.get("coins_earned_today", 0) + amount

# Update crypto prices hourly with fluctuations
@tasks.loop(hours=1)
async def update_crypto_prices():
    for crypto in CRYPTOCURRENCIES:
        base_price = CRYPTOCURRENCIES[crypto]["price"]
        change_percent = random.uniform(-0.05, 0.05)  # ±5%
        new_price = base_price * (1 + change_percent)
        CRYPTOCURRENCIES[crypto]["price"] = round(max(new_price, 0.01), 2)

# Update crypto prices & run crypto news every hour
@tasks.loop(hours=1)
async def crypto_news_event():
    # Fake news affecting crypto prices ±3-7%
    crypto = random.choice(list(CRYPTOCURRENCIES.keys()))
    impact = random.uniform(0.03, 0.07)
    up = random.choice([True, False])
    old_price = CRYPTOCURRENCIES[crypto]["price"]
    new_price = old_price * (1 + impact if up else 1 - impact)
    CRYPTOCURRENCIES[crypto]["price"] = round(max(new_price, 0.01), 2)
    channel = discord.utils.get(bot.get_all_channels(), name="general")  # replace with your channel name
    if channel:
        msg = f"📰 Crypto news: {crypto.title()} price {'surged 📈' if up else 'dropped 📉'} by {int(impact*100)}%! New price: {CRYPTOCURRENCIES[crypto]['price']}"
        await channel.send(msg)

# Update investments every 2 minutes, prices fluctuate ±3%
@tasks.loop(seconds=INVEST_UPDATE_INTERVAL)
async def update_investments():
    for crypto in CRYPTOCURRENCIES:
        base_price = CRYPTOCURRENCIES[crypto]["price"]
        change_percent = random.uniform(-0.03, 0.03)
        new_price = base_price * (1 + change_percent)
        CRYPTOCURRENCIES[crypto]["price"] = round(max(new_price, 0.01), 2)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    update_crypto_prices.start()
    crypto_news_event.start()
    update_investments.start()

# Helper to check and grant achievements
def check_achievements(user):
    unlocked = []
    # first_work
    if "first_work" not in user["achievements"] and user.get("work_done", 0) >= 1:
        unlocked.append("first_work")
    # reach_lvl_5
    if "reach_lvl_5" not in user["achievements"] and user["lvl"] >= 5:
        unlocked.append("reach_lvl_5")
    # buy_10_crypto
    total_crypto = sum(user["inv"].values())
    if "buy_10_crypto" not in user["achievements"] and total_crypto >= 10:
        unlocked.append("buy_10_crypto")
    return unlocked

def grant_achievements(user, unlocked, data):
    for ach in unlocked:
        if ach not in user["achievements"]:
            user["achievements"].append(ach)
            user["exp"] += ACHIEVEMENTS[ach]["exp"]
            user["bal"] += ACHIEVEMENTS[ach]["coins"]

# Economy commands:

@bot.command()
async def bal(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]
    await ctx.send(f"💰 Balance: {user['bal']} | Level: {user['lvl']} | EXP: {user['exp']}/1000 | Job: {user['job'] or 'None'} (Lvl {user['job_lvl']})")

@bot.command()
async def daily(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    left = cooldown_left(data[uid]["daily"], 24 * 3600)
    if left > 0:
        await ctx.send(f"🕒 Wait {int(left//3600)}h {int((left%3600)//60)}m for your daily reward.")
        return
    reward = random.randint(1500, 3500)
    data[uid]["bal"] += reward
    data[uid]["daily"] = datetime.utcnow().isoformat()
    add_exp(data[uid], 60)
    add_coins_earned_today(data[uid], reward)
    save_data(data)
    await ctx.send(f"✅ Daily collected: +{reward} coins, +60 EXP")

@bot.command()
async def work(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]
    base_cd = WORK_COOLDOWN
    # reduce cooldown by 5 mins per booster owned
    booster_reduction = user.get("work_booster", 0) * 300
    cd = max(60, base_cd - booster_reduction)
    left = cooldown_left(user["work"], cd)
    if left > 0:
        await ctx.send(f"🕒 Wait {int(left//60)}m {int(left%60)}s before working again.")
        return
    # Base reward with job bonus
    base_reward = random.randint(1100, 2500)
    job_bonus = 0
    if user["job"]:
        job_bonus = JOBS[user["job"]]["base_income"] * (0.1 * (user["job_lvl"] - 1))
    total_reward = int(base_reward + job_bonus)
    user["bal"] += total_reward
    user["work"] = datetime.utcnow().isoformat()
    add_exp(user, 45)
    add_coins_earned_today(user, total_reward)
    user["work_done"] = user.get("work_done", 0) + 1
    save_data(data)
    await ctx.send(f"💼 Worked and earned {total_reward} coins (+{int(45)} EXP)")

@bot.command()
async def inv(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    inv = data[uid]["inv"]
    boosters = data[uid].get("work_booster", 0)
    msg = "**🎒 Inventory:**\n"
    if not inv and boosters == 0:
        await ctx.send("Your inventory is empty.")
        return
    for item, amount in inv.items():
        if amount > 0:
            msg += f"{item} x{amount}\n"
    if boosters > 0:
        msg += f"Work Boosters x{boosters}\n"
    await ctx.send(msg)

@bot.command()
async def shop(ctx):
    msg = "**🪙 Crypto Shop (prices update hourly):**\n"
    for crypto, info in CRYPTOCURRENCIES.items():
        price_str = f"{info['price']:,}" if info['price'] >= 1 else str(info['price'])
        msg += f"`{crypto}`: {price_str} coins — {info['desc']}\n"
    await ctx.send(msg)

# Buy command supporting amount
@bot.command()
async def buy(ctx, item: str, amount: int = 1):
    data = load_data()
    uid = str(ctx.author.id)
    item = item.lower()
    ensure_user(data, uid)
    user = data[uid]
    if item not in CRYPTOCURRENCIES:
        await ctx.send("❌ That crypto is not available in the shop.")
        return
    if amount < 1:
        await ctx.send("❌ You must buy at least 1 item.")
        return
    cost_per = CRYPTOCURRENCIES[item]["price"]
    total_cost = int(cost_per * amount)
    if user["bal"] < total_cost:
        await ctx.send(f"❌ Not enough coins to buy {amount} {item} ({total_cost} coins).")
        return
    user["bal"] -= total_cost
    inv = user["inv"]
    inv[item] = inv.get(item, 0) + amount
    add_exp(user, 20 * amount)
    add_coins_earned_today(user, total_cost)
    save_data(data)
    await ctx.send(f"✅ Bought {amount} {item} for {total_cost} coins.")

@bot.command()
async def sell(ctx, item: str, amount: int = 1):
    data = load_data()
    uid = str(ctx.author.id)
    item = item.lower()
    ensure_user(data, uid)
    user = data[uid]
    inv = user["inv"]
    if item not in inv or inv[item] < amount or amount < 1:
        await ctx.send("❌ You don't have enough of this item to sell.")
        return
    price = int(CRYPTOCURRENCIES.get(item, {"price":0})["price"] * 0.6)
    total_price = price * amount
    inv[item] -= amount
    user["bal"] += total_price
    save_data(data)
    await ctx.send(f"✅ Sold {amount} {item} for {total_price} coins.")

# Lootbox command (random rewards)
@bot.command()
async def lootbox(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]

    rewards = [
        {"type": "crypto", "item": random.choice(list(CRYPTOCURRENCIES.keys())), "amount": random.randint(1,3)},
        {"type": "work_booster", "amount": 1},
        {"type": "coins", "amount": random.randint(500, 1500)},
    ]
    reward = random.choice(rewards)

    if reward["type"] == "crypto":
        item = reward["item"]
        amt = reward["amount"]
        user["inv"][item] = user["inv"].get(item, 0) + amt
        msg = f"🎁 Lootbox reward: {amt} {item} crypto!"
    elif reward["type"] == "work_booster":
        user["work_booster"] = user.get("work_booster", 0) + 1
        msg = "🎁 Lootbox reward: Work Booster! (reduces work cooldown)"
    else:
        coins = reward["amount"]
        user["bal"] += coins
        add_coins_earned_today(user, coins)
        msg = f"🎁 Lootbox reward: {coins} coins!"

    save_data(data)
    await ctx.send(msg)

# Rob command with cooldown and risk
@bot.command()
async def rob(ctx, target: discord.Member):
    data = load_data()
    uid = str(ctx.author.id)
    tid = str(target.id)
    ensure_user(data, uid)
    ensure_user(data, tid)
    user = data[uid]
    target_user = data[tid]

    if uid == tid:
        await ctx.send("❌ You can't rob yourself.")
        return

    left = cooldown_left(user["rob"], ROB_COOLDOWN)
    if left > 0:
        await ctx.send(f"🕒 Wait {int(left//60)}m {int(left%60)}s before robbing again.")
        return

    if target_user["bal"] < 500:
        await ctx.send("❌ Target doesn't have enough coins to rob.")
        return

    success = random.random() < 0.5
    if success:
        steal_amount = random.randint(100, int(target_user["bal"] * 0.3))
        steal_amount = min(steal_amount, target_user["bal"])
        target_user["bal"] -= steal_amount
        user["bal"] += steal_amount
        await ctx.send(f"💰 You successfully robbed {steal_amount} coins from {target.display_name}!")
    else:
        penalty = random.randint(50, 200)
        user["bal"] = max(0, user["bal"] - penalty)
        await ctx.send(f"🚨 Robbery failed! You lost {penalty} coins as penalty.")

    user["rob"] = datetime.utcnow().isoformat()
    save_data(data)

# Slots gambling game
@bot.command()
async def slots(ctx, amount: int):
    if amount <= 0 or amount > MAX_BET:
        await ctx.send(f"❌ Bet must be between 1 and {MAX_BET}.")
        return

    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]

    if user["bal"] < amount:
        await ctx.send("❌ Not enough coins for that bet.")
        return

    emojis = ["🍒", "🍋", "🔔", "⭐", "7️⃣"]
    result = [random.choice(emojis) for _ in range(3)]

    win = 0
    if result[0] == result[1] == result[2]:
        win = amount * 5
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        win = amount * 2

    if win > 0:
        user["bal"] += win
        add_exp(user, 40)
        await ctx.send(f"🎰 {' | '.join(result)}\n🎉 You won {win} coins!")
    else:
        user["bal"] -= amount
        add_exp(user, 10)
        await ctx.send(f"🎰 {' | '.join(result)}\n💀 You lost {amount} coins.")

    save_data(data)

# Coin investment commands
@bot.command()
async def invest(ctx, action: str, crypto: str = None, amount: int = 0):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]
    action = action.lower()

    if action == "buy":
        if crypto is None or amount <= 0:
            await ctx.send("Usage: !invest buy <crypto> <amount>")
            return
        crypto = crypto.lower()
        if crypto not in CRYPTOCURRENCIES:
            await ctx.send("Crypto not found.")
            return
        cost = CRYPTOCURRENCIES[crypto]["price"] * amount
        if user["bal"] < cost:
            await ctx.send("Not enough coins.")
            return
        user["bal"] -= int(cost)
        user["investments"][crypto] = user["investments"].get(crypto, 0) + amount
        save_data(data)
        await ctx.send(f"Bought {amount} {crypto} at {CRYPTOCURRENCIES[crypto]['price']} coins each.")

    elif action == "sell":
        if crypto is None or amount <= 0:
            await ctx.send("Usage: !invest sell <crypto> <amount>")
            return
        crypto = crypto.lower()
        if crypto not in user["investments"] or user["investments"][crypto] < amount:
            await ctx.send("Not enough invested coins.")
            return
        price = CRYPTOCURRENCIES[crypto]["price"]
        gain = price * amount
        user["investments"][crypto] -= amount
        if user["investments"][crypto] == 0:
            del user["investments"][crypto]
        user["bal"] += int(gain)
        save_data(data)
        await ctx.send(f"Sold {amount} {crypto} at {price} coins each for {int(gain)} coins.")

    elif action == "portfolio":
        if not user["investments"]:
            await ctx.send("Your investment portfolio is empty.")
            return
        msg = "**📈 Your Investments:**\n"
        total_val = 0
        for c, amt in user["investments"].items():
            price = CRYPTOCURRENCIES[c]["price"]
            val = price * amt
            total_val += val
            msg += f"{c}: {amt} coins, worth {val:.2f} coins\n"
        msg += f"Total portfolio value: {total_val:.2f} coins"
        await ctx.send(msg)

    else:
        await ctx.send("Invalid invest command. Use buy/sell/portfolio.")

# Jobs commands
@bot.command()
async def job(ctx, jobname=None):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]

    if jobname is None:
        # Show current job or options
        msg = f"Your current job: {user['job'] or 'None'} (Level {user['job_lvl']})\nAvailable jobs:\n"
        for j, info in JOBS.items():
            msg += f"{j} {info['emoji']} - Base income: {info['base_income']} coins/work\n"
        await ctx.send(msg)
        return

    jobname = jobname.lower()
    if jobname not in JOBS:
        await ctx.send("Job not found.")
        return

    user["job"] = jobname
    user["job_lvl"] = 1
    save_data(data)
    await ctx.send(f"✅ You are now a {jobname} {JOBS[jobname]['emoji']}")

@bot.command()
async def joblvlup(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]
    if not user["job"]:
        await ctx.send("You don't have a job.")
        return
    cost = user["job_lvl"] * 10000
    if user["bal"] < cost:
        await ctx.send(f"You need {cost} coins to level up your job.")
        return
    user["bal"] -= cost
    user["job_lvl"] += 1
    save_data(data)
    await ctx.send(f"Job level increased to {user['job_lvl']}! Income increased.")

# Daily quests command
@bot.command()
async def dailyquest(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]
    if user.get("daily_quest_completed", False):
        await ctx.send("You already completed today's daily quest.")
        return
    for quest in DAILY_QUESTS:
        if quest["check"](user):
            user["exp"] += quest["reward_exp"]
            user["bal"] += quest["reward_coins"]
            user["daily_quest_completed"] = True
            save_data(data)
            await ctx.send(f"✅ Daily quest completed: {quest['desc']}! You got {quest['reward_exp']} EXP and {quest['reward_coins']} coins.")
            return
    await ctx.send("You haven't completed any daily quests yet. Keep playing!")

# Admin commands (only owner)
def is_owner():
    async def predicate(ctx):
        return await bot.is_owner(ctx.author)
    return commands.check(predicate)

@bot.command()
@is_owner()
async def reset(ctx, user: discord.Member = None):
    data = load_data()
    if user:
        uid = str(user.id)
        if uid in data:
            del data[uid]
            save_data(data)
            await ctx.send(f"Reset data for {user.display_name}.")
        else:
            await ctx.send("User data not found.")
    else:
        data.clear()
        save_data(data)
        await ctx.send("Reset all user data.")

@bot.command()
@is_owner()
async def resetcd(ctx, user: discord.Member = None):
    data = load_data()
    if user:
        uid = str(user.id)
        if uid in data:
            userd = data[uid]
            userd["work"] = None
            userd["rob"] = None
            userd["daily"] = None
            save_data(data)
            await ctx.send(f"Cooldowns reset for {user.display_name}.")
        else:
            await ctx.send("User data not found.")
    else:
        for u in data.values():
            u["work"] = None
            u["rob"] = None
            u["daily"] = None
        save_data(data)
        await ctx.send("All cooldowns reset.")

@bot.command()
@is_owner()
async def givexp(ctx, user: discord.Member, amount: int):
    data = load_data()
    uid = str(user.id)
    ensure_user(data, uid)
    data[uid]["exp"] += amount
    save_data(data)
    await ctx.send(f"Gave {amount} EXP to {user.display_name}.")

# Help command override - to avoid conflicts with default
@bot.command(name="help")
async def help_cmd(ctx):
    msg = """
**Available Commands:**
`!bal` - Check your balance and level
`!daily` - Collect daily coins
`!work` - Work to earn coins
`!inv` - Check your inventory
`!shop` - Show crypto shop
`!buy <crypto> [amount]` - Buy cryptos
`!sell <crypto> [amount]` - Sell cryptos
`!lootbox` - Open a lootbox with random rewards
`!rob @user` - Rob another user (30m cooldown)
`!slots <amount>` - Play slot machine gambling
`!invest buy/sell/portfolio` - Manage crypto investments
`!job [jobname]` - Choose or check job
`!joblvlup` - Level up your job (cost coins)
`!dailyquest` - Complete daily quests for rewards

(Admin only commands available)

"""
    await ctx.send(msg)

# Reset daily quest status daily at midnight UTC
@tasks.loop(hours=24)
async def reset_daily_quests():
    data = load_data()
    for user in data.values():
        user["daily_quest_completed"] = False
        user["coins_earned_today"] = 0
        user["exp_gained_today"] = 0
    save_data(data)

# Start the daily quest reset task at midnight UTC
from datetime import time, timezone

@bot.event
async def on_connect():
    now = datetime.utcnow()
    target = datetime.combine(now.date(), time.min).replace(tzinfo=None) + timedelta(days=1)
    delay = (target - now).total_seconds()
    await asyncio.sleep(delay)
    reset_daily_quests.start()

bot.run(os.getenv("DISCORD_TOKEN"))
