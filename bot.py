import os
import asyncio
import logging
import datetime
from dotenv import load_dotenv

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ChatMemberHandler,
    ContextTypes,
    TypeHandler,
    ApplicationHandlerStop
)
from database import (
    init_db,
    register_member,
    get_member,
    get_all_members,
    add_weekly_problem,
    get_weekly_problems,
    delete_weekly_problems,
    mute_user,
    unmute_user,
    is_user_muted,
    save_snapshot,
    get_all_snapshots
)

from leetcode import fetch_leetcode_stats

import html
import random

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_TELEGRAM_ID")

SLAP_WEAPONS = [
    "una trucha 🐟",
    "un periódico 📄",
    "un teclado ⌨️",
    "su propia mano 👋",
    "un pato de goma 🦆",
]

DEFAULT_TARGET = os.getenv("DEFAULT_SLAP_TARGET")
COMMAND_SPAM_TRACKER = {}

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

async def amarillo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Amarillo")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 *SolvIIT LeetCode Bot — Commands*\n\n"
        "• `/register <leetcode_user>` — Link your LeetCode handle and lock your starting baseline.\n"
        "• `/profile` — View your lifetime stats and progress made since joining.\n"
        "• `/leaderboard [delta|total|rating] [easy|medium|hard] [me]` — View club standings.\n"
        "• `/ping` — Check bot latency.\n"
        "• `/problems` — Display weekly session problem log.\n\n"
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

