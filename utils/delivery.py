import logging
import asyncio
import urllib.request
import json
from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import database
import config

logger = logging.getLogger(__name__)


async def get_shortened_url(long_url: str) -> str | None:
    """Shorten the start URL using configured third-party link shortener API."""
    if not config.SHORTENER_API_URL or not config.SHORTENER_API_KEY:
        return None
    url = f"{config.SHORTENER_API_URL}?api={config.SHORTENER_API_KEY}&url={long_url}"

    def _call():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as response:
                content_type = response.headers.get("Content-Type", "")
                body = response.read().decode("utf-8")

                if "application/json" in content_type:
                    try:
                        data = json.loads(body)
                        for key in [
                            "shortenedUrl",
                            "short_url",
                            "shortened_url",
                            "url",
                        ]:
                            if key in data:
                                return data[key]
                    except Exception:
                        pass

                if body.strip().startswith("http"):
                    return body.strip()
        except Exception as e:
            logger.error(f"Error calling URL shortener API: {e}")
        return None

    return await asyncio.to_thread(_call)


async def deliver_files(
    client: Client, chat_id: int, file_doc: dict, bypass_monetization: bool = False
):
    files = file_doc.get("files", [])
    token = file_doc.get("token")

    if not files:
        await client.send_message(chat_id, "No files found in this sharing link.")
        return

    if not token or not await database.start_delivery(chat_id, token):
        logger.warning(
            f"Delivery already in progress for user {chat_id} on token {token}. Skipping duplicate delivery."
        )
        return

    try:
        is_premium = await database.is_user_premium(chat_id)

        # Track file view event
        await database.track_event(chat_id, "file_view", token=token)

        # Apply monetization checks if not premium and not bypassed
        if not is_premium and not bypass_monetization:
            bot_me = client.me or await client.get_me()
            user_doc = await database.get_user(chat_id)
            user_lang = user_doc.get("language_code") if user_doc else None

            # Check if there are active shorteners (either sub-bot specific or global)
            bot_id = file_doc.get("bot_id")
            active_shorteners = await database.get_shorteners(
                bot_id=bot_id, active_only=True
            )
            if not active_shorteners and bot_id is not None:
                active_shorteners = await database.get_shorteners(
                    bot_id=None, active_only=True
                )

            has_shorteners = len(active_shorteners) > 0
            use_config_fallback = not has_shorteners and bool(
                config.SHORTENER_API_URL and config.SHORTENER_API_KEY
            )

            # Check for active sponsored download page ads first
            active_sponsored = await database.get_all_ads(ad_type="sponsored_page")
            active_sponsored = [
                a for a in active_sponsored if a.get("status") == "active"
            ]

            if active_sponsored and config.REDIRECT_BASE_URL:
                # Send user to branded sponsored page before file access
                sponsored_url = f"{config.REDIRECT_BASE_URL.rstrip('/')}/sponsored/{token}/{chat_id}"
                await client.send_message(
                    chat_id,
                    "🖼 **Sponsored Content**\n\n"
                    "This file is brought to you by our sponsors. "
                    "Click below to continue to your download:",
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "🖼 View Sponsored Page", url=sponsored_url
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "🌟 Bypass with Premium",
                                    callback_data="buy_premium_info",
                                )
                            ],
                        ]
                    ),
                )
                return

            if has_shorteners or use_config_fallback:
                short_url = None

                if config.REDIRECT_BASE_URL:
                    # Web-enhanced flow: redirect to our web server /go endpoint first
                    short_url = (
                        f"{config.REDIRECT_BASE_URL.rstrip('/')}/go/{token}/{chat_id}"
                    )
                else:
                    # Fallback flow: shorten directly
                    long_url = f"https://t.me/{bot_me.username}?start=unl_{token}"
                    if has_shorteners:
                        shortener = await database.get_best_shortener(
                            bot_id=bot_id, user_lang=user_lang
                        )
                        if shortener:
                            from utils.web_server import generate_short_link

                            short_url = await generate_short_link(shortener, long_url)
                            if short_url:
                                # Increment stats
                                await database.increment_shortener_stats(
                                    shortener["_id"], views=1
                                )
                                await database.increment_link_monetization_stats(
                                    token, views=1
                                )

                    if not short_url and use_config_fallback:
                        # Fallback to config
                        short_url = await get_shortened_url(long_url)

                if short_url:
                    await client.send_message(
                        chat_id,
                        "🔗 **Link Monetized!**\n\n"
                        "To download the files, you must complete the link verification. "
                        "This helps keep our service free.\n\n"
                        "👉 **Click the button below to unlock your files:**",
                        reply_markup=InlineKeyboardMarkup(
                            [
                                [
                                    InlineKeyboardButton(
                                        "🔓 Unlock Files", url=short_url
                                    )
                                ],
                                [
                                    InlineKeyboardButton(
                                        "🌟 Bypass with Premium",
                                        callback_data="buy_premium_info",
                                    )
                                ],
                            ]
                        ),
                    )
                    return

            # 2. Try Wait Countdown Timer
            wait_seconds = getattr(config, "WAIT_TIMER_SECONDS", 10)
            if wait_seconds > 0:
                timer_msg = await client.send_message(
                    chat_id,
                    f"⏳ **Preparing your files...**\n"
                    f"Please wait **{wait_seconds}** seconds...\n\n"
                    f"🌟 *Want to skip this wait? Type /premium to unlock instant downloads!*",
                )
                remaining = wait_seconds
                while remaining > 0:
                    await asyncio.sleep(2.5)
                    remaining -= 2.5
                    if remaining <= 0:
                        break
                    try:
                        await timer_msg.edit_text(
                            f"⏳ **Preparing your files...**\n"
                            f"Please wait **{int(remaining)}** seconds...\n\n"
                            f"🌟 *Want to skip this wait? Type /premium to unlock instant downloads!*"
                        )
                    except Exception:
                        pass
                try:
                    await timer_msg.delete()
                except Exception:
                    pass

        # Proceed to deliver files
        delay = getattr(config, "AUTO_DELETE_SECONDS", 300)
        if delay >= 60:
            minutes = delay // 60
            time_str = f"{minutes} minute{'s' if minutes > 1 else ''}"
        else:
            time_str = f"{delay} second{'s' if delay != 1 else ''}"

        info_msg = await client.send_message(
            chat_id,
            f"Delivering {len(files)} file(s)...\n\n"
            f"Note: All delivered files and this info message will be automatically deleted after {time_str} for security purposes.",
        )

        sent_message_ids = []
        if info_msg:
            sent_message_ids.append(info_msg.id)

        failures = 0
        for index, file_obj in enumerate(files):
            file_id = file_obj.get("file_id")
            caption = file_obj.get("caption", "")
            try:
                msg = await client.send_cached_media(
                    chat_id=chat_id, file_id=file_id, caption=caption
                )
                if msg:
                    sent_message_ids.append(msg.id)
            except Exception as e:
                logger.error(
                    f"Failed to deliver file index {index} with ID {file_id}: {e}"
                )
                failures += 1

        if failures == len(files):
            await client.send_message(
                chat_id,
                "All file deliveries failed. The files may have been deleted or the bot lacks permissions.",
            )
        else:
            await database.increment_link_downloads(token, chat_id)
            await database.track_event(chat_id, "file_download", token=token)

            # Inject sponsored block for non-premium users
            if not is_premium:
                try:
                    active_pinned_ads = await database.get_all_ads(ad_type="pinned")
                    active_pinned_ads = [a for a in active_pinned_ads if a.get("status") == "active"]
                    if active_pinned_ads:
                        import random
                        ad = random.choice(active_pinned_ads)
                        ad_id = str(ad["_id"])
                        
                        ad_text = (
                            f"━━━━━━━━━━━━━━━\n"
                            f"📢 **Sponsored**\n\n"
                            f"🔥 **{ad.get('title')}**\n"
                            f"🚀 {ad.get('description')}\n"
                            f"━━━━━━━━━━━━━━━"
                        )
                        
                        from utils.ads_engine import get_ad_click_url
                        click_url = get_ad_click_url(ad_id, chat_id)
                        reply_markup = InlineKeyboardMarkup(
                            [[InlineKeyboardButton(ad.get("button_text") or "Visit Sponsor 🌐", url=click_url)]]
                        )
                        
                        ad_msg = await client.send_message(
                            chat_id,
                            text=ad_text,
                            reply_markup=reply_markup
                        )
                        if ad_msg:
                            sent_message_ids.append(ad_msg.id)
                            # Log impression
                            await database.log_ad_impression(ad_id, chat_id)
                except Exception as ad_err:
                    logger.error(f"Failed to inject pinned ad for user {chat_id}: {ad_err}")

            # Log successful access/download
            try:
                catalog_item = await database.get_catalog_item_by_token(token)
                catalog_item_id = str(catalog_item["_id"]) if catalog_item else None
                method = (
                    "premium"
                    if is_premium
                    else ("bypass" if bypass_monetization else "direct")
                )
                await database.log_access(
                    user_id=chat_id,
                    token=token,
                    action="download",
                    method=method,
                    catalog_item_id=catalog_item_id,
                )
            except Exception as e:
                logger.error(f"Failed to log download access for user {chat_id}: {e}")

            await database.schedule_deletion(
                chat_id, sent_message_ids, delay_seconds=delay
            )
    finally:
        await database.finish_delivery(chat_id, token)
