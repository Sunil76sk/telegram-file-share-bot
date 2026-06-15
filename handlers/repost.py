from __future__ import annotations

import logging
import datetime
from bson import ObjectId
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from bot import app
import database
from database.mongo import db
from database.creator_db import (
    create_repost_job,
    update_repost_job_run,
    mark_repost_job_failed,
    mark_repost_job_retry,
)
from utils.helpers import banned_filter
from utils.publisher import publish_post
from handlers.scheduler import scheduler

logger = logging.getLogger(__name__)

async def send_repost_menu(client: Client, chat_id: int, draft: dict):
    interval = draft.get("repost_interval_minutes")
    interval_str = f"{interval} minutes" if interval else "Not Set"
    delete_old = "Yes" if draft.get("repost_delete_old", False) else "No"
    
    text = (
        "🔄 **Auto Repost Configuration**\n\n"
        f"🎬 **Movie:** {draft.get('movie_title')} [{draft.get('movie_year')}]\n"
        f"📢 **Channel:** {draft.get('channel_name')}\n\n"
        f"⏱ **Interval:** `{interval_str}`\n"
        f"🗑 **Delete Old Post:** `{delete_old}`\n\n"
        "Configure how often this post should be automatically re-posted to the channel. "
        "When enabled, the bot will periodically send the post again."
    )
    
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏱ Set Interval", callback_data="repost_menu_interval"),
            InlineKeyboardButton(f"🗑 Delete Old: {delete_old}", callback_data="repost_toggle_delete")
        ],
        [
            InlineKeyboardButton("✅ Confirm & Enable Auto Repost", callback_data="repost_confirm")
        ],
        [
            InlineKeyboardButton("↩️ Back", callback_data="build_btn_back")
        ]
    ])
    
    await client.send_message(chat_id=chat_id, text=text, reply_markup=kb)

async def edit_repost_menu(message: Message, draft: dict):
    interval = draft.get("repost_interval_minutes")
    interval_str = f"{interval} minutes" if interval else "Not Set"
    delete_old = "Yes" if draft.get("repost_delete_old", False) else "No"
    
    text = (
        "🔄 **Auto Repost Configuration**\n\n"
        f"🎬 **Movie:** {draft.get('movie_title')} [{draft.get('movie_year')}]\n"
        f"📢 **Channel:** {draft.get('channel_name')}\n\n"
        f"⏱ **Interval:** `{interval_str}`\n"
        f"🗑 **Delete Old Post:** `{delete_old}`\n\n"
        "Configure how often this post should be automatically re-posted to the channel. "
        "When enabled, the bot will periodically send the post again."
    )
    
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏱ Set Interval", callback_data="repost_menu_interval"),
            InlineKeyboardButton(f"🗑 Delete Old: {delete_old}", callback_data="repost_toggle_delete")
        ],
        [
            InlineKeyboardButton("✅ Confirm & Enable Auto Repost", callback_data="repost_confirm")
        ],
        [
            InlineKeyboardButton("↩️ Back", callback_data="build_btn_back")
        ]
    ])
    
    await message.edit_text(text, reply_markup=kb)

# Callback: Open Repost Menu
@app.on_callback_query(filters.regex(r"^builder_repost$"))
async def builder_repost_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    await edit_repost_menu(callback_query.message, draft)
    await callback_query.answer()

# Callback: Show Interval Options
@app.on_callback_query(filters.regex(r"^repost_menu_interval$"))
async def repost_menu_interval_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1 Hour", callback_data="repost_set_interval_60"),
            InlineKeyboardButton("3 Hours", callback_data="repost_set_interval_180")
        ],
        [
            InlineKeyboardButton("6 Hours", callback_data="repost_set_interval_360"),
            InlineKeyboardButton("12 Hours", callback_data="repost_set_interval_720")
        ],
        [
            InlineKeyboardButton("24 Hours", callback_data="repost_set_interval_1440")
        ],
        [
            InlineKeyboardButton("✏️ Custom Minutes", callback_data="repost_interval_custom")
        ],
        [
            InlineKeyboardButton("↩️ Back", callback_data="builder_repost")
        ]
    ])
    
    await callback_query.message.edit_text(
        "⏱ **Select Repost Interval**\n\n"
        "Choose one of the standard intervals below or enter a custom duration in minutes:",
        reply_markup=kb
    )
    await callback_query.answer()

