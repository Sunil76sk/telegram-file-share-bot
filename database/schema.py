"""Database schema definition and migration utilities."""

from __future__ import annotations

import datetime
import logging

from database.mongo import db, client, config

logger = logging.getLogger(__name__)

REQUIRED_COLLECTIONS = {
    "users": [
        ("user_id", None),
        ("username", None),
        ("joined_at", None),
    ],
    "files": [
        ("token", None),
        ("owner_id", None),
        ("created_at", None),
    ],
    "channels": [
        ("user_id", None),
        ("channel_id", None),
    ],
    "processed_updates": [
        ("update_id", None),
        ("processed_at", None),
    ],
    "runtime_lock": [
        ("lock_name", None),
    ],
    "user_states": [
        ("state", None),
        ("updated_at", None),
    ],
    "state_transitions": [
        ("user_id", None),
        ("transitioned_at", None),
    ],
    "callback_tokens": [
        ("user_id", None),
        ("expires_at", None),
    ],
    "callback_execution_log": [
        ("user_id", None),
        ("executed_at", None),
    ],
    "admin_audit_log": [
        ("admin_id", None),
        ("timestamp", None),
    ],
    "error_audit_log": [
        ("module", None),
        ("timestamp", None),
    ],
    "event_audit_log": [
        ("event_type", None),
        ("timestamp", None),
    ],
    "worker_status": [
        ("worker_name", None),
    ],
    "queue_tasks": [
        ("status", None),
        ("scheduled_at", None),
    ],
    "diagnostics_logs": [
        ("module", None),
        ("timestamp", None),
    ],
    "notification_queue": [
        ("user_id", None),
        ("created_at", None),
    ],
    "user_preferences": [
        ("user_id", None),
    ],
    "backup_jobs": [
        ("status", None),
        ("created_at", None),
    ],
    "media_library": [
        ("user_id", None),
        ("created_at", None),
    ],
    "published_posts": [
        ("channel_id", None),
        ("published_at", None),
    ],
    "reaction_votes": [
        ("chat_id", None),
        ("message_id", None),
    ],
    "categories": [
        ("slug", None),
    ],
    "products": [
        ("token", None),
        ("owner_id", None),
    ],
    "purchases": [
        ("user_id", None),
        ("created_at", None),
    ],
    "downloads": [
        ("user_id", None),
        ("downloaded_at", None),
    ],
    "premium_users": [
        ("user_id", None),
    ],
    "premium_plans": [
        ("name", None),
    ],
    "referrals": [
        ("referrer_id", None),
    ],
    "referral_rewards": [
        ("user_id", None),
    ],
    "referral_logs": [
        ("user_id", None),
    ],
    "store_products": [
        ("owner_id", None),
    ],
    "store_orders": [
        ("user_id", None),
    ],
    "coupons": [
        ("code", None),
    ],
    "ad_impressions": [
        ("ad_id", None),
    ],
    "ad_clicks": [
        ("ad_id", None),
    ],
    "password_sessions": [
        ("user_id", None),
    ],
    "file_links": [
        ("code", None),
    ],
    "upi_pending": [
        ("user_id", None),
    ],
    "batches": [
        ("user_id", None),
    ],
    "edit_sessions": [
        ("user_id", None),
    ],
    "deletions": [
        ("delete_at", None),
    ],
    "password_settings": [
        ("_id", None),
    ],
    "password_entries": [
        ("_id", None),
    ],
    "active_deliveries": [
        ("_id", None),
    ],
    "payments": [
        ("user_id", None),
    ],
    "shorteners": [
        ("status", None),
    ],
    "ads": [
        ("type", None),
    ],
    "ad_drafts": [
        ("_id", None),
    ],
    "analytics_events": [
        ("date", None),
    ],
    "sub_bots": [
        ("bot_id", None),
    ],
    "scheduled_posts": [
        ("scheduled_time", None),
    ],
    "templates": [
        ("user_id", None),
    ],
    "repost_jobs": [
        ("next_post_at", None),
    ],
    "drafts": [
        ("user_id", None),
        ("state", None),
    ],
    "settings": [
        ("_id", None),
    ],
    "channel_stats": [
        ("channel_id", None),
    ],
    "button_clicks": [
        ("user_id", None),
    ],
    "channel_post_history": [
        ("channel_id", None),
        ("posted_at", None),
    ],
    "crash_recovery": [
        ("crashed_at", None),
    ],
    "error_recovery": [
        ("recorded_at", None),
    ],
    "draft_recovery": [
        ("user_id", None),
        ("recorded_at", None),
    ],
    "queue_execution_log": [
        ("task_id", None),
    ],
    "botfather_menu": [
        ("type", None),
    ],
    "worker_heartbeats": [
        ("worker_name", None),
        ("timestamp", None),
    ],
    "movie_metadata": [
        ("title", None),
        ("year", None),
    ],
    "movie_download_buttons": [
        ("user_id", None),
    ],
    "movie_templates": [
        ("user_id", None),
    ],
    "backups": [
        ("status", None),
        ("created_at", None),
    ],
    "audit_admin_logs": [
        ("admin_id", None),
    ],
    "audit_error_logs": [
        ("module", None),
    ],
    "audit_event_logs": [
        ("event_type", None),
    ],
    "user_language": [
        ("user_id", None),
    ],
    "translations": [
        ("lang", None),
    ],
}

