import os
import asyncio
import datetime
import html
import logging
from zoneinfo import ZoneInfo
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database import (
    get_all_members,
    get_all_snapshots,
    save_snapshot_if_not_exists,
    check_and_mark_milestone
)
from leetcode import fetch_leetcode_stats
from handlers.utils import process_milestones

async def milestone_polling_job(context: ContextTypes.DEFAULT_TYPE):
    """Monitors members' LeetCode progress and posts milestone alerts to the group chat.

    Retrieves current LeetCode statistics for all registered members, compares them 
    against yesterday's recorded snapshot (or baseline values), and triggers milestone 
    processing. Also ensures a snapshot for the current day is saved in the database.

    Args:
        context: The callback context provided by python-telegram-bot's JobQueue, 
        containing bot instance data and optional global state.

    Note:
        - Chat destination is resolved from the `GROUP_CHAT_ID` environment variable 
          or `context.bot_data["main_group_id"]`; exits early if neither is found.
        - Synchronous operations (`fetch_leetcode_stats` and `save_snapshot_if_not_exists`) 
          run off the main thread using `asyncio.to_thread`.
        - Local dates for snapshot comparisons are generated in Madrid local time (`Europe/Madrid`).
        - Includes a 0.5-second delay (`asyncio.sleep(0.5)`) between processing members to 
          prevent LeetCode API rate-limiting.
    """

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
        await asyncio.sleep(0.5)