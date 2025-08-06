
import discord
from discord.ext import commands, tasks
import os, random, json
from datetime import datetime, timedelta

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
DATA = "economy.json"
MAX_BET = 250_000
CD = 2400  # 40 minutes cooldown

CRYPTOS = {
    "BTC": {"price": 30000, "desc": "Bitcoin"},
    "ETH": {"price": 2000, "desc": "Ethereum"},
    "DOGE": {"price": 0.1, "desc": "Dogecoin"},
    "XRP": {"price": 0.5, "desc": "Ripple"},
    "SOL": {"price": 25, "desc": "Solana"},
}

def load():
    try:
        with open(DATA) as f: return json.load(f)
    except: return {}

def save(data):
    with open(DATA, "w") as f: json.dump(data, f, indent=2)

def ensure(data, uid):
    if uid not in data:
        data[uid] = {"bal": 1000, "exp": 0, "lvl": 1, "daily": None, "work": None, "inv": {}}

def cd_left(last):
    if not last: return 0
    diff = (datetime.utcnow() - datetime.fromisoformat(last)).total_seconds()
    return max(0, CD - diff)

def add_exp(user, amt):
    user["exp"] += amt
    while user["exp"] >= 1000:
        user["exp"] -= 1000
        user["lvl"] += 1

@tasks.loop(hours=1)
async def update_crypto_prices():
    for sym in CRYPTOS:
        base = CRYPTOS[sym]["price"]
        fluctuation = base * random.uniform(-0.15, 0.25)
        CRYPTOS[sym]["price"] = round(max(0.01, base + fluctuation), 2)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    update_crypto_prices.start()

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")

@bot.command()
async def shop(ctx):
    msg = "**🪙 Crypto Shop (prices update hourly):**\n"
    for sym, data in CRYPTOS.items():
        msg += f"`{sym}`: ${data['price']} — {data['desc']}\n"
    await ctx.send(msg)

@bot.command(name="hr")
async def horse_race(ctx, bet: int, horse: int):
    data = load()
    uid = str(ctx.author.id)
    ensure(data, uid)
    
    if bet <= 0 or bet > MAX_BET:
        await ctx.send(f"❌ Bet must be between 1 and {MAX_BET} coins.")
        return
    if data[uid]["bal"] < bet:
        await ctx.send("❌ You don't have enough coins.")
        return
    if not 1 <= horse <= 5:
        await ctx.send("❌ Choose a horse number between 1 and 5.")
        return

    track_length = 20
    positions = [0]*5  # all horses start at position 0
    horse_emoji = "🏇"
    finish_line = track_length

    msg_text = "🐎 **Horse Race!** 🐎\n"
    msg_text += f"Bet: {bet} coins on horse #{horse}\n"
    msg_text += "First horse to reach the finish line wins!\n\n"

    def render_race():
        lines = []
        for i, pos in enumerate(positions, start=1):
            line = f"Horse {i}: " + "-"*pos + horse_emoji + "-"*(track_length - pos)
            lines.append(line)
        return "\n".join(lines)

    msg_text += render_race()

    race_msg = await ctx.send(msg_text)

    winner = None
    while not winner:
        await asyncio.sleep(1.2)  # pause between updates

        # Move horses randomly forward 0 or 1 step (weighted to sometimes 0)
        for i in range(5):
            move = random.choices([0,1], weights=[0.3,0.7])[0]
            positions[i] = min(finish_line, positions[i] + move)
            if positions[i] >= finish_line:
                winner = i + 1  # horse number (1-indexed)
                break

        # Edit message with new race state
        new_text = "🐎 **Horse Race!** 🐎\n"
        new_text += f"Bet: {bet} coins on horse #{horse}\n"
        new_text += "First horse to reach the finish line wins!\n\n"
        new_text += render_race()

        await race_msg.edit(content=new_text)

    # Resolve bet
    if winner == horse:
        winnings = bet * 3
        data[uid]["bal"] += winnings
        add_exp(data[uid], 60)
        result_msg = f"🎉 Your horse #{winner} won! You win {winnings} coins!"
    else:
        data[uid]["bal"] -= bet
        add_exp(data[uid], 15)
        result_msg = f"💀 Your horse #{horse} lost. The winner was horse #{winner}. You lost {bet} coins."

    save(data)
    await ctx.send(result_msg)

