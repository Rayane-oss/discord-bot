import discord
from discord.ext import commands
import os
import random  # Move import here

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")

@bot.command()
async def joke(ctx):
    jokes = [
        "Why don’t scientists trust atoms? Because they make up everything!",
        "I told my computer I needed a break, and it said 'No problem, I’ll go to sleep.'",
        "Why did the scarecrow win an award? Because he was outstanding in his field!"
    ]
    await ctx.send(random.choice(jokes))

@bot.command()
async def coinflip(ctx):
    outcome = random.choice(["Heads", "Tails"])
    await ctx.send(f"The coin landed on **{outcome}**!")

@bot.command()
async def roll(ctx, sides: int = 6):
    """Roll a dice with a specified number of sides (default 6)."""
    result = random.randint(1, sides)
    await ctx.send(f"🎲 You rolled a **{result}** on a {sides}-sided dice!")

@bot.command()
async def eightball(ctx, *, question):
    responses = [
        "It is certain.",
        "Without a doubt.",
        "You may rely on it.",
        "Ask again later.",
        "Better not tell you now.",
        "Don't count on it.",
        "My reply is no.",
        "Very doubtful."
    ]
    answer = random.choice(responses)
    await ctx.send(f"🎱 Question: {question}\nAnswer: {answer}")

bot.run(os.environ["TOKEN"])
