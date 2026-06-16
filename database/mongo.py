import logging
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure, ConfigurationError
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
drafts_col = db["drafts"]
settings_col = db["settings"]
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

# Creator Studio new collections
channel_post_history_col = db["channel_post_history"]
crash_recovery_col = db["crash_recovery"]
error_recovery_col = db["error_recovery"]
draft_recovery_col = db["draft_recovery"]
queue_tasks_col = db["queue_tasks"]
queue_execution_log_col = db["queue_execution_log"]
botfather_menu_col = db["botfather_menu"]
worker_heartbeats_col = db["worker_heartbeats"]
movie_metadata_col = db["movie_metadata"]
movie_download_buttons_col = db["movie_download_buttons"]
movie_templates_col = db["movie_templates"]
backups_col = db["backups"]
audit_admin_logs_col = db["audit_admin_logs"]
audit_error_logs_col = db["audit_error_logs"]

# Products store collections
products_col = db["products"]
purchases_col = db["purchases"]
downloads_col = db["downloads"]
categories_col = db["categories"]
audit_event_logs_col = db["audit_event_logs"]
notification_queue_col = db["notification_queue"]
notification_preferences_col = db["notification_preferences"]
user_language_col = db["user_language"]
translations_col = db["translations"]


# Whether the connected MongoDB deployment supports multi-document
# transactions (replica set / mongos). Determined lazily on first use; a
# standalone mongod will set this to False and we degrade to sequential writes.
_transactions_supported: bool | None = None


async def with_transaction(operation):
    """Run ``await operation(session)`` inside a MongoDB transaction when the
    deployment supports it, otherwise run it sequentially without a session.

    ``operation`` must be an async callable taking a single ``session`` argument
    (which may be ``None`` in the fallback path). On a standalone mongod the
    first transactional write fails before committing anything, so re-running the
    operation without a session is safe.
    """
    global _transactions_supported

    if _transactions_supported is False:
        await operation(None)
        return

    try:
        async with await client.start_session() as session:
            async with session.start_transaction():
                await operation(session)
        _transactions_supported = True
    except (OperationFailure, ConfigurationError) as e:
        msg = str(e)
        unsupported = (
            "replica set" in msg
            or "Transaction numbers" in msg
            or "transactions are not supported" in msg.lower()
            or getattr(e, "code", None) in (20, 263)
        )
        if _transactions_supported is None and unsupported:
            logger.warning(
                "MongoDB transactions are not supported by this deployment; "
                "falling back to sequential writes."
            )
            _transactions_supported = False
            await operation(None)
        else:
            raise


async def init_db():
    try:
        from database.schema import ensure_collections, ensure_indexes, run_migrations
        await ensure_collections()
        await ensure_indexes()
        await run_migrations()

        await processed_updates_col.create_index("processed_at", expireAfterSeconds=86400)

        rate_limits_col = db["rate_limits"]
        await rate_limits_col.create_index([("user_id", 1), ("action", 1)])
        await published_posts_col.create_index([("post_id", 1), ("channel_id", 1)])

        await users_col.update_many(
            {"source": {"$exists": False}},
            {"$set": {"source": "direct", "campaign": None}}
        )

        logger.info("Database schema, indexes, and migrations initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
