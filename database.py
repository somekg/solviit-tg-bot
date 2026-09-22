import sqlite3
from typing import Optional, Dict, Any, List

DB_PATH = "data/club.db"

def init_db():
    """Initializes table for members with registration baselines."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS members (
                telegram_id INTEGER PRIMARY KEY,
                telegram_username TEXT,
                leetcode_username TEXT UNIQUE NOT NULL,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                base_total_solved INTEGER NOT NULL,
                base_easy_solved INTEGER NOT NULL,
                base_medium_solved INTEGER NOT NULL,
                base_hard_solved INTEGER NOT NULL,
                base_contest_rating REAL DEFAULT 0.0
            );
        """)
        conn.commit()

def register_member(telegram_id: int, tg_username: str, stats: Dict[str, Any]) -> tuple[bool, str]:
    """
    Registers a member with their starting baseline.
    Returns (True, "OK") if registered successfully.
    Returns (False, error_reason) if user or handle already exists.
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # 1. Check if this Telegram account is already registered
        cursor.execute("SELECT leetcode_username FROM members WHERE telegram_id = ?;", (telegram_id,))
        existing_user = cursor.fetchone()
        if existing_user:
            return False, f"You are already registered with handle `{existing_user[0]}`! Baselines cannot be reset."

        # 2. Check if the LeetCode handle is already registered by someone else
        cursor.execute("SELECT telegram_username FROM members WHERE LOWER(leetcode_username) = LOWER(?);", (stats["username"],))
        existing_handle = cursor.fetchone()
        if existing_handle:
            return False, f"Handle `{stats['username']}` is already linked to another user."

        # 3. Insert fresh registration
        cursor.execute("""
            INSERT INTO members (
                telegram_id, telegram_username, leetcode_username,
                base_total_solved, base_easy_solved, base_medium_solved, base_hard_solved, base_contest_rating
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            telegram_id,
            tg_username,
            stats["username"],
            stats["total_solved"],
            stats["easy_solved"],
            stats["medium_solved"],
            stats["hard_solved"],
            stats["contest_rating"]
        ))
        conn.commit()
        return True, "OK"
        

def get_member(telegram_id: int) -> Optional[Dict[str, Any]]:
    """Fetches a single member by Telegram ID."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM members WHERE telegram_id = ?;", (telegram_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_all_members() -> List[Dict[str, Any]]:
    """Fetches all registered members."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM members;")
        return [dict(row) for row in cursor.fetchall()]