import discord
from discord.ext import commands, tasks
import os, random, json, asyncio
from datetime import datetime, timedelta

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# Use Railway volume path for persistent storage, fallback to current dir
DATA_FILE = os.getenv("VOLUME_PATH", ".") + "/economy.json"
MAX_BET = 250_000
COOLDOWN_SECONDS = 40 * 60  # 40 minutes cooldown for daily/work

# Initial crypto shop list
CRYPTOCURRENCIES = {
    "bitcoin": {"price": 50000, "desc": "BTC - Most popular crypto"},
    "ethereum": {"price": 3200, "desc": "ETH - Smart contracts"},
    "dogecoin": {"price": 0.3, "desc": "DOGE - Meme coin"},
    "litecoin": {"price": 180, "desc": "LTC - Faster Bitcoin"},
    "ripple": {"price": 1, "desc": "XRP - Bank payments"},
}

# Data helpers
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
            "inv": {}
        }

def cooldown_left(last_time):
    if not last_time:
        return 0
    delta = (datetime.utcnow() - datetime.fromisoformat(last_time)).total_seconds()
    return max(0, COOLDOWN_SECONDS - delta)

def add_exp(user, amount):
    user["exp"] += amount
    while user["exp"] >= 1000:
        user["exp"] -= 1000
        user["lvl"] += 1

# Update crypto prices hourly with random fluctuations
@tasks.loop(hours=1)
async def update_crypto_prices():
    for crypto in CRYPTOCURRENCIES:
        base_price = CRYPTOCURRENCIES[crypto]["price"]
        # Change price by +/- up to 5%
        change_percent = random.uniform(-0.05, 0.05)
        new_price = base_price * (1 + change_percent)
        CRYPTOCURRENCIES[crypto]["price"] = round(max(new_price, 0.01), 2)
    print("Updated crypto prices:", {k: v['price'] for k, v in CRYPTOCURRENCIES.items()})

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    update_crypto_prices.start()

# --- Economy commands ---

