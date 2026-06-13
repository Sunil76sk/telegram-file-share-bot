from __future__ import annotations

import datetime
from bson import ObjectId
from database.mongo import (
    channels_col,
    scheduled_posts_col,
    templates_col,
    repost_jobs_col,
    post_drafts_col,
    channel_stats_col,
    button_clicks_col,
)

# ─── CHANNEL MANAGEMENT HELPERS ──────────────────────────────────────

async def add_creator_channel(
    user_id: int,
    channel_id: int | str,
    title: str,
    username: str | None = None,
    invite_link: str | None = None,
    permissions_verified: bool = True,
):
    """Add a channel owned by a creator to Creator Studio."""
    await channels_col.update_one(
        {"_id": channel_id},
        {
            "$set": {
                "user_id": user_id,
                "channel_id": channel_id,
                "channel_title": title,
                "title": title,
                "username": username,
                "invite_link": invite_link,
                "permissions_verified": permissions_verified,
                "service_enabled": True,
                "added_at": datetime.datetime.now(datetime.timezone.utc),
            }
        },
        upsert=True,
    )

async def get_creator_channels(user_id: int) -> list:
    """Get all channels managed by a specific creator."""
    cursor = channels_col.find({"user_id": user_id})
    return [doc async for doc in cursor]

async def get_channel_by_id(channel_id: int | str):
    """Get channel details."""
    return await channels_col.find_one({"_id": channel_id})

# ─── POST DRAFT HELPERS ──────────────────────────────────────────────

async def save_post_draft(user_id: int, draft: dict):
    """Save or update a creator's current post draft builder session."""
    draft["updated_at"] = datetime.datetime.now(datetime.timezone.utc)
    await post_drafts_col.update_one(
        {"_id": user_id},
        {"$set": draft},
        upsert=True,
    )

async def get_post_draft(user_id: int):
    """Get the active post draft for a user."""
    return await post_drafts_col.find_one({"_id": user_id})

async def delete_post_draft(user_id: int):
    """Delete a user's post draft session."""
    await post_drafts_col.delete_one({"_id": user_id})

# ─── SCHEDULED POST HELPERS ──────────────────────────────────────────

async def create_scheduled_post(
    user_id: int,
    channel_id: int | str,
    media_type: str,
    file_id: str | None,
    caption: str | None,
    buttons: list,
    scheduled_time: datetime.datetime,
    reactions: list | None = None,
    comments: bool = False,
    pin: bool = False,
    caption_above: bool = False,
    poster_url: str | None = None,
    poster_media: dict | None = None,
    layout_type: str = "layout_a",
    download_files: list | None = None,
    custom_buttons: list | None = None,
) -> str:
    """Create a scheduled post record."""
    doc = {
        "user_id": user_id,
        "channel_id": channel_id,
        "media_type": media_type,
        "file_id": file_id,
        "caption": caption,
        "buttons": buttons,
        "scheduled_time": scheduled_time,
        "reactions": reactions or [],
        "comments": comments,
        "pin": pin,
        "caption_above": caption_above,
        "poster_url": poster_url,
        "poster_media": poster_media or {"type": None, "file_id": None},
        "layout_type": layout_type,
        "download_files": download_files or [],
        "custom_buttons": custom_buttons or [],
        "status": "pending",
        "retry_count": 0,
        "failure_reason": None,
        "created_at": datetime.datetime.now(datetime.timezone.utc),
    }
    result = await scheduled_posts_col.insert_one(doc)
    return str(result.inserted_id)

async def get_pending_scheduled_posts() -> list:
    """Fetch scheduled posts that are due to be sent."""
    now = datetime.datetime.now(datetime.timezone.utc)
    cursor = scheduled_posts_col.find({"status": "pending", "scheduled_time": {"$lte": now}})
    return [doc async for doc in cursor]

async def mark_post_sent(post_id: str):
    """Mark scheduled post as completed."""
    await scheduled_posts_col.update_one(
        {"_id": ObjectId(post_id)},
        {"$set": {"status": "completed", "sent_at": datetime.datetime.now(datetime.timezone.utc)}},
    )

