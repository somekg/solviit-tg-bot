import sqlite3
from typing import Optional, Dict, Any

DB_PATH = "data/club.db"

def init_db():
    """Initializes tables for members and weekly snapshot baselines."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS members (
                telegram_id INTEGER PRIMARY KEY,
                telegram_username TEXT,
                leetcode_username TEXT UNIQUE NOT NULL,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                total_solved INTEGER NOT NULL,
                easy_solved INTEGER NOT NULL,
                medium_solved INTEGER NOT NULL,
                hard_solved INTEGER NOT NULL,
                contest_rating REAL DEFAULT 0.0,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (telegram_id) REFERENCES members(telegram_id) ON DELETE CASCADE
            );
        """)
        conn.commit()

def add_member(telegram_id: int, tg_username: str, leetcode_username: str):
    """Inserts or updates a member."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO members (telegram_id, telegram_username, leetcode_username)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                leetcode_username = excluded.leetcode_username,
                telegram_username = excluded.telegram_username;
        """, (telegram_id, tg_username, leetcode_username))
        conn.commit()

def save_snapshot(telegram_id: int, stats: Dict[str, Any]):
    """Records a fresh snapshot (used on registration and weekly reset)."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO snapshots (
                telegram_id, total_solved, easy_solved, medium_solved, hard_solved, contest_rating
            ) VALUES (?, ?, ?, ?, ?, ?);
        """, (
            telegram_id,
            stats["total_solved"],
            stats["easy_solved"],
            stats["medium_solved"],
            stats["hard_solved"],
            stats["contest_rating"]
        ))
        conn.commit()

def get_baseline_snapshot(telegram_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves the latest recorded baseline snapshot for a user."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT total_solved, easy_solved, medium_solved, hard_solved, contest_rating
            FROM snapshots
            WHERE telegram_id = ?
            ORDER BY recorded_at DESC LIMIT 1;
        """, (telegram_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_all_members():
    """Fetches all registered handles."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id, leetcode_username, telegram_username FROM members;")
        return cursor.fetchall()

def get_member(telegram_id: int):
    """Fetches a single member by their Telegram ID."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id, telegram_username, leetcode_username FROM members WHERE telegram_id = ?;", (telegram_id,))
        row = cursor.fetchone()
        return dict(row) if row else None