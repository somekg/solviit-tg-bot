import os
import asyncio
import logging
import datetime
import time  
import html
import random
from zoneinfo import ZoneInfo  
from dotenv import load_dotenv
from telegram.error import RetryAfter
from telegram import Update, ChatPermissions
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
    update_member_username,
    update_member_baselines,  
    get_member,
    get_all_members,
    add_weekly_problem,
    get_weekly_problems,
    delete_weekly_problems,
    mute_user,
    unmute_user,
    is_user_muted,
    save_snapshot,
    save_snapshot_if_not_exists,
    get_all_snapshots,
    get_muted_users,
    get_member_by_username,
    check_and_mark_milestone
)

from leetcode import fetch_leetcode_stats
from donut import donut_command  

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

COMMAND_SPAM_TRACKER = {}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)

MUTE_PERMISSIONS = ChatPermissions(
    can_send_messages=False, can_send_audios=False, can_send_documents=False,
    can_send_photos=False, can_send_videos=False, can_send_video_notes=False,
    can_send_voice_notes=False, can_send_polls=False, can_send_other_messages=False,
    can_add_web_page_previews=False
)

UNMUTE_PERMISSIONS = ChatPermissions(
    can_send_messages=True, can_send_audios=True, can_send_documents=True,
    can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
    can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
    can_add_web_page_previews=True
)

async def safe_delete(message):
    if not message: return
    try:
        await message.delete()
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after)
        try: await message.delete()
        except Exception: pass
    except Exception as e:
        logging.debug(f"Could not delete message: {e}")

