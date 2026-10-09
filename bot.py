import os
import asyncio
import logging
from dotenv import load_dotenv

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ChatMemberHandler, ContextTypes
from database import (
    init_db,
    register_member,
    get_member,
    get_all_members,
    add_weekly_problem,
    get_weekly_problems,
    delete_weekly_problems
)
from leetcode import fetch_leetcode_stats

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_TELEGRAM_ID")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome to SolvIIT Bot!*\n\n"
        "Link your handle:\n`/register <leetcode_username>`\n\n"
        "Type `/help` to see available commands.",
        parse_mode=ParseMode.MARKDOWN
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong! 🏓")

async def gay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🌈 Soy gay 🌈")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 *SolvIIT LeetCode Bot — Commands*\n\n"
        "• `/register <leetcode_user>` — Link your LeetCode handle and lock your starting baseline.\n"
        "• `/profile` — View your lifetime stats and progress made since joining.\n"
        "• `/leaderboard [delta|total|rating]` — View club standings.\n"
        "• `/ping` — Check bot latency.\n"
        "• `/help` — Show this command directory.\n\n"
        "💡 *Tip:* To avoid cluttering the group, you can register and check your profile by DMing me directly!"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: `/register <leetcode_username>`", parse_mode=ParseMode.MARKDOWN)
        return

    leetcode_user = context.args[0].strip()
    tg_user = update.effective_user

    await update.message.reply_text(f"🔍 Checking LeetCode handle `{leetcode_user}`...", parse_mode=ParseMode.MARKDOWN)

    stats = fetch_leetcode_stats(leetcode_user)
    if not stats:
        await update.message.reply_text(
            f"❌ Could not find LeetCode account `{leetcode_user}`. Check spelling and public profile settings.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        success, message = register_member(
            telegram_id=tg_user.id,
            tg_username=tg_user.username or tg_user.first_name,
            stats=stats
        )

        if not success:
            await update.message.reply_text(f"⚠️ {message}", parse_mode=ParseMode.MARKDOWN)
            return

        reply = (
            f"✅ *Registered `{stats['username']}`!*\n\n"
            f"📊 *Starting Baseline Locked:*\n"
            f"• Total Solved: *{stats['total_solved']}*\n"
            f"  - 🟢 Easy: {stats['easy_solved']}\n"
            f"  - 🟡 Medium: {stats['medium_solved']}\n"
            f"  - 🔴 Hard: {stats['hard_solved']}\n"
            f"• Contest Rating: *{stats['contest_rating']}*\n\n"
            f"Your club growth will be measured starting from these stats!"
        )
        await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logging.error(f"Registration error: {e}")
        await update.message.reply_text("❌ Database error occurred during registration.")

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

    delta_total = stats["total_solved"] - member["base_total_solved"]
    delta_easy = stats["easy_solved"] - member["base_easy_solved"]
    delta_med = stats["medium_solved"] - member["base_medium_solved"]
    delta_hard = stats["hard_solved"] - member["base_hard_solved"]
    delta_rating = round(stats["contest_rating"] - member["base_contest_rating"], 1)

    rating_delta_str = f"+{delta_rating}" if delta_rating > 0 else f"{delta_rating}"

    msg = (
        f"👤 *LeetCode Profile: {stats['username']}*\n"
        f"🏆 *Contest Rating:* {stats['contest_rating']} ({rating_delta_str} since joining)\n\n"
        f"📊 *Lifetime Solved:* {stats['total_solved']}\n"
        f"• 🟢 Easy: {stats['easy_solved']} (+{delta_easy})\n"
        f"• 🟡 Medium: {stats['medium_solved']} (+{delta_med})\n"
        f"• 🔴 Hard: {stats['hard_solved']} (+{delta_hard})\n\n"
        f"📈 *Club Progress:* **+{delta_total} problems solved**"
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
            "• `/leaderboard` or `/leaderboard delta` (Progress since joining)\n"
            "• `/leaderboard total` (All-time solved count)\n"
            "• `/leaderboard rating` (Contest ranking)",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    wait_msg = await update.message.reply_text("⏳ Generating club leaderboard...", parse_mode=ParseMode.MARKDOWN)

    board_data = []
    for m in members:
        live_stats = fetch_leetcode_stats(m["leetcode_username"])
        if not live_stats:
            continue
        
        delta_solved = live_stats["total_solved"] - m["base_total_solved"]
        
        board_data.append({
            "name": m["telegram_username"] or m["leetcode_username"],
            "handle": m["leetcode_username"],
            "total": live_stats["total_solved"],
            "rating": live_stats["contest_rating"],
            "delta": delta_solved
        })
        await asyncio.sleep(0.3)

    if mode == "delta":
        board_data.sort(key=lambda x: x["delta"], reverse=True)
        title = "🚀 *SolvIIT Leaderboard — Progress Since Joining (Δ Solved)*\n"
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
    await wait_msg.edit_text(full_message, parse_mode=ParseMode.MARKDOWN)

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Greets new members when they join the group."""
    result = update.chat_member
    if not result:
        return

    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status

    # Trigger only when someone transitions into being a member
    if old_status in ["left", "kicked"] and new_status == "member":
        user = result.new_chat_member.user
        
        # Skip if the new member is a bot
        if user.is_bot:
            return

        name = user.first_name
        welcome_text = (
            f"👋 Bienvenido a SolvIIT! *{name}*!\n\n"
            "Para participar en el leaderboard y registrar tu progreso:\n"
            "1. Linkea tu cuenta de LeetCode haciendo \n\t`/register <usuario>`\n"
            "2. Escribe `/help` para ver la lista de comandos del bot.\n\n"
            "También recomendado:\n"
            "1. Crearse cuenta de NeetCode y seguir el roadmap."
            "Suerte..."
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=welcome_text,
            parse_mode=ParseMode.MARKDOWN
        )

async def add_problem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /addproblem <week> <name/url>"""
    user_id = str(update.effective_user.id)
    admin_id = os.getenv("ADMIN_TELEGRAM_ID")

    # Reject if ADMIN_TELEGRAM_ID is missing/empty, or if caller is not the admin
    if not admin_id or user_id != str(admin_id).strip():
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ Usage: /addproblem <week_number> <problem_title_or_link>\n"
            "Example: /addproblem 1 Two Sum - https://leetcode.com/problems/two-sum/"
        )
        return

    try:
        week_num = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Week number must be an integer.")
        return

    problem_name = " ".join(context.args[1:]).strip()
    added = add_weekly_problem(week_num, problem_name)
    if added:
        await update.message.reply_text(f"✅ Added to Week {week_num}:\n{problem_name}")
    else:
        await update.message.reply_text(f"⚠️ That problem is already registered under Week {week_num}!")

