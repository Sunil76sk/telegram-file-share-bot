from __future__ import annotations

import logging
import asyncio
import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from bot import app
import database
from utils.helpers import banned_filter

logger = logging.getLogger(__name__)


# ─── STATE HANDLERS FOR POST BUILDER INTEGRATION ──────────────────────

@app.on_message(filters.private & ~banned_filter, group=6)
async def scheduler_input_handler(client: Client, message: Message):
    user_id = message.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft or draft.get("state") not in ["awaiting_schedule_time", "awaiting_repost_interval", "awaiting_delete_gap"]:
        return

    state = draft.get("state")
    text = message.text.strip() if message.text else ""

    if text.lower() == "/cancel":
        await database.delete_post_draft(user_id)
        await message.reply_text("❌ **Post builder session cancelled.**")
        message.stop_propagation()
        return

    # 1. Parse Schedule Time
    if state == "awaiting_schedule_time":
        try:
            scheduled_time = datetime.datetime.strptime(text, "%Y-%m-%d %H:%M")
            # Make timezone aware (UTC)
            scheduled_time = scheduled_time.replace(tzinfo=datetime.timezone.utc)
            
            if scheduled_time <= datetime.datetime.now(datetime.timezone.utc):
                await message.reply_text("❌ Scheduled time must be in the future. Please send again:")
                message.stop_propagation()
                return

            is_premium = await database.is_user_premium(user_id)
            max_future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
            if not is_premium and scheduled_time > max_future:
                await message.reply_text(
                    "❌ **Advanced Scheduling is a Premium Feature!**\n\n"
                    "Free creators can only schedule posts up to **24 hours in advance**.\n"
                    "Please enter a time within 24 hours, or upgrade to Premium with `/premium`."
                )
                message.stop_propagation()
                return

            # Save scheduled post
            await database.create_scheduled_post(
                user_id=user_id,
                channel_id=draft["channel_id"],
                media_type=draft["media_type"],
                file_id=draft["file_id"],
                caption=draft["caption"],
                buttons=draft["buttons"],
                scheduled_time=scheduled_time,
                reactions=draft["reactions"],
                comments=draft["comments"],
                pin=draft["pin"],
                caption_above=draft.get("caption_above", False)
            )
            # Update stats
            await database.increment_channel_stat(draft["channel_id"], "scheduled_posts", 1)
            await database.delete_post_draft(user_id)
            await message.reply_text(f"✅ **Post scheduled successfully for {text} UTC!**")
        except ValueError:
            await message.reply_text("❌ Invalid format. Please send in `YYYY-MM-DD HH:MM` format (e.g. `2026-06-15 14:30`):")
        message.stop_propagation()
        return

    # 2. Parse Repost Settings (Interval)
    elif state == "awaiting_repost_interval":
        try:
            interval = int(text)
            if interval < 5:
                await message.reply_text("❌ Minimum interval is 5 minutes. Please enter again:")
                message.stop_propagation()
                return
            draft["repost_interval"] = interval
            draft["state"] = "awaiting_delete_gap"
            await database.save_post_draft(user_id, draft)
            await message.reply_text(
                "🔄 **Auto Reposting Setup**\n\n"
                "Please enter the **Delete Gap** (delay in seconds between deleting the old post and sending the new one):\n"
                "Example: `10`"
            )
        except ValueError:
            await message.reply_text("❌ Please enter a valid integer representing minutes:")
        message.stop_propagation()
        return

    # 3. Parse Repost Settings (Delete Gap)
    elif state == "awaiting_delete_gap":
        try:
            gap = int(text)
            if gap < 0:
                await message.reply_text("❌ Delete gap cannot be negative. Please enter again:")
                message.stop_propagation()
                return
            
            # Create Reposting Job
            await database.create_repost_job(
                user_id=user_id,
                channel_id=draft["channel_id"],
                media_type=draft["media_type"],
                file_id=draft["file_id"],
                caption=draft["caption"],
                buttons=draft["buttons"],
                repost_interval=draft["repost_interval"],
                delete_gap=gap,
                reactions=draft["reactions"],
                comments=draft["comments"],
                pin=draft["pin"],
                caption_above=draft.get("caption_above", False)
            )
            await database.delete_post_draft(user_id)
            await message.reply_text("✅ **Auto Reposting Job created and started successfully!**")
        except ValueError:
            await message.reply_text("❌ Please enter a valid integer representing seconds:")
        message.stop_propagation()
        return


