# jobs/weekly_chart.py
import io
import os
import datetime
import time  
import asyncio
from zoneinfo import ZoneInfo
from typing import Optional
from telegram.ext import ContextTypes

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for headless server operation
import matplotlib.pyplot as plt

from database import get_all_members, get_snapshots_for_date_range
from leetcode import fetch_leetcode_stats
from handlers.utils import calculate_points

DAYS = ["Inicio", "L", "M", "X", "J", "V", "S", "D"]

def generate_points_chart() -> Optional[io.BytesIO]:
    """Generates a line chart PNG representing members' weekly points progression.

    Queries daily database snapshots starting from the pre-week baseline at index 0 
    through the current date, calculates accumulated points relative to the baseline 
    (1 point Easy, 2 points Medium, 3 points Hard), and renders a line plot across 
    an 8-tick scale (Inicio to D).
    """
    spain_tz = ZoneInfo("Europe/Madrid")
    now = datetime.datetime.now(spain_tz)
    today_str = now.strftime('%Y-%m-%d')
    
    weekday = now.weekday()  # Monday = 0, Sunday = 6
    if weekday == 0 and now.hour < 12:
        monday = (now - datetime.timedelta(days=7)).date()
        target_days_count = 7
    else:
        monday = (now - datetime.timedelta(days=weekday)).date()
        target_days_count = weekday + 1

    # Fetch Sunday (pre-week) date for accurate Monday baseline comparison
    sunday_before = (monday - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    dates = [(monday + datetime.timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
    active_dates = dates[:target_days_count]

    members = get_all_members()
    if not members:
        return None

    # Fetch snapshots starting from Sunday prior to Monday
    raw_snaps = get_snapshots_for_date_range(sunday_before, active_dates[-1])
    
    snap_map = {}
    for s in raw_snaps:
        snap_map.setdefault(s["telegram_id"], {})[s["snapshot_date"]] = s

    fig, ax = plt.subplots(figsize=(8, 5))

    # Distinct styles and markers so overlapping paths remain visible
    line_styles = ['-', '--', '-.', ':']
    markers = ['o', 's', '^', 'D', 'v', 'P', '*', 'X']
    
    active_member_idx = 0

    for m in members:
        tid = m["telegram_id"]
        name = m["leetcode_username"]
        m_snaps = snap_map.get(tid, {})
        
        sun_snap = m_snaps.get(sunday_before)
        if sun_snap:
            base_pts = calculate_points(sun_snap["easy_solved"], sun_snap["medium_solved"], sun_snap["hard_solved"])
        else:
            base_pts = calculate_points(m["base_easy_solved"], m["base_medium_solved"], m["base_hard_solved"])

        points_y = [0]
        last_known_pts = base_pts

        for d_str in active_dates:
            if d_str == today_str:
                live = fetch_leetcode_stats(name)
                if live:
                    pts = calculate_points(live["easy_solved"], live["medium_solved"], live["hard_solved"])
                    time.sleep(0.5)
                else:
                    snap = m_snaps.get(d_str)
                    pts = calculate_points(snap["easy_solved"], snap["medium_solved"], snap["hard_solved"]) if snap else last_known_pts
            else:
                snap = m_snaps.get(d_str)
                if snap:
                    pts = calculate_points(snap["easy_solved"], snap["medium_solved"], snap["hard_solved"])
                else:
                    pts = last_known_pts
            
            last_known_pts = pts
            points_y.append(max(0, pts - base_pts))

        if max(points_y) == 0:
            continue

        # Tiny vertical micro-offset (e.g., ±0.08 pts) so identical lines sit side-by-side instead of hiding each other
        jitter = (active_member_idx % 3 - 1) * 0.08
        plotted_y = [y + jitter if y > 0 else 0 for y in points_y]

        style = line_styles[active_member_idx % len(line_styles)]
        marker = markers[active_member_idx % len(markers)]

        x_indices = list(range(len(plotted_y)))
        ax.plot(
            x_indices, 
            plotted_y, 
            linestyle=style,
            marker=marker, 
            markersize=7,
            linewidth=2.2, 
            alpha=0.88,
            label=f"{name} ({points_y[-1]} pts)"  # Also shows current score right in the legend
        )
        active_member_idx += 1

    # Style graph
    ax.set_xticks(range(8))
    ax.set_xticklabels(DAYS, fontsize=11, fontweight='bold')
    ax.set_ylabel("Points", fontsize=11, fontweight='bold', color='gold', rotation=0, labelpad=25)
    ax.set_xlabel("Día", fontsize=10, fontweight='bold', color='gold', labelpad=10)
    ax.yaxis.set_label_position("left")
    
    # Clean borders
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_linewidth(2)
    ax.spines['bottom'].set_linewidth(2)
    
    # Collect all points plotted across all active lines
    all_points = [pt for line in ax.lines for pt in line.get_ydata()]
    max_pts = max(all_points) if all_points else 0

    # Give ~20% vertical padding above the highest score, keeping a minimum top of 5
    top_limit = max(5, int(max_pts * 1.2) + 1)
    
    ax.set_ylim(bottom=0, top=top_limit)
    ax.grid(True, linestyle='--', alpha=0.3)
    ax.legend(loc='upper left', frameon=False)

    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png', dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf

async def daily_chart_job(context: ContextTypes.DEFAULT_TYPE):
    """Executes a scheduled daily task to post the weekly points chart to the group chat.

    Designed for use with python-telegram-bot's JobQueue (configured for 8:00 AM Europe/Madrid). 
    Offloads Matplotlib image rendering off the main thread via `asyncio.to_thread` 
    and broadcasts the result as a Telegram photo message.

    Args:
        context: The callback context provided by python-telegram-bot's JobQueue, 
            containing bot instance data and optional global state.

    Note:
        - Resolves chat destination from the `GROUP_CHAT_ID` environment variable 
          or `context.bot_data["main_group_id"]`; exits silently if neither is set.
        - Formats the photo caption using HTML (`parse_mode="HTML"`).
    """

    chat_id = os.getenv("GROUP_CHAT_ID") or context.bot_data.get("main_group_id")
    if not chat_id:
        return

    buf = await asyncio.to_thread(generate_points_chart)
    if buf:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=buf,
            caption="📊 <b>Puntos acumulados esta semana (1 pt Easy | 2 pts Med | 3 pts Hard)</b>",
            parse_mode="HTML"
        )