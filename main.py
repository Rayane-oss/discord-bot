import discord
from discord.ext import commands, tasks
import os, random, json, asyncio
from datetime import datetime, timedelta

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = os.getenv("VOLUME_PATH", ".") + "/economy.json"
MAX_BET = 250_000
BASE_COOLDOWN = 40 * 60
INVEST_UPDATE_INTERVAL = 120  # seconds

# Base crypto list and starting prices
CRYPTOCURRENCIES = {
    "bitcoin": {"price": 50000, "desc": "BTC - Most popular crypto"},
    "ethereum": {"price": 3200, "desc": "ETH - Smart contracts"},
    "dogecoin": {"price": 0.3, "desc": "DOGE - Meme coin"},
    "litecoin": {"price": 180, "desc": "LTC - Faster Bitcoin"},
    "ripple": {"price": 1, "desc": "XRP - Bank payments"},
}

# Jobs definitions
JOBS = {
    "hacker": {"emoji": "🕵️‍♂️", "base_income": (900, 1600)},
    "trader": {"emoji": "📈", "base_income": (800, 1400)},
    "miner": {"emoji": "⛏️", "base_income": (700, 1300)},
}

# Achievement rewards (easy)
ACHIEVEMENTS = {
    "first_work": {"desc": "Do your first work", "exp": 100, "coins": 500},
    "level_5": {"desc": "Reach level 5", "exp": 200, "coins": 1000},
    "buy_10_crypto": {"desc": "Buy 10 cryptos total", "exp": 150, "coins": 700},
}

# --- Data handling ---

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
            "boosters": 0,
            "achievements": [],
            "job": None,
            "job_level": 1,
            "job_exp": 0,
            "rob_cooldown": None,
            "quests": {},
            "investments": {},  # coin: amount invested
            "coins_bought_total": 0,
        }

# --- Utilities ---

def cooldown_left(last_time, booster=False, base_cd=BASE_COOLDOWN):
    if not last_time:
        return 0
    cd = base_cd // 2 if booster else base_cd
    delta = (datetime.utcnow() - datetime.fromisoformat(last_time)).total_seconds()
    return max(0, cd - delta)

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
    while user["job_exp"] >= 1000:
        user["job_exp"] -= 1000
        user["job_level"] += 1
        leveled_up = True
    return leveled_up

def check_achievements(user):
    new_achievements = []
    # first work
    if "first_work" not in user["achievements"] and user.get("work") is not None:
        user["achievements"].append("first_work")
        new_achievements.append("first_work")
    # level 5
    if "level_5" not in user["achievements"] and user["lvl"] >= 5:
        user["achievements"].append("level_5")
        new_achievements.append("level_5")
    # buy 10 crypto total
    if "buy_10_crypto" not in user["achievements"] and user.get("coins_bought_total",0) >= 10:
        user["achievements"].append("buy_10_crypto")
        new_achievements.append("buy_10_crypto")
    return new_achievements

# --- Crypto prices update with news system ---

NEWS_EVENTS = [
    {"desc": "Market crash! Prices drop!", "multiplier": 0.7},
    {"desc": "Bull market! Prices soar!", "multiplier": 1.3},
    {"desc": "Stable market, minor changes.", "multiplier": 1.0},
    {"desc": "Crypto regulation announced, prices dip.", "multiplier": 0.8},
    {"desc": "Tech breakthrough, prices rise.", "multiplier": 1.2},
]

current_news = {"desc": "No news currently.", "multiplier": 1.0}

@tasks.loop(seconds=INVEST_UPDATE_INTERVAL)
async def update_crypto_prices():
    global current_news
    news = random.choice(NEWS_EVENTS)
    current_news = news
    for crypto in CRYPTOCURRENCIES:
        base_price = CRYPTOCURRENCIES[crypto]["price"]
        change = random.uniform(-0.05, 0.05)
        new_price = base_price * (1 + change) * news["multiplier"]
        CRYPTOCURRENCIES[crypto]["price"] = round(max(new_price, 0.01), 2)
    print(f"Crypto prices updated with news: {news['desc']}")

# --- Commands ---

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    update_crypto_prices.start()

@bot.command()
async def bal(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]
    job_name = user["job"] or "None"
    await ctx.send(f"💰 Balance: {user['bal']} | Level: {user['lvl']} | EXP: {user['exp']}/1000 | Job: {job_name} {JOBS.get(job_name, {}).get('emoji','')} Lv{user['job_level']} | Boosters: {user['boosters']}")

