from __future__ import annotations

import logging
import datetime
import calendar
import pytz
from bson import ObjectId
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import MessageNotModified
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.mongodb import MongoDBJobStore

from bot import app
import config
import database
from utils.helpers import banned_filter
from utils.publisher import publish_post

logger = logging.getLogger(__name__)

# Configure APScheduler with MongoDB jobstore
jobstores = {
    "default": MongoDBJobStore(
        database=config.DB_NAME,
        collection="apscheduler_jobs",
        host=config.MONGO_URI
    )
}

scheduler = AsyncIOScheduler(
    jobstores=jobstores,
    job_defaults={
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 3600
    },
    timezone=pytz.utc
)

_scheduler_started = False

async def init_scheduler(client: Client):
    global _scheduler_started
    if not _scheduler_started:
        scheduler.start()
        _scheduler_started = True
        logger.info("APScheduler started with MongoDB jobstore.")
    # Reconcile the DB (source of truth) with the scheduler so no pending post
    # is lost across restarts / downtime longer than the misfire grace window.
    await recover_scheduled_posts(client)

async def stop_scheduler():
    global _scheduler_started
    if _scheduler_started and scheduler.running:
        scheduler.shutdown(wait=False)
        _scheduler_started = False
        logger.info("APScheduler shut down gracefully.")

# Job wrapper function that gets executed by APScheduler
async def publish_scheduled_post(post_id: str):
    """APScheduler task to publish a scheduled post."""
    from database.mongo import db
    try:
        oid = ObjectId(post_id)
    except Exception:
        logger.error(f"Scheduled post id {post_id} is not a valid ObjectId.")
        return

    # Atomically claim the post. Only the runner that flips pending -> publishing
    # proceeds, so a recovered job and a leftover jobstore job (or a duplicate
    # bot instance) can never publish the same post twice.
    claim = await db.scheduled_posts.update_one(
        {"_id": oid, "status": "pending"},
        {"$set": {"status": "publishing", "claimed_at": datetime.datetime.now(datetime.timezone.utc)}},
    )
    if claim.modified_count == 0:
        existing = await db.scheduled_posts.find_one({"_id": oid})
        status = existing.get("status") if existing else "missing"
        logger.info(f"Scheduled post {post_id} not claimable (status={status}). Skipping.")
        return

    try:
        post = await db.scheduled_posts.find_one({"_id": oid})
        # Publish the post
        await publish_post(post, app, delete_draft=False)

        # Mark as completed
        await db.scheduled_posts.update_one(
            {"_id": oid},
            {"$set": {"status": "completed", "sent_at": datetime.datetime.now(datetime.timezone.utc)}}
        )
        logger.info(f"Scheduled post {post_id} published successfully.")
    except Exception as e:
        logger.error(f"Failed to publish scheduled post {post_id}: {e}", exc_info=True)
        # Retry with backoff (max 3 attempts) before giving up. Reset to pending
        # so the next attempt can re-claim it; the startup recovery sweep also
        # re-picks it if the retry job is lost on restart.
        try:
            doc = await db.scheduled_posts.find_one({"_id": oid})
            retry_count = (doc.get("retry_count", 0) if doc else 0) + 1
            now = datetime.datetime.now(datetime.timezone.utc)
            if retry_count < 3:
                await db.scheduled_posts.update_one(
                    {"_id": oid},
                    {
                        "$set": {"status": "pending", "retry_count": retry_count, "last_error": str(e)},
                        "$unset": {"claimed_at": ""},
                    },
                )
                retry_at = now + datetime.timedelta(minutes=5)
                scheduler.add_job(
                    publish_scheduled_post,
                    "date",
                    run_date=retry_at,
                    args=[post_id],
                    id=f"sched_{post_id}",
                    replace_existing=True,
                )
                logger.info(f"Scheduled post {post_id} will retry ({retry_count}/3) at {retry_at.isoformat()}.")
            else:
                await db.scheduled_posts.update_one(
                    {"_id": oid},
                    {"$set": {
                        "status": "failed",
                        "failure_reason": str(e),
                        "retry_count": retry_count,
                        "failed_at": now,
                    }}
                )
                logger.error(f"Scheduled post {post_id} failed permanently after {retry_count} attempts.")
        except Exception:
            pass


