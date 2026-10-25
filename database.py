import sqlite3
import time
from typing import Optional, Dict, Any, List

DB_PATH = "data/club.db"

def init_db():
    """Initializes tables without touching existing member data."""
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        
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

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS muted_users (
                telegram_id INTEGER PRIMARY KEY,
                muted_until INTEGER NOT NULL
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_snapshots (
                telegram_id INTEGER,
                snapshot_date TEXT,
                total_solved INTEGER,
                easy_solved INTEGER,
                medium_solved INTEGER,
                hard_solved INTEGER,
                contest_rating REAL,
                PRIMARY KEY (telegram_id, snapshot_date)
            );
        """)

        # New table for milestone tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS announced_milestones (
                telegram_id INTEGER,
                milestone_type TEXT,
                milestone_value INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (telegram_id, milestone_type, milestone_value)
            );
        """)

        conn.commit()

def register_member(telegram_id: int, tg_username: str, stats: Dict[str, Any]) -> tuple[bool, str]:
    clean_tg = tg_username.lstrip("@").strip() if tg_username else ""
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT leetcode_username FROM members WHERE telegram_id = ?;", (telegram_id,))
        existing_user = cursor.fetchone()
        if existing_user:
            return False, f"You are already registered with handle `{existing_user[0]}`! Baselines cannot be reset."

        cursor.execute("SELECT telegram_username FROM members WHERE LOWER(leetcode_username) = LOWER(?);", (stats["username"],))
        existing_handle = cursor.fetchone()
        if existing_handle:
            return False, f"Handle `{stats['username']}` is already linked to another user."

        cursor.execute("""
            INSERT INTO members (
                telegram_id, telegram_username, leetcode_username,
                base_total_solved, base_easy_solved, base_medium_solved, base_hard_solved, base_contest_rating
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            telegram_id, clean_tg, stats["username"], stats["total_solved"],
            stats["easy_solved"], stats["medium_solved"], stats["hard_solved"], stats["contest_rating"]
        ))
        conn.commit()
        return True, "OK"

def update_member_baselines(telegram_id: int, tg_username: str, stats: Dict[str, Any]) -> tuple[bool, str]:
    clean_tg = tg_username.lstrip("@").strip() if tg_username else ""
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id FROM members WHERE LOWER(leetcode_username) = LOWER(?);", (stats["username"],))
        existing_handle = cursor.fetchone()
        if existing_handle and existing_handle[0] != telegram_id:
            return False, f"Handle `{stats['username']}` is already linked to another user."
        
        cursor.execute("""
            UPDATE members SET 
                telegram_username = ?,
                leetcode_username = ?,
                base_total_solved = ?,
                base_easy_solved = ?,
                base_medium_solved = ?,
                base_hard_solved = ?,
                base_contest_rating = ?
            WHERE telegram_id = ?;
        """, (
            clean_tg, stats["username"], stats["total_solved"],
            stats["easy_solved"], stats["medium_solved"], stats["hard_solved"], stats["contest_rating"],
            telegram_id
        ))
        cursor.execute("DELETE FROM daily_snapshots WHERE telegram_id = ?;", (telegram_id,))
        conn.commit()
        return True, "OK"
        
def update_member_username(telegram_id: int, tg_username: str):
    if not tg_username:
        return
    clean_tg = tg_username.lstrip("@").strip()
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE members SET telegram_username = ? WHERE telegram_id = ? AND telegram_username != ?;",
            (clean_tg, telegram_id, clean_tg)
        )
        conn.commit()

def get_member(telegram_id: int) -> Optional[Dict[str, Any]]:
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM members WHERE telegram_id = ?;", (telegram_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_all_members() -> List[Dict[str, Any]]:
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM members;")
        return [dict(row) for row in cursor.fetchall()]

def add_weekly_problem(week_number: int, problem_name: str) -> bool:
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id FROM weekly_problems 
            WHERE week_number = ? AND LOWER(problem_name) = LOWER(?);
        """, (week_number, problem_name.strip()))
        if cursor.fetchone():
            return False

        cursor.execute("""
            INSERT INTO weekly_problems (week_number, problem_name)
            VALUES (?, ?);
        """, (week_number, problem_name.strip()))
        conn.commit()
        return True