@bot.command()
async def daily(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    left = cooldown_left(data[uid]["daily"])
    if left > 0:
        return await ctx.send(f"🕒 Wait {int(left//60)}m {int(left%60)}s for daily.")
    reward = random.randint(1500, 3500)
    data[uid]["bal"] += reward
    data[uid]["daily"] = datetime.utcnow().isoformat()
    add_exp(data[uid], 60)
    save_data(data)
    await ctx.send(f"✅ Daily collected: +{reward} coins, +60 EXP")

@bot.command()
async def work(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    booster = data[uid]["boosters"] > 0
    left = cooldown_left(data[uid]["work"], booster=booster)
    if left > 0:
        return await ctx.send(f"🕒 Wait {int(left//60)}m {int(left%60)}s before working again.")
    job = data[uid]["job"]
    min_income, max_income = (1000, 2000)
    if job in JOBS:
        base_min, base_max = JOBS[job]["base_income"]
        lvl_mult = 1 + (data[uid]["job_level"] - 1)*0.1
        min_income, max_income = int(base_min*lvl_mult), int(base_max*lvl_mult)
    reward = random.randint(min_income, max_income)
    data[uid]["bal"] += reward
    data[uid]["work"] = datetime.utcnow().isoformat()
    add_exp(data[uid], 45)
    if booster:
        data[uid]["boosters"] -= 1
    leveled = False
    if job:
        leveled = add_job_exp(data[uid], 30)
    save_data(data)
    msg = f"💼 Worked and earned {reward} coins. +45 EXP"
    if booster:
        msg += " (booster used)"
    if leveled:
        msg += f"\n🎉 Your {job} job leveled up to {data[uid]['job_level']}!"
    await ctx.send(msg)

@bot.command()
async def inv(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    inv = data[uid]["inv"]
    if not inv:
        return await ctx.send("🎒 Inventory empty.")
    msg = "**🎒 Inventory:**\n"
    for item, amount in inv.items():
        if amount > 0:
            msg += f"{item} x{amount}\n"
    await ctx.send(msg)

@bot.command()
async def shop(ctx):
    msg = "**🪙 Crypto Shop (updates every 2 minutes):**\n"
    for name, info in CRYPTOCURRENCIES.items():
        p = f"{info['price']:,}" if info['price'] >= 1 else str(info['price'])
        msg += f"`{name}`: {p} coins — {info['desc']}\n"
    msg += f"\nCurrent news: {current_news['desc']}"
    await ctx.send(msg)

@bot.command()
async def buy(ctx, item: str, amount: int = 1):
    data = load_data()
    uid = str(ctx.author.id)
    item = item.lower()
    ensure_user(data, uid)
    if item not in CRYPTOCURRENCIES:
        return await ctx.send("❌ Not in the shop.")
    if amount <= 0:
        return await ctx.send("❌ Amount must be 1 or more.")
    cost = int(CRYPTOCURRENCIES[item]["price"]) * amount
    if data[uid]["bal"] < cost:
        return await ctx.send(f"❌ Not enough coins to buy {amount} {item} ({cost}).")
    data[uid]["bal"] -= cost
    data[uid]["inv"][item] = data[uid]["inv"].get(item, 0) + amount
    data[uid]["coins_bought_total"] = data[uid].get("coins_bought_total",0) + amount
    add_exp(data[uid], 20 * amount)
    new_achs = check_achievements(data[uid])
    save_data(data)
    resp = f"✅ Bought {amount} {item} for {cost} coins."
    if new_achs:
        resp += "\n🏆 Achievements unlocked: " + ", ".join(ACHIEVEMENTS[a]["desc"] for a in new_achs)
    await ctx.send(resp)

@bot.command()
async def sell(ctx, item: str, amount: int = 1):
    data = load_data()
    uid = str(ctx.author.id)
    item = item.lower()
    ensure_user(data, uid)
    inv = data[uid]["inv"]
    if inv.get(item, 0) < amount:
        return await ctx.send("❌ Not enough items to sell.")
    price = int(CRYPTOCURRENCIES.get(item, {"price":0})["price"] * 0.6) * amount
    inv[item] -= amount
    data[uid]["bal"] += price
    save_data(data)
    await ctx.send(f"✅ Sold {amount} {item} for {price} coins.")

@bot.command()
async def lootbox(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    roll = random.randint(1, 100)
    if roll <= 70:  # crypto
        crypto = random.choice(list(CRYPTOCURRENCIES.keys()))
        qty = random.randint(1, 3)
        data[uid]["inv"][crypto] = data[uid]["inv"].get(crypto, 0) + qty
        reward = f"{qty}x {crypto}"
    else:
        data[uid]["boosters"] += 1
        reward = "1x Work Booster"
    save_data(data)
    await ctx.send(f"🎁 Lootbox opened: {reward}")

@bot.command()
async def boosters(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    await ctx.send(f"⚡ You have {data[uid]['boosters']} work boosters.")

@bot.command()
async def rob(ctx, target: discord.Member):
    data = load_data()
    uid = str(ctx.author.id)
    tid = str(target.id)
    ensure_user(data, uid)
    ensure_user(data, tid)
    if uid == tid:
        return await ctx.send("❌ You can't rob yourself.")
    left = cooldown_left(data[uid].get("rob_cooldown"), base_cd=60*15)  # 15 min cooldown
    if left > 0:
        return await ctx.send(f"🕒 Wait {int(left//60)}m {int(left%60)}s before robbing again.")
    if data[tid]["bal"] < 500:
        return await ctx.send("❌ Target doesn't have enough money to rob.")
    success = random.random() < 0.45  # 45% success rate
    if success:
        stolen = random.randint(200, min(1000, data[tid]["bal"]))
        data[tid]["bal"] -= stolen
        data[uid]["bal"] += stolen
        data[uid]["rob_cooldown"] = datetime.utcnow().isoformat()
        save_data(data)
        await ctx.send(f"💰 You robbed {target.mention} and stole {stolen} coins!")
    else:
        penalty = random.randint(100, 300)
        data[uid]["bal"] = max(0, data[uid]["bal"] - penalty)
        data[uid]["rob_cooldown"] = datetime.utcnow().isoformat()
        save_data(data)
        await ctx.send(f"🚓 Robbery failed! You lost {penalty} coins as penalty.")

@bot.command()
async def slots(ctx, bet: int):
    if bet <= 0 or bet > MAX_BET:
        return await ctx.send(f"❌ Bet must be 1 to {MAX_BET}.")
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    if data[uid]["bal"] < bet:
        return await ctx.send("❌ Not enough coins to bet.")
    emojis = ["🍒", "🍋", "🍊", "🍇", "🔔", "⭐"]
    spin = [random.choice(emojis) for _ in range(3)]
    await ctx.send(f"🎰 {' | '.join(spin)}")
    if spin[0] == spin[1] == spin[2]:
        winnings = bet * 5
        data[uid]["bal"] += winnings
        add_exp(data[uid], 40)
        msg = f"🎉 Jackpot! You won {winnings} coins!"
    elif spin[0] == spin[1] or spin[1] == spin[2] or spin[0] == spin[2]:
        winnings = bet * 2
        data[uid]["bal"] += winnings
        add_exp(data[uid], 25)
        msg = f"✨ You won {winnings} coins!"
    else:
        data[uid]["bal"] -= bet
        add_exp(data[uid], 10)
        msg = f"💀 You lost {bet} coins."
    save_data(data)
    await ctx.send(msg)

@bot.command()
async def invest(ctx, coin: str, amount: int):
    coin = coin.lower()
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    if coin not in CRYPTOCURRENCIES:
        return await ctx.send("❌ That coin is not investable.")
    if amount <= 0:
        return await ctx.send("❌ Amount must be positive.")
    if data[uid]["bal"] < amount:
        return await ctx.send("❌ Not enough coins.")
    data[uid]["bal"] -= amount
    inv = data[uid]["investments"]
    inv[coin] = inv.get(coin, 0) + amount
    save_data(data)
    await ctx.send(f"📈 Invested {amount} coins into {coin}.")

@bot.command()
async def cashout(ctx, coin: str):
    coin = coin.lower()
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    inv = data[uid]["investments"]
    if coin not in inv or inv[coin] <= 0:
        return await ctx.send("❌ You have no investment in that coin.")
    invested_amount = inv[coin]
    current_price = CRYPTOCURRENCIES[coin]["price"]
    # Calculate returns: current price / base price (assumed base 1 for simplicity)
    # To keep simple, payout = invested_amount * (current_price / base_price)
    # We'll store base_price as 1 for all coins, so returns = invested_amount * current_price
    returns = int(invested_amount * current_price / max(1, CRYPTOCURRENCIES[coin]["price"]))
    # Simplify: just return invested_amount + a small gain/loss based on price movement
    returns = int(invested_amount * (random.uniform(0.8, 1.2)))  # random 80-120%
    data[uid]["bal"] += returns
    inv[coin] = 0
    save_data(data)
    await ctx.send(f"💰 Cashed out investment in {coin} for {returns} coins.")

@bot.command()
async def achievements(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    achs = data[uid]["achievements"]
    if not achs:
        return await ctx.send("🏆 You have no achievements yet.")
    msg = "**🏆 Achievements:**\n"
    for a in achs:
        msg += f"- {ACHIEVEMENTS[a]['desc']}\n"
    await ctx.send(msg)

@bot.command()
async def job(ctx, action: str = None):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]
    if action is None:
        job = user["job"]
        if not job:
            return await ctx.send("❌ You have no job. Use `!job list` to see jobs or `!job pick <job>` to choose.")
        lvl = user["job_level"]
        exp = user["job_exp"]
        return await ctx.send(f"💼 Job: {job} {JOBS[job]['emoji']} | Level: {lvl} | EXP: {exp}/1000")
    parts = action.split()
    if action == "list":
        msg = "**Available jobs:**\n"
        for j, info in JOBS.items():
            msg += f"- `{j}` {info['emoji']} (earnings increase with level)\n"
        return await ctx.send(msg)
    if action.startswith("pick"):
        job_name = action[5:].strip().lower()
        if job_name not in JOBS:
            return await ctx.send("❌ Job not found.")
        user["job"] = job_name
        user["job_level"] = 1
        user["job_exp"] = 0
        save_data(data)
        return await ctx.send(f"✅ You picked the job: {job_name} {JOBS[job_name]['emoji']}")

@bot.command()
async def quests(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    quests = data[uid]["quests"]
    msg = "**🎯 Daily Quests:**\n"
    # example quest: work 1 time, buy crypto 3 times, rob once
    defaults = {
        "work": {"desc": "Work once", "goal": 1},
        "buy_crypto": {"desc": "Buy crypto 3 times", "goal": 3},
        "rob": {"desc": "Rob once", "goal": 1},
    }
    for q, info in defaults.items():
        progress = quests.get(q, 0)
        done = progress >= info["goal"]
        msg += f"- {info['desc']}: {progress}/{info['goal']} {'✅' if done else ''}\n"
    await ctx.send(msg)

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")

# --- Admin commands ---

@bot.command()
@commands.is_owner()
async def resetdata(ctx):
    with open(DATA_FILE, "w") as f:
        f.write("{}")
    await ctx.send("⚠️ All data reset.")

@bot.command()
@commands.is_owner()
async def resetcooldowns(ctx, user: discord.User = None):
    data = load_data()
    if user:
        uid = str(user.id)
        if uid in data:
            data[uid]["daily"] = None
            data[uid]["work"] = None
            data[uid]["rob_cooldown"] = None
            save_data(data)
            await ctx.send(f"✅ Reset cooldowns for {user}.")
        else:
            await ctx.send("❌ User not found in data.")
    else:
        for uid in data:
            data[uid]["daily"] = None
            data[uid]["work"] = None
            data[uid]["rob_cooldown"] = None
        save_data(data)
        await ctx.send("✅ Reset cooldowns for all users.")

# --- Add basic help override for new commands ---

@bot.command()
async def help(ctx):
    msg = """
**Commands:**
`!bal` - Show your balance and stats
`!daily` - Collect daily reward
`!work` - Work for coins (boosters reduce cooldown)
`!lootbox` - Open a lootbox (crypto or booster)
`!boosters` - Show your work boosters
`!rob @user` - Try to rob another user (15 min cooldown)
`!shop` - Show crypto shop and prices
`!buy <crypto> [amount]` - Buy crypto (default 1)
`!sell <crypto> [amount]` - Sell crypto from inventory
`!invest <crypto> <amount>` - Invest coins in crypto
`!cashout <crypto>` - Cash out investment (profit/loss)
`!slots <bet>` - Play slot machine game
`!achievements` - Show your achievements
`!job [list|pick <job>]` - Job system
`!quests` - Show daily quests
`!inv` - Show your inventory
`!ping` - Ping the bot
**Admin commands:** `!resetdata`, `!resetcooldowns [user]` (owner only)
"""
    await ctx.send(msg)

# --- Run bot ---

if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN:
        print("Error: DISCORD_TOKEN environment variable not set.")
        exit(1)
    bot.run(TOKEN)
