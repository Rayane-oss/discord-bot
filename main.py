import discord
from discord.ext import commands, tasks
import os, json, random, asyncio
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "economy.json"

# Load/save economy data
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

# Shop items base prices and description
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
    while user["exp"] >= user["level"] * 100:
        user["exp"] -= user["level"] * 100
        user["level"] += 1

# Cooldowns
cooldowns = {
    "daily": {},
    "gamble": {}
}

MAX_GAMBLE = 250_000

def is_on_cooldown(user_id, cmd):
    now = datetime.utcnow()
    last = cooldowns[cmd].get(user_id)
    if last is None:
        return False
    return (now - last) < timedelta(minutes=40)

def set_cooldown(user_id, cmd):
    cooldowns[cmd][user_id] = datetime.utcnow()

# Bot events and commands
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} - Ready!")
    update_shop_prices()
    refresh_shop_prices.start()

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
        await ctx.send(f"⏳ {ctx.author.mention}, daily reward on cooldown. Wait 40 minutes.")
        return

    income = random.randint(5000, 10000)
    data[str(ctx.author.id)]["balance"] += income
    set_cooldown(ctx.author.id, "daily")
    add_exp(data, ctx.author.id, 50)
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
        await ctx.send(f"❌ {ctx.author.mention}, insufficient coins. Cost: {cost}")
        return

    data[str(ctx.author.id)]["balance"] -= cost
    inv = data[str(ctx.author.id)]["inventory"]
    inv[item] = inv.get(item, 0) + amount
    add_exp(data, ctx.author.id, 20 * amount)
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
    add_exp(data, ctx.author.id, 10 * amount)
    save_data(data)
    await ctx.send(f"💵 {ctx.author.mention} sold {amount}x {item} for {price} coins.")

# Gambling commands

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

    outcome = random.choices(["win", "lose"], weights=[45, 55])[0]
    if outcome == "win":
        winnings = int(amount * random.uniform(1.5, 2))
        data[str(ctx.author.id)]["balance"] += winnings
        add_exp(data, ctx.author.id, amount//100)
        await ctx.send(f"🎉 {ctx.author.mention} won {winnings} coins on coinflip!")
    else:
        data[str(ctx.author.id)]["balance"] -= amount
        await ctx.send(f"😢 {ctx.author.mention} lost {amount} coins on coinflip.")

    set_cooldown(ctx.author.id, "gamble")
    save_data(data)

# Blackjack game
@bot.command(name="bj")
async def blackjack(ctx, bet: int):
    data = load_data()
    ensure_user(data, ctx.author.id)

    if bet <= 0 or bet > MAX_GAMBLE:
        await ctx.send(f"❌ {ctx.author.mention}, bet must be between 1 and {MAX_GAMBLE}.")
        return

    if data[str(ctx.author.id)]["balance"] < bet:
        await ctx.send(f"❌ {ctx.author.mention}, insufficient balance.")
        return

    if is_on_cooldown(ctx.author.id, "gamble"):
        await ctx.send(f"⏳ {ctx.author.mention}, gambling cooldown is 40 minutes.")
        return

    # Simple blackjack logic: player and dealer get random 1-21, player wins if higher or tie, else lose
    player_score = random.randint(15, 21)
    dealer_score = random.randint(15, 21)

    if player_score >= dealer_score:
        winnings = bet + int(bet * 0.5)
        data[str(ctx.author.id)]["balance"] += winnings
        result = f"🎉 You won! Your score: {player_score}, Dealer: {dealer_score}. You earned {winnings} coins."
        add_exp(data, ctx.author.id, bet//50)
    else:
        data[str(ctx.author.id)]["balance"] -= bet
        result = f"😢 You lost! Your score: {player_score}, Dealer: {dealer_score}. Lost {bet} coins."

    set_cooldown(ctx.author.id, "gamble")
    save_data(data)
    await ctx.send(f"{ctx.author.mention} {result}")

# Plinko game with emoji
@bot.command(name="pl")
async def plinko(ctx, bet: int):
    data = load_data()
    ensure_user(data, ctx.author.id)

    if bet <= 0 or bet > MAX_GAMBLE:
        await ctx.send(f"❌ {ctx.author.mention}, bet must be between 1 and {MAX_GAMBLE}.")
        return

    if data[str(ctx.author.id)]["balance"] < bet:
        await ctx.send(f"❌ {ctx.author.mention}, insufficient balance.")
        return

    if is_on_cooldown(ctx.author.id, "gamble"):
        await ctx.send(f"⏳ {ctx.author.mention}, gambling cooldown is 40 minutes.")
        return

    data[str(ctx.author.id)]["balance"] -= bet
    save_data(data)

    # Simulate plinko drop: random multiplier from 0 to 3x
    multiplier = random.choices([0, 0.5, 1, 1.5, 2, 3], weights=[15, 20, 30, 20, 10, 5])[0]
    winnings = int(bet * multiplier)

    if winnings > 0:
        data[str(ctx.author.id)]["balance"] += winnings
        add_exp(data, ctx.author.id, winnings//100)
        save_data(data)
        await ctx.send(f"🎲 {ctx.author.mention} plinko win! Multiplier: x{multiplier}. You won {winnings} coins!")
    else:
        await ctx.send(f"😢 {ctx.author.mention} plinko loss! You won nothing this time.")

    set_cooldown(ctx.author.id, "gamble")

# Cups game
@bot.command(name="cups")
async def cups(ctx):
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content in ["1", "2", "3"]

    cup_positions = [":cup_with_straw:", ":cup_with_straw:", ":cup_with_straw:"]
    prize_cup = random.randint(0, 2)

    msg = await ctx.send(f"Guess which cup has the prize? Type 1, 2, or 3.\n{cup_positions[0]}  {cup_positions[1]}  {cup_positions[2]}")

    try:
        guess = await bot.wait_for("message", check=check, timeout=20)
    except asyncio.TimeoutError:
        return await ctx.send(f"⌛ {ctx.author.mention} you took too long!")

    guess_index = int(guess.content) - 1
    if guess_index == prize_cup:
        await ctx.send(f"🎉 Correct! Cup {guess.content} had the prize!")
    else:
        await ctx.send(f"❌ Wrong! Cup {guess.content} was empty. The prize was under cup {prize_cup + 1}.")

# EXP command
@bot.command(name="xp")
async def exp(ctx):
    data = load_data()
    ensure_user(data, ctx.author.id)
    user = data[str(ctx.author.id)]
    await ctx.send(f"📊 {ctx.author.mention} — Level: {user['level']} | EXP: {user['exp']}")

# Help command
@bot.command(name="h")
async def help_command(ctx):
    help_text = """
**Commands:**
!bal - Check balance
!d - Daily reward (40m cooldown)
!shop - Show shop
!buy <item> <amount> - Buy items
!sell <item> <amount> - Sell items
!inv - Show inventory
!cf <amount> - Coinflip gamble (max 250k)
!bj <amount> - Blackjack gamble (max 250k)
!pl <amount> - Plinko gamble (max 250k)
!cups - Cups guessing game
!xp - Show level and EXP
!h - Show this help
"""
    await ctx.send(help_text)

# Run bot
if __name__ == "__main__":
    token = os.environ.get("TOKEN")
    if not token:
        print("ERROR: TOKEN env var missing!")
    else:
        bot.run(token)