# Callback: Toggle Delete Old Post
@app.on_callback_query(filters.regex(r"^repost_toggle_delete$"))
async def repost_toggle_delete_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    draft["repost_delete_old"] = not draft.get("repost_delete_old", False)
    await database.save_post_draft(user_id, draft)
    await callback_query.answer(f"Delete old post: {'Yes' if draft['repost_delete_old'] else 'No'}")
    await edit_repost_menu(callback_query.message, draft)

# Callback: Set Pre-defined Interval
@app.on_callback_query(filters.regex(r"^repost_set_interval_(\d+)$"))
async def repost_set_interval_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    interval = int(callback_query.matches[0].group(1))
    
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    draft["repost_interval_minutes"] = interval
    await database.save_post_draft(user_id, draft)
    await callback_query.answer(f"Interval set to {interval}m")
    await edit_repost_menu(callback_query.message, draft)

# Callback: Request Custom Interval Input
@app.on_callback_query(filters.regex(r"^repost_interval_custom$"))
async def repost_interval_custom_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    draft["state"] = "awaiting_repost_interval"
    await database.save_post_draft(user_id, draft)
    await callback_query.answer()
    
    await callback_query.message.edit_text(
        "✏️ **Custom Repost Interval**\n\n"
        "Please enter the repost interval in minutes (between 10 and 10080):\n"
        "Example: `45` or `120`"
    )

# Callback: Confirm and Enable Repost
@app.on_callback_query(filters.regex(r"^repost_confirm$"))
async def repost_confirm_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    if not draft.get("repost_interval_minutes"):
        await callback_query.answer("❌ Please set an interval first", show_alert=True)
        return

    if not draft.get("poster_file_id"):
        await callback_query.answer("❌ Please upload a poster first", show_alert=True)
        return

    await callback_query.answer("Enabling Auto Repost...")
    
    try:
        # Create repost job in DB
        job_id = await create_repost_job(
            user_id=user_id,
            channel_id=draft["channel_id"],
            media_type="photo",
            file_id=draft["poster_file_id"],
            caption=draft["caption_html"],
            buttons=draft["url_buttons"],
            repost_interval=draft["repost_interval_minutes"],
            delete_gap=0,
            reactions=draft.get("reactions") or [],
            comments=draft.get("comments_enabled", False),
            pin=draft.get("pin_message", False),
        )
        
        # Save custom field delete_old in DB
        await db.repost_jobs.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": {"delete_old": draft.get("repost_delete_old", False)}}
        )
        
        # Schedule in APScheduler immediately
        job_key = f"repost_{job_id}"
        scheduler.add_job(
            run_repost_job,
            "interval",
            minutes=draft["repost_interval_minutes"],
            next_run_time=datetime.datetime.now(datetime.timezone.utc), # run first post immediately
            args=[job_id],
            id=job_key,
            replace_existing=True
        )
        
        # Increment stats
        await database.increment_channel_stat(draft["channel_id"], "scheduled_posts", 1)
        
        # Delete draft
        await database.delete_post_draft(user_id)
        
        await callback_query.message.edit_text(
            f"✅ **Auto Repost successfully enabled!**\n\n"
            f"📢 **Channel:** {draft['channel_name']}\n"
            f"⏱ **Interval:** every {draft['repost_interval_minutes']} minutes\n"
            f"🗑 **Delete Old Post:** {'Yes' if draft['repost_delete_old'] else 'No'}\n\n"
            "Bot will execute the first repost now."
        )
    except Exception as e:
        logger.error(f"Failed to enable auto repost: {e}", exc_info=True)
        await callback_query.message.edit_text(f"❌ **Failed to enable Auto Repost:** `{e}`")

