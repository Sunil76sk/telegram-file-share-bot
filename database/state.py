from __future__ import annotations

import datetime
import logging
from database.mongo import (
    batches_col,
    edit_sessions_col,
    deletions_col,
    password_settings_col,
    password_entries_col,
    active_deliveries_col,
    ad_drafts_col,
)

logger = logging.getLogger(__name__)

# --- BATCH UPLOAD HELPERS ---


async def get_active_batch(user_id: int):
    """Retrieve the current active batch session for an admin/user."""
    return await batches_col.find_one({"user_id": user_id})


async def create_batch(user_id: int, custom_token: str | None = None):
    """Initialize a new empty batch session for an admin/user."""
    await batches_col.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "files": [],
                "batch_message_id": None,
                "custom_token": custom_token,
                "created_at": datetime.datetime.now(datetime.timezone.utc),
            }
        },
        upsert=True,
    )


async def add_to_batch(
    user_id: int,
    file_id: str,
    file_unique_id: str | None,
    media_type: str,
    caption: str | None,
    file_name: str,
    file_size: int,
):
    """Append a file to the admin/user's active batch session."""
    file_obj = {
        "file_id": file_id,
        "file_unique_id": file_unique_id,
        "media_type": media_type,
        "caption": caption,
        "file_name": file_name,
        "file_size": file_size,
    }
    await batches_col.update_one(
        {"user_id": user_id},
        {"$push": {"files": file_obj}},
    )


async def update_batch_status_message(user_id: int, status_message_id: int):
    """Update the status message ID for the admin/user's active batch."""
    await batches_col.update_one(
        {"user_id": user_id}, {"$set": {"batch_message_id": status_message_id}}
    )


async def delete_batch(user_id: int) -> bool:
    """Delete/clear the batch session for an admin/user."""
    result = await batches_col.delete_one({"user_id": user_id})
    return result.deleted_count > 0


# --- EDIT SESSION HELPERS ---


async def get_edit_session(user_id: int):
    """Retrieve the current active link edit session for an admin."""
    return await edit_sessions_col.find_one({"user_id": user_id})


async def create_edit_session(
    user_id: int,
    token: str,
    files: list | None = None,
):
    """Start an editing session for a specific share token with files preloaded."""
    await edit_sessions_col.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "token": token,
                "pending_deletes": [],
                "active": True,
                "files": files or [],
                "status_message_id": None,
                "created_at": datetime.datetime.now(datetime.timezone.utc),
            }
        },
        upsert=True,
    )


async def update_edit_session_status_message(user_id: int, status_message_id: int):
    """Update the status message ID of the active edit session."""
    await edit_sessions_col.update_one(
        {"user_id": user_id}, {"$set": {"status_message_id": status_message_id}}
    )


async def update_edit_session_files(
    user_id: int,
    files: list,
    pending_deletes: list | None = None,
):
    """Update the files list and optionally pending_deletes list in the active edit session."""
    update_data = {"files": files}
    if pending_deletes is not None:
        update_data["pending_deletes"] = pending_deletes
    await edit_sessions_col.update_one(
        {"user_id": user_id},
        {"$set": update_data},
    )


async def delete_edit_session(user_id: int) -> bool:
    """Clear/delete the active edit session for an admin."""
    result = await edit_sessions_col.delete_one({"user_id": user_id})
    return result.deleted_count > 0


# --- PASSWORD SESSION HELPERS ---


async def create_password_setting_session(user_id: int, code: str):
    """Save that this user is setting a password for a specific code."""
    await password_settings_col.update_one(
        {"_id": user_id},
        {
            "$set": {
                "code": code,
                "created_at": datetime.datetime.now(datetime.timezone.utc),
            }
        },
        upsert=True,
    )


async def get_password_setting_session(user_id: int):
    return await password_settings_col.find_one({"_id": user_id})


async def delete_password_setting_session(user_id: int):
    await password_settings_col.delete_one({"_id": user_id})


async def create_password_entry_session(
    user_id: int, code: str, bypass_monetization: bool = False
):
    """Save that this user is entering a password for a specific code."""
    await password_entries_col.update_one(
        {"_id": user_id},
        {
            "$set": {
                "code": code,
                "bypass_monetization": bypass_monetization,
                "created_at": datetime.datetime.now(datetime.timezone.utc),
            }
        },
        upsert=True,
    )


async def get_password_entry_session(user_id: int):
    return await password_entries_col.find_one({"_id": user_id})


async def delete_password_entry_session(user_id: int):
    await password_entries_col.delete_one({"_id": user_id})


# --- DELETION HELPERS ---


async def schedule_deletion(chat_id: int, message_ids: list, delay_seconds: int = 300):
    """Schedule a list of messages for deletion after a delay."""
    await deletions_col.insert_one(
        {
            "chat_id": chat_id,
            "message_ids": message_ids,
            "delete_at": datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(seconds=delay_seconds),
        }
    )


