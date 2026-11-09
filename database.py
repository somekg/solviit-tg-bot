import sqlite3
import time
from typing import Optional, Dict, Any, List, Tuple

DB_PATH = "data/club.db"

def init_db() -> None:
    """Initializes the SQLite database schema and enables Write-Ahead Logging (WAL) mode.

    Creates necessary tables (`members`, `weekly_problems`, `muted_users`, `daily_snapshots`, 
    `announced_milestones`) if they do not already exist without touching pre-existing data.

    Note:
        - Sets PRAGMA journal_mode=WAL for optimized concurrent reads and writes.
        - Enforces unique constraints on LeetCode handles and composite keys for snapshots/milestones.
    """
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

def get_snapshots_for_date_range(start_date_str: str, end_date_str: str) -> List[Dict[str, Any]]:
    """Retrieves all daily member snapshots within a specified date range (inclusive).

    Queries the `daily_snapshots` table for records created on or between `start_date_str` 
    and `end_date_str`, ordered chronologically by snapshot date.

    Args:
        start_date_str: Starting date string in 'YYYY-MM-DD' format.
        end_date_str: Ending date string in 'YYYY-MM-DD' format.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries representing snapshot rows with 
        keys `telegram_id`, `snapshot_date`, `total_solved`, `easy_solved`, `medium_solved`, 
        and `hard_solved`.
    """
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT telegram_id, snapshot_date, total_solved, easy_solved, medium_solved, hard_solved
            FROM daily_snapshots
            WHERE snapshot_date >= ? AND snapshot_date <= ?
            ORDER BY snapshot_date ASC;
        """, (start_date_str, end_date_str))
        return [dict(row) for row in cursor.fetchall()]
    
def register_member(telegram_id: int, tg_username: str, stats: Dict[str, Any]) -> Tuple[bool, str]:
    """Registers a new user in the database and stores their initial baseline stats.

    Validates that neither the Telegram ID nor the case-insensitive LeetCode username 
    is already linked to another member before inserting a new record.

    Args:
        telegram_id: The Telegram user ID to register.
        tg_username: The Telegram handle or display name of the user.
        stats: Dictionary containing live LeetCode stats (`username`, `total_solved`, 
            `easy_solved`, `medium_solved`, `hard_solved`, `contest_rating`).

    Returns:
        Tuple[bool, str]: A tuple containing:
            - success (bool): True if registration succeeded, False otherwise.
            - message (str): "OK" on success, or an error explanation string.
    """
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

def update_member_baselines(telegram_id: int, tg_username: str, stats: Dict[str, Any]) -> Tuple[bool, str]:
    """Updates an existing member's handle, resets baseline stats, and clears historical snapshots.

    Executed during re-registration (`/register <user> confirm`). Checks if the target 
    LeetCode handle is available, updates baseline statistics to current values, 
    and wipes `daily_snapshots` history for the user.

    Args:
        telegram_id: The Telegram user ID being updated.
        tg_username: The Telegram handle or display name of the user.
        stats: Dictionary containing current LeetCode performance statistics.

    Returns:
        Tuple[bool, str]: A tuple containing:
            - success (bool): True if baselines were successfully updated, False otherwise.
            - message (str): "OK" on success, or an error explanation string.
    """
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
        
def update_member_username(telegram_id: int, tg_username: str) -> None:
    """Updates a registered member's saved Telegram username in the database.

    Synchronizes changes to a user's Telegram `@username` when detected during 
    command execution or group interactions.

    Args:
        telegram_id: The Telegram user ID whose username needs updating.
        tg_username: The new Telegram handle to persist.
    """
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
    """Fetches a member's record by their Telegram ID.

    Args:
        telegram_id: The numeric Telegram ID of the member.

    Returns:
        Optional[Dict[str, Any]]: Dictionary containing database row columns if found, 
        or `None` if the member is not registered.
    """
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM members WHERE telegram_id = ?;", (telegram_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_all_members() -> List[Dict[str, Any]]:
    """Retrieves records for all registered club members.

    Returns:
        List[Dict[str, Any]]: List of dictionary objects representing all rows in `members`.
    """
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM members;")
        return [dict(row) for row in cursor.fetchall()]

def add_weekly_problem(week_number: int, problem_name: str) -> bool:
    """Inserts a new challenge problem for a specific week into the database.

    Checks for case-insensitive duplicate problem entries within the specified week 
    prior to insertion.

    Args:
        week_number: Integer week identifier (e.g., 1, 2, 3).
        problem_name: Problem title or URL link string.

    Returns:
        bool: True if inserted successfully, False if duplicate entry exists.
    """
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
    """Retrieves weekly challenge problems filtered by week number or all history.

    Args:
        week_number: Optional integer week identifier. If `None`, returns all recorded 
            weekly problems ordered descending by week.

    Returns:
        List[Dict[str, Any]]: List of dictionary rows with keys `week_number`, 
        `problem_name`, and `added_at`.
    """
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
    """Deletes all problem entries recorded for a given week.

    Args:
        week_number: The target week integer to remove.

    Returns:
        int: Total number of deleted problem records.
    """
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM weekly_problems WHERE week_number = ?;", (week_number,))
        deleted_count = cursor.rowcount
        conn.commit()
        return deleted_count

def mute_user(telegram_id: int, duration_seconds: int = 1800) -> None:
    """Mutes a Telegram user in the local database until a future timestamp.

    Updates existing mute expiration if the user is already muted (upsert logic).

    Args:
        telegram_id: Target user Telegram ID.
        duration_seconds: Mute duration in seconds (defaults to 1800 / 30 mins).
    """
    muted_until = int(time.time()) + duration_seconds
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO muted_users (telegram_id, muted_until)
            VALUES (?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET muted_until = excluded.muted_until;
        """, (telegram_id, muted_until))
        conn.commit()

