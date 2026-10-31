# handlers/admin.py
import asyncio
import html
import datetime
import logging
import time
import os 

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ApplicationHandlerStop

from config import MUTE_PERMISSIONS, UNMUTE_PERMISSIONS, COMMAND_SPAM_TRACKER
from handlers.utils import (
    safe_delete, 
    resolve_target_user
)
from database import (
    add_weekly_problem,
    delete_weekly_problems,
    mute_user,
    unmute_user,
    get_muted_users,
    is_user_muted,
    update_member_username
)

async def add_problem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adds a new problem to a specified weekly challenge set in the database.

    Restricted strictly to the designated administrator (`ADMIN_TELEGRAM_ID`). 
    Parses the week number from the first command argument and concatenates all 
    remaining arguments into the problem title or link.

    Args:
        update: The incoming Telegram update containing message context.
        context: Context object containing command arguments (`context.args`).

    Note:
        - Rejects requests from non-admin users with an authorization error message.
        - Returns a warning message if the problem title already exists for that week.
    """

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
    


async def delete_problem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deletes all recorded problems for a specific week from the database.

    Restricted strictly to the designated administrator (`ADMIN_TELEGRAM_ID`). 
    Requires exactly one integer argument representing the week number.

    Args:
        update: The incoming Telegram update containing message context.
        context: Context object containing command arguments (`context.args`).

    Note:
        - Formats response messages using Markdown parsing mode (`ParseMode.MARKDOWN`).
        - Informs the caller if no problems were registered under the provided week number.
    """

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



async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mutes a specified user in both the local database and native Telegram group permissions.

    Restricted to the bot administrator (`ADMIN_TELEGRAM_ID`). Resolves the target user 
    and mute duration (in minutes, defaulting to 30) via `resolve_target_user`. Restricts 
    native group chat permissions using `MUTE_PERMISSIONS` if executed in a group context.

    Args:
        update: The incoming Telegram update containing message context.
        context: Context object containing parsed command arguments and bot methods.

    Note:
        - Prevents the administrator from muting their own user ID.
        - Enforces a minimum mute duration of 1 minute.
        - Catches and logs native permission restriction failures gracefully.
    """

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
    """Restores full privileges to a previously muted user in the database and Telegram chat.

    Restricted to the bot administrator (`ADMIN_TELEGRAM_ID`). Resolves the target 
    user via `resolve_target_user`, clears their muted status in the database, and 
    restores native group posting permissions using `UNMUTE_PERMISSIONS`.

    Args:
        update: The incoming Telegram update containing message context.
        context: Context object containing parsed command arguments and bot methods.

    Note:
        - Differentiates feedback messages based on whether the user was actively 
          muted in the local database or only required native permission restoration.
    """

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
    """Displays an HTML-formatted list of all currently muted users and their remaining durations.

    Restricted to the bot administrator (`ADMIN_TELEGRAM_ID`). Queries the local database 
    for active mutes, calculates remaining durations relative to the current timestamp, 
    and outputs a formatted list with user identifiers.

    Args:
        update: The incoming Telegram update containing message context.
        context: Context object containing active bot state.

    Note:
        - Formats the list using HTML (`ParseMode.HTML`).
        - Displays a distinct label ("Solvro (Bot Maintenance Mode)") when the bot itself is muted.
    """

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
    """Middleware handler that enforces active mutes, command anti-spam protection, and bot status.

    Acts as an entry-point check for incoming updates:
    1. **Context Update**: Saves active group chat ID and updates user Telegram usernames in the database background.
    2. **Maintenance Mode**: Halts group processing if the bot itself is muted (unless overridden by an admin command).
    3. **Mute Enforcement**: Silently deletes group messages or warns private chat users if they are currently muted.
    4. **Anti-Spam Check**: Tracks command frequency for non-admin users (>=5 commands within 6 seconds) 
       and automatically mutes violators for 30 minutes.

    Args:
        update: The incoming Telegram update containing user and chat metadata.
        context: Context object containing bot data and command tracking state.

    Raises:
        ApplicationHandlerStop: Stops the python-telegram-bot handler chain if the user is muted, 
            the bot is maintenance-locked, or an anti-spam mute was triggered.

    Note:
        - Background tasks (`update_member_username`, `safe_delete`) are dispatched via `asyncio.create_task`.
        - Tracks user command frequency in `COMMAND_SPAM_TRACKER` over a sliding 6-second window.
    """

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