# Add auto repost entrypoint to builder menu
@app.on_callback_query(filters.regex(r"^build_btn_repost$"))
async def build_btn_repost_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Draft expired.", show_alert=True)
        return
    await callback_query.answer()
    draft["state"] = "awaiting_repost_interval"
    await database.save_post_draft(user_id, draft)
    await callback_query.message.edit_text(
        "🔄 **Auto Reposting Setup**\n\n"
        "Please enter the **Repost Interval** (in minutes) after which the post should be auto-reposted:\n"
        "Example: `60` (for every 1 hour)"
    )


# ─── LISTING & CANCELING SCHEDULED POSTS ──────────────────────────────

@app.on_message(filters.command("schedule") & filters.private & ~banned_filter)
async def list_schedule_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    posts = await database.get_scheduled_posts_by_user(user_id)
    if not posts:
        await message.reply_text("📅 **No scheduled posts pending.**")
        return

    text = "📅 **Pending Scheduled Posts:**\n\n"
    buttons = []
    for index, post in enumerate(posts, start=1):
        time_str = post["scheduled_time"].strftime("%Y-%m-%d %H:%M UTC")
        channel = await database.get_channel_by_id(post["channel_id"])
        ch_title = channel.get("title") if channel else str(post["channel_id"])
        
        text += f"{index}. **Channel:** {ch_title}\n   **Time:** `{time_str}`\n"
        buttons.append([InlineKeyboardButton(f"🗑 Delete #{index}", callback_data=f"del_sch_{post['_id']}")])

    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^del_sch_(.+)"))
async def delete_schedule_callback_handler(client: Client, callback_query: CallbackQuery):
    post_id = callback_query.matches[0].group(1)
    deleted = await database.delete_scheduled_post(post_id)
    if deleted:
        await callback_query.answer("🗑 Scheduled post deleted.", show_alert=True)
        try:
            await callback_query.message.delete()
        except Exception:
            pass
    else:
        await callback_query.answer("❌ Failed to delete scheduled post.", show_alert=True)


# ─── LISTING & CANCELING REPOST JOBS ──────────────────────────────────

@app.on_message(filters.command("reposts") & filters.private & ~banned_filter)
async def list_reposts_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    jobs = await database.get_repost_jobs_by_user(user_id)
    if not jobs:
        await message.reply_text("🔄 **No active auto-reposting jobs.**")
        return

    text = "🔄 **Active Auto-Reposting Jobs:**\n\n"
    buttons = []
    for index, job in enumerate(jobs, start=1):
        channel = await database.get_channel_by_id(job["channel_id"])
        ch_title = channel.get("title") if channel else str(job["channel_id"])
        text += f"{index}. **Channel:** {ch_title}\n   **Interval:** `{job['repost_interval']}m` | **Delete Gap:** `{job['delete_gap']}s`\n"
        buttons.append([InlineKeyboardButton(f"🗑 Stop Job #{index}", callback_data=f"del_rep_{job['_id']}")])

    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^del_rep_(.+)"))
async def delete_repost_callback_handler(client: Client, callback_query: CallbackQuery):
    job_id = callback_query.matches[0].group(1)
    deleted = await database.delete_repost_job(job_id)
    if deleted:
        await callback_query.answer("🗑 Auto-reposting job stopped.", show_alert=True)
        try:
            await callback_query.message.delete()
        except Exception:
            pass
    else:
        await callback_query.answer("❌ Failed to stop job.", show_alert=True)


# ─── BACKGROUND WORKER ENGINE ────────────────────────────────────────