@bot.command()
async def bal(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    user = data[uid]
    await ctx.send(f"💰 Balance: {user['bal']} | Level: {user['lvl']} | EXP: {user['exp']}/1000")

@bot.command()
async def daily(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    left = cooldown_left(data[uid]["daily"])
    if left > 0:
        await ctx.send(f"🕒 You have to wait {int(left // 60)}m {int(left % 60)}s for daily reward.")
        return
    reward = random.randint(1500, 3500)
    data[uid]["bal"] += reward
    data[uid]["daily"] = datetime.utcnow().isoformat()
    add_exp(data[uid], 60)
    save_data(data)
    await ctx.send(f"✅ You collected your daily reward: +{reward} coins, +60 EXP")

@bot.command()
async def work(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    left = cooldown_left(data[uid]["work"])
    if left > 0:
        await ctx.send(f"🕒 You need to wait {int(left // 60)}m {int(left % 60)}s before working again.")
        return
    reward = random.randint(1100, 2500)
    data[uid]["bal"] += reward
    data[uid]["work"] = datetime.utcnow().isoformat()
    add_exp(data[uid], 45)
    save_data(data)
    await ctx.send(f"💼 You worked and earned {reward} coins, +45 EXP")

@bot.command()
async def inv(ctx):
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    inv = data[uid]["inv"]
    if not inv:
        await ctx.send("🎒 Your inventory is empty.")
        return
    msg = "**🎒 Inventory:**\n"
    for item, amount in inv.items():
        if amount > 0:
            msg += f"{item} x{amount}\n"
    await ctx.send(msg)

# --- Shop with cryptocurrencies ---

@bot.command()
async def shop(ctx):
    msg = "**🪙 Crypto Shop (prices update hourly):**\n"
    for crypto, info in CRYPTOCURRENCIES.items():
        price_str = f"{info['price']:,}" if info['price'] >= 1 else str(info['price'])
        msg += f"`{crypto}`: {price_str} coins — {info['desc']}\n"
    await ctx.send(msg)

@bot.command()
async def buy(ctx, item: str):
    data = load_data()
    uid = str(ctx.author.id)
    item = item.lower()
    ensure_user(data, uid)
    if item not in CRYPTOCURRENCIES:
        await ctx.send("❌ That crypto is not available in the shop.")
        return
    cost = int(CRYPTOCURRENCIES[item]["price"])
    if data[uid]["bal"] < cost:
        await ctx.send(f"❌ You don't have enough coins to buy {item} ({cost} coins).")
        return
    data[uid]["bal"] -= cost
    inv = data[uid]["inv"]
    inv[item] = inv.get(item, 0) + 1
    add_exp(data[uid], 20)
    save_data(data)
    await ctx.send(f"✅ You bought 1 {item} for {cost} coins.")

@bot.command()
async def sell(ctx, item: str):
    data = load_data()
    uid = str(ctx.author.id)
    item = item.lower()
    ensure_user(data, uid)
    inv = data[uid]["inv"]
    if item not in inv or inv[item] < 1:
        await ctx.send("❌ You don't own this item to sell.")
        return
    price = int(CRYPTOCURRENCIES.get(item, {"price":0})["price"] * 0.6)
    inv[item] -= 1
    data[uid]["bal"] += price
    save_data(data)
    await ctx.send(f"✅ You sold 1 {item} for {price} coins.")

# --- Coinflip game ---

@bot.command()
async def cf(ctx, amount: int, guess: str):
    guess = guess.lower()
    if guess not in ("heads", "tails"):
        await ctx.send("❌ Guess must be 'heads' or 'tails'.")
        return
    if amount <= 0 or amount > MAX_BET:
        await ctx.send(f"❌ Bet must be between 1 and {MAX_BET}.")
        return

    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    if data[uid]["bal"] < amount:
        await ctx.send("❌ You don't have enough coins for that bet.")
        return

    result = random.choice(["heads", "tails"])
    if guess == result:
        win = int(amount * 0.85)
        data[uid]["bal"] += win
        add_exp(data[uid], 30)
        await ctx.send(f"🎉 You won {win} coins! Result: {result}")
    else:
        data[uid]["bal"] -= amount
        add_exp(data[uid], 10)
        await ctx.send(f"💀 You lost {amount} coins. Result: {result}")
    save_data(data)

# --- Blackjack game with reaction controls ---

@bot.command()
async def bj(ctx, bet: int):
    if bet <= 0 or bet > MAX_BET:
        await ctx.send(f"❌ Bet must be between 1 and {MAX_BET}.")
        return
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    if data[uid]["bal"] < bet:
        await ctx.send("❌ You don't have enough coins for that bet.")
        return

    # Helper functions
    def deal_card():
        cards = [2,3,4,5,6,7,8,9,10,10,10,10,11]
        return random.choice(cards)

    def hand_value(hand):
        val = sum(hand)
        aces = hand.count(11)
        while val > 21 and aces:
            val -= 10
            aces -= 1
        return val

    player_hand = [deal_card(), deal_card()]
    dealer_hand = [deal_card(), deal_card()]

    def format_hand(hand):
        return ", ".join(str(card) for card in hand)

    def get_embed(title, desc, footer):
        embed = discord.Embed(title=title, description=desc, color=0x2ecc71)
        embed.set_footer(text=footer)
        return embed

    msg = await ctx.send(embed=get_embed(
        "Blackjack",
        f"Your hand: {format_hand(player_hand)} (Total: {hand_value(player_hand)})\nDealer shows: {dealer_hand[0]}",
        "React with 🖐 (stand) or ✋ (hit)"
    ))

    # Add reaction controls
    await msg.add_reaction("✋")  # hit
    await msg.add_reaction("🖐")  # stand

    def check(reaction, user):
        return (
            user == ctx.author
            and reaction.message.id == msg.id
            and str(reaction.emoji) in ["✋", "🖐"]
        )

    while True:
        try:
            reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send("⏰ Timeout! Game ended.")
            return

        if str(reaction.emoji) == "✋":  # hit
            player_hand.append(deal_card())
            val = hand_value(player_hand)
            await msg.edit(embed=get_embed(
                "Blackjack",
                f"You drew a card: {player_hand[-1]}\nYour hand: {format_hand(player_hand)} (Total: {val})\nDealer shows: {dealer_hand[0]}",
                "React with 🖐 (stand) or ✋ (hit)"
            ))
            if val > 21:
                data[uid]["bal"] -= bet
                add_exp(data[uid], 10)
                save_data(data)
                await ctx.send("💥 Bust! You went over 21. You lose.")
                return
        else:  # stand
            break

    # Dealer turn
    while hand_value(dealer_hand) < 17:
        dealer_hand.append(deal_card())

    p_val = hand_value(player_hand)
    d_val = hand_value(dealer_hand)

    await msg.edit(embed=get_embed(
        "Blackjack - Result",
        f"Your hand: {format_hand(player_hand)} (Total: {p_val})\nDealer's hand: {format_hand(dealer_hand)} (Total: {d_val})",
        ""
    ))

    if d_val > 21 or p_val > d_val:
        win_amount = int(bet * 1.8)
        data[uid]["bal"] += win_amount
        add_exp(data[uid], 50)
        await ctx.send(f"🎉 You win {win_amount} coins!")
    elif p_val == d_val:
        await ctx.send("🤝 Push! It's a tie. Your bet is returned.")
    else:
        data[uid]["bal"] -= bet
        add_exp(data[uid], 10)
        await ctx.send("💀 Dealer wins. You lose.")
    save_data(data)

# --- Cups game with reaction controls ---

@bot.command()
async def cups(ctx, bet: int):
    if bet <= 0 or bet > MAX_BET:
        await ctx.send(f"❌ Bet must be between 1 and {MAX_BET}.")
        return
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    if data[uid]["bal"] < bet:
        await ctx.send("❌ You don't have enough coins for that bet.")
        return

    cups_list = ["🥤", "🥤", "🥤"]
    prize_cup = random.randint(1, 3)

    display_msg = "Guess the cup with the prize! React with 1️⃣, 2️⃣, or 3️⃣.\n"
    display_msg += "1️⃣ 2️⃣ 3️⃣\n"
    display_msg += "🥤 🥤 🥤"

    msg = await ctx.send(display_msg)
    reactions = ["1️⃣", "2️⃣", "3️⃣"]

    for r in reactions:
        await msg.add_reaction(r)

    def check(reaction, user):
        return user == ctx.author and reaction.message.id == msg.id and str(reaction.emoji) in reactions

    try:
        reaction, user = await bot.wait_for("reaction_add", timeout=30, check=check)
    except asyncio.TimeoutError:
        await ctx.send("⏰ Timeout! Game cancelled.")
        return

    guess = reactions.index(str(reaction.emoji)) + 1
    # Shuffle prize cup position
    positions = [1, 2, 3]
    random.shuffle(positions)
    real_pos = positions.index(prize_cup) + 1

    if guess == real_pos:
        winnings = int(bet * 2.5)
        data[uid]["bal"] += winnings
        add_exp(data[uid], 50)
        await ctx.send(f"🎉 Correct! The prize was under cup {real_pos}. You win {winnings} coins!")
    else:
        data[uid]["bal"] -= bet
        add_exp(data[uid], 10)
        await ctx.send(f"💀 Wrong! The prize was under cup {real_pos}. You lost {bet} coins.")
    save_data(data)

# --- Horse racing game ---

@bot.command()
async def hr(ctx, bet: int):
    if bet <= 0 or bet > MAX_BET:
        await ctx.send(f"❌ Bet must be between 1 and {MAX_BET}.")
        return
    data = load_data()
    uid = str(ctx.author.id)
    ensure_user(data, uid)
    if data[uid]["bal"] < bet:
        await ctx.send("❌ You don't have enough coins for that bet.")
        return

    horses = {
        1: {"name": "Thunder", "progress": 0},
        2: {"name": "Blaze", "progress": 0},
        3: {"name": "Rocket", "progress": 0},
        4: {"name": "Shadow", "progress": 0},
        5: {"name": "Comet", "progress": 0},
    }

    track_length = 20  # number of emoji steps

    msg = await ctx.send("🐎 Horse race starting soon...")

    await asyncio.sleep(1)
    await msg.edit(content="🐎 Horse race started!")

    def format_track(progress):
        track = "⬜" * progress + "🏇" + "⬛" * (track_length - progress)
        return track

    winner = None
    while not winner:
        for h_id in horses:
            # Each horse moves 0-3 steps per iteration, weighted to favor slower movement mostly
            step = random.choices([0,1,2,3], weights=[20, 50, 20, 10])[0]
            horses[h_id]["progress"] = min(track_length, horses[h_id]["progress"] + step)
            if horses[h_id]["progress"] >= track_length:
                winner = h_id
                break
        # Build race status message
        race_status = "**🏇 Horse Race 🏇**\n"
        for h_id, h in horses.items():
            race_status += f"{h['name']}: {format_track(h['progress'])}\n"
        await msg.edit(content=race_status)
        await asyncio.sleep(1.5)

    winner_name = horses[winner]["name"]

    # For now user always bets on "Thunder" horse #1
    if winner_name == "Thunder":
        winnings = int(bet * 3)
        data[uid]["bal"] += winnings
        await ctx.send(f"🎉 Your horse Thunder won! You win {winnings} coins!")
    else:
        data[uid]["bal"] -= bet
        await ctx.send(f"💀 Your horse lost. Winner: {winner_name}. You lost {bet} coins.")
    add_exp(data[uid], 50)
    save_data(data)

# --- Ping command ---

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")

# --- Run bot ---

if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN:
        print("Error: DISCORD_TOKEN environment variable not set.")
        exit(1)
    bot.run(TOKEN)
