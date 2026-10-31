import asyncio
import datetime
import logging
from zoneinfo import ZoneInfo
from telegram.ext import ContextTypes

from database import get_all_members, save_snapshot
from leetcode import fetch_leetcode_stats

async def daily_snapshot_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Asynchronously fetches LeetCode statistics for all registered members 
    and saves daily snapshots to the database.

    Designed for use with python-telegram-bot's JobQueue. Iterates over all database 
    members, retrieves their LeetCode performance stats off the main thread, and records 
    a daily snapshot timestamped with the current date in the Europe/Madrid timezone.

    Args:
        context: The callback context provided by python-telegram-bot's JobQueue, 
        containing bot instance data and optional global state.

    Note:
    - Timezone: Dates are generated using the `Europe/Madrid` timezone (`%Y-%m-%d`).
    - Concurrency: Blocking I/O operations (`fetch_leetcode_stats` and `save_snapshot`) 
      are offloaded to a worker thread via `asyncio.to_thread` to prevent freezing the event loop.
    - Rate Limiting: Includes a `0.5` second asynchronous sleep between member processing 
      to avoid triggering LeetCode API rate limits.
    """

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

