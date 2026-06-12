from __future__ import annotations

import datetime
import logging
from typing import Any

from database.mongo import db

logger = logging.getLogger(__name__)

DRAFT_RECOVERY_COL = db["draft_recovery"]


async def record_draft_state(
    user_id: int,
    draft_id: str | None,
    state: str,
    metadata: dict | None = None,
):
    doc = {
        "user_id": user_id,
        "draft_id": draft_id,
        "state": state,
        "metadata": metadata or {},
        "recorded_at": datetime.datetime.now(datetime.timezone.utc),
    }
    await DRAFT_RECOVERY_COL.insert_one(doc)


async def recover_drafts_for_user(user_id: int) -> list[dict]:
    cursor = (
        DRAFT_RECOVERY_COL.find({"user_id": user_id})
        .sort("recorded_at", -1)
        .limit(5)
    )
    return [doc async for doc in cursor]


async def get_stale_drafts(max_age_minutes: int = 30) -> list[dict]:
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=max_age_minutes)
    cursor = DRAFT_RECOVERY_COL.find({"recorded_at": {"$lt": cutoff}}).sort("recorded_at", -1)
    return [doc async for doc in cursor]


async def cleanup_draft_recovery(hours: int = 48):
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    result = await DRAFT_RECOVERY_COL.delete_many({"recorded_at": {"$lt": cutoff}})
    if result.deleted_count:
        logger.info(f"Cleaned {result.deleted_count} draft recovery records older than {hours}h")


async def recover_interrupted_drafts() -> int:
    from database.creator_db import get_post_draft, save_post_draft

    recovered = 0
    cursor = DRAFT_RECOVERY_COL.aggregate([
        {"$group": {"_id": "$user_id", "last_record": {"$last": "$$ROOT"}}},
    ])

    async for group in cursor:
        user_id = group["_id"]
        last = group["last_record"]

        draft = await get_post_draft(user_id)
        if draft and draft.get("state") in ("awaiting_media", "awaiting_caption", "awaiting_buttons", "awaiting_reactions"):
            draft["state"] = "active"
            draft["recovered_at"] = datetime.datetime.now(datetime.timezone.utc)
            await save_post_draft(user_id, draft)
            logger.info(f"Recovered draft for user {user_id} from state '{last.get('state')}'")
            recovered += 1

    logger.info(f"Total draft recoveries: {recovered}")
    return recovered