def get_metric(data_obj, mode, difficulty):
    """Helper to extract the specific metric being sorted on."""
    if not data_obj: return 0
    if mode == "rating": return data_obj["rating"]
    keys = {"all": "total", "easy": "easy", "medium": "medium", "hard": "hard"}
    k = keys[difficulty]
    return data_obj[k] if mode == "total" else data_obj[k] - data_obj["base"][k]

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    members = get_all_members()
    if not members:
        await update.message.reply_text("No club members registered yet.", parse_mode=ParseMode.MARKDOWN)
        return

    # Parse Arguments
    mode = "delta"
    difficulty = "all"
    me_only = False

    if context.args:
        args = [a.lower() for a in context.args]
        if "me" in args:
            me_only = True
            args.remove("me")
        valid_modes = {"delta", "total", "rating"}
        valid_diffs = {"easy", "medium", "hard", "all"}
        for arg in args:
            if arg in valid_modes: mode = arg
            elif arg in valid_diffs: difficulty = arg

    wait_msg = await update.message.reply_text("⏳ Generating club leaderboard...", parse_mode=ParseMode.MARKDOWN)

    today_str = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
    yesterday_str = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    yesterday_snapshots = get_all_snapshots(yesterday_str)

    live_data = []
    yesterday_data = []

    # --- NEW: Concurrent Data Fetching ---
    async def process_member(m):
        # Runs the synchronous request in a background thread so the bot doesn't freeze
        live = await asyncio.to_thread(fetch_leetcode_stats, m["leetcode_username"])
        if not live:
            return None
            
        tid = m["telegram_id"]
        base = {
            "total": m["base_total_solved"], "easy": m["base_easy_solved"],
            "medium": m["base_medium_solved"], "hard": m["base_hard_solved"],
            "rating": m["base_contest_rating"]
        }
        
        # Format live item
        l_item = {
            "id": tid, "name": m["telegram_username"] or m["leetcode_username"],
            "total": live["total_solved"], "easy": live["easy_solved"],
            "medium": live["medium_solved"], "hard": live["hard_solved"],
            "rating": live["contest_rating"], "base": base
        }

        # Format yesterday item
        y_snap = yesterday_snapshots.get(tid)
        if y_snap:
            y_item = {
                "id": tid, "total": y_snap["total_solved"], "easy": y_snap["easy_solved"],
                "medium": y_snap["medium_solved"], "hard": y_snap["hard_solved"],
                "rating": y_snap["contest_rating"], "base": base
            }
        else:
            y_item = {
                "id": tid, "total": base["total"], "easy": base["easy"],
                "medium": base["medium"], "hard": base["hard"],
                "rating": base["rating"], "base": base
            }
            
        # Save snapshot synchronously but in a thread
        await asyncio.to_thread(save_snapshot, tid, today_str, live)
        return l_item, y_item

    # Gather all LeetCode API requests simultaneously
    results = await asyncio.gather(*(process_member(m) for m in members))

    for res in results:
        if res:
            live_data.append(res[0])
            yesterday_data.append(res[1])
    # --- END Concurrent Fetching ---

    # Sort & generate ranks
    live_data.sort(key=lambda x: get_metric(x, mode, difficulty), reverse=True)
    yesterday_data.sort(key=lambda x: get_metric(x, mode, difficulty), reverse=True)
    yesterday_ranks = {item["id"]: idx for idx, item in enumerate(yesterday_data)}
    yesterday_map = {item["id"]: item for item in yesterday_data}

    lines = []
    for i, item in enumerate(live_data):
        tid = item["id"]
        if me_only and str(tid) != str(update.effective_user.id):
            continue

        metric = get_metric(item, mode, difficulty)
        y_item = yesterday_map.get(tid)
        y_metric = get_metric(y_item, mode, difficulty) if y_item else 0
        hoy = metric - y_metric
        
        curr_rank = i + 1
        y_rank = yesterday_ranks.get(tid, 999) + 1
        rank_diff = y_rank - curr_rank

        # Status text formatting
        if mode == "rating":
            stats_str = f"{item['rating']:>6.1f}"
        elif mode == "delta":
            if difficulty == "all":
                d_e = item["easy"] - item["base"]["easy"]
                d_m = item["medium"] - item["base"]["medium"]
                d_h = item["hard"] - item["base"]["hard"]
                stats_str = f"+{d_e:<3} +{d_m:<3} +{d_h:<3}"
            else:
                stats_str = f"+{metric:<3}"
        else: # total
            if difficulty == "all":
                stats_str = f"{item['easy']:<3} {item['medium']:<3} {item['hard']:<3}"
            else:
                stats_str = f"{metric:<3}"

        # Today formatting (Removed "Hoy" and adjusted padding)
        if mode == "rating":
            hoy_str = f"{round(hoy,1):>4}" if hoy > 0 else "    "
        else:
            hoy_str = f"{int(hoy):>4}" if hoy > 0 else "    "

        # Rank arrow formatting
        if rank_diff > 0 and y_rank != 1000:
            rank_str = f"{rank_diff:>2}↑"
        elif rank_diff < 0 and y_rank != 1000:
            rank_str = f"{abs(rank_diff):>2}↓"
        else:
            rank_str = "   "

        # Truncate and pad names to max 10 chars so it doesn't overflow mobile screens
        name_clean = item['name'][:10].ljust(10)
        
        # Added extra spaces between stats_str and hoy_str for visual separation
        lines.append(f"{curr_rank:>2}. {name_clean} {stats_str}  {hoy_str} {rank_str}")

    # Title generation
    diff_str = f" ({difficulty.title()})" if difficulty != "all" else ""
    if mode == "delta": title = f"🚀 *SolvIIT Leaderboard — Progress{diff_str}*"
    elif mode == "total": title = f"📚 *SolvIIT Leaderboard — Total Solved{diff_str}*"
    else: title = "🏆 *SolvIIT Leaderboard — Contest Rating*"

    # Dynamic columns legend (Shortened to prevent text wrapping)
    if difficulty == "all":
        legend_diff = "E-M-H"
    else:
        legend_diff = difficulty.title()
        
    metric_name = "RateΔ" if mode == "rating" else "Today"
    legend = f"📊 *Cols:* `{legend_diff} | {metric_name} | RankΔ`"

    # Wrap the ranking list in a markdown monospace block
    board_text = "\n".join(lines)
    full_message = f"{title}\n{legend}\n```text\n{board_text}\n```"
    
    await wait_msg.edit_text(full_message, parse_mode=ParseMode.MARKDOWN)

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    if not result: return
    
    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status

    if old_status in ["left", "kicked"] and new_status == "member":
        user = result.new_chat_member.user
        if user.is_bot: return

        name = user.first_name
        welcome_text = (
            f"👋 Bienvenido a SolvIIT! *{name}*!\n\n"
            "Para participar en el leaderboard y registrar tu progreso:\n"
            "1. Linkea tu cuenta de LeetCode haciendo \n\t`/register <usuario>`\n"
            "2. Escribe `/help` para ver la lista de comandos del bot.\n\n"
            "También recomendado:\n"
            "1. Crearse cuenta de NeetCode y seguir el roadmap.\n"
            "Suerte..."
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=welcome_text,
            parse_mode=ParseMode.MARKDOWN
        )

