# handlers/general.py
from telegram import Update, ChatMember
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database import get_weekly_problems

async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles member join events to post customized welcome messages.

    Differentiates between first-time joins (or standard rejoins) and 
    users rejoining after previously being banned/kicked.

    Note:
        Requires the handler to be registered via `ChatMemberHandler` 
        and `allowed_updates=["chat_member"]` enabled in application setup.

    Args:
        update: The incoming Telegram update containing `chat_member` data.
        context: Context object containing bot instances and job queue.
    """

    result = update.chat_member
    if not result:
        return

    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status
    user = result.new_chat_member.user

    # Ignore bots joining the chat
    if user.is_bot:
        return

    name = user.first_name
    chat_id = result.chat.id

    # 1. Standard Join (First time or joining after voluntarily leaving)
    if old_status == ChatMember.LEFT and new_status == ChatMember.MEMBER:
        welcome_text = (
            f"👋 Bienvenido a SolvIIT! *{name}*!\n\n"
            "Vincula tu usuario:\n`/register <usuario_leetcode>`\n\n"
            "Escribe `/help` para ver los comandos disponibles.\n\n"
            "¡Únete también al canal de noticias en la descripción para saber "
            "que vamos a ver en las próximas sesiones!"
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=welcome_text,
            parse_mode=ParseMode.MARKDOWN
        )

    # 2. Rejoining after being previously kicked/banned
    elif old_status == ChatMember.KICKED and new_status == ChatMember.MEMBER:
        welcome_kicked_text = f"Te estaré vigilando *{name}* 👀\n\n"
        await context.bot.send_message(
            chat_id=chat_id,
            text=welcome_kicked_text,
            parse_mode=ParseMode.MARKDOWN
        )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Checks bot responsiveness.

    Args:
        update: The incoming Telegram update containing message data.
        context: Context object containing bot instances and job queue.
    """
    await update.message.reply_text("pong! 🏓")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays bot command list. 

    Args:
        update: The incoming Telegram update containing message data.
        context: Context object containing bot instances and job queue.
    """
    help_text = (
        "🤖 *SolvIIT LeetCode Bot — Comandos*\n\n"
        "• `/register <usuario_leetcode>` — Vincula tu usuario de LeetCode y fija tu progreso inicial.\n"
        "• `/profile` — Mira tus estadísticas y progreso desde que te uniste.\n"
        "• `/leaderboard [delta|total|rating|points] [easy|medium|hard] [me]` — Mira la clasificación del club.\n"
        "• `/ping` — Revisa el ping del bot.\n"
        "• `/problems` — Muestra el registro de problemas semanales.\n\n"
        "• `/help` — Muestra este menú.\n\n"
        "💡 *Tip:* ¡Para evitar hacer spam en el grupo, puedes registrarte y ver tu perfil hablándome por MD!"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def list_problems(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_week = None
    if context.args:
        try: target_week = int(context.args[0])
        except ValueError:
            await update.message.reply_text("⚠️ Uso: /problems o /problems <semana>")
            return

    problems = get_weekly_problems(target_week)
    if not problems:
        await update.message.reply_text("Todavía no hay problemas guardados.")
        return

    weeks = {}
    for p in problems: weeks.setdefault(p["week_number"], []).append(p["problem_name"])
    
    text_blocks = ["📚 Club SolvIIT — Archivo de Problemas\n"]
    for w in sorted(weeks.keys(), reverse=True):
        text_blocks.append(f"🗓️ Semana {w}")
        for item in weeks[w]: text_blocks.append(f"• {item}")
        text_blocks.append("")
    await update.message.reply_text("\n".join(text_blocks))