async def mark_post_failed(post_id: str, error_msg: str):
    """Mark scheduled post as failed after all retries exhausted."""
    await scheduled_posts_col.update_one(
        {"_id": ObjectId(post_id)},
        {"$set": {"status": "failed", "failure_reason": error_msg, "failed_at": datetime.datetime.now(datetime.timezone.utc)}},
    )

async def mark_post_retry(post_id: str, retry_count: int, error_msg: str):
    """Increment retry count for a scheduled post (stays pending for retry)."""
    await scheduled_posts_col.update_one(
        {"_id": ObjectId(post_id)},
        {"$set": {"retry_count": retry_count, "last_error": error_msg, "status": "pending"}},
    )

async def get_scheduled_posts_by_user(user_id: int) -> list:
    """Get all scheduled posts for a user."""
    cursor = scheduled_posts_col.find({"user_id": user_id}).sort("scheduled_time", 1)
    return [doc async for doc in cursor]

async def delete_scheduled_post(post_id: str) -> bool:
    """Delete a scheduled post."""
    result = await scheduled_posts_col.delete_one({"_id": ObjectId(post_id)})
    return result.deleted_count > 0

# ─── REPOST JOB HELPERS ──────────────────────────────────────────────

async def create_repost_job(
    user_id: int,
    channel_id: int | str,
    media_type: str,
    file_id: str | None,
    caption: str | None,
    buttons: list,
    repost_interval: int,
    delete_gap: int,
    reactions: list | None = None,
    comments: bool = False,
    pin: bool = False,
    caption_above: bool = False,
    poster_url: str | None = None,
    poster_media: dict | None = None,
    layout_type: str = "layout_a",
    download_files: list | None = None,
    custom_buttons: list | None = None,
) -> str:
    """Create a new auto-reposting job configuration."""
    now = datetime.datetime.now(datetime.timezone.utc)
    doc = {
        "user_id": user_id,
        "channel_id": channel_id,
        "media_type": media_type,
        "file_id": file_id,
        "caption": caption,
        "buttons": buttons,
        "repost_interval": repost_interval,
        "delete_gap": delete_gap,
        "reactions": reactions or [],
        "comments": comments,
        "pin": pin,
        "caption_above": caption_above,
        "poster_url": poster_url,
        "poster_media": poster_media or {"type": None, "file_id": None},
        "layout_type": layout_type,
        "download_files": download_files or [],
        "custom_buttons": custom_buttons or [],
        "last_post_id": None,
        "last_posted_at": None,
        "next_post_at": now,
        "created_at": now,
        "status": "active",
        "retry_count": 0,
        "failure_reason": None,
    }
    result = await repost_jobs_col.insert_one(doc)
    return str(result.inserted_id)

async def get_active_repost_jobs() -> list:
    """Get all active reposting tasks that are ready to trigger."""
    now = datetime.datetime.now(datetime.timezone.utc)
    cursor = repost_jobs_col.find({"status": "active", "next_post_at": {"$lte": now}})
    return [doc async for doc in cursor]

async def update_repost_job_run(job_id: str, last_post_id: int, next_post_at: datetime.datetime):
    """Update active repost task after successful posting."""
    await repost_jobs_col.update_one(
        {"_id": ObjectId(job_id)},
        {
            "$set": {
                "last_post_id": last_post_id,
                "last_posted_at": datetime.datetime.now(datetime.timezone.utc),
                "next_post_at": next_post_at,
                "retry_count": 0,
                "failure_reason": None,
            }
        },
    )

async def mark_repost_job_failed(job_id: str, error_msg: str):
    """Mark repost job as failed after all retries exhausted."""
    await repost_jobs_col.update_one(
        {"_id": ObjectId(job_id)},
        {"$set": {"status": "failed", "failure_reason": error_msg, "failed_at": datetime.datetime.now(datetime.timezone.utc)}},
    )

async def mark_repost_job_retry(job_id: str, retry_count: int, error_msg: str):
    """Increment retry count for repost job (schedule retry in 5 minutes)."""
    next_retry = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5)
    await repost_jobs_col.update_one(
        {"_id": ObjectId(job_id)},
        {"$set": {"retry_count": retry_count, "last_error": error_msg, "next_post_at": next_retry}},
    )

