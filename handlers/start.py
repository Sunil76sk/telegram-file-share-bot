from __future__ import annotations

import datetime
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot import app, INSTANCE_ID, current_update_info
import database
import config
from utils.helpers import (
    get_not_subscribed_channels,
    is_valid_token,
    send_stars_invoice,
    banned_filter,
)
from utils.locks import user_locks
from utils.security import verify_password, hash_password
from utils.delivery import deliver_files
from utils.movie_download_buttons import get_download_button_config

logger = logging.getLogger(__name__)


@app.on_message(
    filters.command("start")
    & filters.private
    & ~filters.create(lambda _, __, m: m.text is None),
    group=0,
)
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id

    # Parse arguments early to extract traffic source & campaign
    text_split = message.text.split(None, 1)
    payload = ""
    if len(text_split) > 1:
        payload = text_split[1].strip()

    # Handle deep-linked ad clicks first
    if payload.startswith("adclk_"):
        ad_id = payload.split("_")[1]
        try:
            await database.log_ad_click(ad_id, user_id)
            ad = await database.get_ad(ad_id)
            if ad and ad.get("button_url"):
                await message.reply_text(
                    f"✨ **Redirecting to Sponsor**\n\nClick the button below to visit the link:",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton(ad.get("button_text", "Visit Sponsor"), url=ad.get("button_url"))]]
                    )
                )
                message.stop_propagation()
                return
        except Exception as e:
            logger.error(f"Error handling adclk deep link: {e}")

    # Determine traffic source and campaign
    source = "direct"
    campaign = None

    if payload:
        payload_lower = payload.lower()
        
        # Check for referral payload
        ref_payload = None
        if payload.startswith("ref_"):
            ref_payload = payload
        elif "start=ref_" in payload:
            ref_payload = payload.split("start=")[1].split("&")[0]
            
        if ref_payload:
            source = "referral"
        else:
            # Check for source keyword
            import re
            if "instagram" in payload_lower:
                source = "instagram"
            elif "youtube" in payload_lower:
                source = "youtube"
            elif "telegram" in payload_lower:
                source = "telegram"
            elif "referral" in payload_lower:
                source = "referral"
            
            # Extract campaign token (first part or custom campaign param)
            camp_match = re.match(r"^([a-zA-Z0-9_-]+)", payload)
            if camp_match:
                camp = camp_match.group(1)
                if camp.lower() not in ["instagram", "youtube", "telegram", "referral", "direct"]:
                    campaign = camp

            # Check for explicit src= or campaign= params
            src_param = re.search(r"src[=_]([a-zA-Z0-9_-]+)", payload_lower)
            if src_param:
                val = src_param.group(1)
                if val in ["instagram", "youtube", "telegram", "referral", "direct"]:
                    source = val
            
            camp_param = re.search(r"campaign[=_]([a-zA-Z0-9_-]+)", payload_lower)
            if camp_param:
                campaign = camp_param.group(1)

    # 1. Add user to database (Check if exists first to help with referral checks)
    is_new_user = False
    existing_user = await database.get_user(user_id)
    if not existing_user:
        is_new_user = True

    await database.add_user(
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        source=source,
        campaign=campaign,
    )
    await database.track_event(user_id, "active")

    # 2. Check if user is banned
    if await database.is_banned(user_id):
        await message.reply_text("⛔️ You have been banned from using this bot.")
        message.stop_propagation()
        return
    if len(text_split) > 1:
        payload = text_split[1].strip()

    # Handle referral payloads (e.g. start=ref_123456 or ref_123456)
    ref_payload = None
    if payload.startswith("ref_"):
        ref_payload = payload
    elif "start=ref_" in payload:
        ref_payload = payload.split("start=")[1].split("&")[0]

    if ref_payload:
        try:
            referrer_id = int(ref_payload.split("_")[1])
            if is_new_user and referrer_id != user_id:
                # Set referrer and credit points
                await database.set_user_referred_by(user_id, referrer_id)
                await database.add_user_points(
                    referrer_id, config.REFERRAL_REWARD_POINTS
                )
                try:
                    await client.send_message(
                        chat_id=referrer_id,
                        text=f"🎉 **New Referral!**\n\nSomeone joined using your referral link! You earned **{config.REFERRAL_REWARD_POINTS} Point(s)**. Type /referral to check your rewards!",
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Error processing referral: {e}")
        # Clear payload so they get the standard welcome message instead of trying to download a file
        payload = ""
    # Simple /start with no payload
    if not payload:
        welcome_text = (
            f"👋 Hello {message.from_user.mention}!\n\n"
            "I am the **File Share Bot**.\n"
            "I can generate permanent shareable links for files stored on Telegram.\n\n"
            "📤 **How to use:**\n"
            "• Send me any file directly to generate a single-file sharing link.\n"
            "• Use `/batch` to start uploading multiple files, and `/done` when finished to generate a combined batch sharing link.\n"
            "• Use `/cancel` to abort an active batch session.\n\n"
            "💰 **Monetization:**\n"
            "• `/premium` - View subscription plans & upgrade\n"
            "• `/referral` - View your referral link and redeem rewards\n\n"
            "📢 **Force Join:**\n"
            "• Premium users can use `/add_channel`, `/del_channel`, `/channels` to customize force subscription channels."
        )
        if await database.is_admin(user_id, client):
            welcome_text += (
                "\n\n🛠 **Admin Commands:**\n"
                "• `/stats` - View bot statistics\n"
                "• `/broadcast` - Broadcast a message to all users\n"
                "• `/shorteners` - Manage URL shortener configuration\n"
                "• `/edit_link [code]` - Edit/manage files in a shared link\n"
                "• `/add_admin [user_id]` - Add dynamic admin\n"
                "• `/del_admin [user_id]` - Remove dynamic admin\n"
                "• `/upi_pending` - View pending UPI payments\n"
                "• `/grantpremium [user_id] [days] [tier]` - Grant premium status\n"
                "• `/revokepremium [user_id]` - Revoke premium status\n"
                "• `/ads` - Sponsored promotions dashboard\n"
                "• `/analytics [dau|growth|top|geo|sources|funnel]` - View analytics dashboard\n"
                "• `/advertise` - View advertiser portal"
            )

        await message.reply_text(welcome_text)
        message.stop_propagation()
        return

    # Handle /start <token> payload
    if "start=" in payload:
        token = payload.split("start=")[1].split("&")[0]
    elif "/" in payload:
        token = payload.split("/")[-1].split("?")[0]
    else:
        token = payload

    # Check for direct unlock token (bypass monetization)
    bypass_monetization = False
    if token.startswith("unl_"):
        if "start=" in token:
            token = token.split("start=")[1].split("&")[0]
        else:
            token = token[len("unl_") :]
        bypass_monetization = True

    # Check for deep-linked movie download button configuration
    if token.startswith("dl_"):
        config_id = token.replace("dl_", "", 1)
        btn_config = await get_download_button_config(config_id)
        if not btn_config:
            await message.reply_text("❌ Download configuration not found.")
            message.stop_propagation()
            return

        # 1. Premium Check
        if btn_config.get("requires_premium") or btn_config.get("link_type") == "premium":
            is_premium = await database.is_user_premium(user_id)
            if not is_premium:
                await message.reply_text(
                    "🌟 **Premium Only File** 🌟\n\n"
                    "This file is reserved for Premium subscribers. Please upgrade to premium to access it!",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎫 Subscribe to Premium", callback_data="premium_menu_home")]])
                )
                message.stop_propagation()
                return

        # 2. Paid Check
        price = btn_config.get("price", 0)
        if price > 0 or btn_config.get("link_type") == "paid":
            has_unlocked = await database.has_user_unlocked_link(user_id, f"btn_{config_id}")
            if not has_unlocked:
                try:
                    await send_stars_invoice(
                        client=client,
                        chat_id=user_id,
                        title="Unlock Premium Download",
                        description=f"Pay {price} Stars to permanently unlock access to this download.",
                        payload=f"unlock_btn_{config_id}",
                        amount=int(price),
                    )
                except Exception as e:
                    logger.error(f"Failed to send unlock invoice for button: {e}")
                    await message.reply_text("❌ Failed to generate payment invoice. Please try again.")
                message.stop_propagation()
                return

        # 3. Password Check
        password = btn_config.get("password")
        if (btn_config.get("requires_password") or btn_config.get("link_type") == "password") and password:
            await database.create_password_entry_session(user_id, f"btn_{config_id}", bypass_monetization=bypass_monetization)
            await message.reply_text(
                "🔒 **Password Protected Download**\n\n"
                "This download is protected by a password. Please enter the password below to proceed."
            )
            message.stop_propagation()
            return

        # 4. Force Join Check
        not_joined = await get_not_subscribed_channels(client, user_id)
        if not_joined:
            buttons = []
            for index, channel in enumerate(not_joined, start=1):
                btn_label = "📢 Join Channel" if len(not_joined) == 1 else f"📢 Join Channel {index}"
                buttons.append([InlineKeyboardButton(btn_label, url=channel["invite_link"])])
            buttons.append([InlineKeyboardButton("🔄 Try Again", callback_data=f"checksub_dl_{config_id}")])
            await message.reply_text(
                "⚠️ **Access Denied!**\n\n"
                "You must join our channel before you can download this file. Please join the channel below and click Try Again to proceed.",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            message.stop_propagation()
            return

        # 5. Deliver
        await deliver_button_config(client, message, btn_config)
        message.stop_propagation()
        return

    file_doc = await database.get_file_link(token)

    if not file_doc:
        await message.reply_text(
            "❌ The file link you followed is invalid, expired, or has been deleted by an administrator."
        )
        message.stop_propagation()
        return

    # Check if expired
    expires_at = file_doc.get("expires_at")
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
        if datetime.datetime.now(datetime.timezone.utc) > expires_at:
            await message.reply_text("❌ This file link has expired.")
            message.stop_propagation()
            return

    # Increment view counter
    await database.increment_link_views(token, user_id)

    # Perform monetization access checks (unless bypassed, or if user is owner/admin)
    if not bypass_monetization:
        is_bot_admin = await database.is_admin(user_id, client)
        is_link_owner = file_doc.get("owner_id") == user_id

        if not is_bot_admin and not is_link_owner:
            # 1. Premium-only check
            if file_doc.get("is_premium_only", False):
                is_premium = await database.is_user_premium(user_id)
                if not is_premium:
                    await message.reply_text(
                        "🌟 **Premium Only File** 🌟\n\n"
                        "This link is reserved for Premium subscribers. "
                        "Please upgrade your account to Premium to access this file!",
                        reply_markup=InlineKeyboardMarkup(
                            [
                                [
                                    InlineKeyboardButton(
                                        "🎫 Subscribe to Premium",
                                        callback_data="premium_menu_home",
                                    )
                                ]
                            ]
                        ),
                    )
                    message.stop_propagation()
                    return

            # 2. Pay-to-unlock check
            price = file_doc.get("price", 0)
            if price > 0:
                has_unlocked = await database.has_user_unlocked_link(user_id, token)
                if not has_unlocked:
                    try:
                        await send_stars_invoice(
                            client=client,
                            chat_id=user_id,
                            title="Unlock Shared Files",
                            description=f"Pay {price} Stars to permanently unlock access to these files.",
                            payload=f"unlock_{token}",
                            amount=price,
                        )
                    except Exception as e:
                        logger.error(f"Failed to send unlock invoice: {e}")
                        await message.reply_text(
                            "❌ Failed to generate payment invoice. Please try again."
                        )
                    message.stop_propagation()
                    return

    # Check if password protected
    password_hash = file_doc.get("password_hash")
    if password_hash:
        await database.create_password_entry_session(
            user_id, token, bypass_monetization=bypass_monetization
        )
        await message.reply_text(
            "🔒 **Password Protected Link**\n\n"
            "This link is protected by a password. Please enter the password below to access the files."
        )
        message.stop_propagation()
        return

    # 3. Check force subscription
    not_joined = await get_not_subscribed_channels(client, user_id)
    if not_joined:
        # Check for active force-join ads
        sponsored_ad = None
        try:
            active_fj_ads = await database.get_force_join_ads()
            if active_fj_ads:
                import random
                sponsored_ad = random.choice(active_fj_ads)
        except Exception as e:
            logger.error(f"Error fetching force-join ads: {e}")

        # User must subscribe to channels
        buttons = []

        # If there is a sponsored ad, insert its button at the top
        if sponsored_ad:
            ad_id = str(sponsored_ad["_id"])
            await database.log_ad_impression(ad_id, user_id)
            from utils.ads_engine import get_ad_click_url
            click_url = get_ad_click_url(ad_id, user_id)
            buttons.append([InlineKeyboardButton("📢 Visit Sponsor", url=click_url)])

        for index, channel in enumerate(not_joined, start=1):
            btn_label = (
                "📢 Join Channel"
                if len(not_joined) == 1
                else f"📢 Join Channel {index}"
            )
            buttons.append(
                [InlineKeyboardButton(btn_label, url=channel["invite_link"])]
            )

        # Add Try Again button
        cb_data = f"checksub_{'unl_' if bypass_monetization else ''}{token}"
        buttons.append([InlineKeyboardButton("🔄 Try Again", callback_data=cb_data)])

        ad_header = ""
        if sponsored_ad:
            ad_header = (
                f"📢 **Sponsored:**\n"
                f"🔥 **{sponsored_ad.get('title')}**\n"
                f"🚀 {sponsored_ad.get('description')}\n\n"
                f"━━━━━━━━━━━━━━━\n\n"
            )

        await message.reply_text(
            f"{ad_header}"
            f"⚠️ **Access Denied!**\n\n"
            f"You must join our channel before you can download this file. "
            f"Please join the channel below and click Try Again to proceed.",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        message.stop_propagation()
        return

    # 4. Deliver the files
    await deliver_files(
        client, message.chat.id, file_doc, bypass_monetization=bypass_monetization
    )
    message.stop_propagation()


async def _not_command(_, __, message):
    if not message.text:
        return False
    return not message.text.startswith("/")


not_command_filter = filters.create(_not_command)


@app.on_message(filters.private & filters.text & not_command_filter, group=1)
async def text_message_handler(client: Client, message: Message):
    current_update_info.set({
        "handler": "text_message_handler",
        "update_id": message.id,
        "message_id": message.id
    })
    log_msg = (
        f"[HANDLER_ENTER]\n"
        f"instance={INSTANCE_ID}\n"
        f"handler=text_message_handler\n"
        f"update_id={message.id}\n"
        f"message_id={message.id}"
    )
    logger.info(log_msg)
    print(log_msg, flush=True)
    user_id = message.from_user.id
    logger.info(f"DEBUG BYPASS: user={user_id}, text='{message.text[:20]}...'")
    text = message.text.strip()

    if await database.is_banned(user_id):
        message.stop_propagation()
        return

    user_doc = await database.get_user(user_id)

    # Bypass if user is in an active ad draft session (auto-delete if older than 24 hours)
    ad_draft = await database.get_ad_draft(user_id)
    if ad_draft:
        created_at = ad_draft.get("created_at")
        if created_at:
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=datetime.timezone.utc)
            if datetime.datetime.now(datetime.timezone.utc) - created_at > datetime.timedelta(hours=24):
                await database.clear_ad_draft(user_id)
                ad_draft = None
    if ad_draft and ad_draft.get("step") == "awaiting_details":
        return

    # Bypass if user is in an active wizard state
    if user_doc and user_doc.get("state"):
        return

    # Bypass if user is in an active post builder or scheduling session
    draft = await database.get_post_draft(user_id)
    draft_exists = draft is not None
    draft_state = draft.get("state") if draft_exists else None
    
    # Requirements:
    # 1. user_id
    # 2. draft exists?
    # 3. full draft state
    # 4. draft document
    # 5. branch taken
    logger.info(f"[text_message_handler] user_id={user_id}")
    logger.info(f"[text_message_handler] draft exists={draft_exists}")
    logger.info(f"[text_message_handler] state={draft_state}")
    logger.info(f"[text_message_handler] draft doc={draft}")
    
    if draft and draft.get("state") in [
        "awaiting_media", "awaiting_caption", "awaiting_buttons", "awaiting_reactions",
        "awaiting_schedule_time", "awaiting_repost_interval", "awaiting_delete_gap"
    ]:
        logger.info("[text_message_handler]\ndraft exists=True\nstate=awaiting_caption\nACTION=bypass")
        return
    else:
        logger.info(f"[text_message_handler]\ndraft exists={draft_exists}\nstate={draft_state}\nACTION=send_welcome")

    # Intercept shortener registration states
    if user_doc and user_doc.get("state", "").startswith("sh_"):
        if text.lower() == "/cancel":
            await database.users_col.update_one(
                {"_id": user_id}, {"$unset": {"state": "", "shortener_draft": ""}}
            )
            await message.reply_text("❌ Shortener configuration cancelled.")
            message.stop_propagation()
            return

        from handlers.shorteners import handle_shortener_state

        await handle_shortener_state(
            client, message, user_id, user_doc["state"], user_doc
        )
        message.stop_propagation()
        return

    async with user_locks[user_id]:
        # 1. Check if user is entering a password to access a link
        entry_session = await database.get_password_entry_session(user_id)
        if entry_session:
            token = entry_session["code"]
            bypass_monetization = entry_session.get("bypass_monetization", False)

            if token.startswith("btn_"):
                config_id = token.replace("btn_", "", 1)
                btn_config = await get_download_button_config(config_id)
                if not btn_config:
                    await database.delete_password_entry_session(user_id)
                    await message.reply_text("❌ The download configuration no longer exists.")
                    message.stop_propagation()
                    return

                expected_password = btn_config.get("password")
                if not expected_password or verify_password(expected_password, text) or expected_password == text:
                    await database.delete_password_entry_session(user_id)

                    not_joined = await get_not_subscribed_channels(client, user_id)
                    if not_joined:
                        buttons = []
                        for index, channel in enumerate(not_joined, start=1):
                            btn_label = "📢 Join Channel" if len(not_joined) == 1 else f"📢 Join Channel {index}"
                            buttons.append([InlineKeyboardButton(btn_label, url=channel["invite_link"])])
                        buttons.append([InlineKeyboardButton("🔄 Try Again", callback_data=f"checksub_dl_{config_id}")])
                        await message.reply_text(
                            "⚠️ **Access Denied!**\n\n"
                            "Password verified successfully! However, you must join our channel before you can download this file. Please join the channel below and click Try Again to proceed.",
                            reply_markup=InlineKeyboardMarkup(buttons)
                        )
                        message.stop_propagation()
                        return

                    await deliver_button_config(client, message, btn_config)
                    message.stop_propagation()
                else:
                    await message.reply_text("❌ **Incorrect Password!** Access denied. Please try again.")
                    message.stop_propagation()
                return

            file_doc = await database.get_file_link(token)
            if not file_doc:
                await database.delete_password_entry_session(user_id)
                await message.reply_text(
                    "❌ The file link you were trying to access no longer exists."
                )
                message.stop_propagation()
                return

            # Check if expired
            expires_at = file_doc.get("expires_at")
            if expires_at:
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
                if datetime.datetime.now(datetime.timezone.utc) > expires_at:
                    await database.delete_password_entry_session(user_id)
                    await message.reply_text("❌ This file link has expired.")
                    message.stop_propagation()
                    return

            password_hash = file_doc.get("password_hash")
            if not password_hash or verify_password(password_hash, text):
                # Correct password! Delete entry session
                await database.delete_password_entry_session(user_id)

                # Now proceed with force subscription checks
                not_joined = await get_not_subscribed_channels(client, user_id)
                if not_joined:
                    buttons = []
                    for index, channel in enumerate(not_joined, start=1):
                        btn_label = (
                            "📢 Join Channel"
                            if len(not_joined) == 1
                            else f"📢 Join Channel {index}"
                        )
                        buttons.append(
                            [
                                InlineKeyboardButton(
                                    btn_label, url=channel["invite_link"]
                                )
                            ]
                        )

                    cb_data = f"checksub_{'unl_' if bypass_monetization else ''}{token}"
                    buttons.append(
                        [InlineKeyboardButton("🔄 Try Again", callback_data=cb_data)]
                    )

                    await message.reply_text(
                        "⚠️ **Access Denied!**\n\n"
                        "Password verified successfully! However, you must join our channel before you can download this file. "
                        "Please join the channel below and click Try Again to proceed.",
                        reply_markup=InlineKeyboardMarkup(buttons),
                    )
                    message.stop_propagation()
                    return

                # Deliver files!
                await deliver_files(
                    client,
                    message.chat.id,
                    file_doc,
                    bypass_monetization=bypass_monetization,
                )
                message.stop_propagation()
            else:
                # Wrong password! Keep session open so they can try again
                await message.reply_text(
                    "❌ **Incorrect Password!** Access denied. Please try again."
                )
                message.stop_propagation()
            return

        # 2. Check if user is setting a password for a generated link
        setting_session = await database.get_password_setting_session(user_id)
        if setting_session:
            token = setting_session["code"]
            # Hash the password
            hashed = hash_password(text)
            await database.set_link_password(token, hashed)
            await database.delete_password_setting_session(user_id)

            buttons = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("1 Hour", callback_data=f"exp_1h_{token}"),
                        InlineKeyboardButton("1 Day", callback_data=f"exp_1d_{token}"),
                    ],
                    [
                        InlineKeyboardButton("7 Days", callback_data=f"exp_7d_{token}"),
                        InlineKeyboardButton(
                            "Permanent", callback_data=f"exp_perm_{token}"
                        ),
                    ],
                ]
            )
            await message.reply_text(
                f"🔒 **Password Set Successfully!**\n🔑 Password: `{text}`\n\n"
                "Please choose how long this share link should remain valid:",
                reply_markup=buttons,
            )
            message.stop_propagation()
            return

        # 4. Check if user sent a shareable link or raw token
        token = None
        bypass_monetization = False

        if "start=" in text:
            token = text.split("start=")[1].split("&")[0].strip()
        elif "t.me/" in text:
            token = text.split("/")[-1].split("?")[0].strip()
        elif is_valid_token(text):
            if await database.get_file_link(text) or text.startswith("unl_"):
                token = text

        if token:
            if token.startswith("unl_"):
                token = token.replace("unl_", "", 1)
                bypass_monetization = True

            file_doc = await database.get_file_link(token)
            if file_doc:
                # Check if expired
                expires_at = file_doc.get("expires_at")
                if expires_at:
                    if expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
                    if datetime.datetime.now(datetime.timezone.utc) > expires_at:
                        await message.reply_text("❌ This file link has expired.")
                        message.stop_propagation()
                        return

                # Increment view counter
                await database.increment_link_views(token, user_id)

                # Perform monetization access checks (unless bypassed, or if user is owner/admin)
                if not bypass_monetization:
                    is_bot_admin = await database.is_admin(user_id, client)
                    is_link_owner = file_doc.get("owner_id") == user_id

                    if not is_bot_admin and not is_link_owner:
                        # 1. Premium-only check
                        if file_doc.get("is_premium_only", False):
                            is_premium = await database.is_user_premium(user_id)
                            if not is_premium:
                                await message.reply_text(
                                    "🌟 **Premium Only File** 🌟\n\n"
                                    "This link is reserved for Premium subscribers. "
                                    "Please upgrade your account to Premium to access this file!",
                                    reply_markup=InlineKeyboardMarkup(
                                        [
                                            [
                                                InlineKeyboardButton(
                                                    "🎫 Subscribe to Premium",
                                                    callback_data="buy_premium_info",
                                                )
                                            ]
                                        ]
                                    ),
                                )
                                message.stop_propagation()
                                return

                        # 2. Pay-to-unlock check
                        price = file_doc.get("price", 0)
                        if price > 0:
                            has_unlocked = await database.has_user_unlocked_link(
                                user_id, token
                            )
                            if not has_unlocked:
                                try:
                                    await send_stars_invoice(
                                        client=client,
                                        chat_id=user_id,
                                        title="Unlock Shared Files",
                                        description=f"Pay {price} Stars to permanently unlock access to these files.",
                                        payload=f"unlock_{token}",
                                        amount=price,
                                    )
                                except Exception as e:
                                    logger.error(f"Failed to send unlock invoice: {e}")
                                    await message.reply_text(
                                        "❌ Failed to generate payment invoice. Please try again."
                                    )
                                message.stop_propagation()
                                return

                # Check if password protected
                password_hash = file_doc.get("password_hash")
                if password_hash:
                    await database.create_password_entry_session(
                        user_id, token, bypass_monetization=bypass_monetization
                    )
                    await message.reply_text(
                        "🔒 **Password Protected Link**\n\n"
                        "This link is protected by a password. Please enter the password below to access the files."
                    )
                    message.stop_propagation()
                    return

                # Check force subscription
                not_joined = await get_not_subscribed_channels(client, user_id)
                if not_joined:
                    buttons = []
                    for index, channel in enumerate(not_joined, start=1):
                        btn_label = (
                            "📢 Join Channel"
                            if len(not_joined) == 1
                            else f"📢 Join Channel {index}"
                        )
                        buttons.append(
                            [
                                InlineKeyboardButton(
                                    btn_label, url=channel["invite_link"]
                                )
                            ]
                        )

                    cb_data = f"checksub_{'unl_' if bypass_monetization else ''}{token}"
                    buttons.append(
                        [InlineKeyboardButton("🔄 Try Again", callback_data=cb_data)]
                    )

                    await message.reply_text(
                        "⚠️ **Access Denied!**\n\n"
                        "You must join our channel before you can download this file. "
                        "Please join the channel below and click Try Again to proceed.",
                        reply_markup=InlineKeyboardMarkup(buttons),
                    )
                    message.stop_propagation()
                    return

                # Deliver the files
                await deliver_files(
                    client,
                    message.chat.id,
                    file_doc,
                    bypass_monetization=bypass_monetization,
                )
                message.stop_propagation()
                return

    # Fallback: unrecognized text
    logger.info(f"[text_message_handler] SENDING welcome message to user_id={user_id}")
    logger.info("👋 Hello! I am the File Share Bot")
    await message.reply_text(
        "👋 **Hello!**\n\n"
        "I am the File Share Bot. I can generate permanent shareable links for files stored on Telegram.\n\n"
        "📤 **Send me a file** to generate a sharing link.\n"
        "📋 Use **/batch** to upload multiple files.\n"
        "💰 Use **/premium** to view subscription plans.\n"
        "🛍 Use **/store** to browse the premium catalog.\n\n"
        "Type **/start** to see all available commands."
    )
    message.stop_propagation()


async def deliver_button_config(client: Client, message: Message, btn_config: dict):
    chat_id = message.chat.id
    file_id = btn_config.get("file_id")
    link_url = btn_config.get("link_url")

    # Track download click count
    from utils.movie_download_buttons import increment_download_click
    await increment_download_click(str(btn_config["_id"]))

    if file_id:
        file_doc = {
            "token": f"btn_{btn_config['_id']}",
            "files": [{"file_id": file_id, "file_name": btn_config.get("name", "File"), "file_size": 0, "media_type": "document"}]
        }
        await deliver_files(client, chat_id, file_doc, bypass_monetization=True)
    elif link_url:
        await client.send_message(
            chat_id=chat_id,
            text=f"📂 **Your Download Link is Ready!**\n\nClick the button below to open your destination:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Open Link", url=link_url)]])
        )


@app.on_message(filters.command("upload") & filters.private & ~banned_filter)
async def upload_command_handler(client: Client, message: Message):
    await message.reply_text(
        "📤 **How to upload files:**\n\n"
        "Simply send any file (photo, video, document, audio, animation) directly to me in this chat! "
        "I will automatically generate a permanent, shareable download link for it."
    )
    message.stop_propagation()
