from __future__ import annotations

import datetime
import logging
from typing import Any

from bson import ObjectId
from database.mongo import db

logger = logging.getLogger(__name__)

CHANNEL_POST_HISTORY_COL = db["channel_post_history"]


async def record_post(
    channel_id: int | str,
    user_id: int,
    message_id: int,
    media_type: str,
    caption: str,
    buttons: list | None = None,
    reactions: list | None = None,
    comments: bool = False,
    pin: bool = False,
    caption_above: bool = False,
    scheduled: bool = False,
    repost: bool = False,
) -> str:
    doc = {
        "channel_id": channel_id,
        "user_id": user_id,
        "message_id": message_id,
        "media_type": media_type,
        "caption": caption,
        "buttons": buttons or [],
        "reactions": reactions or [],
        "comments": comments,
        "pin": pin,
        "caption_above": caption_above,
        "scheduled": scheduled,
        "repost": repost,
        "posted_at": datetime.datetime.now(datetime.timezone.utc),
        "views": 0,
        "clicks": 0,
    }
    result = await CHANNEL_POST_HISTORY_COL.insert_one(doc)
    return str(result.inserted_id)


async def get_channel_post_history(
    channel_id: int | str,
    limit: int = 50,
    skip: int = 0,
) -> list[dict]:
    cursor = (
        CHANNEL_POST_HISTORY_COL.find({"channel_id": channel_id})
        .sort("posted_at", -1)
        .skip(skip)
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def get_user_post_history(
    user_id: int,
    limit: int = 50,
    skip: int = 0,
) -> list[dict]:
    cursor = (
        CHANNEL_POST_HISTORY_COL.find({"user_id": user_id})
        .sort("posted_at", -1)
        .skip(skip)
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def get_post_history_entry(post_id: str) -> dict | None:
    try:
        return await CHANNEL_POST_HISTORY_COL.find_one({"_id": ObjectId(post_id)})
    except Exception:
        return None


async def delete_post_history_entry(post_id: str, user_id: int) -> bool:
    try:
        result = await CHANNEL_POST_HISTORY_COL.delete_one(
            {"_id": ObjectId(post_id), "user_id": user_id}
        )
        return result.deleted_count > 0
    except Exception:
        return False


async def increment_post_views(post_id: str) -> bool:
    try:
        result = await CHANNEL_POST_HISTORY_COL.update_one(
            {"_id": ObjectId(post_id)},
            {"$inc": {"views": 1}},
        )
        return result.modified_count > 0
    except Exception:
        return False


async def increment_post_clicks(post_id: str) -> bool:
    try:
        result = await CHANNEL_POST_HISTORY_COL.update_one(
            {"_id": ObjectId(post_id)},
            {"$inc": {"clicks": 1}},
        )
        return result.modified_count > 0
    except Exception:
        return False


async def get_channel_post_count(channel_id: int | str) -> int:
    return await CHANNEL_POST_HISTORY_COL.count_documents({"channel_id": channel_id})


async def get_user_post_count(user_id: int) -> int:
    return await CHANNEL_POST_HISTORY_COL.count_documents({"user_id": user_id})


async def cleanup_old_history(days: int = 90):
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=days
    )
    result = await CHANNEL_POST_HISTORY_COL.delete_many({"posted_at": {"$lt": cutoff}})
    if result.deleted_count:
        logger.info(
            f"Cleaned {result.deleted_count} old post history entries (> {days}d)"
        )