async def recover_scheduled_posts(client: Client):
    """Re-register or replay scheduled posts so none are lost across restarts.

    APScheduler's MongoDB jobstore persists jobs, but one-shot 'date' jobs whose
    run time elapsed during downtime are treated as misfires and dropped. The
    scheduled_posts collection is the source of truth, so on startup we:
      - reclaim posts stuck in 'publishing' from a crashed run,
      - immediately (staggered) re-publish any pending post whose time has passed,
      - (re)register a job for any pending future post.
    """
    from database.mongo import db
    now = datetime.datetime.now(datetime.timezone.utc)
    stale_cutoff = now - datetime.timedelta(minutes=15)
    query = {
        "$or": [
            {"status": "pending"},
            {"status": "publishing", "claimed_at": {"$lt": stale_cutoff}},
        ]
    }

    overdue_offset = 5
    recovered = 0
    async for post in db.scheduled_posts.find(query):
        post_id = str(post["_id"])
        job_key = f"sched_{post_id}"

        scheduled_time = post.get("scheduled_time")
        if scheduled_time is None:
            continue
        if scheduled_time.tzinfo is None:
            scheduled_time = scheduled_time.replace(tzinfo=datetime.timezone.utc)

        # Reset a stale 'publishing' claim so publish_scheduled_post can claim it again.
        if post.get("status") == "publishing":
            await db.scheduled_posts.update_one(
                {"_id": post["_id"]},
                {"$set": {"status": "pending"}, "$unset": {"claimed_at": ""}},
            )

        if scheduled_time <= now:
            # Overdue: stagger to avoid a thundering herd when many are due at once.
            run_date = now + datetime.timedelta(seconds=overdue_offset)
            overdue_offset += 3
        else:
            run_date = scheduled_time

        try:
            scheduler.add_job(
                publish_scheduled_post,
                "date",
                run_date=run_date,
                args=[post_id],
                id=job_key,
                replace_existing=True,
            )
            recovered += 1
        except Exception as e:
            logger.error(f"Failed to recover scheduled post {post_id}: {e}", exc_info=True)

    logger.info(f"Recovered and scheduled {recovered} pending scheduled post(s).")

# Helper: Build Calendar Inline Keyboard
def get_calendar_keyboard(year: int, month: int, timezone_str: str) -> InlineKeyboardMarkup:
    try:
        tz = pytz.timezone(timezone_str)
    except pytz.UnknownTimeZoneError:
        tz = pytz.timezone("Asia/Kolkata")
        
    now_local = datetime.datetime.now(tz).date()
    max_date = now_local + datetime.timedelta(days=30)
    
    kb_rows = []
    
    # Month Header Row
    month_name = calendar.month_name[month]
    kb_rows.append([
        InlineKeyboardButton("◀️", callback_data=f"schedule_month_prev_{year}_{month}"),
        InlineKeyboardButton(f"{month_name} {year}", callback_data="noop"),
        InlineKeyboardButton("▶️", callback_data=f"schedule_month_next_{year}_{month}")
    ])
    
    # Weekday Header Row
    kb_rows.append([
        InlineKeyboardButton(day, callback_data="noop") for day in ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
    ])
    
    # Weeks
    cal = calendar.Calendar(firstweekday=0)
    month_days = cal.monthdayscalendar(year, month)
    
    for week in month_days:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="noop"))
            else:
                date_obj = datetime.date(year, month, day)
                if date_obj < now_local or date_obj > max_date:
                    # Past or >30 days out -> disabled
                    row.append(InlineKeyboardButton(f"~{day}~", callback_data="noop"))
                else:
                    # Highlight today
                    if date_obj == now_local:
                        label = f"•{day}•"
                    else:
                        label = str(day)
                    date_str = date_obj.strftime("%Y%m%d")
                    row.append(InlineKeyboardButton(label, callback_data=f"schedule_date_{date_str}"))
        kb_rows.append(row)
        
    # Quick select buttons
    today_str = now_local.strftime("%Y%m%d")
    tomorrow_str = (now_local + datetime.timedelta(days=1)).strftime("%Y%m%d")
    plus3_str = (now_local + datetime.timedelta(days=3)).strftime("%Y%m%d")
    
    kb_rows.append([
        InlineKeyboardButton("Today", callback_data=f"schedule_date_{today_str}"),
        InlineKeyboardButton("Tomorrow", callback_data=f"schedule_date_{tomorrow_str}"),
        InlineKeyboardButton("+3 Days", callback_data=f"schedule_date_{plus3_str}")
    ])
    
    kb_rows.append([
        InlineKeyboardButton("↩️ Cancel", callback_data="build_btn_back")
    ])
    
    return InlineKeyboardMarkup(kb_rows)