async def process_milestones(context: ContextTypes.DEFAULT_TYPE, chat_id: int, member: dict, live_stats: dict, yesterday_total: int, today_str: str):
    lc_user = member["leetcode_username"]
    announcements = []

    # 1. Daily Multiples of 5
    daily_total = live_stats["total_solved"] - yesterday_total
    daily_mult = (daily_total // 5) * 5
    if daily_mult > 0:
        if check_and_mark_milestone(member["telegram_id"], f"daily_total_{today_str}", daily_mult):
            announcements.append(f"🔥 ¡<b>{html.escape(lc_user)}</b> ha resuelto <b>{daily_mult} problemas</b> hoy!")

    # 2. Delta Multiples of 50 since joining
    deltas = {
        "Total": live_stats["total_solved"] - member["base_total_solved"],
        "fáciles": live_stats["easy_solved"] - member["base_easy_solved"],
        "medios": live_stats["medium_solved"] - member["base_medium_solved"],
        "difíciles": live_stats["hard_solved"] - member["base_hard_solved"]
    }
    
    for diff, val in deltas.items():
        mult = (val // 50) * 50
        if mult > 0:
            if check_and_mark_milestone(member["telegram_id"], f"delta_{diff.lower()}", mult):
                if diff == "Total":
                    announcements.append(f"🏆 ¡<b>{html.escape(lc_user)}</b> ha llegado a <b>+{mult} problemas en total</b> desde que se unió!")
                else:
                    announcements.append(f"🎉 ¡<b>{html.escape(lc_user)}</b> ha llegado a <b>+{mult} problemas {diff}</b> desde que se unió!")

    for msg in announcements:
        try:
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML)
            await asyncio.sleep(0.5)
        except Exception as e:
            logging.error(f"Milestone announcement failed: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *¡Bienvenido a SolvIIT Bot!*\n\n"
        "Vincula tu usuario:\n`/register <usuario_leetcode>`\n\n"
        "Escribe `/help` para ver los comandos disponibles.",
        parse_mode=ParseMode.MARKDOWN
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong! 🏓")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 *SolvIIT LeetCode Bot — Comandos*\n\n"
        "• `/register <usuario_leetcode>` — Vincula tu usuario de LeetCode y fija tu progreso inicial.\n"
        "• `/profile` — Mira tus estadísticas y progreso desde que te uniste.\n"
        "• `/leaderboard [delta|total|rating|points] [easy|medium|hard] [me]` — Mira la clasificación del club.\n"
        "• `/ping` — Revisa el ping del bot.\n"
        "• `/problems` — Muestra el registro de problemas semanales.\n\n"
        "• `/help` — Muestra este menú.\n\n"
        "💡 *Tip:* ¡Para evitar hacer spam en el grupo, puedes registrarte y ver tu perfil hablándome por MD!"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Uso: `/register <usuario_leetcode>`", parse_mode=ParseMode.MARKDOWN)
        return

    leetcode_user = context.args[0].strip()
    is_confirm = len(context.args) > 1 and context.args[1].lower() == "confirm"
    tg_user = update.effective_user

    existing_member = get_member(tg_user.id)
    if existing_member:
        if existing_member["leetcode_username"].lower() == leetcode_user.lower():
            await update.message.reply_text(f"✅ Ya estás registrado con el usuario `{existing_member['leetcode_username']}`.", parse_mode=ParseMode.MARKDOWN)
            return
        if not is_confirm:
            await update.message.reply_text(
                f"⚠️ Actualmente estás registrado como `{existing_member['leetcode_username']}`.\n\n"
                f"Si te equivocaste de nombre y necesitas cambiar tu cuenta a `{leetcode_user}`, **esto reiniciará tus estadísticas iniciales y borrará tu progreso del club.**\n\n"
                f"Para confirmar, responde con:\n`/register {leetcode_user} confirm`",
                parse_mode=ParseMode.MARKDOWN
            )
            return

    await update.message.reply_text(f"🔍 Buscando el usuario de LeetCode `{leetcode_user}`...", parse_mode=ParseMode.MARKDOWN)

    stats = await asyncio.to_thread(fetch_leetcode_stats, leetcode_user)
    if not stats:
        await update.message.reply_text(
            f"❌ No se encontró la cuenta de LeetCode `{leetcode_user}`. Comprueba cómo está escrito y tu configuración de perfil público.",
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
        await update.message.reply_text("⛔ No estás autorizado para usar este comando.")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ Uso: /addproblem <semana> <título_o_enlace>")
        return

    try: week_num = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ El número de la semana debe ser un entero.")
        return

    problem_name = " ".join(context.args[1:]).strip()
    if add_weekly_problem(week_num, problem_name):
        await update.message.reply_text(f"✅ Añadido a la Semana {week_num}:\n{problem_name}")
    else:
        await update.message.reply_text(f"⚠️ ¡Ese problema ya está registrado en la Semana {week_num}!")

async def list_problems(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_week = None
    if context.args:
        try: target_week = int(context.args[0])
        except ValueError:
            await update.message.reply_text("⚠️ Uso: /problems o /problems <semana>")
            return

    problems = get_weekly_problems(target_week)
    if not problems:
        await update.message.reply_text("Todavía no hay problemas guardados.")
        return

    weeks = {}
    for p in problems: weeks.setdefault(p["week_number"], []).append(p["problem_name"])
    
    text_blocks = ["📚 Club SolvIIT — Archivo de Problemas\n"]
    for w in sorted(weeks.keys(), reverse=True):
        text_blocks.append(f"🗓️ Semana {w}")
        for item in weeks[w]: text_blocks.append(f"• {item}")
        text_blocks.append("")
    await update.message.reply_text("\n".join(text_blocks))

async def delete_problems(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admin_id = os.getenv("ADMIN_TELEGRAM_ID")
    if not admin_id or user_id != str(admin_id).strip():
        await update.message.reply_text("⛔ No estás autorizado para usar este comando.")
        return

    if not context.args or len(context.args) != 1:
        await update.message.reply_text("⚠️ Uso: `/deleteproblems <semana>`", parse_mode=ParseMode.MARKDOWN)
        return

    try: week_num = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ El número de la semana debe ser un entero.")
        return

    deleted_count = delete_weekly_problems(week_num)
    if deleted_count > 0:
        await update.message.reply_text(f"🗑️ Eliminado(s) {deleted_count} problema(s) de la *Semana {week_num}*.", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(f"⚠️ No se encontraron problemas para la Semana {week_num}.")

async def slap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user
    slapper = sender.first_name or sender.username or "Alguien"
    weapon = random.choice(SLAP_WEAPONS)
    
    reply = update.message.reply_to_message
    is_real_reply = reply and not getattr(reply, "forum_topic_created", None)

    if context.args:
        target_mention = html.escape(" ".join(context.args).strip())
    elif is_real_reply:
        target_user = reply.from_user
        target_name = target_user.first_name or target_user.username or "Usuario"
        target_mention = f'<a href="tg://user?id={target_user.id}">{html.escape(target_name)}</a>'
    else:
        target_mention = f'<a href="tg://user?id={sender.id}">{html.escape(slapper)}</a>'
        
    text = f"<b>{html.escape(slapper)}</b> le da un guantazo a {target_mention} con {weapon}!"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def gay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user
    slapper = sender.first_name or sender.username or "Alguien"
    
    reply = update.message.reply_to_message
    is_real_reply = reply and not getattr(reply, "forum_topic_created", None)

    if context.args:
        target_mention = html.escape(" ".join(context.args).strip())
    elif is_real_reply:
        target_user = reply.from_user
        target_name = target_user.first_name or target_user.username or "Usuario"
        target_mention = f'<a href="tg://user?id={target_user.id}">{html.escape(target_name)}</a>'
    else:
        target_mention = f'<a href="tg://user?id={sender.id}">{html.escape(slapper)}</a>'
        
    text = f"🏳️‍🌈 <b>{html.escape(slapper)}</b> llama gay a {target_mention}, lol, que gay."
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def resolve_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id = None
    target_name = "Usuario"
    duration_minutes = 30

    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_id = target_user.id
        target_name = target_user.first_name or target_user.username or str(target_id)
        if context.args:
            try: duration_minutes = int(context.args[0])
            except ValueError: pass
        return target_id, target_name, duration_minutes, None

    if not context.args:
        return None, None, duration_minutes, "missing_args"

    first_arg = context.args[0].strip()

    if update.message.entities:
        for entity in update.message.entities:
            if entity.type == "text_mention" and entity.user:
                target_id = entity.user.id
                target_name = entity.user.first_name or entity.user.username or str(target_id)
                break

    if not target_id and first_arg.lstrip("-").isdigit():
        target_id = int(first_arg)
        member = get_member(target_id)
        if member:
            target_name = member.get("telegram_username") or member.get("leetcode_username") or f"ID {target_id}"
        else:
            target_name = f"ID {target_id}"

    if not target_id:
        bot_username = (context.bot.username or "").lower()
        clean_arg = first_arg.lstrip("@").strip().lower()
        if clean_arg in (bot_username, "solvro"):
            target_id = context.bot.id
            target_name = context.bot.first_name or "Solvro"

    if not target_id:
        member = get_member_by_username(first_arg)
        if member:
            target_id = member["telegram_id"]
            target_name = member.get("telegram_username") or member.get("leetcode_username") or f"ID {target_id}"
        else:
            return None, first_arg, duration_minutes, "not_found"

    if len(context.args) > 1:
        try: duration_minutes = int(context.args[1])
        except ValueError: pass

    return target_id, target_name, duration_minutes, None

async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admin_id = os.getenv("ADMIN_TELEGRAM_ID")
    if not admin_id or user_id != str(admin_id).strip():
        await update.message.reply_text("⛔ No tienes permiso.")
        return

    target_id, target_name, duration_minutes, error = await resolve_target_user(update, context)

    if error == "missing_args":
        await update.message.reply_text("⚠️ Uso: Responde a un mensaje con <code>/mute [mins]</code> o usa <code>/mute &lt;@usuario|usuario_leetcode|id&gt; [mins]</code>", parse_mode=ParseMode.HTML)
        return
    elif error == "not_found":
        await update.message.reply_text(f"⚠️ No se encontró a <code>{html.escape(str(target_name))}</code> en la base de datos.", parse_mode=ParseMode.HTML)
        return

    if str(target_id) == str(admin_id).strip():
        await update.message.reply_text("⚠️ ¡No puedes mutearte a ti mismo!")
        return

    duration_minutes = max(1, duration_minutes)
    mute_user(target_id, duration_seconds=duration_minutes * 60)

    if target_id != context.bot.id and update.effective_chat.type in ["group", "supergroup"]:
        until_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=duration_minutes)
        try:
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=target_id,
                permissions=MUTE_PERMISSIONS,
                until_date=until_time
            )
        except Exception as e:
            logging.error(f"Failed to natively restrict user {target_id}: {e}")

    await update.message.reply_text(
        f"🤫 <b>{html.escape(str(target_name))}</b> (ID: <code>{target_id}</code>) ha sido muteado por {duration_minutes} minutos.",
        parse_mode=ParseMode.HTML
    )

async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admin_id = os.getenv("ADMIN_TELEGRAM_ID")
    if not admin_id or user_id != str(admin_id).strip():
        await update.message.reply_text("⛔ No tienes permiso.")
        return

    target_id, target_name, _, error = await resolve_target_user(update, context)

    if error == "missing_args":
        await update.message.reply_text("⚠️ Uso: Responde a un mensaje con <code>/unmute</code> o usa <code>/unmute &lt;@usuario|usuario_leetcode|id&gt;</code>", parse_mode=ParseMode.HTML)
        return
    elif error == "not_found":
        await update.message.reply_text(f"⚠️ No se pudo encontrar a <code>{html.escape(str(target_name))}</code>.", parse_mode=ParseMode.HTML)
        return

    db_unmuted = unmute_user(target_id)

    if target_id != context.bot.id and update.effective_chat.type in ["group", "supergroup"]:
        try:
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=target_id,
                permissions=UNMUTE_PERMISSIONS
            )
        except Exception as e:
            logging.error(f"Failed to restore native permissions for {target_id}: {e}")

    if db_unmuted:
        await update.message.reply_text(f"🔊 <b>{html.escape(str(target_name))}</b> (ID: <code>{target_id}</code>) ha sido desmuteado.", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(f"🔊 Permisos nativos restaurados para <b>{html.escape(str(target_name))}</b> (ID: <code>{target_id}</code>).", parse_mode=ParseMode.HTML)

async def mutelist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    admin_id = os.getenv("ADMIN_TELEGRAM_ID")
    if not admin_id or user_id != str(admin_id).strip():
        await update.message.reply_text("⛔ No tienes permiso.")
        return

    muted = get_muted_users()
    if not muted:
        await update.message.reply_text("✅ Actualmente no hay usuarios muteados.")
        return

    now = int(time.time())
    lines = ["🔇 <b>Usuarios Muteados Actualmente:</b>\n"]
    
    for u in muted:
        tid = u["telegram_id"]
        mins_left = max(1, (u["muted_until"] - now) // 60)
        name = "Solvro (Bot Maintenance Mode)" if tid == context.bot.id else (u.get("telegram_username") or u.get("leetcode_username") or "Miembro Desconocido")
        name_clean = html.escape(str(name))
        lines.append(f"• {name_clean} (ID: <code>{tid}</code>) — {mins_left}m restantes")
        
    lines.append("\n<i>Usa <code>/unmute &lt;id&gt;</code> para restaurar sus permisos.</i>")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

async def check_mute_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    
    user = update.effective_user
    user_id = user.id
    admin_id = os.getenv("ADMIN_TELEGRAM_ID")
    is_admin = bool(admin_id and str(user_id) == str(admin_id).strip())

    if update.effective_chat.type in ["group", "supergroup"]:
        context.bot_data["main_group_id"] = update.effective_chat.id

    if user.username:
        asyncio.create_task(asyncio.to_thread(update_member_username, user_id, user.username))

    bot_muted, _ = is_user_muted(context.bot.id)
    if bot_muted and update.effective_chat.type in ["group", "supergroup"]:
        text = (update.message.text or "").strip()
        if is_admin and (text.startswith("/unmute") or text.startswith("/mutelist")):
            return
        raise ApplicationHandlerStop

    is_muted, remaining = is_user_muted(user_id)
    if is_muted:
        if update.effective_chat.type == "private":
            mins_left = max(1, remaining // 60)
            await update.message.reply_text(f"🤐 Estás silenciado. Te quedan {mins_left}m.")
        else:
            asyncio.create_task(safe_delete(update.message))
        raise ApplicationHandlerStop

    if is_admin: return

    text = update.message.text or update.message.caption or ""
    if text.startswith("/"):
        now = time.time()
        if user_id not in COMMAND_SPAM_TRACKER: COMMAND_SPAM_TRACKER[user_id] = []
        COMMAND_SPAM_TRACKER[user_id].append(now)
        COMMAND_SPAM_TRACKER[user_id] = [t for t in COMMAND_SPAM_TRACKER[user_id] if now - t <= 6]
        
        if len(COMMAND_SPAM_TRACKER[user_id]) >= 5:
            mute_user(user_id, duration_seconds=1800)
            COMMAND_SPAM_TRACKER[user_id] = []
            if update.effective_chat.type in ["group", "supergroup"]:
                until_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=30)
                try:
                    await context.bot.restrict_chat_member(
                        chat_id=update.effective_chat.id, user_id=user_id,
                        permissions=MUTE_PERMISSIONS, until_date=until_time
                    )
                except Exception: pass
            
            user_name = user.first_name or user.username or str(user_id)
            await update.message.reply_text(
                f"🛑 <b>{html.escape(user_name)}</b> ha sido muteado automáticamente por 30 minutos por hacer spam de comandos.",
                parse_mode=ParseMode.HTML
            )
            asyncio.create_task(safe_delete(update.message))
            raise ApplicationHandlerStop

async def milestone_polling_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = os.getenv("GROUP_CHAT_ID") or context.bot_data.get("main_group_id")
    if not chat_id:
        return
        
    members = get_all_members()
    spain_tz = ZoneInfo("Europe/Madrid")
    today_str = datetime.datetime.now(spain_tz).strftime('%Y-%m-%d')
    yesterday_str = (datetime.datetime.now(spain_tz) - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    yesterday_snapshots = get_all_snapshots(yesterday_str)
    
    for m in members:
        live = await asyncio.to_thread(fetch_leetcode_stats, m["leetcode_username"])
        if live:
            y_snap = yesterday_snapshots.get(m["telegram_id"])
            y_total = y_snap["total_solved"] if y_snap else m["base_total_solved"]
            await process_milestones(context, chat_id, m, live, y_total, today_str)
            await asyncio.to_thread(save_snapshot_if_not_exists, m["telegram_id"], today_str, live)
        await asyncio.sleep(1)

async def daily_snapshot_job(context: ContextTypes.DEFAULT_TYPE):
    logging.info("Starting daily snapshot job...")
    members = get_all_members()
    spain_tz = ZoneInfo("Europe/Madrid")
    today_str = datetime.datetime.now(spain_tz).strftime('%Y-%m-%d')
    for m in members:
        stats = await asyncio.to_thread(fetch_leetcode_stats, m["leetcode_username"])
        if stats:
            await asyncio.to_thread(save_snapshot, m["telegram_id"], today_str, stats)
        await asyncio.sleep(0.5)
    logging.info("Daily snapshot job completed.")

if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not found in .env")

    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    job_queue = app.job_queue
    spain_tz = ZoneInfo("Europe/Madrid")
    target_time = datetime.time(hour=23, minute=59, tzinfo=spain_tz)
    
    job_queue.run_daily(daily_snapshot_job, time=target_time)
    job_queue.run_repeating(milestone_polling_job, interval=900, first=30)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("slap", slap))
    app.add_handler(CommandHandler("gay", gay))
    app.add_handler(CommandHandler("problems", list_problems))
    app.add_handler(CommandHandler("donut", donut_command))
    
    app.add_handler(ChatMemberHandler(welcome_new_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(TypeHandler(Update, check_mute_status), group=-1)

    app.add_handler(CommandHandler("mute", mute_command))
    app.add_handler(CommandHandler("unmute", unmute_command)) 
    app.add_handler(CommandHandler("mutelist", mutelist_command))
    app.add_handler(CommandHandler("deleteproblems", delete_problems))
    app.add_handler(CommandHandler("addproblem", add_problem))

    print("Bot en línea...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)