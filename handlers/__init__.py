# handlers/__init__.py
from telegram.ext import CommandHandler, ChatMemberHandler, TypeHandler
from telegram import Update

from handlers.general import welcome, ping, help_command, list_problems
from handlers.leaderboard import register, profile, leaderboard
from handlers.admin import mute_command, unmute_command, mutelist_command, check_mute_status, add_problem, delete_problem
from handlers.fun import slap, gay, amarillo
from donut import donut_command

def register_all_handlers(app):
    # Priority middleware (Group -1)
    app.add_handler(TypeHandler(Update, check_mute_status), group=-1)

    # General & Member
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("leaderboard", leaderboard))

    # Admin
    app.add_handler(CommandHandler("mute", mute_command))
    app.add_handler(CommandHandler("unmute", unmute_command))
    app.add_handler(CommandHandler("mutelist", mutelist_command))
    app.add_handler(CommandHandler("addproblem", add_problem))
    app.add_handler(CommandHandler("deleteproblems", delete_problem))

    # Fun & Utility
    app.add_handler(CommandHandler("slap", slap))
    app.add_handler(CommandHandler("gay", gay))
    app.add_handler(CommandHandler("amarillo", amarillo))

    app.add_handler(CommandHandler("problems", list_problems))
    app.add_handler(CommandHandler("donut", donut_command))

    # Event Handlers
    app.add_handler(ChatMemberHandler(welcome, ChatMemberHandler.CHAT_MEMBER))