async def add_problem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admin_id = os.getenv("ADMIN_TELEGRAM_ID")
    if not admin_id or user_id != str(admin_id).strip():
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ Usage: /addproblem <week_number> <problem_title_or_link>")
        return

    try: week_num = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Week number must be an integer.")
        return

    problem_name = " ".join(context.args[1:]).strip()
    if add_weekly_problem(week_num, problem_name):
        await update.message.reply_text(f"✅ Added to Week {week_num}:\n{problem_name}")
    else:
        await update.message.reply_text(f"⚠️ That problem is already registered under Week {week_num}!")

async def list_problems(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_week = None
    if context.args:
        try: target_week = int(context.args[0])
        except ValueError:
            await update.message.reply_text("⚠️ Usage: /problems or /problems <week_number>")
            return

    problems = get_weekly_problems(target_week)
    if not problems:
        await update.message.reply_text("No problems recorded yet.")
        return

    weeks = {}
    for p in problems: weeks.setdefault(p["week_number"], []).append(p["problem_name"])
    
    text_blocks = ["📚 SolvIIT Club — Problem Archive\n"]
    for w in sorted(weeks.keys(), reverse=True):
        text_blocks.append(f"🗓️ Week {w}")
        for item in weeks[w]: text_blocks.append(f"• {item}")
        text_blocks.append("")
    await update.message.reply_text("\n".join(text_blocks))

async def delete_problems(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admin_id = os.getenv("ADMIN_TELEGRAM_ID")
    if not admin_id or user_id != str(admin_id).strip():
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return

    if not context.args or len(context.args) != 1:
        await update.message.reply_text("⚠️ Usage: `/deleteproblems <week>`", parse_mode=ParseMode.MARKDOWN)
        return

    try: week_num = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Week number must be an integer.")
        return

    deleted_count = delete_weekly_problems(week_num)
    if deleted_count > 0:
        await update.message.reply_text(f"🗑️ Deleted {deleted_count} problem(s) from *Week {week_num}*.", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(f"⚠️ No problems found for Week {week_num}.")

async def slap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    slapper = update.effective_user.first_name
    weapon = random.choice(SLAP_WEAPONS)
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_mention = f'<a href="tg://user?id={target_user.id}">{html.escape(target_user.first_name)}</a>'
        text = f"<b>{html.escape(slapper)}</b> le da un guantazo a {target_mention} con {weapon}!"
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return
    if context.args:
        target_arg = " ".join(context.args).strip()
        target_clean = html.escape(target_arg)
        text = f"<b>{html.escape(slapper)}</b> le da un guantazo a {target_clean} con {weapon}!"
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return
    text = f"<b>{html.escape(slapper)}</b> le da un guantazo a {DEFAULT_TARGET} con {weapon}!"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def gay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    slapper = update.effective_user.first_name
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_mention = f'<a href="tg://user?id={target_user.id}">{html.escape(target_user.first_name)}</a>'
        text = f"🏳️‍🌈 <b>{html.escape(slapper)}</b> llama gay a {target_mention}, lol, que gay."
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return
    if context.args:
        target_clean = html.escape(" ".join(context.args).strip())
        text = f"🏳️‍🌈 <b>{html.escape(slapper)}</b> llama gay a {target_clean}, lol, que gay."
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return
    text = f"🏳️‍🌈 <b>{html.escape(slapper)}</b> llama gay a {DEFAULT_TARGET}, lol, que gay."
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admin_id = os.getenv("ADMIN_TELEGRAM_ID")
    if not admin_id or user_id != str(admin_id).strip():
        await update.message.reply_text("⛔ You are not authorized.")
        return

    duration_minutes = 30
    target_id = None
    target_name = "User"

    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_id = target_user.id
        target_name = target_user.first_name
        if context.args:
            try: duration_minutes = int(context.args[0])
            except ValueError: pass
    elif context.args:
        try:
            target_id = int(context.args[0])
            target_name = f"ID `{target_id}`"
            if len(context.args) > 1: duration_minutes = int(context.args[1])
        except ValueError:
            await update.message.reply_text("⚠️ Usage: Reply with `/mute [mins]` or `/mute <id> [mins]`")
            return
    else:
        await update.message.reply_text("⚠️ Reply to a message with `/mute` or specify a user ID.")
        return

    if str(target_id) == str(admin_id).strip():
        await update.message.reply_text("⚠️ You cannot mute yourself!")
        return

    mute_user(target_id, duration_seconds=duration_minutes * 60)
    
    await update.message.reply_text(
        f"🤫 <b>{html.escape(target_name)}</b> has been completely muted for {duration_minutes} minutes.\n"
        f"<i>(Check remaining time by messaging me in private chat)</i>", 
        parse_mode=ParseMode.HTML
    )

async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /unmute (via reply or ID)"""
    user_id = str(update.effective_user.id)
    admin_id = os.getenv("ADMIN_TELEGRAM_ID")
    if not admin_id or user_id != str(admin_id).strip():
        await update.message.reply_text("⛔ You are not authorized.")
        return

    target_id = None
    target_name = "User"

    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_id = target_user.id
        target_name = target_user.first_name
    elif context.args:
        try:
            target_id = int(context.args[0])
            target_name = f"ID `{target_id}`"
        except ValueError:
            pass

    if not target_id:
        await update.message.reply_text("⚠️ Reply to a message with `/unmute` or specify a user ID.")
        return

    if unmute_user(target_id):
        await update.message.reply_text(f"🔊 <b>{html.escape(target_name)}</b> has been unmuted.", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("⚠️ That user is not currently muted.")

async def check_mute_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user: return
    
    user_id = update.effective_user.id
    admin_id = os.getenv("ADMIN_TELEGRAM_ID")
    
    # 1. Enforce existing mutes
    is_muted, remaining = is_user_muted(user_id)
    if is_muted:
        if update.effective_chat.type == "private":
            mins_left = max(1, remaining // 60)
            await update.message.reply_text(f"🤐 You are silenced. {mins_left}m remaining.")
        else:
            try:
                await update.message.delete()
            except Exception as e:
                logging.error(f"Failed to delete message: {e}")
        raise ApplicationHandlerStop

    # Admin bypass for spam check
    if admin_id and str(user_id) == str(admin_id).strip(): return

    # 2. Check for Command Spam (5 commands in 6 seconds)
    text = update.message.text or update.message.caption or ""
    if text.startswith("/"):
        now = time.time()
        
        # Initialize user's history if not present
        if user_id not in COMMAND_SPAM_TRACKER:
            COMMAND_SPAM_TRACKER[user_id] = []
            
        # Append current command timestamp
        COMMAND_SPAM_TRACKER[user_id].append(now)
        
        # Filter out timestamps older than 6 seconds
        COMMAND_SPAM_TRACKER[user_id] = [t for t in COMMAND_SPAM_TRACKER[user_id] if now - t <= 6]
        
        # Trigger mute if threshold reached
        if len(COMMAND_SPAM_TRACKER[user_id]) >= 5:
            # 30-minute mute
            mute_user(user_id, duration_seconds=1800)
            # Clear tracker so it doesn't instantly re-trigger when they are eventually unmuted
            COMMAND_SPAM_TRACKER[user_id] = []
            
            user_name = update.effective_user.first_name
            await update.message.reply_text(
                f"🛑 <b>{html.escape(user_name)}</b> ha sido muteado automáticamente por 30 minutos por hacer spam de comandos.",
                parse_mode=ParseMode.HTML
            )
            
            try:
                await update.message.delete()
            except Exception:
                pass
                
            raise ApplicationHandlerStop

async def daily_snapshot_job(context: ContextTypes.DEFAULT_TYPE):
    """Background job: Fetches all user stats daily at 23:59 UTC to track rank arrows."""
    logging.info("Starting daily snapshot job...")
    members = get_all_members()
    today_str = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
    for m in members:
        stats = fetch_leetcode_stats(m["leetcode_username"])
        if stats:
            save_snapshot(m["telegram_id"], today_str, stats)
        await asyncio.sleep(0.5)
    logging.info("Daily snapshot job completed.")

if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not found in .env")

    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    # Schedule the daily snapshot background job
    job_queue = app.job_queue
    target_time = datetime.time(hour=23, minute=59, tzinfo=datetime.timezone.utc)
    job_queue.run_daily(daily_snapshot_job, time=target_time)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("amarillo", amarillo))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("slap", slap))
    app.add_handler(CommandHandler("gay", gay))
    app.add_handler(CommandHandler("problems", list_problems))
    
    app.add_handler(ChatMemberHandler(welcome_new_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(TypeHandler(Update, check_mute_status), group=-1)

    app.add_handler(CommandHandler("mute", mute_command))
    app.add_handler(CommandHandler("unmute", unmute_command)) 
    app.add_handler(CommandHandler("deleteproblems", delete_problems))
    app.add_handler(CommandHandler("addproblem", add_problem))

    print("Bot is live (on-demand only)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)