def is_user_muted(telegram_id: int) -> Tuple[bool, int]:
    """Checks whether a user is currently muted in the database.

    Automatically removes expired mute entries from the database upon query.

    Args:
        telegram_id: Target Telegram user ID to verify.

    Returns:
        Tuple[bool, int]: A tuple containing:
            - is_muted (bool): True if actively muted, False otherwise.
            - remaining_seconds (int): Seconds remaining until mute expires (0 if not muted).
    """
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

def save_snapshot(telegram_id: int, date_str: str, stats: Dict[str, Any]) -> None:
    """Saves or updates a daily performance snapshot for a user.

    Overwrites existing snapshot metrics if a record already exists for the given date (upsert).

    Args:
        telegram_id: User's Telegram ID.
        date_str: Date string formatted as 'YYYY-MM-DD'.
        stats: Dictionary containing total, easy, medium, hard solved counts, and rating.
    """
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

def save_snapshot_if_not_exists(telegram_id: int, date_str: str, stats: Dict[str, Any]) -> None:
    """Saves a daily performance snapshot for a user only if one does not exist for the given date.

    Ignores insertion if a snapshot already exists (preserves earliest snapshot of the day).

    Args:
        telegram_id: User's Telegram ID.
        date_str: Date string formatted as 'YYYY-MM-DD'.
        stats: Dictionary containing total, easy, medium, hard solved counts, and rating.
    """
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
    """Retrieves all daily member snapshots for a specific date string.

    Args:
        date_str: Target date string formatted as 'YYYY-MM-DD'.

    Returns:
        Dict[int, Dict[str, Any]]: Dictionary mapping user `telegram_id` to their 
        snapshot data row.
    """
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM daily_snapshots WHERE snapshot_date = ?;", (date_str,))
        return {row["telegram_id"]: dict(row) for row in cursor.fetchall()}

def unmute_user(telegram_id: int) -> bool:
    """Removes a user's muted record from the database.

    Args:
        telegram_id: Target Telegram user ID to unmute.

    Returns:
        bool: True if an active mute entry was deleted, False if user was not muted.
    """
    with sqlite3.connect(DB_PATH, timeout=15) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM muted_users WHERE telegram_id = ?;", (telegram_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted

def get_member_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Finds a member record by matching either their Telegram or LeetCode username.

    Performs case-insensitive matching against stripped handles.

    Args:
        username: Target handle or name to query (with or without leading '@').

    Returns:
        Optional[Dict[str, Any]]: Member record dictionary if found, or `None`.
    """
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
    """Cleans up expired mutes and returns all currently active muted users.

    Joins `muted_users` with `members` to include associated usernames.

    Returns:
        List[Dict[str, Any]]: List of dictionary objects containing `telegram_id`, 
        `muted_until`, `telegram_username`, and `leetcode_username` sorted by expiration.
    """
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
    """Verifies whether a milestone achievement is new and records it to avoid re-announcing.

    Queries the `announced_milestones` table for an existing record matching the composite 
    key (`telegram_id`, `milestone_type`, `milestone_value`). If unrecorded, inserts the entry.

    Args:
        telegram_id: Target Telegram user ID.
        m_type: Milestone identifier string (e.g., 'daily_total_2026-10-31', 'delta_total').
        m_value: Reached numerical milestone value (e.g., 5, 50, 100).

    Returns:
        bool: True if the milestone was unannounced and has now been recorded, 
        False if it was already announced previously.
    """
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