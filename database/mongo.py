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
payments_col = db["payments"]
shorteners_col = db["shorteners"]
upi_pending_col = db["upi_pending"]
ads_col = db["ads"]
ad_impressions_col = db["ad_impressions"]
ad_clicks_col = db["ad_clicks"]
ad_drafts_col = db["ad_drafts"]
analytics_events_col = db["analytics_events"]
sub_bots_col = db["sub_bots"]
scheduled_posts_col = db["scheduled_posts"]
templates_col = db["templates"]
repost_jobs_col = db["repost_jobs"]
post_drafts_col = db["post_drafts"]
channel_stats_col = db["channel_stats"]
button_clicks_col = db["button_clicks"]

# New collections for the Movie Channel Creator Studio migration
diagnostics_logs_col = db["diagnostics_logs"]
error_logs_col = db["error_logs"]
state_logs_col = db["state_logs"]
callback_logs_col = db["callback_logs"]
message_logs_col = db["message_logs"]
payment_logs_col = db["payment_logs"]
admin_logs_col = db["admin_logs"]
processed_updates_col = db["processed_updates"]
published_posts_col = db["published_posts"]
worker_status_col = db["worker_status"]
rate_limits_col = db["rate_limits"]
user_settings_col = db["user_settings"]
roles_col = db["roles"]
admins_config_col = db["admins_config"]  # admins collection config
backup_jobs_col = db["backup_jobs"]
media_library_col = db["media_library"]
runtime_lock_col = db["runtime_lock"]
transactions_col = db["transactions"]
premium_plans_col = db["premium_plans"]
referrals_col = db["referrals"]
referral_rewards_col = db["referral_rewards"]
referral_logs_col = db["referral_logs"]
store_products_col = db["store_products"]
store_orders_col = db["store_orders"]
coupons_col = db["coupons"]
premium_users_col = db["premium_users"]
file_links_col = db["file_links"]
password_sessions_col = db["password_sessions"]


async def init_db():
    try:
        # Create unique index on token
        await files_col.create_index("token", unique=True)
        # Create indexes on user_id
        await users_col.create_index("user_id")
        await batches_col.create_index("user_id")
        await edit_sessions_col.create_index("user_id")

        await payments_col.create_index("user_id")
        await payments_col.create_index("created_at")
        await shorteners_col.create_index("status")

        await upi_pending_col.create_index("user_id")
        await upi_pending_col.create_index("status")

        # Ad Sponsored Promotions indexes
        await ads_col.create_index("type")
        await ads_col.create_index("status")
        await ads_col.create_index([("type", 1), ("status", 1)])
        await ad_impressions_col.create_index("ad_id")
        await ad_impressions_col.create_index("user_id")
        await ad_impressions_col.create_index("timestamp")
        await ad_clicks_col.create_index("ad_id")
        await ad_clicks_col.create_index("user_id")
        await ad_clicks_col.create_index("timestamp")

        # Analytics Monetization indexes
        await analytics_events_col.create_index("date")
        await analytics_events_col.create_index("event")
        await analytics_events_col.create_index("user_id")
        await analytics_events_col.create_index("timestamp")
        await analytics_events_col.create_index("country")
        await analytics_events_col.create_index("source")
        await analytics_events_col.create_index([("event", 1), ("timestamp", 1)])
        await analytics_events_col.create_index([("country", 1), ("timestamp", 1)])
        await analytics_events_col.create_index([("source", 1), ("timestamp", 1)])

        # New migration indexes
        await processed_updates_col.create_index("update_id", unique=True)
        await processed_updates_col.create_index("processed_at", expireAfterSeconds=86400) # TTL index 24h
        await runtime_lock_col.create_index("lock_name", unique=True)
        await rate_limits_col.create_index([("user_id", 1), ("action", 1)])
        await published_posts_col.create_index([("post_id", 1), ("channel_id", 1)])
        await worker_status_col.create_index("worker_name", unique=True)
        await file_links_col.create_index("code", unique=True)

        # Migrate traffic attribution for older users
        await users_col.update_many(
            {"source": {"$exists": False}},
            {"$set": {"source": "direct", "campaign": None}}
        )

        logger.info("Database indexes and migrations initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database indexes/migrations: {e}")