from typing import Any

INDEX_SPECS: dict[str, list[tuple[Any, Any]]] = {
    "users": [
        (("user_id", 1), False),
        (("username", 1), False),
        (("joined_at", -1), False),
    ],
    "files": [
        ("token", True),
        (("owner_id", 1), False),
        (("created_at", -1), False),
    ],
    "channels": [
        (("user_id", 1), False),
        (("channel_id", 1), False),
    ],
    "processed_updates": [
        ("update_id", True),
        (("processed_at", 1), {"expireAfterSeconds": 86400}),
    ],
    "runtime_lock": [
        ("lock_name", True),
    ],
    "user_states": [
        (("user_id", 1), False),
        (("state", 1), False),
    ],
    "state_transitions": [
        (("user_id", 1), False),
        (("transitioned_at", -1), False),
    ],
    "callback_tokens": [
        (("user_id", 1), False),
        (("expires_at", -1), False),
    ],
    "callback_execution_log": [
        (("user_id", 1), False),
        (("executed_at", -1), False),
    ],
    "admin_audit_log": [
        (("admin_id", 1), False),
        (("timestamp", -1), False),
    ],
    "error_audit_log": [
        (("module", 1), False),
        (("timestamp", -1), False),
    ],
    "event_audit_log": [
        (("event_type", 1), False),
        (("timestamp", -1), False),
    ],
    "worker_status": [
        ("worker_name", True),
    ],
    "queue_tasks": [
        (("status", 1), False),
        (("scheduled_at", 1), False),
    ],
    "diagnostics_logs": [
        (("module", 1), False),
        (("timestamp", -1), False),
    ],
    "notification_queue": [
        (("user_id", 1), False),
        (("created_at", 1), False),
    ],
    "user_preferences": [
        (("user_id", 1), True),
    ],
    "backup_jobs": [
        (("status", 1), False),
        (("created_at", -1), False),
    ],
    "media_library": [
        (("user_id", 1), False),
        (("created_at", -1), False),
    ],
    "published_posts": [
        ((("channel_id", 1), ("published_at", -1)), False),
    ],
    "reaction_votes": [
        ((("chat_id", 1), ("message_id", 1), ("user_id", 1), ("emoji", 1)), True),
    ],
    "categories": [
        ("slug", True),
    ],
    "products": [
        ("token", True),
        (("owner_id", 1), False),
    ],
    "purchases": [
        (("user_id", 1), False),
        (("created_at", -1), False),
        ("payment_id", {"unique": True, "sparse": True}),
        ((("user_id", 1), ("product_id", 1), ("status", 1)), False),
    ],
    "downloads": [
        (("user_id", 1), False),
        (("downloaded_at", -1), False),
    ],
    "premium_users": [
        (("user_id", 1), True),
    ],
    "premium_plans": [
        (("name", 1), True),
    ],
    "referrals": [
        (("referrer_id", 1), False),
    ],
    "referral_rewards": [
        (("user_id", 1), False),
    ],
    "referral_logs": [
        (("user_id", 1), False),
    ],
    "store_products": [
        (("owner_id", 1), False),
    ],
    "store_orders": [
        (("user_id", 1), False),
    ],
    "coupons": [
        ("code", True),
    ],
    "ad_impressions": [
        (("ad_id", 1), False),
    ],
    "ad_clicks": [
        (("ad_id", 1), False),
    ],
    "password_sessions": [
        (("user_id", 1), False),
    ],
    "file_links": [
        ("code", True),
    ],
    "upi_pending": [
        (("user_id", 1), False),
        (("status", 1), False),
    ],
    "batches": [
        (("user_id", 1), False),
    ],
    "edit_sessions": [
        (("user_id", 1), False),
    ],
    "deletions": [
        (("delete_at", 1), False),
    ],
    "active_deliveries": [
        (("_id", 1), False),
    ],
    "payments": [
        (("user_id", 1), False),
    ],
    "shorteners": [
        (("status", 1), False),
    ],
    "ads": [
        (("type", 1), False),
    ],
    "ad_drafts": [
        (("_id", 1), False),
    ],
    "analytics_events": [
        (("date", 1), False),
        (("event", 1), False),
        (("timestamp", -1), False),
    ],
    "sub_bots": [
        (("bot_id", 1), False),
    ],
    "scheduled_posts": [
        (("scheduled_time", 1), False),
        (("status", 1), False),
        ((("scheduled_time", 1), ("status", 1)), False),
    ],
    "templates": [
        (("user_id", 1), False),
    ],
    "repost_jobs": [
        (("next_post_at", 1), False),
        (("status", 1), False),
    ],
    "drafts": [
        ((("user_id", 1), ("state", 1)), False),
        (("user_id", 1), True),
        (("updated_at", 1), {"expireAfterSeconds": 86400}),
    ],
    "settings": [],
    "channel_stats": [
        (("channel_id", 1), False),
    ],
    "button_clicks": [
        (("user_id", 1), False),
    ],
    "channel_post_history": [
        (("channel_id", 1), False),
        (("posted_at", -1), False),
    ],
    "crash_recovery": [
        (("crashed_at", -1), False),
    ],
    "error_recovery": [
        (("recorded_at", -1), False),
    ],
    "draft_recovery": [
        (("user_id", 1), False),
        (("recorded_at", -1), False),
    ],
    "queue_execution_log": [
        (("task_id", 1), False),
    ],
    "botfather_menu": [
        ("type", True),
    ],
    "worker_heartbeats": [
        (("worker_name", 1), False),
        (("timestamp", -1), False),
    ],
    "movie_metadata": [
        (("title", "text"), False),
        (("year", 1), False),
        (("genre", 1), False),
    ],
    "movie_download_buttons": [
        (("user_id", 1), False),
    ],
    "movie_templates": [
        (("user_id", 1), False),
    ],
    "backups": [
        (("status", 1), False),
        (("created_at", -1), False),
    ],
    "audit_admin_logs": [
        (("admin_id", 1), False),
        (("timestamp", -1), False),
    ],
    "audit_error_logs": [
        (("module", 1), False),
        (("timestamp", -1), False),
    ],
    "audit_event_logs": [
        (("event_type", 1), False),
        (("timestamp", -1), False),
    ],
    "user_language": [
        (("user_id", 1), True),
    ],
    "translations": [
        (("lang", 1), False),
        (("key", 1), False),
    ],
}


