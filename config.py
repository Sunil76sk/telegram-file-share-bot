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

# Monetization Settings (Telegram Stars & Custom Pricing)
PREMIUM_PRICE_WEEKLY = int(os.getenv("PREMIUM_PRICE_WEEKLY", "100"))  # Stars
PREMIUM_PRICE_MONTHLY = int(os.getenv("PREMIUM_PRICE_MONTHLY", "300"))  # Stars
PREMIUM_PRICE_LIFETIME = int(os.getenv("PREMIUM_PRICE_LIFETIME", "1000"))  # Stars

# Premium Tier Pricing (Telegram Stars)
PREMIUM_SILVER_WEEKLY = int(os.getenv("PREMIUM_SILVER_WEEKLY", "75"))
PREMIUM_SILVER_MONTHLY = int(os.getenv("PREMIUM_SILVER_MONTHLY", "200"))
PREMIUM_GOLD_WEEKLY = int(os.getenv("PREMIUM_GOLD_WEEKLY", "150"))
PREMIUM_GOLD_MONTHLY = int(os.getenv("PREMIUM_GOLD_MONTHLY", "400"))
PREMIUM_GOLD_LIFETIME = int(os.getenv("PREMIUM_GOLD_LIFETIME", "1500"))

# UPI Payment Settings
UPI_ID = os.getenv("UPI_ID", "merchant@upi")
UPI_QR_IMAGE = os.getenv("UPI_QR_IMAGE", "")  # File path or URL to QR code image
UPI_PRICE_WEEKLY = float(os.getenv("UPI_PRICE_WEEKLY", "49"))  # INR
UPI_PRICE_MONTHLY = float(os.getenv("UPI_PRICE_MONTHLY", "149"))  # INR
UPI_PRICE_LIFETIME = float(os.getenv("UPI_PRICE_LIFETIME", "499"))  # INR

# Premium Content Categories
PREMIUM_CATEGORIES = {
    "ai_resources": "🤖 AI Resource Packs",
    "editing_assets": "🎨 Editing Assets",
    "courses": "📚 Courses",
    "templates": "📋 Templates",
    "educational": "🎓 Educational Content",
}


# Referral System Rewards
REFERRAL_REWARD_POINTS = int(
    os.getenv("REFERRAL_REWARD_POINTS", "1")
)  # Points per referral

# Waiting Countdown and Ad Settings
WAIT_TIMER_SECONDS = int(
    os.getenv("WAIT_TIMER_SECONDS", "10")
)  # Timer duration for free users

# URL Shortener Integration
SHORTENER_API_URL = os.getenv("SHORTENER_API_URL", "")  # e.g., https://gplinks.in/api
SHORTENER_API_KEY = os.getenv("SHORTENER_API_KEY", "")
REDIRECT_BASE_URL = os.getenv(
    "REDIRECT_BASE_URL", ""
)  # e.g., http://localhost:8080 or domain
WEB_SERVER_PORT = int(os.getenv("WEB_SERVER_PORT", "8080"))

# SaaS Licensing Platform Settings
PLATFORM_FEE_PERCENT = int(
    os.getenv("PLATFORM_FEE_PERCENT", "10")
)  # Commission fee on sub-bot sales

# SaaS Plan Pricing (INR)
SAAS_STARTER_PRICE = int(os.getenv("SAAS_STARTER_PRICE", "999"))
SAAS_PRO_PRICE = int(os.getenv("SAAS_PRO_PRICE", "2499"))
SAAS_AGENCY_PRICE = int(os.getenv("SAAS_AGENCY_PRICE", "4999"))

# SaaS Subscription UPI Payment
SAAS_UPI_ID = os.getenv("SAAS_UPI_ID", "")  # Falls back to UPI_ID if empty

# Runtime-populated: set by bot.py on startup
BOT_USERNAME: str = ""
