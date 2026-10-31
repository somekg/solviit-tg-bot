# handlers/fun.py
import html
import random

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import SLAP_WEAPONS

async def slap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Slaps a telegram user given a name, a username tag or slaps the person
    to which the command was replied to. 

    Args:
        update: The incoming Telegram update containing message and user data.
        context: Context object containing command arguments and bot instance.
    """

    sender = update.effective_user
    slapper = sender.first_name or sender.username or "Alguien"
    weapon = random.choice(SLAP_WEAPONS)
    
    reply = update.message.reply_to_message
    is_real_reply = reply and not getattr(reply, "forum_topic_created", None)

    if context.args:
        target_mention = html.escape(" ".join(context.args).strip())
    elif is_real_reply:
        target_user = reply.from_user
        target_name = target_user.first_name or target_user.username or "Usuario"
        target_mention = f'<a href="tg://user?id={target_user.id}">{html.escape(target_name)}</a>'
    else:
        target_mention = f'<a href="tg://user?id={sender.id}">{html.escape(slapper)}</a>'
        
    text = f"<b>{html.escape(slapper)}</b> le da un guantazo a {target_mention} con {weapon}!"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def gay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Calls a telegram user gay given a name, a username tag or the person
    who was replied to.

    Args:
        update: The incoming Telegram update containing message and user data.
        context: Context object containing command arguments and bot instance.
    """

    sender = update.effective_user
    slapper = sender.first_name or sender.username or "Alguien"
    
    reply = update.message.reply_to_message
    is_real_reply = reply and not getattr(reply, "forum_topic_created", None)

    if context.args:
        target_mention = html.escape(" ".join(context.args).strip())
    elif is_real_reply:
        target_user = reply.from_user
        target_name = target_user.first_name or target_user.username or "Usuario"
        target_mention = f'<a href="tg://user?id={target_user.id}">{html.escape(target_name)}</a>'
    else:
        target_mention = f'<a href="tg://user?id={sender.id}">{html.escape(slapper)}</a>'
        
    text = f"🏳️‍🌈 <b>{html.escape(slapper)}</b> llama gay a {target_mention}, lol, que gay."
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def amarillo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Says amarillo in chat (SolvIIT Secretary inside joke). 

    Args:
        update: The incoming Telegram update containing message and user data.
        context: Context object containing command arguments and bot instance.
    """
    amarillo_text = (
        "amarillo\n" 
    )
    await update.message.reply_text(amarillo_text, parse_mode=ParseMode.MARKDOWN)