MAX_BET = 250_000

# Add EXP and level helper functions
def add_exp(data, user_id, amount):
    user = data[str(user_id)]
    user.setdefault("exp", 0)
    user.setdefault("level", 1)
    user["exp"] += amount

    # Level up for every 1000 EXP
    while user["exp"] >= 1000:
        user["exp"] -= 1000
        user["level"] += 1

@bot.command(name="bal")
async def balance(ctx):
    data = load_data()
    user_id = ctx.author.id
    ensure_user(data, user_id)
    user = data[str(user_id)]
    bal = user["balance"]
    lvl = user.get("level", 1)
    exp = user.get("exp", 0)
    await ctx.send(f"{ctx.author.mention}, Balance: **{bal} coins**, Level: **{lvl}**, EXP: **{exp}/1000**")

# Updated gambling commands with max bet and harder odds

@bot.command(name="cf")
async def coinflip(ctx, amount: int, choice: str):
    if amount > MAX_BET:
        await ctx.send(f"❌ Max bet is {MAX_BET} coins.")
        return

    data = load_data()
    user_id = ctx.author.id
    ensure_user(data, user_id)
    choice = choice.lower()

    if choice not in ["heads", "tails"]:
        await ctx.send("❌ Choice must be 'heads' or 'tails'.")
        return

    bal = data[str(user_id)]["balance"]
    if amount <= 0:
        await ctx.send("❌ Amount must be positive.")
        return
    if bal < amount:
        await ctx.send(f"❌ You don't have enough coins to gamble that amount. Your balance: {bal} coins.")
        return

    # Harder win chance: 45%
    outcome = random.choices(["heads", "tails"], weights=[45, 55])[0]
    if choice == outcome:
        winnings = int(amount * 0.9)  # Slightly less than double
        data[str(user_id)]["balance"] += winnings
        add_exp(data, user_id, 30)
        await ctx.send(f"🎉 It's {outcome}! You won **{winnings} coins** and gained 30 EXP!")
    else:
        data[str(user_id)]["balance"] -= amount
        add_exp(data, user_id, 10)
        await ctx.send(f"😢 It's {outcome}. You lost **{amount} coins** but gained 10 EXP.")

    save_data(data)

@bot.command(name="bj")
async def blackjack(ctx, amount: int):
    if amount > MAX_BET:
        await ctx.send(f"❌ Max bet is {MAX_BET} coins.")
        return

    data = load_data()
    user_id = ctx.author.id
    ensure_user(data, user_id)

    bal = data[str(user_id)]["balance"]
    if amount <= 0:
        await ctx.send("❌ Bet amount must be positive.")
        return
    if bal < amount:
        await ctx.send(f"❌ You don't have enough coins to bet that amount. Your balance: {bal} coins.")
        return

    await ctx.send(f"♠️ Starting Blackjack for {ctx.author.mention} with bet **{amount} coins**!")

    def draw_card():
        cards = list(range(2, 11)) + [10, 10, 10, 11]
        return random.choice(cards)

    def score(hand):
        total = sum(hand)
        aces = hand.count(11)
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total

    player_hand = [draw_card(), draw_card()]
    dealer_hand = [draw_card(), draw_card()]

    await ctx.send(f"Your hand: {player_hand} (score: {score(player_hand)})")
    await ctx.send(f"Dealer shows: {dealer_hand[0]} and ?")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["hit", "stand"]

    while True:
        await ctx.send("Type 'hit' to draw another card, or 'stand' to hold.")
        try:
            msg = await bot.wait_for("message", check=check, timeout=30)
        except asyncio.TimeoutError:
            await ctx.send("⏰ Timeout! Game ended.")
            return

        if msg.content.lower() == "hit":
            player_hand.append(draw_card())
            p_score = score(player_hand)
            await ctx.send(f"You drew a card: {player_hand} (score: {p_score})")
            if p_score > 21:
                await ctx.send(f"💥 Bust! You went over 21. You lose **{amount} coins**.")
                data[str(user_id)]["balance"] -= amount
                add_exp(data, user_id, 15)
                save_data(data)
                return
        else:  # stand
            break

    d_score = score(dealer_hand)
    while d_score < 17:
        dealer_hand.append(draw_card())
        d_score = score(dealer_hand)

    await ctx.send(f"Dealer's hand: {dealer_hand} (score: {d_score})")

    p_score = score(player_hand)

    if d_score > 21 or p_score > d_score:
        await ctx.send(f"🎉 You win! You earned **{amount} coins** and 50 EXP.")
        data[str(user_id)]["balance"] += amount
        add_exp(data, user_id, 50)
    elif p_score == d_score:
        await ctx.send("🤝 It's a tie! No coins won or lost. You get 20 EXP.")
        add_exp(data, user_id, 20)
    else:
        await ctx.send(f"😢 You lose! You lost **{amount} coins** but gained 15 EXP.")
        data[str(user_id)]["balance"] -= amount
        add_exp(data, user_id, 15)

    save_data(data)

