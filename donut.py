import math
import html
import asyncio
import logging
import os
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

def generate_donut(A, B):
    """Calculates a 3D ASCII donut projection scaled for mobile Telegram."""
    width, height = 40, 20
    output = [' '] * (width * height)
    zbuffer = [0.0] * (width * height)
    
    for j in range(0, 628, 10):
        theta = j / 100
        costheta, sintheta = math.cos(theta), math.sin(theta)
        for i in range(0, 628, 4):
            phi = i / 100
            cosphi, sinphi = math.cos(phi), math.sin(phi)
            
            circlex = 2 + costheta
            circley = sintheta
            
            x = circlex * (math.cos(B) * cosphi + math.sin(A) * math.sin(B) * sinphi) - circley * math.cos(A) * math.sin(B)
            y = circlex * (math.sin(B) * cosphi - math.sin(A) * math.cos(B) * sinphi) + circley * math.cos(A) * math.cos(B)
            z = 1 / (circlex * math.cos(A) * sinphi + circley * math.sin(A) + 5)
            t = cosphi * costheta * math.sin(B) - math.cos(A) * costheta * sinphi - math.sin(A) * sintheta
            
            # Adjusted scale multipliers
            x_idx = int(width / 2 + 18 * x * z)
            y_idx = int(height / 2 + 9 * y * z)
            
            idx = x_idx + width * y_idx
            if 0 <= x_idx < width and 0 <= y_idx < height:
                if z > zbuffer[idx]:
                    zbuffer[idx] = z
                    chars = ".,-~:;=!*#$@"
                    luminance_idx = int(t * 8)
                    output[idx] = chars[max(0, min(11, luminance_idx))]
                    
    # Construct a rigid bordered frame to prevent Telegram from collapsing empty lines
    lines = []
    lines.append("┌" + "─" * width + "┐")
    for k in range(0, len(output), width):
        lines.append("│" + "".join(output[k:k+width]) + "│")
    lines.append("└" + "─" * width + "┘")
    
    return "\n".join(lines)

async def donut_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    '''
    admin_id = os.getenv("ADMIN_TELEGRAM_ID")
    
    # 1. Admin-only restriction
    if not admin_id or user_id != str(admin_id).strip():
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return
    '''
    
    # 2. Selectable length between 1 and 60
    duration = 5
    if context.args:
        try:
            duration = int(context.args[0])
            duration = max(1, min(60, duration))
        except ValueError:
            await update.message.reply_text("⚠️ Usage: /donut [seconds (1-60)]")
            return

    msg = await update.message.reply_text("🍩 <i>Preparing oven...</i>", parse_mode=ParseMode.HTML)
    A, B = 0.0, 0.0
    
    # 3. Animation loop (locked to ~1 FPS due to Telegram API limits)
    for _ in range(duration):
        frame = generate_donut(A, B)
        # Add a static title outside the block so the layout stays anchored
        text = f"🍩 <b>Spinning Donut ({duration}s)</b>\n<pre>{html.escape(frame)}</pre>"
        
        try:
            await msg.edit_text(text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logging.debug(f"Donut edit failed: {e}")
            
        A += 0.5
        B += 0.3
        
        # 1-second pause to safely respect Telegram's rate limit
        await asyncio.sleep(1)
        
    final_text = f"🍩 <b>Donut stopped spinning.</b>\n<pre>{html.escape(frame)}</pre>"
    try:
        await msg.edit_text(final_text, parse_mode=ParseMode.HTML)
    except Exception:
        pass