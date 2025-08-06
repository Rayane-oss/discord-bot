import discord
from discord.ext import commands, tasks
import os, json, random, asyncio
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "economy.json"

# Load/save data helpers
def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def ensure_user(data, uid):
    if str(uid) not in data:
        data[str(uid)] = {
            "balance": 0,
            "last_daily": None,
            "inventory": {},
            "exp": 0,
            "level": 1
        }

# Dynamic shop items with prices updated every hour
SHOP_ITEMS_BASE = {
    "sword": {"base_price": 500, "desc": "A shiny sword."},
    "shield": {"base_price": 300, "desc": "A sturdy shield."},
    "potion": {"base_price": 150, "desc": "Heals you."},
    "helmet": {"base_price": 400, "desc": "Protects your head."},
    "boots": {"base_price": 350, "desc": "Increases speed."}
}

shop_prices = {}

def update_shop_prices():
    for item, info in SHOP_ITEMS_BASE.items():
        # Simulate price changes: base_price ± up to 30%
        variation = random.uniform(0.7, 1.3)
        price = max(1, int(info["base_price"] * variation))
        shop_prices[item] = price

@tasks.loop(hours=1)
async def refresh_shop_prices():
    update_shop_prices()
    print("Shop prices updated:", shop_prices)

# EXP and leveling
def add_exp(user_data, uid, amount=10):
    user = user_data[str(uid)]
    user["exp"] += amount
    # Level up every 100 exp
    while user["exp"] >= user["level"] * 100:
        user["exp"] -= user["level"] * 100
        user["level"] += 1

# Cooldown dicts to store last used time
cooldowns = {
    "daily": {},
    "gamble": {}
}

# Max gamble amount
MAX_GAMBLE = 250_000

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} - Bot ready!")
    update_shop_prices()
    refresh_shop_prices.start()

# Helper cooldown check (40 minutes)
def is_on_cooldown(user_id, cmd):
    now = datetime.utcnow()
    last = cooldowns[cmd].get(user_id)
    if last is None:
        return False
    return (now - last) < timedelta(minutes=40)

def set_cooldown(user_id, cmd):
    cooldowns[cmd][user_id] = datetime.utcnow()

# Commands

@bot.command(name="bal")
async def balance(ctx):
    data = load_data()
    ensure_user(data, ctx.author.id)
    bal = data[str(ctx.author.id)]["balance"]
    await ctx.send(f"💰 {ctx.author.mention}, your balance is **{bal}** coins.")

@bot.command(name="d")
async def daily(ctx):
    data = load_data()
    ensure_user(data, ctx.author.id)

    if is_on_cooldown(ctx.author.id, "daily"):
        await ctx.send(f"⏳ {ctx.author.mention}, daily reward is on cooldown. Wait 40 minutes.")
        return

    income = random.randint(5000, 10000)  # Increased income
    data[str(ctx.author.id)]["balance"] += income
    set_cooldown(ctx.author.id, "daily")
    add_exp(data, ctx.author.id, amount=50)
    save_data(data)
    await ctx.send(f"🎉 {ctx.author.mention} claimed **{income}** coins as daily reward!")

@bot.command(name="shop")
async def shop(ctx):
    embed = discord.Embed(title="🛒 Shop", color=discord.Color.blue())
    for item, price in shop_prices.items():
        desc = SHOP_ITEMS_BASE[item]["desc"]
        embed.add_field(name=f"{item} - {price} coins", value=desc, inline=False)
    await ctx.send(embed=embed)

@bot.command(name="buy")
async def buy(ctx, item: str, amount: int = 1):
    data = load_data()
    ensure_user(data, ctx.author.id)

    item = item.lower()
    if item not in shop_prices:
        await ctx.send(f"❌ {ctx.author.mention}, item `{item}` not found.")
        return

    cost = shop_prices[item] * amount
    if data[str(ctx.author.id)]["balance"] < cost:
        await ctx.send(f"❌ {ctx.author.mention}, you don't have enough coins for {amount}x {item}. Cost: {cost}")
        return

    data[str(ctx.author.id)]["balance"] -= cost
    inv = data[str(ctx.author.id)]["inventory"]
    inv[item] = inv.get(item, 0) + amount
    add_exp(data, ctx.author.id, amount=20 * amount)
    save_data(data)

    await ctx.send(f"✅ {ctx.author.mention} bought {amount}x {item} for {cost} coins.")

