from __future__ import annotations

import asyncio
import datetime
import logging
import os
from bson import ObjectId
from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import config
import database

logger = logging.getLogger(__name__)


async def scheduler_worker(app: Client):
    """Background loop that processes scheduled posts."""
    logger.info("Scheduler worker started.")
    while True:
        try:
            # Sleep 15 seconds between runs
            await asyncio.sleep(15)

            due_posts = await database.get_pending_scheduled_posts()
            if not due_posts:
                continue

            redirect_base = config.REDIRECT_BASE_URL.rstrip("/")

            for post in due_posts:
                post_id_str = str(post["_id"])
                logger.info(f"Processing scheduled post {post_id_str}...")

                try:
                    # 1. Pre-generate a click-tracking post entry ID
                    post_history_id = ObjectId()

                    # 2. Rewrite URLs in buttons
                    buttons = post.get("buttons", [])
                    rewritten_buttons = []
                    for idx, btn in enumerate(buttons):
                        track_url = f"{redirect_base}/clk/{str(post_history_id)}/{idx}"
                        rewritten_buttons.append(
                            {"text": btn["text"], "url": track_url}
                        )

                    # 3. Build inline keyboard
                    keyboard = []
                    for btn in rewritten_buttons:
                        keyboard.append(
                            [InlineKeyboardButton(text=btn["text"], url=btn["url"])]
                        )
                    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

                    # 4. Send the message
                    sent_msg = None
                    caption = post.get("caption", "")
                    media_type = post.get("media_type", "text")
                    poster_url = post.get("poster_url")

                    if media_type == "photo" and poster_url:
                        full_image_path = os.path.join("temp_uploads", poster_url)
                        if os.path.exists(full_image_path):
                            sent_msg = await app.send_photo(
                                chat_id=post["channel_id"],
                                photo=full_image_path,
                                caption=caption,
                                reply_markup=reply_markup,
                            )
                        else:
                            logger.error(
                                f"Scheduled post image not found: {full_image_path}. Sending text fallback."
                            )
                            sent_msg = await app.send_message(
                                chat_id=post["channel_id"],
                                text=caption,
                                reply_markup=reply_markup,
                            )
                    else:
                        sent_msg = await app.send_message(
                            chat_id=post["channel_id"],
                            text=caption,
                            reply_markup=reply_markup,
                        )

                    if sent_msg:
                        # 5. Record post history
                        history_doc = {
                            "_id": post_history_id,
                            "channel_id": post["channel_id"],
                            "user_id": post["user_id"],
                            "message_id": sent_msg.id,
                            "media_type": media_type,
                            "caption": caption,
                            "buttons": buttons,  # Save original buttons/URLs
                            "reactions": [],
                            "comments": False,
                            "pin": False,
                            "caption_above": False,
                            "scheduled": True,
                            "repost": False,
                            "posted_at": datetime.datetime.now(datetime.timezone.utc),
                            "views": 0,
                            "clicks": 0,
                        }
                        await database.CHANNEL_POST_HISTORY_COL.insert_one(history_doc)
                        await database.increment_channel_stat(
                            post["channel_id"], "posts", 1
                        )

                        # 6. Mark post as completed
                        await database.mark_post_sent(post_id_str)
                        logger.info(f"Successfully sent scheduled post {post_id_str}.")

                except Exception as ex:
                    logger.error(f"Error executing scheduled post {post_id_str}: {ex}")
                    retry_count = post.get("retry_count", 0) + 1
                    if retry_count < 3:
                        await database.mark_post_retry(
                            post_id_str, retry_count, str(ex)
                        )
                    else:
                        await database.mark_post_failed(
                            post_id_str, f"Retries exhausted. Last error: {ex}"
                        )

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Unexpected error in scheduled_post worker loop: {e}")