async def list_problems(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Public command: /problems or /problems <week>"""
    target_week = None
    if context.args:
        try:
            target_week = int(context.args[0])
        except ValueError:
            await update.message.reply_text("⚠️ Usage: /problems or /problems <week_number>")
            return

    problems = get_weekly_problems(target_week)
    if not problems:
        msg = f"No problems recorded yet for Week {target_week}." if target_week else "No weekly problems recorded yet."
        await update.message.reply_text(msg)
        return

    # Group problems by week
    weeks = {}
    for p in problems:
        w = p["week_number"]
        weeks.setdefault(w, []).append(p["problem_name"])

    text_blocks = ["📚 SolvIIT Club — Problem Archive\n"]
    for w in sorted(weeks.keys(), reverse=True):
        text_blocks.append(f"🗓️ Week {w}")
        for item in weeks[w]:
            text_blocks.append(f"• {item}")
        text_blocks.append("")  # Empty spacing line

    # Send as plain text without Markdown to avoid formatting crashes with underscores/URLs
    await update.message.reply_text("\n".join(text_blocks))

async def delete_problems(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /deleteproblems <week_number>"""
    user_id = str(update.effective_user.id)
    admin_id = os.getenv("ADMIN_TELEGRAM_ID")
    # Fail closed: reject if admin_id is missing or caller does not match
    if not admin_id or user_id != str(admin_id).strip():
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return

    if not context.args or len(context.args) != 1:
        await update.message.reply_text(
            "⚠️ Usage: `/deleteproblems <week_number>`\n"
            "Example: `/deleteproblems 1`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        week_num = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Week number must be an integer.")
        return

    deleted_count = delete_weekly_problems(week_num)
    if deleted_count > 0:
        await update.message.reply_text(
            f"🗑️ Deleted {deleted_count} problem(s) from *Week {week_num}*.",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(f"⚠️ No problems found for Week {week_num}.")

if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not found in .env")

    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("gay", gay))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    
    app.add_handler(CommandHandler("problems", list_problems))
    # Automatic 
    app.add_handler(ChatMemberHandler(welcome_new_member, ChatMemberHandler.CHAT_MEMBER))

    # Only admin
    app.add_handler(CommandHandler("deleteproblems", delete_problems))
    app.add_handler(CommandHandler("addproblem", add_problem))

    print("Bot is live (on-demand only)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)