# Callback: Open Schedule Flow (STEP 1: Timezone Selection)
@app.on_callback_query(filters.regex(r"^builder_schedule$"))
async def builder_schedule_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    try:
        draft = await database.get_post_draft(user_id)
        if not draft:
            await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
            return
            
        if callback_query.from_user.id != draft.get("user_id"):
            await callback_query.answer("❌ Not your session", show_alert=True)
            return

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🇮🇳 Asia/Kolkata (IST)", callback_data="schedule_tz_Asia/Kolkata"),
                InlineKeyboardButton("🇦🇪 Asia/Dubai (GST)", callback_data="schedule_tz_Asia/Dubai")
            ],
            [
                InlineKeyboardButton("🇸🇬 Asia/Singapore (SGT)", callback_data="schedule_tz_Asia/Singapore"),
                InlineKeyboardButton("🌐 UTC", callback_data="schedule_tz_UTC")
            ],
            [
                InlineKeyboardButton("✏️ Custom Timezone", callback_data="schedule_tz_custom")
            ],
            [
                InlineKeyboardButton("↩️ Back", callback_data="build_btn_back")
            ]
        ])

        await callback_query.message.edit_text(
            "🌍 **Scheduling — Select Timezone**\n\n"
            "Please select the timezone you want to use for scheduling this post:",
            reply_markup=kb
        )
        await callback_query.answer()
    except Exception as e:
        logger.error(f"Error in builder_schedule: {e}", exc_info=True)
        await callback_query.answer("⚠️ Error loading timezone menu", show_alert=True)

# Callback: Timezone Selected
@app.on_callback_query(filters.regex(r"^schedule_tz_(.+)$"))
async def schedule_tz_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    timezone_str = callback_query.matches[0].group(1)
    
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    await callback_query.answer()

    if timezone_str == "custom":
        draft["state"] = "awaiting_custom_timezone"
        await database.save_post_draft(user_id, draft)
        await callback_query.message.edit_text(
            "✏️ **Custom Timezone**\n\n"
            "Please enter your custom timezone name (IANA format):\n"
            "Example: `Europe/London` or `America/New_York`"
        )
        return

    # Standard timezone selected
    draft["schedule_timezone"] = timezone_str
    # Move to Date Picker
    now_tz = datetime.datetime.now(pytz.timezone(timezone_str))
    
    await callback_query.message.edit_text(
        "📅 **Scheduling — Select Date**\n\n"
        f"Timezone: `{timezone_str}`\n"
        "Choose a date from the calendar below (max 30 days ahead):",
        reply_markup=get_calendar_keyboard(now_tz.year, now_tz.month, timezone_str)
    )
    draft["state"] = "awaiting_schedule_date"
    await database.save_post_draft(user_id, draft)

# Callback: Date Selected (YYYYMMDD)
@app.on_callback_query(filters.regex(r"^schedule_date_(\d{8})$"))
async def schedule_date_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    date_str = callback_query.matches[0].group(1)
    
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    draft["schedule_date"] = date_str
    draft["state"] = "awaiting_schedule_time"
    await database.save_post_draft(user_id, draft)
    await callback_query.answer()

    # Reformat date for display
    formatted_date = f"{date_str[6:8]}/{date_str[4:6]}/{date_str[0:4]}"
    tz_str = draft.get("schedule_timezone", "Asia/Kolkata")

    await callback_query.message.edit_text(
        "⏰ **Scheduling — Enter Time**\n\n"
        f"**Selected Date:** {formatted_date}\n"
        f"**Timezone:** {tz_str}\n\n"
        "Please enter the time in **HH:MM** format (24-hour):\n"
        "Example: `08:00` or `20:30`"
    )