@bot.command(name="inv")
async def inventory(ctx):
    data = load_data()
    ensure_user(data, ctx.author.id)
    inv = data[str(ctx.author.id)]["inventory"]
    if not inv:
        await ctx.send(f"📭 {ctx.author.mention}, your inventory is empty.")
        return

    embed = discord.Embed(title=f"{ctx.author.name}'s Inventory", color=discord.Color.green())
    for item, amt in inv.items():
        embed.add_field(name=item, value=f"Quantity: {amt}", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="sell")
async def sell(ctx, item: str, amount: int = 1):
    data = load_data()
    ensure_user(data, ctx.author.id)
    item = item.lower()
    inv = data[str(ctx.author.id)]["inventory"]
    if item not in inv or inv[item] < amount:
        await ctx.send(f"❌ {ctx.author.mention}, you don't have {amount}x {item} to sell.")
        return

    price = shop_prices.get(item, 0) * amount
    if price == 0:
        await ctx.send(f"❌ {ctx.author.mention}, item `{item}` cannot be sold.")
        return

    inv[item] -= amount
    if inv[item] <= 0:
        del inv[item]

    data[str(ctx.author.id)]["balance"] += price
    add_exp(data, ctx.author.id, amount=10 * amount)
    save_data(data)
    await ctx.send(f"💵 {ctx.author.mention} sold {amount}x {item} for {price} coins.")

# Gambling commands with max gamble and tweak odds

@bot.command(name="cf")  # coinflip
async def coinflip(ctx, amount: int):
    data = load_data()
    ensure_user(data, ctx.author.id)

    if amount <= 0 or amount > MAX_GAMBLE:
        await ctx.send(f"❌ {ctx.author.mention}, bet must be between 1 and {MAX_GAMBLE}.")
        return

    if data[str(ctx.author.id)]["balance"] < amount:
        await ctx.send(f"❌ {ctx.author.mention}, insufficient balance.")
        return

    if is_on_cooldown(ctx.author.id, "gamble"):
        await ctx.send(f"⏳ {ctx.author.mention}, gambling cooldown is 40 minutes.")
        return

    outcome = random.choices(["win", "lose"], weights=[45, 55])[0]  # tweak odds so user loses slightly more
    if outcome == "win":
        winnings = int(amount * random.uniform(1.5, 2))
        data[str(ctx.author.id)]["balance"] += winnings
        add_exp(data, ctx.author.id, amount=amount//100)
        await ctx.send(f"🎉 {ctx.author.mention} won {winnings} coins on coinflip!")
    else:
        data[str(ctx.author.id)]["balance"] -= amount
        await ctx.send(f"😢 {ctx.author.mention} lost {amount} coins on coinflip.")

    set_cooldown(ctx.author.id, "gamble")
    save_data(data)

# TODO: Blackjack, Plinko, Cups minigames (complex — can add later step by step)

# EXP and level command
@bot.command(name="xp")
async def exp(ctx):
    data = load_data()
    ensure_user(data, ctx.author.id)
    user = data[str(ctx.author.id)]
    await ctx.send(f"📊 {ctx.author.mention} — Level: {user['level']} | EXP: {user['exp']}")

# Help command override for brevity
@bot.command(name="h")
async def help_command(ctx):
    help_text = """
    Commands:
    !bal - Check balance
    !d - Daily reward (40m cooldown)
    !shop - Show shop
    !buy <item> <amount> - Buy items
    !sell <item> <amount> - Sell items
    !inv - Show inventory
    !cf <amount> - Coinflip gamble (max 250k)
    !xp - Show your level and EXP
    """
    await ctx.send(help_text)

# Run bot
if __name__ == "__main__":
    token = os.environ.get("TOKEN")
    if not token:
        print("ERROR: TOKEN env var missing!")
    else:
        bot.run(token)