# Message handler for custom interval input
@app.on_message(filters.private & ~banned_filter, group=6)
async def repost_input_handler(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    
    if text.lower() == "/cancel":
        return
        
    draft = await database.get_post_draft(user_id)
    if not draft:
        return
        
    state = draft.get("state")
    if state != "awaiting_repost_interval":
        return
        
    try:
        interval = int(text)
        if interval < 10 or interval > 10080:
            await message.reply_text("❌ **Invalid range.** Please enter a number between 10 and 10080:")
            message.stop_propagation()
            return
            
        draft["repost_interval_minutes"] = interval
        draft["state"] = "active"
        await database.save_post_draft(user_id, draft)
        
        await message.reply_text(f"✅ Repost interval set to {interval} minutes.")
        await send_repost_menu(client, user_id, draft)
    except ValueError:
        await message.reply_text("❌ **Invalid number.** Please send an integer value for minutes:")
        
    message.stop_propagation()

# ─── REPOST EXECUTION & RECOVERY ─────────────────────────────────────

async def run_repost_job(job_id: str):
    """Execute the repost job: post new, delete old, update schedule."""
    try:
        job = await db.repost_jobs.find_one({"_id": ObjectId(job_id)})
        if not job or job.get("status") != "active":
            logger.info(f"Repost job {job_id} not active or not found. Skipping.")
            return

        user_id = job["user_id"]
        channel_id = job["channel_id"]
        
        # Prepare post data dictionary mapping to what publish_post expects
        post_data = {
            "user_id": user_id,
            "channel_id": channel_id,
            "poster_file_id": job["file_id"],
            "caption_html": job.get("caption") or "",
            "url_buttons": job.get("buttons") or [],
            "reactions": job.get("reactions") or [],
            "comments_enabled": job.get("comments") or False,
            "pin_message": job.get("pin") or False,
            "repost_enabled": True
        }
        
        logger.info(f"Running repost job {job_id} for channel {channel_id}...")
        
        # Send new post first
        new_msg_id = await publish_post(post_data, app, delete_draft=False)
        logger.info(f"Repost job {job_id} published new message: {new_msg_id}")
        
        # Delete old post if enabled and last_post_id is set
        if job.get("delete_old") and job.get("last_post_id"):
            old_msg_id = job["last_post_id"]
            try:
                await app.delete_messages(chat_id=channel_id, message_ids=[old_msg_id])
                logger.info(f"Repost job {job_id} deleted old message: {old_msg_id}")
            except Exception as e:
                logger.warning(f"Repost job {job_id} failed to delete old message {old_msg_id}: {e}")

        # Calculate next post time
        next_post_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=job["repost_interval"])
        
        # Update run in DB
        await update_repost_job_run(job_id, new_msg_id, next_post_at)
        
    except Exception as e:
        logger.error(f"Error executing repost job {job_id}: {e}", exc_info=True)
        # Handle retry
        try:
            job = await db.repost_jobs.find_one({"_id": ObjectId(job_id)})
            if job:
                retry_count = job.get("retry_count", 0) + 1
                if retry_count >= 5:
                    await mark_repost_job_failed(job_id, f"Max retries (5) exceeded. Last error: {str(e)}")
                    # Remove from scheduler
                    job_key = f"repost_{job_id}"
                    if scheduler.get_job(job_key):
                        scheduler.remove_job(job_key)
                else:
                    await mark_repost_job_retry(job_id, retry_count, str(e))
        except Exception as retry_err:
            logger.error(f"Error handling repost job retry for {job_id}: {retry_err}", exc_info=True)

async def init_repost_jobs(client: Client):
    """Recover and schedule active repost jobs on startup."""
    try:
        # Fetch all active repost jobs from DB
        cursor = db.repost_jobs.find({"status": "active"})
        active_jobs = [doc async for doc in cursor]
        
        count = 0
        for job in active_jobs:
            job_id = str(job["_id"])
            # Remove existing job if any to avoid duplicates
            job_key = f"repost_{job_id}"
            try:
                if scheduler.get_job(job_key):
                    scheduler.remove_job(job_key)
            except Exception:
                pass
                
            # If next_post_at is in the past or not set, run it soon or now
            next_run = job.get("next_post_at")
            now = datetime.datetime.now(datetime.timezone.utc)
            if not next_run:
                next_run = now
            elif next_run.tzinfo is None:
                next_run = next_run.replace(tzinfo=datetime.timezone.utc)
                
            # If it's in the past, set it to run in 5 seconds to avoid flooding immediately
            if next_run <= now:
                next_run = now + datetime.timedelta(seconds=5)
                
            # Register in APScheduler
            scheduler.add_job(
                run_repost_job,
                "interval",
                minutes=job["repost_interval"],
                next_run_time=next_run,
                args=[job_id],
                id=job_key,
                replace_existing=True
            )
            count += 1
            
        logger.info(f"Recovered and scheduled {count} active repost jobs.")
    except Exception as e:
        logger.error(f"Error during repost jobs recovery: {e}", exc_info=True)