# Callback: Navigation Month Change
@app.on_callback_query(filters.regex(r"^schedule_month_(prev|next)_(\d{4})_(\d+)$"))
async def schedule_month_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    direction = callback_query.matches[0].group(1)
    year = int(callback_query.matches[0].group(2))
    month = int(callback_query.matches[0].group(3))
    
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    if direction == "prev":
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    else:
        month += 1
        if month == 13:
            month = 1
            year += 1

    tz_str = draft.get("schedule_timezone", "Asia/Kolkata")
    
    try:
        await callback_query.message.edit_reply_markup(
            reply_markup=get_calendar_keyboard(year, month, tz_str)
        )
    except MessageNotModified:
        pass
    await callback_query.answer()

# Callback: Confirm Schedule
@app.on_callback_query(filters.regex(r"^schedule_confirm$"))
async def schedule_confirm_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    scheduled_time_str = draft.get("pending_schedule_time_utc")
    if not scheduled_time_str:
        await callback_query.answer("❌ No scheduled time set", show_alert=True)
        return

    scheduled_utc = datetime.datetime.fromisoformat(scheduled_time_str)

    # Validate the essentials up front so we never persist an unpublishable post.
    if not draft.get("channel_id") or not draft.get("poster_file_id"):
        await callback_query.answer("❌ Missing channel or poster. Use /newpost", show_alert=True)
        return

    # Save to scheduled_posts collection
    from database.mongo import db
    post_doc = {
        "user_id": user_id,
        "channel_id": draft["channel_id"],
        "channel_name": draft.get("channel_name", ""),
        "poster_file_id": draft["poster_file_id"],
        "poster_bg_style": draft.get("poster_bg_style"),
        "caption_html": draft.get("caption_html", ""),
        "url_buttons": draft.get("url_buttons", []),
        "reactions_enabled": draft.get("reactions_enabled", False),
        "reactions": draft.get("reactions", []),
        "comments_enabled": draft.get("comments_enabled", False),
        "pin_message": draft.get("pin_message", False),
        "caption_above": draft.get("caption_above", False),
        "schedule_enabled": True,

        "scheduled_time": scheduled_utc,
        "schedule_timezone": draft.get("schedule_timezone", "UTC"),
        "repost_enabled": False,
        "status": "pending",
        "created_at": datetime.datetime.now(datetime.timezone.utc)
    }

    result = await db.scheduled_posts.insert_one(post_doc)
    post_id = str(result.inserted_id)

    # Save APScheduler job. The DB row is the source of truth: if registration
    # fails here, recover_scheduled_posts() will pick it up on the next startup,
    # so we log and continue rather than stranding the user.
    try:
        scheduler.add_job(
            publish_scheduled_post,
            "date",
            run_date=scheduled_utc,
            args=[post_id],
            id=f"sched_{post_id}",
            replace_existing=True,
        )
    except Exception as e:
        logger.error(f"Failed to register scheduler job for post {post_id}: {e}", exc_info=True)

    # Increment stats
    await database.increment_channel_stat(draft["channel_id"], "scheduled_posts", 1)

    # Delete draft
    await database.delete_post_draft(user_id)
    await callback_query.answer("Post scheduled successfully!")
    
    tz_str = draft.get("schedule_timezone", "UTC")
    try:
        tz = pytz.timezone(tz_str)
    except:
        tz = pytz.timezone("Asia/Kolkata")
    local_time = scheduled_utc.astimezone(tz)
    
    await callback_query.message.edit_text(
        f"✅ **Post scheduled successfully!**\n\n"
        f"🕐 **Time:** {local_time.strftime('%d %b %Y, %I:%M %p')} ({tz_str})\n"
        f"🌐 **UTC:** {scheduled_utc.strftime('%d %b %Y, %H:%M UTC')}"
    )

# Callback: Change schedule time (re-enter time)
@app.on_callback_query(filters.regex(r"^schedule_change_time$"))
async def schedule_change_time_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    draft["state"] = "awaiting_schedule_time"
    await database.save_post_draft(user_id, draft)
    await callback_query.answer()

    date_str = draft.get("schedule_date")
    formatted_date = f"{date_str[6:8]}/{date_str[4:6]}/{date_str[0:4]}"
    tz_str = draft.get("schedule_timezone", "Asia/Kolkata")

    await callback_query.message.edit_text(
        "⏰ **Scheduling — Enter Time**\n\n"
        f"**Selected Date:** {formatted_date}\n"
        f"**Timezone:** {tz_str}\n\n"
        "Please enter the time in **HH:MM** format (24-hour):\n"
        "Example: `08:00` or `20:30`"
    )