async def repost_worker(app: Client):
    """Background loop that processes auto-reposting configurations."""
    logger.info("Repost worker started.")
    while True:
        try:
            # Sleep 30 seconds between checks
            await asyncio.sleep(30)

            due_jobs = await database.get_active_repost_jobs()
            if not due_jobs:
                continue

            redirect_base = config.REDIRECT_BASE_URL.rstrip("/")

            for job in due_jobs:
                job_id_str = str(job["_id"])
                logger.info(f"Processing repost job {job_id_str}...")

                try:
                    # 1. Delete previous message if delete_old is enabled
                    if job.get("delete_old", True) and job.get("last_post_id"):
                        try:
                            await app.delete_messages(
                                chat_id=job["channel_id"],
                                message_ids=job["last_post_id"],
                            )
                            logger.info(
                                f"Deleted old repost message {job['last_post_id']} in channel {job['channel_id']}."
                            )
                        except Exception as del_ex:
                            logger.warning(
                                f"Failed to delete old message {job['last_post_id']} in channel {job['channel_id']}: {del_ex}"
                            )

                    # 2. Pre-generate a click-tracking post entry ID
                    post_history_id = ObjectId()

                    # 3. Rewrite URLs in buttons
                    buttons = job.get("buttons", [])
                    rewritten_buttons = []
                    for idx, btn in enumerate(buttons):
                        track_url = f"{redirect_base}/clk/{str(post_history_id)}/{idx}"
                        rewritten_buttons.append(
                            {"text": btn["text"], "url": track_url}
                        )

                    # 4. Build inline keyboard
                    keyboard = []
                    for btn in rewritten_buttons:
                        keyboard.append(
                            [InlineKeyboardButton(text=btn["text"], url=btn["url"])]
                        )
                    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

                    # 5. Send new post
                    sent_msg = None
                    caption = job.get("caption", "")
                    media_type = job.get("media_type", "text")
                    poster_url = job.get("poster_url")

                    if media_type == "photo" and poster_url:
                        full_image_path = os.path.join("temp_uploads", poster_url)
                        if os.path.exists(full_image_path):
                            sent_msg = await app.send_photo(
                                chat_id=job["channel_id"],
                                photo=full_image_path,
                                caption=caption,
                                reply_markup=reply_markup,
                            )
                        else:
                            logger.error(
                                f"Repost image not found: {full_image_path}. Sending text fallback."
                            )
                            sent_msg = await app.send_message(
                                chat_id=job["channel_id"],
                                text=caption,
                                reply_markup=reply_markup,
                            )
                    else:
                        sent_msg = await app.send_message(
                            chat_id=job["channel_id"],
                            text=caption,
                            reply_markup=reply_markup,
                        )

                    if sent_msg:
                        # 6. Record post history
                        history_doc = {
                            "_id": post_history_id,
                            "channel_id": job["channel_id"],
                            "user_id": job["user_id"],
                            "message_id": sent_msg.id,
                            "media_type": media_type,
                            "caption": caption,
                            "buttons": buttons,  # Save original buttons/URLs
                            "reactions": [],
                            "comments": False,
                            "pin": False,
                            "caption_above": False,
                            "scheduled": False,
                            "repost": True,
                            "posted_at": datetime.datetime.now(datetime.timezone.utc),
                            "views": 0,
                            "clicks": 0,
                        }
                        await database.CHANNEL_POST_HISTORY_COL.insert_one(history_doc)
                        await database.increment_channel_stat(
                            job["channel_id"], "posts", 1
                        )

                        # 7. Update repost job configuration for next execution
                        interval_minutes = job.get("repost_interval", 60)
                        next_post_at = datetime.datetime.now(
                            datetime.timezone.utc
                        ) + datetime.timedelta(minutes=interval_minutes)
                        await database.update_repost_job_run(
                            job_id_str, sent_msg.id, next_post_at
                        )
                        logger.info(
                            f"Successfully processed repost job {job_id_str}. Next run scheduled at {next_post_at}."
                        )

                except Exception as ex:
                    logger.error(f"Error executing repost job {job_id_str}: {ex}")
                    retry_count = job.get("retry_count", 0) + 1
                    if retry_count < 3:
                        await database.mark_repost_job_retry(
                            job_id_str, retry_count, str(ex)
                        )
                    else:
                        await database.mark_repost_job_failed(
                            job_id_str, f"Retries exhausted. Last error: {ex}"
                        )

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Unexpected error in repost worker loop: {e}")