async def ensure_collections():
    existing = await db.list_collection_names()
    for col_name in REQUIRED_COLLECTIONS:
        if col_name not in existing:
            await db.create_collection(col_name)
            logger.info(f"Created collection: {col_name}")
    logger.info(f"All {len(REQUIRED_COLLECTIONS)} required collections exist")


async def ensure_indexes():
    for col_name, specs in INDEX_SPECS.items():
        col = db[col_name]
        for spec in specs:
            keys, options = spec
            if isinstance(keys, tuple):
                if keys and isinstance(keys[0], str):
                    keys = [keys]
                else:
                    keys = list(keys)
            # Skip _id index as MongoDB manages it automatically
            if keys == "_id" or (isinstance(keys, list) and len(keys) == 1 and keys[0][0] == "_id"):
                continue
            if isinstance(options, bool):
                kwargs: dict = {"unique": options}
            elif isinstance(options, dict):
                kwargs = dict(options)
            else:
                kwargs = {}
            try:
                await col.create_index(keys, **kwargs)
            except Exception as e:
                logger.error(f"Failed to create index on {col_name}: {e}")
    logger.info("All indexes ensured")


async def run_migrations():
    """Run all database migrations in order."""
    migrations_col = db["schema_migrations"]
    applied = set()
    async for doc in migrations_col.find():
        applied.add(doc["name"])

    migrations = [
        _migration_001_add_user_source,
        _migration_002_add_referral_fields,
        _migration_003_add_premium_fields,
        _migration_004_add_creator_fields,
        _migration_005_add_analytics_indexes,
        _migration_006_add_worker_status,
        _migration_007_clean_stale_states,
        _migration_008_fix_drafts_ttl,
    ]

    for migration in migrations:
        name = migration.__name__
        if name not in applied:
            try:
                await migration()
                await migrations_col.insert_one({
                    "name": name,
                    "applied_at": datetime.datetime.now(datetime.timezone.utc),
                })
                logger.info(f"Migration applied: {name}")
            except Exception as e:
                logger.error(f"Migration failed {name}: {e}")


