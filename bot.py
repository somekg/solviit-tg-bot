import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from database import init_db, add_member, save_snapshot, get_member, get_baseline_snapshot, get_all_members
from leetcode import fetch_leetcode_stats

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    member = get_member(user_id)

    if not member:
        await update.message.reply_text("⚠️ You are not registered yet! Use `/register <leetcode_user>` to start.", parse_mode=ParseMode.MARKDOWN)
        return

    stats = fetch_leetcode_stats(member["leetcode_username"])
    if not stats:
        await update.message.reply_text("❌ Could not fetch stats from LeetCode. Please try again shortly.")
        return

    baseline = get_baseline_snapshot(user_id) or stats
    delta_total = stats["total_solved"] - baseline["total_solved"]
    delta_easy = stats["easy_solved"] - baseline["easy_solved"]
    delta_med = stats["medium_solved"] - baseline["medium_solved"]
    delta_hard = stats["hard_solved"] - baseline["hard_solved"]
    delta_rating = round(stats["contest_rating"] - baseline["contest_rating"], 1)

    rating_delta_str = f"+{delta_rating}" if delta_rating > 0 else f"{delta_rating}"

    msg = (
        f"👤 *LeetCode Profile: {stats['username']}*\n"
        f"🏆 *Contest Rating:* {stats['contest_rating']} ({rating_delta_str} this cycle)\n\n"
        f"📊 *Lifetime Solved:* {stats['total_solved']}\n"
        f"• 🟢 Easy: {stats['easy_solved']} (+{delta_easy})\n"
        f"• 🟡 Medium: {stats['medium_solved']} (+{delta_med})\n"
        f"• 🔴 Hard: {stats['hard_solved']} (+{delta_hard})\n\n"
        f"🚀 *Progress Delta:* **+{delta_total} problems**"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    members = get_all_members()
    if not members:
        await update.message.reply_text("No club members registered yet. Be the first with `/register <handle>`!", parse_mode=ParseMode.MARKDOWN)
        return

    mode = context.args[0].lower() if context.args else "delta"
    valid_modes = {"delta", "total", "rating"}

    if mode not in valid_modes:
        await update.message.reply_text(
            "⚠️ Invalid mode. Choose from:\n"
            "• `/leaderboard` or `/leaderboard delta` (Weekly progress)\n"
            "• `/leaderboard total` (All-time solved count)\n"
            "• `/leaderboard rating` (Contest ranking)",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    await update.message.reply_text("⏳ Generating club leaderboard...", parse_mode=ParseMode.MARKDOWN)

    board_data = []
    for tg_id, lc_user, tg_name in members:
        live_stats = fetch_leetcode_stats(lc_user)
        if not live_stats:
            continue
        
        baseline = get_baseline_snapshot(tg_id) or live_stats
        delta_solved = live_stats["total_solved"] - baseline["total_solved"]
        
        board_data.append({
            "name": tg_name or lc_user,
            "handle": lc_user,
            "total": live_stats["total_solved"],
            "rating": live_stats["contest_rating"],
            "delta": delta_solved
        })

    # Sort according to selected category
    if mode == "delta":
        board_data.sort(key=lambda x: x["delta"], reverse=True)
        title = "🚀 *SolvIIT Leaderboard — Weekly Progress (Δ Solved)*\n"
        def line_formatter(idx, item):
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
            return f"{medal} *{item['name']}* (`{item['handle']}`): **+{item['delta']}** problems (Total: {item['total']})"

    elif mode == "total":
        board_data.sort(key=lambda x: x["total"], reverse=True)
        title = "📚 *SolvIIT Leaderboard — Total Problems Solved*\n"
        def line_formatter(idx, item):
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
            return f"{medal} *{item['name']}* (`{item['handle']}`): **{item['total']}** solved"

    elif mode == "rating":
        board_data.sort(key=lambda x: x["rating"], reverse=True)
        title = "🏆 *SolvIIT Leaderboard — Contest Rating*\n"
        def line_formatter(idx, item):
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
            return f"{medal} *{item['name']}* (`{item['handle']}`): **{item['rating']}** rating"

    lines = [line_formatter(i + 1, item) for i, item in enumerate(board_data)]
    full_message = f"{title}\n" + "\n".join(lines)
    await update.message.reply_text(full_message, parse_mode=ParseMode.MARKDOWN)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **Welcome to SolvIIT Bot!**\n\n"
        "Register your handle using:\n`/register <leetcode_username>`",
        parse_mode=ParseMode.MARKDOWN
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong! 🏓")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 *SolvIIT LeetCode Bot — Commands*\n\n"
        "• `/register <leetcode_user>` — Link your LeetCode handle and initialize your baseline.\n"
        "• `/profile` — View your current problem counts and contest rating.\n"
        "• `/leaderboard` — View the weekly club standings based on deltas.\n"
        "• `/ping` — Check bot latency and server status.\n"
        "• `/help` — Show this command directory.\n\n"
        "💡 *Tip:* To avoid spamming the group chat, you can register and check your profile by DMing me directly!"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: `/register <leetcode_username>`", parse_mode=ParseMode.MARKDOWN)
        return

    leetcode_user = context.args[0].strip()
    tg_user = update.effective_user

    await update.message.reply_text(f"🔍 Checking LeetCode handle `{leetcode_user}`...", parse_mode=ParseMode.MARKDOWN)

    # 1. Fetch live data to validate
    stats = fetch_leetcode_stats(leetcode_user)
    if not stats:
        await update.message.reply_text(
            f"❌ Could not find LeetCode account `{leetcode_user}`. Please check spelling.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # 2. Persist member & baseline snapshot
    try:
        add_member(
            telegram_id=tg_user.id,
            tg_username=tg_user.username or tg_user.first_name,
            leetcode_username=stats["username"]
        )
        save_snapshot(tg_user.id, stats)

        reply = (
            f"✅ **Registered `{stats['username']}`!**\n\n"
            f"📊 **Current Baseline:**\n"
            f"• Total Solved: **{stats['total_solved']}**\n"
            f"  - 🟢 Easy: {stats['easy_solved']}\n"
            f"  - 🟡 Medium: {stats['medium_solved']}\n"
            f"  - 🔴 Hard: {stats['hard_solved']}\n"
            f"• Contest Rating: **{stats['contest_rating']}**\n\n"
            f"Weekly delta tracking has started!"
        )
        await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logging.error(f"Registration error: {e}")
        await update.message.reply_text("❌ Database error occurred during registration.")

if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not found in .env")

    # Ensure tables exist
    init_db()

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("help", help_command))
    
    # --- ADD THESE TWO LINES ---
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    # ---------------------------
    
    print("Bot starting...")
    app.run_polling()