# handlers/chart.py 

import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from jobs.weekly_chart import generate_points_chart

async def chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generates and replies with the current week's points progress line chart on demand.

    Sends a temporary loading message, generates the current week's Mon–Sun points graph 
    off the main thread using `generate_points_chart()`, deletes the loading message, 
    and replies with the resulting image.

    Args:
        update: The incoming Telegram update containing user and chat metadata.
        context: Context object containing active bot state and job context.

    Note:
        - Offloads blocking graphic creation to a worker thread via `asyncio.to_thread`.
        - Replaces the initial loading text with an error notification if chart generation 
          fails or returns no data.
    """
    
    wait_msg = await update.message.reply_text("📊 Generando el gráfico de la semana...")
    
    buf = await asyncio.to_thread(generate_points_chart)
    if not buf:
        await wait_msg.edit_text("⚠️ No se encontraron datos suficientes para generar el gráfico.")
        return

    await wait_msg.delete()
    await update.message.reply_photo(
        photo=buf,
        caption="📈 <b>Progreso de puntos semanal</b>",
        parse_mode="HTML"
    )