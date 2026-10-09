import sqlite3
from typing import Optional, Dict, Any, List

DB_PATH = "data/club.db"

def init_db():
    """Initializes tables without touching existing member data."""
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
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS weekly_problems (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_number INTEGER NOT NULL,
                problem_name TEXT NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

def add_weekly_problem(week_number: int, problem_name: str) -> bool:
    """Inserts a problem for a club week if it does not already exist."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id FROM weekly_problems 
            WHERE week_number = ? AND LOWER(problem_name) = LOWER(?);
        """, (week_number, problem_name.strip()))
        
        if cursor.fetchone():
            return False  # Already exists, skip duplicate

        cursor.execute("""
            INSERT INTO weekly_problems (week_number, problem_name)
            VALUES (?, ?);
        """, (week_number, problem_name.strip()))
        conn.commit()
        return True

def get_weekly_problems(week_number: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetches problems for a specific week or all weeks if None."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if week_number is not None:
            cursor.execute("""
                SELECT week_number, problem_name, added_at 
                FROM weekly_problems 
                WHERE week_number = ? 
                ORDER BY id ASC;
            """, (week_number,))
        else:
            cursor.execute("""
                SELECT week_number, problem_name, added_at 
                FROM weekly_problems 
                ORDER BY week_number DESC, id ASC;
            """)
        return [dict(row) for row in cursor.fetchall()]

def delete_weekly_problems(week_number: int) -> int:
    """Deletes all problems for a given week and returns the count of removed items."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM weekly_problems WHERE week_number = ?;", (week_number,))
        deleted_count = cursor.rowcount
        conn.commit()
        return deleted_count