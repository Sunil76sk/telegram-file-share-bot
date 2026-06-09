import os
from dotenv import load_dotenv

# Load environmental variables from .env file
load_dotenv()

# Telegram Bot API Credentials
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Ensure required Telegram parameters are present
if not API_ID or not API_HASH or not BOT_TOKEN:
    raise ValueError(
        "API_ID, API_HASH, and BOT_TOKEN must be configured in the environment or .env file."
    )

try:
    API_ID = int(API_ID)
except ValueError:
    raise ValueError("API_ID must be a valid integer.")

# MongoDB Credentials
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "tg_file_share_bot")

# Administrators
ADMIN_IDS = []
raw_admins = os.getenv("ADMIN_IDS", "")
if raw_admins:
    for admin in raw_admins.split(","):
        admin = admin.strip()
        if admin:
            try:
                ADMIN_IDS.append(int(admin))
            except ValueError:
                # Log or ignore invalid admin ID formats
                pass

# Default force subscription chats
FORCE_SUB_CHATS: list[int | str] = []
raw_force_sub = os.getenv("FORCE_SUB_CHATS", "")
if raw_force_sub:
    for chat in raw_force_sub.split(","):
        chat = chat.strip()
        if chat:
            # Check if it looks like an ID (integer) or username
            if chat.startswith("-") or chat.isdigit():
                try:
                    FORCE_SUB_CHATS.append(int(chat))
                except ValueError:
                    FORCE_SUB_CHATS.append(chat)
            else:
                FORCE_SUB_CHATS.append(chat)

# Auto-delete settings
AUTO_DELETE_SECONDS = os.getenv("AUTO_DELETE_SECONDS", "300")
try:
    AUTO_DELETE_SECONDS = int(AUTO_DELETE_SECONDS)
except ValueError:
    AUTO_DELETE_SECONDS = 300