@bot.command(name="plinko")
async def plinko(ctx, amount: int):
    if amount > MAX_BET:
        await ctx.send(f"❌ Max bet is {MAX_BET} coins.")
        return

    data = load_data()
    user_id = ctx.author.id
    ensure_user(data, user_id)

    bal = data[str(user_id)]["balance"]
    if amount <= 0:
        await ctx.send("❌ Bet amount must be positive.")
        return
    if bal < amount:
        await ctx.send(f"❌ You don't have enough coins to bet that amount. Your balance: {bal} coins.")
        return

    await ctx.send(f"🎯 {ctx.author.mention} is playing Plinko with **{amount} coins** bet!")

    # Reduced payouts and some zeros to increase risk
    slots = list(range(9))
    payouts = [0, int(amount*0.25), int(amount*0.5), int(amount), 0, int(amount*1.5), int(amount*0.5), 0, 0]

    # Show "dropping ball" effect
    await ctx.send("Dropping ball... ⚪️⚪️⚪️⚪️⚪️")
    await asyncio.sleep(2)

    slot = random.choice(slots)
    payout = payouts[slot]

    if payout == 0:
        await ctx.send(f"😢 The ball landed on slot {slot} — You lost your bet of **{amount} coins** but gained 10 EXP.")
        data[str(user_id)]["balance"] -= amount
        add_exp(data, user_id, 10)
    else:
        await ctx.send(f"🎉 The ball landed on slot {slot} — You won **{payout} coins** and gained 40 EXP!")
        data[str(user_id)]["balance"] += payout
        add_exp(data, user_id, 40)

    save_data(data)

# Cups game doesn't involve betting or coins, so just EXP on win/loss
@bot.command(name="cups")
async def cups(ctx):
    cups = ["🥤", "🥤", "🥤"]
    ball_pos = random.randint(0, 2)

    msg = "Here are 3 cups:\n"
    msg += "1️⃣ 2️⃣ 3️⃣\n"
    msg += "".join(cups) + "\n"
    msg += "I placed a ball under one cup. Watch me swap!\n"

    await ctx.send(msg)

    positions = [0, 1, 2]
    for _ in range(5):
        i, j = random.sample(positions, 2)
        cups[i], cups[j] = cups[j], cups[i]
        await ctx.send(" ".join(cups))
        await asyncio.sleep(1)

    await ctx.send(f"{ctx.author.mention}, guess which cup has the ball! Type 1, 2 or 3.")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content in ["1", "2", "3"]

    try:
        guess_msg = await bot.wait_for("message", check=check, timeout=20)
        guess = int(guess_msg.content) - 1
    except asyncio.TimeoutError:
        await ctx.send("⏰ Time's up! Game over.")
        return

    data = load_data()
    user_id = ctx.author.id
    ensure_user(data, user_id)

    if cups[guess] == "🥤" and guess == ball_pos:
        await ctx.send(f"🎉 You guessed right! The ball was under cup {guess+1}. You earned 20 EXP!")
        add_exp(data, user_id, 20)
    else:
        ball_cup = cups.index("🥤") + 1 if "🥤" in cups else ball_pos + 1
        await ctx.send(f"😢 Wrong! The ball was under cup {ball_cup}. You gained 5 EXP.")
        add_exp(data, user_id, 5)

    save_data(data)
