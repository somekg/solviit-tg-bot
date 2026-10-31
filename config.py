# config.py
import os
from dotenv import load_dotenv
from telegram import ChatPermissions

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_TELEGRAM_ID")

SLAP_WEAPONS = [
    "una trucha 🐟",
    "un periódico 📄",
    "un teclado ⌨️",
    "su propia mano 👋",
    "un pato de goma 🦆",
    "un cilindro de 47cm ???"
]

MUTE_PERMISSIONS = ChatPermissions(
    can_send_messages=False, can_send_audios=False, can_send_documents=False,
    can_send_photos=False, can_send_videos=False, can_send_video_notes=False,
    can_send_voice_notes=False, can_send_polls=False, can_send_other_messages=False,
    can_add_web_page_previews=False
)

UNMUTE_PERMISSIONS = ChatPermissions(
    can_send_messages=True, can_send_audios=True, can_send_documents=True,
    can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
    can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
    can_add_web_page_previews=True
)

COMMAND_SPAM_TRACKER = {}