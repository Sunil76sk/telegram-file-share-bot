from __future__ import annotations

import datetime
import logging
from typing import Any

from database.mongo import db

logger = logging.getLogger(__name__)

STATE_COL = db["user_states"]
STATE_LOG_COL = db["state_transitions"]

VALID_STATES = {
    "idle",
    "awaiting_media",
    "awaiting_caption",
    "awaiting_buttons",
    "awaiting_reactions",
    "awaiting_schedule_time",
    "awaiting_repost_interval",
    "awaiting_delete_gap",
    "sh_awaiting_url",
    "sh_awaiting_key",
    "sh_awaiting_weight",
    "sh_awaiting_geo",
    "sh_awaiting_cpm",
    "awaiting_template_name",
    "awaiting_template_type",
    "awaiting_template_content",
    "ad_awaiting_details",
    "awaiting_password_set",
    "awaiting_password_entry",
    "editing_active",
    "batch_active",
}

VALID_TRANSITIONS: dict[str, set[str]] = {
    "idle": {
        "awaiting_media",
        "batch_active",
        "sh_awaiting_url",
        "awaiting_template_name",
        "ad_awaiting_details",
        "awaiting_password_set",
        "awaiting_password_entry",
    },
    "awaiting_media": {
        "idle",
        "awaiting_caption",
        "awaiting_buttons",
        "awaiting_reactions",
    },
    "awaiting_caption": {"idle", "awaiting_buttons", "awaiting_reactions"},
    "awaiting_buttons": {"idle", "awaiting_reactions"},
    "awaiting_reactions": {"idle", "awaiting_schedule_time"},
    "awaiting_schedule_time": {"idle"},
    "awaiting_repost_interval": {"idle", "awaiting_delete_gap"},
    "awaiting_delete_gap": {"idle"},
    "sh_awaiting_url": {"sh_awaiting_key", "idle"},
    "sh_awaiting_key": {"sh_awaiting_weight", "idle"},
    "sh_awaiting_weight": {"sh_awaiting_geo", "idle"},
    "sh_awaiting_geo": {"sh_awaiting_cpm", "idle"},
    "sh_awaiting_cpm": {"idle"},
    "awaiting_template_name": {"awaiting_template_type", "idle"},
    "awaiting_template_type": {"awaiting_template_content", "idle"},
    "awaiting_template_content": {"idle"},
    "ad_awaiting_details": {"idle"},
    "awaiting_password_set": {"idle"},
    "awaiting_password_entry": {"idle"},
    "editing_active": {"idle"},
    "batch_active": {"idle"},
}


async def get_state(user_id: int) -> str | None:
    doc = await STATE_COL.find_one({"_id": user_id})
    return doc.get("state") if doc else None


async def get_state_data(user_id: int) -> dict[str, Any] | None:
    return await STATE_COL.find_one({"_id": user_id})


async def set_state(
    user_id: int,
    new_state: str,
    data: dict[str, Any] | None = None,
    previous_state: str | None = None,
) -> bool:
    if new_state not in VALID_STATES:
        logger.error(f"Invalid state '{new_state}' for user {user_id}")
        return False

    if previous_state:
        allowed = VALID_TRANSITIONS.get(previous_state, set())
        if new_state not in allowed:
            logger.warning(
                f"Invalid transition {previous_state} -> {new_state} for user {user_id}"
            )
            return False

    now = datetime.datetime.now(datetime.timezone.utc)
    doc = {"_id": user_id, "state": new_state, "updated_at": now}
    if data:
        doc["data"] = data

    await STATE_COL.update_one({"_id": user_id}, {"$set": doc}, upsert=True)

    await STATE_LOG_COL.insert_one(
        {
            "user_id": user_id,
            "previous_state": previous_state,
            "new_state": new_state,
            "transitioned_at": now,
        }
    )
    logger.info(f"State transition: user={user_id} {previous_state} -> {new_state}")
    return True


async def clear_state(user_id: int) -> bool:
    result = await STATE_COL.delete_one({"_id": user_id})
    if result.deleted_count:
        await STATE_LOG_COL.insert_one(
            {
                "user_id": user_id,
                "previous_state": "unknown",
                "new_state": "idle",
                "transitioned_at": datetime.datetime.now(datetime.timezone.utc),
            }
        )
        logger.info(f"State cleared for user {user_id}")
        return True
    return False


async def cleanup_stale_states(hours: int = 24):
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        hours=hours
    )
    result = await STATE_COL.delete_many({"updated_at": {"$lt": cutoff}})
    if result.deleted_count:
        logger.info(f"Cleaned {result.deleted_count} stale states older than {hours}h")
