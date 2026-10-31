# main.py
import datetime
import logging
from zoneinfo import ZoneInfo
from telegram.ext import ApplicationBuilder

from config import TOKEN
from database import init_db
from handlers import register_all_handlers
from jobs.milestones import milestone_polling_job
from jobs.daily_snapshot import daily_snapshot_job

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)

def main():
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables.")

    # Initialize SQLite Database
    init_db()

    # Build Application
    app = ApplicationBuilder().token(TOKEN).build()

    # Register Handlers
    register_all_handlers(app)

    # Schedule Jobs
    spain_tz = ZoneInfo("Europe/Madrid")
    target_time = datetime.time(hour=23, minute=59, tzinfo=spain_tz)
    
    app.job_queue.run_daily(daily_snapshot_job, time=target_time)
    app.job_queue.run_repeating(milestone_polling_job, interval=900, first=30)

    print("Bot en línea...")
    app.run_polling()

if __name__ == "__main__":
    main()