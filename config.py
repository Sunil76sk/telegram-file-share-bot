import os
from dotenv import load_dotenv

# Load environmental variables from .env file
load_dotenv()


def get_env_int(key: str, default: int) -> int:
    val = os.getenv(key)
    if val is None or val.strip() == "":
        return default
    try:
        return int(val)
    except ValueError:
        return default


def get_env_float(key: str, default: float) -> float:
    val = os.getenv(key)
    if val is None or val.strip() == "":
        return default
    try:
        return float(val)
    except ValueError:
        return default


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
AUTO_DELETE_SECONDS = get_env_int("AUTO_DELETE_SECONDS", 300)

# Monetization Settings (Telegram Stars & Custom Pricing)
PREMIUM_PRICE_WEEKLY = get_env_int("PREMIUM_PRICE_WEEKLY", 100)  # Stars
PREMIUM_PRICE_MONTHLY = get_env_int("PREMIUM_PRICE_MONTHLY", 300)  # Stars
PREMIUM_PRICE_LIFETIME = get_env_int("PREMIUM_PRICE_LIFETIME", 1000)  # Stars

# Premium Tier Pricing (Telegram Stars)
PREMIUM_SILVER_WEEKLY = get_env_int("PREMIUM_SILVER_WEEKLY", 75)
PREMIUM_SILVER_MONTHLY = get_env_int("PREMIUM_SILVER_MONTHLY", 200)
PREMIUM_GOLD_WEEKLY = get_env_int("PREMIUM_GOLD_WEEKLY", 150)
PREMIUM_GOLD_MONTHLY = get_env_int("PREMIUM_GOLD_MONTHLY", 400)
PREMIUM_GOLD_LIFETIME = get_env_int("PREMIUM_GOLD_LIFETIME", 1500)

# UPI Payment Settings
UPI_ID = os.getenv("UPI_ID")
if not UPI_ID or UPI_ID.strip() == "":
    UPI_ID = "sunil.kembhavi@ybl"

UPI_QR_IMAGE = os.getenv("UPI_QR_IMAGE")
if not UPI_QR_IMAGE or UPI_QR_IMAGE.strip() == "":
    if os.path.exists("assets/upi_qr.png"):
        UPI_QR_IMAGE = "assets/upi_qr.png"
    else:
        UPI_QR_IMAGE = ""
UPI_PRICE_WEEKLY = get_env_float("UPI_PRICE_WEEKLY", 49.0)  # INR
UPI_PRICE_MONTHLY = get_env_float("UPI_PRICE_MONTHLY", 149.0)  # INR
UPI_PRICE_LIFETIME = get_env_float("UPI_PRICE_LIFETIME", 499.0)  # INR

# Premium Content Categories
PREMIUM_CATEGORIES = {
    "ai_resources": "🤖 AI Resource Packs",
    "editing_assets": "🎨 Editing Assets",
    "courses": "📚 Courses",
    "templates": "📋 Templates",
    "educational": "🎓 Educational Content",
}


# Referral System Rewards
REFERRAL_REWARD_POINTS = get_env_int("REFERRAL_REWARD_POINTS", 1)  # Points per referral

# Waiting Countdown and Ad Settings
WAIT_TIMER_SECONDS = get_env_int(
    "WAIT_TIMER_SECONDS", 10
)  # Timer duration for free users

# URL Shortener Integration
SHORTENER_API_URL = os.getenv("SHORTENER_API_URL", "")  # e.g., https://gplinks.in/api
SHORTENER_API_KEY = os.getenv("SHORTENER_API_KEY", "")
REDIRECT_BASE_URL = os.getenv(
    "REDIRECT_BASE_URL", ""
)  # e.g., http://localhost:8080 or domain
WEB_SERVER_PORT = get_env_int("WEB_SERVER_PORT", 8080)

# SaaS Licensing Platform Settings
PLATFORM_FEE_PERCENT = get_env_int(
    "PLATFORM_FEE_PERCENT", 10
)  # Commission fee on sub-bot sales

# SaaS Plan Pricing (INR)
SAAS_STARTER_PRICE = get_env_int("SAAS_STARTER_PRICE", 999)
SAAS_PRO_PRICE = get_env_int("SAAS_PRO_PRICE", 2499)
SAAS_AGENCY_PRICE = get_env_int("SAAS_AGENCY_PRICE", 4999)

# SaaS Subscription UPI Payment
SAAS_UPI_ID = os.getenv("SAAS_UPI_ID")
if not SAAS_UPI_ID or SAAS_UPI_ID.strip() == "":
    SAAS_UPI_ID = UPI_ID

# Runtime-populated: set by bot.py on startup
BOT_USERNAME: str = ""
