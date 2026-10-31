# handles/utils.py
import asyncio
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import RetryAfter
from telegram.ext import ContextTypes

from database import (
    get_member, 
    get_member_by_username,
    check_and_mark_milestone
)

async def safe_delete(message):
    """Safely attempts to delete a Telegram message, handling rate limits and missing permissions.

    Catches `RetryAfter` exceptions to wait out Telegram API rate-limit delays before 
    retrying once. All other deletion exceptions are swallowed and logged silently at 
    the debug level to avoid crashing calling handlers.

    Args:
        message: The Telegram `Message` object to delete. If `None` or falsy, 
            the function returns immediately without taking action.

    Note:
        - Uses `asyncio.sleep` to respect Telegram's rate-limit recommendations (`e.retry_after`).
        - Exceptions during the second attempt after a rate limit pause are ignored silently.
    """

    if not message: return
    try:
        await message.delete()
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after)
        try: await message.delete()
        except Exception: pass
    except Exception as e:
        logging.debug(f"Could not delete message: {e}")

async def resolve_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Extracts target user details and an optional duration argument from a Telegram command update.

    Resolves a target user and duration (in minutes, defaults to 30) across multiple command formats:
    1. **Reply**: User target is inferred from `update.message.reply_to_message`. Optional duration is parsed from `args[0]`.
    2. **Text Mention**: Extracted from message entities (`entity.type == "text_mention"`).
    3. **Numerical ID**: Parsed directly from integer string in `args[0]`, cross-referenced with the database.
    4. **Bot Mention**: Detects mentions of the bot itself (`@bot_username` or `'solvro'`) and returns bot metadata.
    5. **Username Lookup**: Queries the database via `get_member_by_username()` using `args[0]`.

    Args:
        update: The incoming Telegram update containing message context and entities.
        context: The callback context object containing parsed command arguments (`context.args`) 
            and bot instance metadata.

    Returns:
        tuple: A 4-element tuple containing:
            - target_id (int | None): The resolved Telegram user ID, or `None` if resolution failed.
            - target_name (str | None): Display name or identifier for the target user, or the failed search query.
            - duration_minutes (int): Extracted duration in minutes (defaults to 30).
            - error_key (str | None): Error indicator (`"missing_args"` or `"not_found"`), or `None` if successful.

    Note:
        - Database fallbacks (`get_member`, `get_member_by_username`) prioritize saved Telegram 
          usernames, then LeetCode usernames, before falling back to formatted string IDs.
        - When resolving via username or ID, the duration argument shifts to `context.args[1]`.
    """

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

async def process_milestones(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int, 
    member: dict, 
    live_stats: dict, 
    yesterday_total: int, 
    today_str: str
) -> None:
    """Evaluates and announces a member's LeetCode achievements and milestones.

    Checks for three types of milestones and posts HTML-formatted announcements to chat:
      1. Daily Solved Milestones: Triggers for every batch of 5 problems solved in 
         a single day (e.g., 5, 10, 15). Tracked per date to prevent duplicate alerts.
      2. Total Delta Milestones: Triggers for every 50 problems solved since joining 
         the club (tracked globally and across Easy/Medium/Hard difficulties).
      3. Lifetime Total Milestones: Triggers for every 50 problems solved in lifetime 
         total stats (tracked globally and across Easy/Medium/Hard difficulties).

    Args:
        context: Telegram context object used to send messages.
        chat_id: The target Telegram chat ID where announcements will be posted.
        member: Database dictionary containing member details and baseline stats.
        live_stats: Real-time LeetCode statistics dictionary from the API.
        yesterday_total: Solved count from yesterday's snapshot (or baseline fallback).
        today_str: Current date string formatted as 'YYYY-MM-DD' in local timezone.

    Note:
        - Uses `check_and_mark_milestone` as a database gatekeeper to ensure each 
          milestone threshold is awarded and announced only once.
        - Employs `asyncio.sleep(0.5)` between messages to respect Telegram API rate limits.
        - Usernames are escaped with `html.escape()` to safely handle HTML `parse_mode`.
    """

    lc_user = member["leetcode_username"]
    announcements = []

    # 1. Daily Solved Milestones (Multiples of 5)
    daily_total = live_stats["total_solved"] - yesterday_total
    daily_mult = (daily_total // 5) * 5
    if daily_mult > 0:
        if check_and_mark_milestone(member["telegram_id"], f"daily_total_{today_str}", daily_mult):
            announcements.append(f"🔥 ¡<b>{html.escape(lc_user)}</b> ha resuelto <b>{daily_mult} problemas</b> hoy!")

    # 2. Total Delta Milestones (Multiples of 50 since joining)
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

    # 3. Lifetime Total Milestones (Multiples of 50 overall on LeetCode)
    lifetime_totals = {
        "Total": live_stats["total_solved"],
        "fáciles": live_stats["easy_solved"],
        "medios": live_stats["medium_solved"],
        "difíciles": live_stats["hard_solved"]
    }

    for diff, val in lifetime_totals.items():
        mult = (val // 50) * 50
        if mult > 0:
            if check_and_mark_milestone(member["telegram_id"], f"lifetime_{diff.lower()}", mult):
                if diff == "Total":
                    announcements.append(f"🌟 ¡<b>{html.escape(lc_user)}</b> ha alcanzado los <b>{mult} problemas resueltos en total</b> en LeetCode!")
                else:
                    announcements.append(f"⭐ ¡<b>{html.escape(lc_user)}</b> ha alcanzado los <b>{mult} problemas {diff}</b> en total en LeetCode!")

    # Send queued announcements
    for msg in announcements:
        try:
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML)
            await asyncio.sleep(0.5)
        except Exception as e:
            logging.error(f"Milestone announcement failed: {e}")