# Message input handler for scheduling states (custom timezone & time input)
@app.on_message(filters.private & ~banned_filter, group=4)
async def scheduler_input_handler(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""

    if text.lower() == "/cancel":
        return  # Handled by main cancel handler in post_builder.py

    ctx = await database.get_active_builder_context(user_id)
    if not ctx["is_scheduler_state"]:
        return
    draft = ctx["draft"]
    state = ctx["state"]

    # Handle Custom Timezone input
    if state == "awaiting_custom_timezone":
        try:
            pytz.timezone(text)
            draft["schedule_timezone"] = text
            
            now_tz = datetime.datetime.now(pytz.timezone(text))
            draft["state"] = "awaiting_schedule_date"
            await database.save_post_draft(user_id, draft)
            
            await message.reply_text(
                "📅 **Scheduling — Select Date**\n\n"
                f"Timezone: `{text}`\n"
                "Choose a date from the calendar below (max 30 days ahead):",
                reply_markup=get_calendar_keyboard(now_tz.year, now_tz.month, text)
            )
        except pytz.UnknownTimeZoneError:
            await message.reply_text(
                "❌ **Invalid timezone name.**\n\n"
                "Please enter a valid IANA timezone name (e.g. `Europe/London`, `Asia/Kolkata`):"
            )
        message.stop_propagation()
        return

    # Handle Time input (HH:MM)
    elif state == "awaiting_schedule_time":
        import re
        if not re.match(r"^\d{2}:\d{2}$", text):
            await message.reply_text("❌ **Invalid format.** Use HH:MM (e.g. 14:30):")
            message.stop_propagation()
            return
            
        parts = text.split(":")
        hours = int(parts[0])
        minutes = int(parts[1])
        if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
            await message.reply_text("❌ **Invalid time values.** Hours: 0-23, Minutes: 0-59. Enter again:")
            message.stop_propagation()
            return

        date_str = draft.get("schedule_date")
        tz_str = draft.get("schedule_timezone", "Asia/Kolkata")
        
        try:
            tz = pytz.timezone(tz_str)
        except:
            tz = pytz.timezone("Asia/Kolkata")

        # Parse date and combine
        try:
            year = int(date_str[0:4])
            month = int(date_str[4:6])
            day = int(date_str[6:8])
            
            local_naive = datetime.datetime(year, month, day, hours, minutes)
            local_aware = tz.localize(local_naive)
            scheduled_utc = local_aware.astimezone(pytz.utc)
            
            now_utc = datetime.datetime.now(pytz.utc)
            if scheduled_utc <= now_utc:
                await message.reply_text("❌ **Time is in the past.** Please enter a future time:")
                message.stop_propagation()
                return

            # Save pending time to draft in ISO format
            draft["pending_schedule_time_utc"] = scheduled_utc.isoformat()
            draft["state"] = "active"
            await database.save_post_draft(user_id, draft)

            # Step 4: Show confirmation
            confirm_text = (
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "📅 **SCHEDULE CONFIRMATION**\n\n"
                f"📢 **Channel:** {draft['channel_name']}\n"
                f"🎬 **Movie:** {draft['movie_title']} [{draft['movie_year']}]\n\n"
                f"🕐 **Scheduled:**\n"
                f"{local_aware.strftime('%d %b %Y, %I:%M %p')} ({tz_str})\n"
                f"(UTC: {scheduled_utc.strftime('%d %b %Y, %H:%M UTC')})\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
            
            await message.reply_text(
                confirm_text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Confirm Schedule", callback_data="schedule_confirm")],
                    [
                        InlineKeyboardButton("✏️ Change Time", callback_data="schedule_change_time"),
                        InlineKeyboardButton("❌ Cancel", callback_data="builder_cancel")
                    ]
                ])
            )
        except Exception as e:
            logger.error(f"Error calculating scheduled time: {e}", exc_info=True)
            await message.reply_text("⚠️ Something went wrong. Let's try again. Enter time:")
            
        message.stop_propagation()
        return
