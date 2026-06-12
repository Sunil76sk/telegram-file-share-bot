from __future__ import annotations

import datetime
import logging
from typing import Any

from database.mongo import db

logger = logging.getLogger(__name__)

NOTIFICATION_COL = db["notification_queue"]
USER_PREF_COL = db["user_preferences"]

NOTIFICATION_TYPES = {
    "premium_expiry": "premium_expiry",
    "premium_activated": "premium_activated",
    "scheduled_post_sent": "scheduled_post_sent",
    "scheduled_post_failed": "scheduled_post_failed",
    "repost_completed": "repost_completed",
    "payment_received": "payment_received",
    "payment_approved": "payment_approved",
    "payment_rejected": "payment_rejected",
    "broadcast_message": "broadcast_message",
    "referral_reward": "referral_reward",
    "admin_alert": "admin_alert",
    "system_notification": "system_notification",
}


async def send_notification(
    user_id: int,
    notification_type: str,
    title: str,
    message: str,
    data: dict[str, Any] | None = None,
    priority: int = 0,
):
    if notification_type not in NOTIFICATION_TYPES.values():
        logger.error(f"Invalid notification type: {notification_type}")
        return

    pref = await USER_PREF_COL.find_one({"_id": user_id})
    if pref:
        disabled = pref.get("disabled_notifications", [])
        if notification_type in disabled:
            logger.debug(f"User {user_id} has disabled {notification_type} notifications")
            return

    doc = {
        "user_id": user_id,
        "type": notification_type,
        "title": title,
        "message": message,
        "data": data or {},
        "priority": priority,
        "status": "pending",
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "sent_at": None,
    }
    await NOTIFICATION_COL.insert_one(doc)
    logger.info(f"Notification queued: type={notification_type} user={user_id} title={title}")


async def mark_notification_sent(notification_id: str) -> bool:
    result = await NOTIFICATION_COL.update_one(
        {"_id": notification_id},
        {"$set": {"status": "sent", "sent_at": datetime.datetime.now(datetime.timezone.utc)}}
    )
    return result.modified_count > 0


async def mark_notification_failed(notification_id: str, error: str):
    await NOTIFICATION_COL.update_one(
        {"_id": notification_id},
        {"$set": {"status": "failed", "error": error, "sent_at": datetime.datetime.now(datetime.timezone.utc)}}
    )


async def get_pending_notifications(limit: int = 50) -> list[dict]:
    cursor = NOTIFICATION_COL.find({"status": "pending"}).sort("priority", -1).limit(limit)
    return [doc async for doc in cursor]


async def get_user_notifications(
    user_id: int,
    limit: int = 20,
    skip: int = 0,
    include_sent: bool = False,
) -> list[dict]:
    query: dict = {"user_id": user_id}
    if not include_sent:
        query["status"] = "pending"
    cursor = NOTIFICATION_COL.find(query).sort("created_at", -1).skip(skip).limit(limit)
    return [doc async for doc in cursor]


async def clear_user_notifications(user_id: int):
    result = await NOTIFICATION_COL.delete_many({"user_id": user_id, "status": "sent"})
    if result.deleted_count:
        logger.info(f"Cleared {result.deleted_count} sent notifications for user {user_id}")


async def get_user_preferences(user_id: int) -> dict:
    doc = await USER_PREF_COL.find_one({"_id": user_id})
    if not doc:
        doc = {"_id": user_id, "disabled_notifications": []}
        await USER_PREF_COL.insert_one(doc)
    return doc


async def update_user_preferences(user_id: int, prefs: dict):
    await USER_PREF_COL.update_one(
        {"_id": user_id},
        {"$set": prefs},
        upsert=True,
    )


async def disable_notification_type(user_id: int, notification_type: str):
    await USER_PREF_COL.update_one(
        {"_id": user_id},
        {"$addToSet": {"disabled_notifications": notification_type}},
        upsert=True,
    )


async def enable_notification_type(user_id: int, notification_type: str):
    await USER_PREF_COL.update_one(
        {"_id": user_id},
        {"$pull": {"disabled_notifications": notification_type}},
    )


async def get_user_notification_preferences(user_id: int) -> bool:
    """Get whether notifications are enabled for a user (simplified)."""
    doc = await USER_PREF_COL.find_one({"_id": user_id})
    if not doc:
        return True
    disabled = doc.get("disabled_notifications", [])
    return len(disabled) == 0


async def set_user_notification_preference(user_id: int, notification_type: str, enabled: bool):
    """Enable or disable a notification type (or 'all' for all)."""
    if notification_type == "all":
        if enabled:
            await USER_PREF_COL.update_one(
                {"_id": user_id},
                {"$set": {"disabled_notifications": []}},
                upsert=True,
            )
        else:
            await USER_PREF_COL.update_one(
                {"_id": user_id},
                {"$set": {"disabled_notifications": list(NOTIFICATION_TYPES.values())}},
                upsert=True,
            )
    elif enabled:
        await enable_notification_type(user_id, notification_type)
    else:
        await disable_notification_type(user_id, notification_type)


async def cleanup_old_notifications(days: int = 30):
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    result = await NOTIFICATION_COL.delete_many({"created_at": {"$lt": cutoff}})
    if result.deleted_count:
        logger.info(f"Cleaned {result.deleted_count} notifications older than {days} days")
