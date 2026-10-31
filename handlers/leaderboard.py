# handlers/leaderboard.py
import asyncio
import datetime
import time  

from telegram import Update 
from telegram.constants import ParseMode
from telegram.ext import ContextTypes 
from zoneinfo import ZoneInfo  

from database import (
    register_member,
    get_member,
    get_all_members,
    save_snapshot,
    save_snapshot_if_not_exists,
    get_all_snapshots,
    check_and_mark_milestone
)
from leetcode import fetch_leetcode_stats
from handlers.utils import process_milestones

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Registers or updates a user's LeetCode account in the leaderboard database.

    Fetches current LeetCode statistics to establish baseline progress. If a user 
    is already registered under a different username, requires 'confirm' as a 
    second argument to overwrite their database record and reset progress.

    Args:
        update: The incoming Telegram update containing message and user data.
        context: Context object containing command arguments and bot instance.

    Note:
        - Network call to LeetCode API is run asynchronously via `asyncio.to_thread`.
        - Initial statistics snapshot is stamped in Madrid local time (`Europe/Madrid`).
    """

    if not context.args:
        await update.message.reply_text("⚠️ Uso: `/register <usuario_leetcode>`", parse_mode=ParseMode.MARKDOWN)
        return

    leetcode_user = context.args[0].strip()
    is_confirm = len(context.args) > 1 and context.args[1].lower() == "confirm"
    tg_user = update.effective_user

    # Grab user from database if already in it.
    existing_member = get_member(tg_user.id)
    if existing_member:
        # Case-insensitive user registration, could cause problems if there are
        # two users with same name and different case. 
        if existing_member["leetcode_username"].lower() == leetcode_user.lower():
            await update.message.reply_text(f"✅ Ya estás registrado con el usuario `{existing_member['leetcode_username']}`.", parse_mode=ParseMode.MARKDOWN)
            return
        if not is_confirm:
            await update.message.reply_text(
                f"⚠️ Actualmente estás registrado como `{existing_member['leetcode_username']}`.\n\n"
                f"Si te equivocaste de nombre y necesitas cambiar tu cuenta a `{leetcode_user}`"
                f" **esto reiniciará tus estadísticas iniciales y borrará tu progreso del club.**\n\n"
                f"Para confirmar, responde con:\n`/register {leetcode_user} confirm`",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    await update.message.reply_text(f"🔍 Buscando el usuario de LeetCode `{leetcode_user}`...", parse_mode=ParseMode.MARKDOWN)

    stats = await asyncio.to_thread(fetch_leetcode_stats, leetcode_user)
    if not stats:
        await update.message.reply_text(
            f"❌ No se encontró la cuenta de LeetCode `{leetcode_user}`. Comprueba cómo está escrito y que tu perfil sea público.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        if existing_member and is_confirm:
            success, message = update_member_baselines(tg_user.id, tg_user.username or tg_user.first_name, stats)
            action_text = "Base actualizada y reiniciada para"
        else:
            success, message = register_member(tg_user.id, tg_user.username or tg_user.first_name, stats)
            action_text = "Registrado"

        if not success:
            await update.message.reply_text(f"⚠️ {message}", parse_mode=ParseMode.MARKDOWN)
            return

        # Bot is configured to Madrid time for leaderboard updates.
        spain_tz = ZoneInfo("Europe/Madrid")
        today_str = datetime.datetime.now(spain_tz).strftime('%Y-%m-%d')
        await asyncio.to_thread(save_snapshot, tg_user.id, today_str, stats)

        reply = (
            f"✅ *¡{action_text} `{stats['username']}`!*\n\n"
            f"📊 *Nivel inicial guardado:*\n"
            f"• Total Resueltos: *{stats['total_solved']}*\n"
            f"  - 🟢 Easy: {stats['easy_solved']}\n"
            f"  - 🟡 Medium: {stats['medium_solved']}\n"
            f"  - 🔴 Hard: {stats['hard_solved']}\n"
            f"• Contest Rating: *{stats['contest_rating']}*\n\n"
            f"¡Tu progreso en el club se medirá a partir de estas estadísticas!"
        )
        await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logging.error(f"Registration error: {e}")
        await update.message.reply_text("❌ Hubo un error en la base de datos al intentar registrarte.")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays a member's LeetCode profile, progress, and rating changes.

    Fetches real-time stats from LeetCode, computes total progress (deltas) 
    since joining the club, checks for milestone achievements asynchronously, 
    and returns a formatted summary message to the chat.

    Args:
        update: The incoming Telegram update containing message and user data.
        context: Context object containing bot instances and job queue.

    Note:
        - Network call to LeetCode API is run asynchronously via `asyncio.to_thread`.
        - `process_milestones` is spawned as a non-blocking background task via 
          `asyncio.create_task` so profile rendering is not delayed.
        - Date operations are normalized to Madrid time (`Europe/Madrid`).
    """

    user_id = update.effective_user.id
    member = get_member(user_id)

    if not member:
        await update.message.reply_text("⚠️ ¡Aún no te has registrado! Usa `/register <usuario>` para empezar.", parse_mode=ParseMode.MARKDOWN)
        return

    stats = await asyncio.to_thread(fetch_leetcode_stats, member["leetcode_username"])
    if not stats:
        await update.message.reply_text("❌ No se pudieron obtener las estadísticas de LeetCode. Por favor, inténtalo de nuevo en un momento.")
        return

    spain_tz = ZoneInfo("Europe/Madrid")
    today_str = datetime.datetime.now(spain_tz).strftime('%Y-%m-%d')
    yesterday_str = (datetime.datetime.now(spain_tz) - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    y_snap = get_all_snapshots(yesterday_str).get(user_id)
    y_total = y_snap["total_solved"] if y_snap else member["base_total_solved"]
    
    asyncio.create_task(process_milestones(context, update.effective_chat.id, member, stats, y_total, today_str))

    delta_total = stats["total_solved"] - member["base_total_solved"]
    delta_easy = stats["easy_solved"] - member["base_easy_solved"]
    delta_med = stats["medium_solved"] - member["base_medium_solved"]
    delta_hard = stats["hard_solved"] - member["base_hard_solved"]
    delta_rating = round(stats["contest_rating"] - member["base_contest_rating"], 1)

    rating_delta_str = f"+{delta_rating}" if delta_rating > 0 else f"{delta_rating}"

    msg = (
        f"👤 *Perfil de LeetCode: {stats['username']}*\n"
        f"🏆 *Contest Rating:* {stats['contest_rating']} ({rating_delta_str} desde que se unió)\n\n"
        f"📊 *Total Resueltos:* {stats['total_solved']}\n"
        f"• 🟢 Easy: {stats['easy_solved']} (+{delta_easy})\n"
        f"• 🟡 Medium: {stats['medium_solved']} (+{delta_med})\n"
        f"• 🔴 Hard: {stats['hard_solved']} (+{delta_hard})\n\n"
        f"📈 *Progreso del Club:* **+{delta_total} problemas resueltos**"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


def get_metric(data_obj, mode, difficulty):
    """Calculates a specific ranking metric for a member based on mode and difficulty.

    Extracts or computes numerical values (contest rating, points system, totals, or 
    deltas) from a member's dataset to determine their position on the leaderboard.
    Point system: 
        - 1 point for each easy solved.
        - 2 point for each medium solved.
        - 3 point for each hard solved.

    Args:
        data_obj: Dictionary containing current or snapshot member statistics and baselines.
        mode: Metric type to calculate ('rating', 'points', 'total', or 'delta').
        difficulty: Difficulty scope filter ('all', 'easy', 'medium', or 'hard').

    Returns:
        The calculated metric score. Returns 0 if data_obj is empty or invalid.
    """

    if not data_obj: return 0
    if mode == "rating": return data_obj["rating"]
    if mode == "points":
        pts = (data_obj["easy"] * 1) + (data_obj["medium"] * 2) + (data_obj["hard"] * 3)
        base_pts = (data_obj["base"]["easy"] * 1) + (data_obj["base"]["medium"] * 2) + (data_obj["base"]["hard"] * 3)
        return pts - base_pts
        
    keys = {"all": "total", "easy": "easy", "medium": "medium", "hard": "hard"}
    k = keys[difficulty]
    return data_obj[k] if mode == "total" else data_obj[k] - data_obj["base"][k]

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generates, formats, and displays the club's LeetCode leaderboard.

    Fetches statistics concurrently for all registered members, calculates ranking metrics 
    and rank changes relative to yesterday's snapshot, triggers milestone checks in the 
    background, and renders a monospaced table view.

    Supported Command Arguments:
        - Mode filters: 'delta' (default progress), 'total', 'rating', 'points'.
        - Difficulty filters: 'all' (default), 'easy', 'medium', 'hard'.
        - Target filter: 'me' (restricts output to the requesting user's row).

    Args:
        update: Incoming Telegram update containing command and chat information.
        context: Telegram context object containing parsed command arguments (`context.args`).

    Note:
        - Member stats are fetched concurrently using `asyncio.gather` and `asyncio.to_thread`.
        - Background milestone processing (`process_milestones`) is scheduled via `asyncio.create_task`.
        - Employs a temporary waiting message (`edit_text`) to improve user experience while loading.
    """

    members = get_all_members()
    if not members:
        await update.message.reply_text("Todavía no hay miembros registrados.", parse_mode=ParseMode.MARKDOWN)
        return

    mode, difficulty, me_only = "delta", "all", False
    if context.args:
        args = [a.lower() for a in context.args]
        if "me" in args:
            me_only = True
            args.remove("me")
        valid_modes = {"delta", "total", "rating", "points"}
        valid_diffs = {"easy", "medium", "hard", "all"}
        for arg in args:
            if arg in valid_modes: mode = arg
            elif arg in valid_diffs: difficulty = arg

    wait_msg = await update.message.reply_text("⏳ Generando la clasificación del club...", parse_mode=ParseMode.MARKDOWN)

    spain_tz = ZoneInfo("Europe/Madrid")
    today_str = datetime.datetime.now(spain_tz).strftime('%Y-%m-%d')
    yesterday_str = (datetime.datetime.now(spain_tz) - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    yesterday_snapshots = get_all_snapshots(yesterday_str)

    live_data = []
    yesterday_data = []

    async def process_member(m):
        live = await asyncio.to_thread(fetch_leetcode_stats, m["leetcode_username"])
        if not live: return None
            
        tid = m["telegram_id"]
        base = {
            "total": m["base_total_solved"], "easy": m["base_easy_solved"],
            "medium": m["base_medium_solved"], "hard": m["base_hard_solved"],
            "rating": m["base_contest_rating"]
        }
        
        l_item = {
            "id": tid, "name": m["leetcode_username"],
            "total": live["total_solved"], "easy": live["easy_solved"],
            "medium": live["medium_solved"], "hard": live["hard_solved"],
            "rating": live["contest_rating"], "base": base
        }

        y_snap = yesterday_snapshots.get(tid)
        y_total = y_snap["total_solved"] if y_snap else base["total"]
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
            
        await asyncio.to_thread(save_snapshot_if_not_exists, tid, today_str, live)
        return l_item, y_item, m, live, y_total

    results = await asyncio.gather(*(process_member(m) for m in members))

    for res in results:
        if res:
            live_data.append(res[0])
            yesterday_data.append(res[1])
            m, live, y_total = res[2], res[3], res[4]
            asyncio.create_task(process_milestones(context, update.effective_chat.id, m, live, y_total, today_str))

    live_data.sort(key=lambda x: get_metric(x, mode, difficulty), reverse=True)
    yesterday_data.sort(key=lambda x: get_metric(x, mode, difficulty), reverse=True)
    yesterday_ranks = {item["id"]: idx for idx, item in enumerate(yesterday_data)}
    yesterday_map = {item["id"]: item for item in yesterday_data}

    lines = []
    for i, item in enumerate(live_data):
        tid = item["id"]
        if me_only and str(tid) != str(update.effective_user.id): continue

        metric = get_metric(item, mode, difficulty)
        y_item = yesterday_map.get(tid)
        y_metric = get_metric(y_item, mode, difficulty) if y_item else 0
        hoy = metric - y_metric
        
        curr_rank = i + 1
        y_rank = yesterday_ranks.get(tid, 999) + 1
        rank_diff = y_rank - curr_rank

        if mode == "rating": stats_str = f"{item['rating']:>6.1f}"
        elif mode == "points": stats_str = f"{metric:>4} pts"
        elif mode == "delta":
            if difficulty == "all":
                d_e = item["easy"] - item["base"]["easy"]
                d_m = item["medium"] - item["base"]["medium"]
                d_h = item["hard"] - item["base"]["hard"]
                stats_str = f"+{d_e:<3} +{d_m:<3} +{d_h:<3}"
            else:
                stats_str = f"+{metric:<3}"
        else:
            if difficulty == "all": stats_str = f"{item['easy']:<3} {item['medium']:<3} {item['hard']:<3}"
            else: stats_str = f"{metric:<3}"

        if mode == "rating": hoy_str = f"{round(hoy,1):>4}" if hoy > 0 else "    "
        else: hoy_str = f"{int(hoy):>4}" if hoy > 0 else "    "

        if y_rank == 1000: rank_str = " NUEVO"
        elif rank_diff > 0: rank_str = f"{rank_diff:>2}↑"
        elif rank_diff < 0: rank_str = f"{abs(rank_diff):>2}↓"
        else: rank_str = "  ="

        name_clean = item['name'][:10].ljust(10)
        lines.append(f"{curr_rank:>2}. {name_clean} {stats_str}  {hoy_str} {rank_str}")

    diff_str = f" ({difficulty.title()})" if difficulty != "all" else ""
    if mode == "delta": title = f"🚀 *Clasificación SolvIIT — Progreso{diff_str}*"
    elif mode == "total": title = f"📚 *Clasificación SolvIIT — Total Resueltos{diff_str}*"
    elif mode == "points": title = "🎯 *Clasificación SolvIIT — Sistema de Puntos*"
    else: title = "🏆 *Clasificación SolvIIT — Contest Rating*"

    legend_diff = "Pts" if mode == "points" else ("E-M-H" if difficulty == "all" else difficulty.title())
    metric_name = "RateΔ" if mode == "rating" else "Hoy"
    legend = f"📊 *Cols:* `{legend_diff} | {metric_name} | RankΔ`"

    board_text = "\n".join(lines)
    full_message = f"{title}\n{legend}\n```text\n{board_text}\n```"
    await wait_msg.edit_text(full_message, parse_mode=ParseMode.MARKDOWN)