async def get_expired_deletions() -> list:
    """Retrieve all deletion tasks that are due."""
    cursor = deletions_col.find(
        {"delete_at": {"$lte": datetime.datetime.now(datetime.timezone.utc)}}
    )
    return [doc async for doc in cursor]


async def remove_deletion_task(task_id):
    """Remove a deletion task from DB after processing."""
    await deletions_col.delete_one({"_id": task_id})


# --- ACTIVE DELIVERIES IDEMPOTENCY LOCKS ---


async def start_delivery(user_id: int, code: str) -> bool:
    """
    Attempt to register a delivery task as in-progress for user_id and code.
    Cleans up stale records older than 60 seconds automatically.
    Returns True if successfully started, False if already in-progress.
    """
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        stale_limit = now - datetime.timedelta(seconds=60)

        # Remove stale lock documents
        await active_deliveries_col.delete_many({"started_at": {"$lt": stale_limit}})

        # Atomically register the lock using user_id + code as unique _id
        result = await active_deliveries_col.update_one(
            {"_id": f"{user_id}_{code}"},
            {"$setOnInsert": {"user_id": user_id, "code": code, "started_at": now}},
            upsert=True,
        )

        # If upserted_id is set, it means a new document was inserted (lock acquired successfully)
        return result.upserted_id is not None
    except Exception as e:
        logger.error(
            f"Failed to start delivery for user {user_id} and code {code}: {e}"
        )
        return False


async def finish_delivery(user_id: int, code: str):
    """Mark the delivery as finished by releasing the lock."""
    try:
        await active_deliveries_col.delete_one({"_id": f"{user_id}_{code}"})
    except Exception as e:
        logger.error(
            f"Failed to finish delivery for user {user_id} and code {code}: {e}"
        )


# --- AD DRAFT SESSION HELPERS ---


async def upsert_ad_draft(user_id: int, data: dict) -> None:
    if "created_at" not in data:
        data["created_at"] = datetime.datetime.now(datetime.timezone.utc)
    await ad_drafts_col.update_one(
        {"_id": user_id},
        {"$set": data},
        upsert=True,
    )


async def get_ad_draft(user_id: int) -> dict | None:
    return await ad_drafts_col.find_one({"_id": user_id})


async def clear_ad_draft(user_id: int) -> None:
    await ad_drafts_col.delete_one({"_id": user_id})


async def delete_expired_drafts_and_states() -> None:
    """Clear all drafts and temporary states older than 24 hours on startup or via worker."""
    now = datetime.datetime.now(datetime.timezone.utc)
    limit_24h = now - datetime.timedelta(hours=24)

    try:
        # 1. Clear expired ad drafts
        res = await ad_drafts_col.delete_many({"created_at": {"$lt": limit_24h}})
        if res.deleted_count > 0:
            logger.info(f"Deleted {res.deleted_count} expired ad drafts.")

        # 2. Clear expired upload batches
        res = await batches_col.delete_many({"created_at": {"$lt": limit_24h}})
        if res.deleted_count > 0:
            logger.info(f"Deleted {res.deleted_count} expired upload batches.")

        # 3. Clear expired edit sessions
        res = await edit_sessions_col.delete_many({"created_at": {"$lt": limit_24h}})
        if res.deleted_count > 0:
            logger.info(f"Deleted {res.deleted_count} expired edit sessions.")

        # 4. Clear expired password sessions
        res = await password_settings_col.delete_many({"created_at": {"$lt": limit_24h}})
        res2 = await password_entries_col.delete_many({"created_at": {"$lt": limit_24h}})
        if res.deleted_count > 0 or res2.deleted_count > 0:
            logger.info(f"Deleted {res.deleted_count + res2.deleted_count} expired password sessions.")

        # 5. Clear expired post drafts
        from database.mongo import drafts_col
        res = await drafts_col.delete_many({"updated_at": {"$lt": limit_24h}})
        if res.deleted_count > 0:
            logger.info(f"Deleted {res.deleted_count} expired post drafts.")

        # 6. Clear stale user states/drafts (where last_seen < 24h ago)
        from database.mongo import users_col
        res = await users_col.update_many(
            {"last_seen": {"$lt": limit_24h}},
            {"$unset": {
                "state": "",
                "catalog_draft": "",
                "marketplace_draft": "",
                "shortener_draft": "",
                "saas_pending_plan": ""
            }}
        )
        if res.modified_count > 0:
            logger.info(f"Cleared stale user states/drafts for {res.modified_count} users.")
    except Exception as e:
        logger.error(f"Error deleting expired drafts and states: {e}")


async def clear_active_deliveries():
    """Clear all active deliveries on startup (useful for server restarts)."""
    try:
        await active_deliveries_col.delete_many({})
        logger.info("Cleared all active deliveries from the database.")
    except Exception as e:
        logger.error(f"Failed to clear active deliveries: {e}")
