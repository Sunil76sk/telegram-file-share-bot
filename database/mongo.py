import logging
from motor.motor_asyncio import AsyncIOMotorClient
import config

logger = logging.getLogger(__name__)

# Initialize MongoDB Client
client = AsyncIOMotorClient(config.MONGO_URI)
db = client[config.DB_NAME]

# Collections
users_col = db["users"]
files_col = db["files"]
channels_col = db["channels"]
admins_col = db["admins"]
batches_col = db["batches"]
edit_sessions_col = db["edit_sessions"]
deletions_col = db["deletions"]
password_settings_col = db["password_settings"]
password_entries_col = db["password_entries"]
active_deliveries_col = db["active_deliveries"]


async def init_db():
    try:
        # Create unique index on token
        await files_col.create_index("token", unique=True)
        # Create indexes on user_id
        await users_col.create_index("user_id")
        await batches_col.create_index("user_id")
        await edit_sessions_col.create_index("user_id")
        logger.info("Database indexes initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database indexes: {e}")