async def _migration_001_add_user_source():
    await db.users.update_many(
        {"source": {"$exists": False}},
        {"$set": {"source": "direct", "campaign": None}}
    )


async def _migration_002_add_referral_fields():
    await db.users.update_many(
        {"points": {"$exists": False}},
        {"$set": {"points": 0, "referred_by": None, "unlocked_links": []}}
    )


async def _migration_003_add_premium_fields():
    await db.users.update_many(
        {"premium_expiry": {"$exists": False}},
        {"$set": {"premium_expiry": None, "is_premium_lifetime": False, "premium_tier": None}}
    )


async def _migration_004_add_creator_fields():
    await db.channels.update_many(
        {"service_enabled": {"$exists": False}},
        {"$set": {"service_enabled": True, "permissions_verified": True}}
    )
    await db.drafts.update_many(
        {"updated_at": {"$exists": False}},
        {"$set": {"updated_at": datetime.datetime.now(datetime.timezone.utc)}}
    )


async def _migration_005_add_analytics_indexes():
    await db.analytics_events.create_index([("date", 1), ("event", 1)])
    await db.analytics_events.create_index([("country", 1), ("timestamp", -1)])


async def _migration_006_add_worker_status():
    await db.worker_status.update_one(
        {"worker_name": "scheduler"},
        {"$set": {"status": "stopped", "last_heartbeat": None}},
        upsert=True,
    )
    await db.worker_status.update_one(
        {"worker_name": "deletion"},
        {"$set": {"status": "stopped", "last_heartbeat": None}},
        upsert=True,
    )
    await db.worker_status.update_one(
        {"worker_name": "expiry"},
        {"$set": {"status": "stopped", "last_heartbeat": None}},
        upsert=True,
    )
    await db.worker_status.update_one(
        {"worker_name": "ads_scheduler"},
        {"$set": {"status": "stopped", "last_heartbeat": None}},
        upsert=True,
    )


async def _migration_007_clean_stale_states():
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
    await db.user_states.delete_many({"updated_at": {"$lt": cutoff}})


async def _migration_008_fix_drafts_ttl():
    """Move the drafts TTL from created_at to updated_at.

    The old TTL on created_at deleted post drafts 24h after first creation,
    silently destroying in-progress wizard sessions. The new TTL (on updated_at,
    refreshed on every save) only reaps drafts after 24h of inactivity. Drop the
    legacy index so it stops competing with the new one.
    """
    for index_name in ("created_at_1",):
        try:
            await db.drafts.drop_index(index_name)
            logger.info(f"Dropped legacy drafts index: {index_name}")
        except Exception:
            # Index may not exist (fresh deploy) — nothing to drop.
            pass