def get_weekly_problems(week_number: Optional[int] = None) -> List[Dict[str, Any]]:
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
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
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM weekly_problems WHERE week_number = ?;", (week_number,))
        deleted_count = cursor.rowcount
        conn.commit()
        return deleted_count

def mute_user(telegram_id: int, duration_seconds: int = 1800):
    muted_until = int(time.time()) + duration_seconds
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO muted_users (telegram_id, muted_until)
            VALUES (?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET muted_until = excluded.muted_until;
        """, (telegram_id, muted_until))
        conn.commit()

def is_user_muted(telegram_id: int) -> tuple[bool, int]:
    now = int(time.time())
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT muted_until FROM muted_users WHERE telegram_id = ?;", (telegram_id,))
        row = cursor.fetchone()
        if not row:
            return False, 0
        
        muted_until = row[0]
        if now < muted_until:
            return True, muted_until - now
        else:
            cursor.execute("DELETE FROM muted_users WHERE telegram_id = ?;", (telegram_id,))
            conn.commit()
            return False, 0

def save_snapshot(telegram_id: int, date_str: str, stats: Dict[str, Any]):
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO daily_snapshots (
                telegram_id, snapshot_date, total_solved, easy_solved, medium_solved, hard_solved, contest_rating
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id, snapshot_date) DO UPDATE SET
                total_solved = excluded.total_solved,
                easy_solved = excluded.easy_solved,
                medium_solved = excluded.medium_solved,
                hard_solved = excluded.hard_solved,
                contest_rating = excluded.contest_rating;
        """, (
            telegram_id, date_str, stats["total_solved"], stats["easy_solved"],
            stats["medium_solved"], stats["hard_solved"], stats["contest_rating"]
        ))
        conn.commit()

def save_snapshot_if_not_exists(telegram_id: int, date_str: str, stats: Dict[str, Any]):
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO daily_snapshots (
                telegram_id, snapshot_date, total_solved, easy_solved, medium_solved, hard_solved, contest_rating
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (
            telegram_id, date_str, stats["total_solved"], stats["easy_solved"],
            stats["medium_solved"], stats["hard_solved"], stats["contest_rating"]
        ))
        conn.commit()
        
def get_all_snapshots(date_str: str) -> Dict[int, Dict[str, Any]]:
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM daily_snapshots WHERE snapshot_date = ?;", (date_str,))
        return {row["telegram_id"]: dict(row) for row in cursor.fetchall()}

def unmute_user(telegram_id: int) -> bool:
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM muted_users WHERE telegram_id = ?;", (telegram_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted

def get_member_by_username(username: str) -> Optional[Dict[str, Any]]:
    clean = username.lstrip("@").strip().lower()
    if not clean:
        return None
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM members;")
        for r in cursor.fetchall():
            tg_name = (r["telegram_username"] or "").lstrip("@").strip().lower()
            lc_name = (r["leetcode_username"] or "").strip().lower()
            if clean in (tg_name, lc_name):
                return dict(r)
        return None
        
def get_muted_users() -> List[Dict[str, Any]]:
    now = int(time.time())
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("DELETE FROM muted_users WHERE muted_until <= ?;", (now,))
        conn.commit()
        cursor.execute("""
            SELECT mu.telegram_id, mu.muted_until, m.telegram_username, m.leetcode_username
            FROM muted_users mu
            LEFT JOIN members m ON mu.telegram_id = m.telegram_id
            ORDER BY mu.muted_until ASC;
        """)
        return [dict(row) for row in cursor.fetchall()]

def check_and_mark_milestone(telegram_id: int, m_type: str, m_value: int) -> bool:
    """Returns True if the milestone is new and needs announcing, False if it was already announced."""
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM announced_milestones 
            WHERE telegram_id = ? AND milestone_type = ? AND milestone_value = ?;
        """, (telegram_id, m_type, m_value))
        if cursor.fetchone():
            return False
            
        cursor.execute("""
            INSERT INTO announced_milestones (telegram_id, milestone_type, milestone_value)
            VALUES (?, ?, ?);
        """, (telegram_id, m_type, m_value))
        conn.commit()
        return True