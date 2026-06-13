from __future__ import annotations

import logging
import asyncio
import datetime
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
from bot import app
import config
import database
from utils.helpers import banned_filter
from utils.caption_builder import build_telegram_caption_html

logger = logging.getLogger(__name__)

_scheduler = None


async def init_scheduler(client: Client):
    """Initialize APScheduler and start background jobs."""
    global _scheduler
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        logger.error("APScheduler not installed. Run: pip install apscheduler")
        return

    _scheduler = AsyncIOScheduler(timezone=getattr(config, "SCHEDULER_TIMEZONE", "UTC"))

    _scheduler.add_job(
        _process_scheduled_posts,
        IntervalTrigger(seconds=15),
        args=[client],
        id="scheduled_posts_checker",
        replace_existing=True,
        max_instances=1,
    )

    _scheduler.add_job(
        _process_repost_jobs,
        IntervalTrigger(seconds=30),
        args=[client],
        id="repost_jobs_checker",
        replace_existing=True,
        max_instances=1,
    )

    _scheduler.start()
    logger.info("APScheduler started with scheduled_posts_checker (15s) and repost_jobs_checker (30s).")


async def stop_scheduler():
    """Shutdown the scheduler gracefully."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler shut down.")


# ─── BACKGROUND WORKER: SCHEDULED POSTS ──────────────────────────────

async def _process_scheduled_posts(client: Client):
    """Process pending scheduled posts with retry logic."""
    from handlers.post_builder import build_post_keyboard, get_comments_url

    pending = await database.get_pending_scheduled_posts()
    for post in pending:
        post_id = str(post["_id"])
        retry_count = post.get("retry_count", 0)

        try:
            channel_id = post["channel_id"]
            caption = post.get("caption", "")
            poster_media = post.get("poster_media") or {}
            layout_type = post.get("layout_type", "layout_a")
            download_files = post.get("download_files", [])
            custom_buttons = post.get("custom_buttons", [])

            comments_url = None
            if post.get("comments"):
                comments_url = await get_comments_url(client, channel_id)

            reply_markup = build_post_keyboard(
                layout_type=layout_type,
                download_configs=download_files,
                custom_buttons=custom_buttons,
                reactions=post.get("reactions", []),
                comments_url=comments_url,
            )

            poster_type = poster_media.get("type") if poster_media else None
            poster_fid = poster_media.get("file_id") if poster_media else None
            parsed_caption = build_telegram_caption_html(caption) if caption else ""

            if poster_type == "photo":
                msg = await client.send_photo(
                    chat_id=channel_id, photo=poster_fid,
                    caption=parsed_caption, reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML if parsed_caption else None,
                )
            elif poster_type == "video":
                msg = await client.send_video(
                    chat_id=channel_id, video=poster_fid,
                    caption=parsed_caption, reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML if parsed_caption else None,
                )
            elif post.get("media_type") == "text":
                msg = await client.send_message(
                    chat_id=channel_id, text=parsed_caption, reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML if parsed_caption else None,
                )
            else:
                if post.get("caption_above") and post.get("file_id"):
                    msg = await client.send_message(
                        chat_id=channel_id, text=parsed_caption, reply_markup=reply_markup,
                        parse_mode=ParseMode.HTML if parsed_caption else None,
                    )
                    await client.send_cached_media(chat_id=channel_id, file_id=post["file_id"])
                elif post.get("file_id"):
                    msg = await client.send_cached_media(
                        chat_id=channel_id, file_id=post["file_id"],
                        caption=parsed_caption, reply_markup=reply_markup,
                        parse_mode=ParseMode.HTML if parsed_caption else None,
                    )
                else:
                    msg = await client.send_message(
                        chat_id=channel_id, text=parsed_caption, reply_markup=reply_markup,
                        parse_mode=ParseMode.HTML if parsed_caption else None,
                    )

            if post.get("pin") and msg:
                try:
                    await client.pin_chat_message(chat_id=channel_id, message_id=msg.id)
                except Exception:
                    pass

            await database.mark_post_sent(post_id)

        except Exception as post_err:
            logger.error(f"Scheduled post {post_id} failed (attempt {retry_count + 1}): {post_err}")
            new_retry = retry_count + 1
            if new_retry >= 3:
                await database.mark_post_failed(post_id, str(post_err))
            else:
                await database.mark_post_retry(post_id, new_retry, str(post_err))


# ─── BACKGROUND WORKER: AUTO REPOST ─────────────────────────────────

async def _process_repost_jobs(client: Client):
    """Process auto-repost jobs with persistent state."""
    from handlers.post_builder import build_post_keyboard, get_comments_url

    reposts = await database.get_active_repost_jobs()
    for job in reposts:
        job_id = str(job["_id"])
        retry_count = job.get("retry_count", 0)

        try:
            channel_id = job["channel_id"]
            caption = job.get("caption", "")
            poster_media = job.get("poster_media") or {}
            layout_type = job.get("layout_type", "layout_a")
            download_files = job.get("download_files", [])
            custom_buttons = job.get("custom_buttons", [])

            comments_url = None
            if job.get("comments"):
                comments_url = await get_comments_url(client, channel_id)

            reply_markup = build_post_keyboard(
                layout_type=layout_type,
                download_configs=download_files,
                custom_buttons=custom_buttons,
                reactions=job.get("reactions", []),
                comments_url=comments_url,
            )

            # Delete old message if exists
            old_msg_id = job.get("last_post_id")
            if old_msg_id:
                try:
                    await client.delete_messages(chat_id=channel_id, message_ids=old_msg_id)
                except Exception as del_err:
                    logger.warning(f"Failed to delete old repost message in {channel_id}: {del_err}")

            # Wait custom delete gap
            delete_gap = job.get("delete_gap", 5)
            if delete_gap > 0:
                await asyncio.sleep(delete_gap)

            # Send new message
            poster_type = poster_media.get("type") if poster_media else None
            poster_fid = poster_media.get("file_id") if poster_media else None
            parsed_caption = build_telegram_caption_html(caption) if caption else ""

            if poster_type == "photo":
                msg = await client.send_photo(
                    chat_id=channel_id, photo=poster_fid,
                    caption=parsed_caption, reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML if parsed_caption else None,
                )
            elif poster_type == "video":
                msg = await client.send_video(
                    chat_id=channel_id, video=poster_fid,
                    caption=parsed_caption, reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML if parsed_caption else None,
                )
            elif job.get("media_type") == "text":
                msg = await client.send_message(
                    chat_id=channel_id, text=parsed_caption, reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML if parsed_caption else None,
                )
            else:
                if job.get("caption_above") and job.get("file_id"):
                    msg = await client.send_message(
                        chat_id=channel_id, text=parsed_caption, reply_markup=reply_markup,
                        parse_mode=ParseMode.HTML if parsed_caption else None,
                    )
                    await client.send_cached_media(chat_id=channel_id, file_id=job["file_id"])
                elif job.get("file_id"):
                    msg = await client.send_cached_media(
                        chat_id=channel_id, file_id=job["file_id"],
                        caption=parsed_caption, reply_markup=reply_markup,
                        parse_mode=ParseMode.HTML if parsed_caption else None,
                    )
                else:
                    msg = await client.send_message(
                        chat_id=channel_id, text=parsed_caption, reply_markup=reply_markup,
                        parse_mode=ParseMode.HTML if parsed_caption else None,
                    )

            if job.get("pin") and msg:
                try:
                    await client.pin_chat_message(chat_id=channel_id, message_id=msg.id)
                except Exception:
                    pass

            # Update job state (persistent — survives restart)
            next_repost_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=job["repost_interval"])
            await database.update_repost_job_run(job_id, msg.id, next_repost_at)
            await database.increment_channel_stat(channel_id, "reposts", 1)

        except Exception as post_err:
            logger.error(f"Repost job {job_id} failed (attempt {retry_count + 1}): {post_err}")
            new_retry = retry_count + 1
            if new_retry >= 3:
                await database.mark_repost_job_failed(job_id, str(post_err))
            else:
                await database.mark_repost_job_retry(job_id, new_retry, str(post_err))


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
        await message.reply_text("Post builder session cancelled.")
        message.stop_propagation()
        return

    # 1. Parse Schedule Time (timezone-aware)
    if state == "awaiting_schedule_time":
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        user_doc = await database.get_user(user_id)
        user_tz = (user_doc or {}).get("timezone", "Asia/Kolkata")

        try:
            tz = ZoneInfo(user_tz)
        except (ZoneInfoNotFoundError, KeyError):
            tz = ZoneInfo("Asia/Kolkata")

        try:
            # Parse user input as naive datetime
            text_clean = text.strip()
            if not text_clean:
                await message.reply_text(
                    "❌ **Empty input!**\n\n"
                    "Send time in format: `YYYY-MM-DD HH:MM`\n"
                    "Example: `2026-06-15 14:30`"
                )
                message.stop_propagation()
                return

            try:
                scheduled_naive = datetime.datetime.strptime(text_clean, "%Y-%m-%d %H:%M")
            except ValueError as parse_err:
                logger.error(f"strptime failed for user {user_id}, input '{text_clean}': {parse_err}")
                await message.reply_text(
                    "❌ **Invalid format!**\n\n"
                    "Send time in format: `YYYY-MM-DD HH:MM`\n"
                    "Example: `2026-06-15 14:30`\n\n"
                    f"Your timezone: {user_tz}"
                )
                message.stop_propagation()
                return

            # Localize to user's timezone (naive → aware)
            scheduled_aware = scheduled_naive.replace(tzinfo=tz)
            
            # Convert to UTC for storage and comparison
            scheduled_utc = scheduled_aware.astimezone(datetime.timezone.utc)
            now_utc = datetime.datetime.now(datetime.timezone.utc)

            # Validate: must be in future
            if scheduled_utc <= now_utc:
                now_in_tz = now_utc.astimezone(tz)
                await message.reply_text(
                    f"❌ **Time is in the past!**\n\n"
                    f"Current time: `{now_in_tz.strftime('%Y-%m-%d %H:%M')} {user_tz}`\n"
                    f"Please enter a future time."
                )
                message.stop_propagation()
                return

            # Validate: premium users only can schedule > 24 hours ahead
            is_premium = await database.is_user_premium(user_id)
            max_future_utc = now_utc + datetime.timedelta(days=1)
            if not is_premium and scheduled_utc > max_future_utc:
                max_future_tz = max_future_utc.astimezone(tz)
                await message.reply_text(
                    "⏰ **Advanced Scheduling is a Premium Feature!**\n\n"
                    "Free creators can only schedule posts up to **24 hours in advance**.\n\n"
                    f"Max allowed: `{max_future_tz.strftime('%Y-%m-%d %H:%M')} {user_tz}`\n"
                    "Upgrade to Premium with `/premium` for unlimited scheduling."
                )
                message.stop_propagation()
                return

            # Format display time in user's timezone
            try:
                tz_abbrev = tz.tzname(scheduled_aware) or user_tz.split("/")[-1]
            except Exception:
                tz_abbrev = user_tz.split("/")[-1]

            display_time = scheduled_aware.strftime("%Y-%m-%d %I:%M %p")

            # Create scheduled post (store UTC time)
            await database.create_scheduled_post(
                user_id=user_id,
                channel_id=draft["channel_id"],
                media_type=draft["media_type"],
                file_id=draft["file_id"],
                caption=draft["caption"],
                buttons=draft.get("custom_buttons", []),
                scheduled_time=scheduled_utc,
                reactions=draft.get("reactions", []),
                comments=draft.get("comments_enabled", False),
                pin=draft.get("pin_message", False),
                caption_above=draft.get("caption_above", False),
                poster_media=draft.get("poster_media"),
                layout_type=draft.get("layout_type", "layout_a"),
                download_files=draft.get("download_files", []),
                custom_buttons=draft.get("custom_buttons", []),
            )
            await database.increment_channel_stat(draft["channel_id"], "scheduled_posts", 1)
            await database.delete_post_draft(user_id)
            
            await message.reply_text(
                f"✅ **Post scheduled successfully!**\n\n"
                f"**Time:** {display_time} {tz_abbrev}\n"
                f"**UTC:** {scheduled_utc.strftime('%Y-%m-%d %H:%M')} UTC"
            )
        except Exception as e:
            logger.error(f"Unexpected error scheduling post for user {user_id}: {e}", exc_info=True)
            await message.reply_text(
                "❌ **Error scheduling post**\n\n"
                "An unexpected error occurred. Please try again or contact support."
            )
        message.stop_propagation()
        return

    # 2. Parse Repost Settings (Interval)
    elif state == "awaiting_repost_interval":
        try:
            interval = int(text)
            if interval < 5:
                await message.reply_text("Minimum interval is 5 minutes. Please enter again:")
                message.stop_propagation()
                return
            draft["repost_interval"] = interval
            draft["state"] = "awaiting_delete_gap"
            await database.save_post_draft(user_id, draft)
            await message.reply_text(
                "Auto Reposting Setup\n\n"
                "Please enter the **Delete Gap** (delay in seconds between deleting the old post and sending the new one):\n"
                "Example: `10`"
            )
        except ValueError:
            await message.reply_text("Please enter a valid integer representing minutes:")
        message.stop_propagation()
        return

    # 3. Parse Repost Settings (Delete Gap)
    elif state == "awaiting_delete_gap":
        try:
            gap = int(text)
            if gap < 0:
                await message.reply_text("Delete gap cannot be negative. Please enter again:")
                message.stop_propagation()
                return

            await database.create_repost_job(
                user_id=user_id,
                channel_id=draft["channel_id"],
                media_type=draft["media_type"],
                file_id=draft["file_id"],
                caption=draft["caption"],
                buttons=draft.get("custom_buttons", []),
                repost_interval=draft["repost_interval"],
                delete_gap=gap,
                reactions=draft.get("reactions", []),
                comments=draft.get("comments_enabled", False),
                pin=draft.get("pin_message", False),
                caption_above=draft.get("caption_above", False),
                poster_media=draft.get("poster_media"),
                layout_type=draft.get("layout_type", "layout_a"),
                download_files=draft.get("download_files", []),
                custom_buttons=draft.get("custom_buttons", []),
            )
            await database.delete_post_draft(user_id)
            await message.reply_text("Auto Reposting Job created and started successfully!")
        except ValueError:
            await message.reply_text("Please enter a valid integer representing seconds:")
        message.stop_propagation()
        return


# ─── LISTING & CANCELING SCHEDULED POSTS ──────────────────────────────

@app.on_message(filters.command("schedule") & filters.private & ~banned_filter)
async def list_schedule_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    posts = await database.get_scheduled_posts_by_user(user_id)
    if not posts:
        await message.reply_text("No scheduled posts pending.")
        return

    text = "Pending Scheduled Posts:\n\n"
    buttons = []
    for index, post in enumerate(posts, start=1):
        time_str = post["scheduled_time"].strftime("%Y-%m-%d %H:%M UTC")
        channel = await database.get_channel_by_id(post["channel_id"])
        ch_title = channel.get("channel_title") if channel else str(post["channel_id"])
        status = post.get("status", "pending")

        text += f"{index}. **Channel:** {ch_title}\n   **Time:** `{time_str}`\n   **Status:** `{status}`\n"
        buttons.append([InlineKeyboardButton(f"Delete #{index}", callback_data=f"del_sch_{post['_id']}")])

    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^del_sch_(.+)"))
async def delete_schedule_callback_handler(client: Client, callback_query: CallbackQuery):
    post_id = callback_query.matches[0].group(1)
    deleted = await database.delete_scheduled_post(post_id)
    if deleted:
        await callback_query.answer("Scheduled post deleted.", show_alert=True)
        try:
            await callback_query.message.delete()
        except Exception:
            pass
    else:
        await callback_query.answer("Failed to delete scheduled post.", show_alert=True)


# ─── LISTING & CANCELING REPOST JOBS ──────────────────────────────────

@app.on_message(filters.command("reposts") & filters.private & ~banned_filter)
async def list_reposts_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    jobs = await database.get_repost_jobs_by_user(user_id)
    if not jobs:
        await message.reply_text("No active auto-reposting jobs.")
        return

    text = "Active Auto-Reposting Jobs:\n\n"
    buttons = []
    for index, job in enumerate(jobs, start=1):
        channel = await database.get_channel_by_id(job["channel_id"])
        ch_title = channel.get("channel_title") if channel else str(job["channel_id"])
        status = job.get("status", "active")
        text += f"{index}. **Channel:** {ch_title}\n   **Interval:** `{job['repost_interval']}m` | **Status:** `{status}`\n"
        buttons.append([InlineKeyboardButton(f"Stop Job #{index}", callback_data=f"del_rep_{job['_id']}")])

    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^del_rep_(.+)"))
async def delete_repost_callback_handler(client: Client, callback_query: CallbackQuery):
    job_id = callback_query.matches[0].group(1)
    deleted = await database.delete_repost_job(job_id)
    if deleted:
        await callback_query.answer("Auto-reposting job stopped.", show_alert=True)
        try:
            await callback_query.message.delete()
        except Exception:
            pass
    else:
        await callback_query.answer("Failed to stop job.", show_alert=True)



