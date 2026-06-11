from __future__ import annotations

import asyncio
import logging
import datetime
from pyrogram import Client
from pyrogram.errors import FloodWait, UserIsBlocked, UserDeactivated, PeerIdInvalid
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import database
import config

logger = logging.getLogger(__name__)


def get_ad_click_url(ad_id: str, user_id: int) -> str:
    base = config.REDIRECT_BASE_URL
    if base:
        return f"{base.rstrip('/')}/ad_click/{ad_id}/{user_id}"
    else:
        bot_username = getattr(config, "BOT_USERNAME", "file_share_bot")
        return f"https://t.me/{bot_username}?start=adclk_{ad_id}"


async def send_ad_message(client: Client, chat_id: int, ad: dict):
    title = ad.get("title", "")
    description = ad.get("description", "")
    text = f"📢 **{title}**\n\n{description}"
    
    # Inline keyboard if button is configured
    reply_markup = None
    button_text = ad.get("button_text")
    button_url = ad.get("button_url")
    if button_text and button_url:
        click_url = get_ad_click_url(str(ad["_id"]), chat_id)
        reply_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton(button_text, url=click_url)]]
        )

    media = ad.get("media")
    if media:
        try:
            return await client.send_photo(
                chat_id=chat_id,
                photo=media,
                caption=text,
                reply_markup=reply_markup
            )
        except Exception:
            try:
                return await client.send_document(
                    chat_id=chat_id,
                    document=media,
                    caption=text,
                    reply_markup=reply_markup
                )
            except Exception:
                return await client.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=reply_markup
                )
    else:
        return await client.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup
        )


async def ads_scheduler_worker(client: Client):
    """Background task to run active broadcast ads."""
    logger.info("Ads scheduler worker started.")
    while True:
        try:
            # Query active broadcast ads
            ads = await database.get_ads_due_for_broadcast()
            for ad in ads:
                # Only broadcast if pending
                if ad.get("broadcast_status") in ["running", "completed"]:
                    continue

                ad_id = str(ad["_id"])
                # Mark running
                await database.ads_col.update_one(
                    {"_id": ad["_id"]},
                    {"$set": {"broadcast_status": "running"}}
                )
                logger.info(f"Starting broadcast for Ad ID: {ad_id} - {ad.get('title')}")

                users = await database.get_all_users()
                sent = 0
                delivered = 0
                failed = 0

                for user_id in users:
                    try:
                        sent += 1
                        await send_ad_message(client, user_id, ad)
                        delivered += 1
                        # Log impression
                        await database.log_ad_impression(ad_id, user_id)
                        await asyncio.sleep(0.05) # Small throttle
                    except FloodWait as e:
                        logger.warning(f"FloodWait encountered in broadcast: sleeping {e.value}s")
                        await asyncio.sleep(e.value)
                        # Retry once after sleep
                        try:
                            await send_ad_message(client, user_id, ad)
                            delivered += 1
                            await database.log_ad_impression(ad_id, user_id)
                        except Exception as retry_err:
                            logger.error(f"Failed to deliver ad to {user_id} on retry: {retry_err}")
                            failed += 1
                    except (UserIsBlocked, UserDeactivated, PeerIdInvalid) as block_err:
                        logger.info(f"User {user_id} is inactive or blocked bot: {block_err}")
                        failed += 1
                        await database.set_user_active_status(user_id, False)
                    except Exception as err:
                        logger.error(f"Error sending ad to {user_id}: {err}")
                        failed += 1

                # Update completed status & counts
                await database.ads_col.update_one(
                    {"_id": ad["_id"]},
                    {
                        "$set": {
                            "broadcast_status": "completed",
                            "status": "completed",
                            "stats_sent": sent,
                            "stats_delivered": delivered,
                            "stats_failed": failed
                        }
                    }
                )
                logger.info(f"Finished broadcast for Ad ID: {ad_id}. Sent={sent}, Delivered={delivered}, Failed={failed}")

        except Exception as e:
            logger.error(f"Error in ads_scheduler_worker loop: {e}")

        await asyncio.sleep(60)