async def get_repost_jobs_by_user(user_id: int) -> list:
    """Get all reposting jobs configured by a user."""
    cursor = repost_jobs_col.find({"user_id": user_id})
    return [doc async for doc in cursor]

async def delete_repost_job(job_id: str) -> bool:
    """Delete a repost job configuration."""
    result = await repost_jobs_col.delete_one({"_id": ObjectId(job_id)})
    return result.deleted_count > 0

# ─── POST TEMPLATES HELPERS ──────────────────────────────────────────

async def save_template(user_id: int, name: str, template_type: str, caption: str | None, buttons: list):
    """Save a post template."""
    doc = {
        "user_id": user_id,
        "name": name,
        "type": template_type,
        "caption": caption,
        "buttons": buttons,
        "created_at": datetime.datetime.now(datetime.timezone.utc),
    }
    await templates_col.insert_one(doc)

async def get_user_templates(user_id: int) -> list:
    """Get all templates saved by a user."""
    cursor = templates_col.find({"user_id": user_id})
    return [doc async for doc in cursor]

async def get_template(template_id: str):
    """Fetch template details."""
    try:
        return await templates_col.find_one({"_id": ObjectId(template_id)})
    except Exception:
        return None

async def delete_template(template_id: str) -> bool:
    """Delete a saved template."""
    try:
        result = await templates_col.delete_one({"_id": ObjectId(template_id)})
        return result.deleted_count > 0
    except Exception:
        return False

# ─── CHANNEL ANALYTICS HELPERS ───────────────────────────────────────

async def increment_channel_stat(channel_id: int | str, stat_name: str, inc: int = 1):
    """Increment published posts, scheduled count, views, or clicks for a channel."""
    date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    await channel_stats_col.update_one(
        {"channel_id": channel_id, "date": date_str},
        {"$inc": {stat_name: inc}},
        upsert=True,
    )

async def get_channel_stats(channel_id: int | str, days: int = 30) -> list:
    """Get daily statistics logs for a channel."""
    cursor = channel_stats_col.find({"channel_id": channel_id}).sort("date", -1).limit(days)
    return [doc async for doc in cursor]

async def log_button_click(user_id: int, channel_id: int | str, message_id: int, button_text: str):
    """Log a user's click on a post builder URL button."""
    doc = {
        "user_id": user_id,
        "channel_id": channel_id,
        "message_id": message_id,
        "button_text": button_text,
        "clicked_at": datetime.datetime.now(datetime.timezone.utc),
    }
    await button_clicks_col.insert_one(doc)
    await increment_channel_stat(channel_id, "button_clicks", 1)


async def delete_creator_channel(channel_id: int | str, user_id: int) -> bool:
    """Remove a channel from Creator Studio channels collection, ensuring ownership."""
    channel = await channels_col.find_one({"_id": channel_id})
    if not channel:
        return False
    if channel.get("user_id") != user_id:
        return False
    result = await channels_col.delete_one({"_id": channel_id})
    return result.deleted_count > 0


async def toggle_reaction(chat_id: int, message_id: int, user_id: int, emoji: str) -> dict:
    """Toggle user's reaction on a message and return updated counts."""
    from database.mongo import db
    votes_col = db["reaction_votes"]
    existing = await votes_col.find_one({
        "chat_id": chat_id,
        "message_id": message_id,
        "user_id": user_id,
        "emoji": emoji
    })
    if existing:
        await votes_col.delete_one({"_id": existing["_id"]})
    else:
        await votes_col.insert_one({
            "chat_id": chat_id,
            "message_id": message_id,
            "user_id": user_id,
            "emoji": emoji,
            "timestamp": datetime.datetime.now(datetime.timezone.utc)
        })
    
    cursor = votes_col.find({"chat_id": chat_id, "message_id": message_id})
    votes = [doc async for doc in cursor]
    
    counts = {}
    for vote in votes:
        e = vote["emoji"]
        counts[e] = counts.get(e, 0) + 1
    return counts