async def start_scheduler_loop(client: Client):
    """Loop to process scheduled posts and auto-repost loops."""
    from handlers.post_builder import build_post_keyboard, get_comments_url
    while True:
        try:
            await asyncio.sleep(15)
            # 1. Process Scheduled Posts
            pending = await database.get_pending_scheduled_posts()
            for post in pending:
                post_id = str(post["_id"])
                channel_id = post["channel_id"]
                caption = post.get("caption", "")
                
                comments_url = None
                if post.get("comments"):
                    comments_url = await get_comments_url(client, channel_id)

                reply_markup = build_post_keyboard(
                    buttons_spec=post.get("buttons", []),
                    reactions=post.get("reactions", []),
                    reaction_counts=None,
                    comments_url=comments_url
                )

                try:
                    if post["media_type"] == "text":
                        msg = await client.send_message(chat_id=channel_id, text=caption, reply_markup=reply_markup)
                    else:
                        if post.get("caption_above"):
                            msg = await client.send_message(chat_id=channel_id, text=caption, reply_markup=reply_markup)
                            media_msg = await client.send_cached_media(chat_id=channel_id, file_id=post["file_id"])
                        else:
                            msg = await client.send_cached_media(chat_id=channel_id, file_id=post["file_id"], caption=caption, reply_markup=reply_markup)
                    
                    if post.get("pin") and msg:
                        try:
                            await client.pin_chat_message(chat_id=channel_id, message_id=msg.id)
                        except Exception:
                            pass

                    await database.mark_post_sent(post_id)
                except Exception as post_err:
                    logger.error(f"Scheduled post delivery failed for {post_id}: {post_err}")
                    await database.mark_post_failed(post_id, str(post_err))

            # 2. Process Auto Reposting Jobs
            reposts = await database.get_active_repost_jobs()
            for job in reposts:
                job_id = str(job["_id"])
                channel_id = job["channel_id"]
                caption = job.get("caption", "")
                
                comments_url = None
                if job.get("comments"):
                    comments_url = await get_comments_url(client, channel_id)

                reply_markup = build_post_keyboard(
                    buttons_spec=job.get("buttons", []),
                    reactions=job.get("reactions", []),
                    reaction_counts=None,
                    comments_url=comments_url
                )
                
                # Delete old message if exists
                if job.get("last_post_id"):
                    try:
                        await client.delete_messages(chat_id=channel_id, message_ids=job["last_post_id"])
                    except Exception as del_err:
                        logger.warning(f"Failed to delete old repost message in {channel_id}: {del_err}")

                # Wait custom delete gap
                delete_gap = job.get("delete_gap", 5)
                if delete_gap > 0:
                    await asyncio.sleep(delete_gap)

                # Send new message
                try:
                    if job["media_type"] == "text":
                        msg = await client.send_message(chat_id=channel_id, text=caption, reply_markup=reply_markup)
                    else:
                        if job.get("caption_above"):
                            msg = await client.send_message(chat_id=channel_id, text=caption, reply_markup=reply_markup)
                            media_msg = await client.send_cached_media(chat_id=channel_id, file_id=job["file_id"])
                        else:
                            msg = await client.send_cached_media(chat_id=channel_id, file_id=job["file_id"], caption=caption, reply_markup=reply_markup)
                    
                    if job.get("pin") and msg:
                        try:
                            await client.pin_chat_message(chat_id=channel_id, message_id=msg.id)
                        except Exception:
                            pass

                    # Calculate next post time
                    next_post_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=job["repost_interval"])
                    await database.update_repost_job_run(job_id, msg.id, next_post_time)
                    # Update stats
                    await database.increment_channel_stat(channel_id, "reposts", 1)
                except Exception as post_err:
                    logger.error(f"Repost job failed for {job_id}: {post_err}")
                    # Push next post time slightly to retry later
                    from database.mongo import repost_jobs_col
                    next_retry = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5)
                    await repost_jobs_col.update_one({"_id": job["_id"]}, {"$set": {"next_post_at": next_retry}})

        except Exception as loop_err:
            logger.error(f"Error in scheduler loop step: {loop_err}")
