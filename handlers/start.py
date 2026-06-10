from __future__ import annotations

import datetime
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot import app
import database
import config
from utils.helpers import (
    get_not_subscribed_channels,
    is_valid_token,
    send_stars_invoice,
)
from utils.locks import user_locks
from utils.security import verify_password, hash_password
from utils.delivery import deliver_files
from utils.funnel import parse_campaign_payload, is_valid_source
from handlers.funnel import show_campaign_detail

logger = logging.getLogger(__name__)


@app.on_message(
    filters.command("start")
    & filters.private
    & ~filters.create(lambda _, __, m: m.text is None),
    group=0,
)
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id

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
    )
    await database.track_event(user_id, "active")

    # 2. Check if user is banned
    if await database.is_banned(user_id):
        await message.reply_text("⛔️ You have been banned from using this bot.")
        message.stop_propagation()
        return

    # Parse arguments
    text_split = message.text.split(None, 1)
    payload = ""
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

    # Handle campaign / source tracking payload (e.g. cmp_summer_wp&src_instagram)
    campaign_info = parse_campaign_payload(payload)
    if campaign_info.get("campaign_id"):
        campaign_id = campaign_info["campaign_id"]
        source = campaign_info.get("source")
        ref = campaign_info.get("ref")
        if source and is_valid_source(source):
            await database.log_source_visit(user_id, source, campaign_id, ref)
            logger.info(
                f"User {user_id} arrived from source={source} via campaign={campaign_id}"
            )
        campaign = await database.get_campaign(campaign_id)
        if campaign:
            await show_campaign_detail(client, message, campaign_id)
            message.stop_propagation()
            return
        # If campaign not found, fall through to normal payload handling

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
            "💰 **Monetization & SaaS:**\n"
            "• `/premium` - View subscription plans & upgrade\n"
            "• `/store` - Browse & purchase premium catalog items\n"
            "• `/referral` - View your referral link and redeem rewards\n"
            "• `/createbot` - Build your own custom file share bot\n"
            "• `/marketplace` - Browse & purchase digital products\n"
            "• `/sell` - List your own digital products for sale\n"
            "• `/my_products` - Manage your listed products\n"
            "• `/seller` - View your seller dashboard"
        )
        # Add admin helper text if user is admin of this bot
        if await database.is_admin(user_id, client):
            welcome_text += (
                "\n\n🛠 **Admin Commands:**\n"
                "• `/stats` - View bot statistics\n"
                "• `/broadcast` - Broadcast a message to all users\n"
                "• `/channels` - List force subscription channels\n"
                "• `/add_channel [channel_id_or_username] [invite_link]` - Add force-join channel\n"
                "• `/del_channel [channel_id_or_username]` - Remove force-join channel\n"
                "• `/edit_link [code]` - Edit/manage files in a shared link\n"
                "• `/add_admin [user_id]` - Add dynamic admin\n"
                "• `/del_admin [user_id]` - Remove dynamic admin\n"
                "• `/addcatalog` - Add premium catalog item\n"
                "• `/catalog` - Manage premium catalog items\n"
                "• `/upi_pending` - View pending UPI payments\n"
                "• `/accesslogs [user_id|token]` - View content access logs\n"
                "• `/grantpremium [user_id] [days] [tier]` - Grant premium status\n"
                "• `/revokepremium [user_id]` - Revoke premium status\n"
                "• `/ads` - Sponsored promotions dashboard\n"
                "• `/mycampaigns` - Manage audience funnel campaigns\n"
                "• `/addcampaign [id] [src] [type] [chat] [link] [title] [desc]` - Add audience campaign\n"
                "• `/delcampaign [id]` - Delete audience campaign\n"
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
        token = token.replace("unl_", "", 1)
        bypass_monetization = True

    # Check for marketplace product link
    if token.startswith("prod_"):
        prod_token = token.replace("prod_", "", 1)
        product = await database.get_product_by_token(prod_token)
        if product:
            # Increment view count
            await database.increment_product_views(product["_id"])
            from handlers.marketplace import show_product_card

            await show_product_card(client, message.chat.id, product, user_id)
            message.stop_propagation()
            return
        else:
            await message.reply_text("❌ Product not found or deleted.")
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
    if expires_at and datetime.datetime.now(datetime.timezone.utc) > expires_at:
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

                # Check tier requirement if there's a catalog item linked to this token
                catalog_item = await database.get_catalog_item_by_token(token)
                if catalog_item and catalog_item.get("tier_required"):
                    req_tier = catalog_item["tier_required"]
                    user_tier = await database.get_user_premium_tier(user_id)

                    if req_tier == "gold" and user_tier != "gold":
                        await message.reply_text(
                            "👑 **Gold Tier Required** 👑\n\n"
                            "This premium content requires a **Gold Tier** subscription.\n"
                            "Your current subscription is Silver tier. Please upgrade to Gold to access this file!",
                            reply_markup=InlineKeyboardMarkup(
                                [
                                    [
                                        InlineKeyboardButton(
                                            "👑 Upgrade to Gold Tier",
                                            callback_data="premium_tier_gold",
                                        )
                                    ]
                                ]
                            ),
                        )
                        message.stop_propagation()
                        return
                    elif req_tier == "silver" and user_tier not in ["silver", "gold"]:
                        await message.reply_text(
                            "🥈 **Silver Tier Required** 🥈\n\n"
                            "This premium content requires at least a **Silver Tier** subscription. Please upgrade to access it!",
                            reply_markup=InlineKeyboardMarkup(
                                [
                                    [
                                        InlineKeyboardButton(
                                            "🥈 Upgrade to Silver",
                                            callback_data="premium_tier_silver",
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
        # User must subscribe to channels
        buttons = []
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

        await message.reply_text(
            "⚠️ **Access Denied!**\n\n"
            "You must join our channel before you can download this file. "
            "Please join the channel below and click Try Again to proceed.",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        message.stop_propagation()
        return

    # 4. Deliver the files
    await deliver_files(
        client, message.chat.id, file_doc, bypass_monetization=bypass_monetization
    )
    message.stop_propagation()


@app.on_message(filters.private & filters.text & ~filters.regex(r"^/"), group=1)
async def text_message_handler(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip()

    if await database.is_banned(user_id):
        return

    # Check SaaS sub-bot token registration state
    user_doc = await database.get_user(user_id)

    # Intercept premium catalog addition states
    if user_doc and user_doc.get("state", "").startswith("catalog_"):
        if text.lower() == "/cancel":
            await database.users_col.update_one(
                {"_id": user_id}, {"$unset": {"state": "", "catalog_draft": ""}}
            )
            await message.reply_text("❌ Catalog item creation cancelled.")
            return

        from handlers.premium_admin import handle_catalog_state

        await handle_catalog_state(
            client, message, user_id, user_doc["state"], user_doc
        )
        return

    # Intercept marketplace product creation wizard states
    if user_doc and user_doc.get("state", "").startswith("market_"):
        if text.lower() == "/cancel":
            await database.users_col.update_one(
                {"_id": user_id}, {"$unset": {"state": "", "marketplace_draft": ""}}
            )
            await message.reply_text("❌ Product creation cancelled.")
            return

        from handlers.marketplace import handle_marketplace_state

        await handle_marketplace_state(
            client, message, user_id, user_doc["state"], user_doc
        )
        return

    # Intercept shortener registration states
    if user_doc and user_doc.get("state", "").startswith("sh_"):
        if text.lower() == "/cancel":
            await database.users_col.update_one(
                {"_id": user_id}, {"$unset": {"state": "", "shortener_draft": ""}}
            )
            await message.reply_text("❌ Shortener configuration cancelled.")
            return

        from handlers.shorteners import handle_shortener_state

        await handle_shortener_state(
            client, message, user_id, user_doc["state"], user_doc
        )
        return

    if user_doc and user_doc.get("state") in ("awaiting_token", "saas_awaiting_token"):
        if text.lower() == "/cancel":
            await database.users_col.update_one(
                {"_id": user_id}, {"$unset": {"state": ""}}
            )
            await message.reply_text("❌ Registration cancelled.")
            return

        await message.reply_text("🔍 **Validating token...** please wait.")
        from handlers.saas import validate_bot_token
        from utils.saas import saas_runner

        username = await validate_bot_token(text)
        if username:
            existing = await database.sub_bots_col.find_one({"bot_token": text})
            if existing:
                await message.reply_text(
                    f"❌ This bot token is already registered to user ID {existing.get('owner_id')}."
                )
                return

            await database.add_sub_bot(user_id, text, username)
            await database.users_col.update_one(
                {"_id": user_id}, {"$unset": {"state": ""}}
            )

            await saas_runner.start_bot(text, username)

            await message.reply_text(
                f"🎉 **Bot successfully registered!**\n\n"
                f"Bot Username: @{username}\n"
                f"Status: **🟢 Running**\n\n"
                f"Your bot is now active and will respond to commands and deliver files independently!"
            )
        else:
            await message.reply_text(
                "❌ **Invalid Bot Token!**\n\n"
                "Please check the token format and make sure it is a valid token from @BotFather. "
                "Try sending it again, or type `/cancel` to abort."
            )
        return

    if user_doc and user_doc.get("state") == "saas_awaiting_screenshot":
        if text.lower() == "/cancel":
            await database.users_col.update_one(
                {"_id": user_id},
                {"$unset": {"state": "", "saas_pending_plan": ""}},
            )
            await message.reply_text("❌ Payment cancelled.")
            return

        if not message.photo and not message.document:
            await message.reply_text(
                "📸 **Please send a screenshot** of your UPI payment as a photo or document.\n"
                "Type `/cancel` to abort."
            )
            return

        plan_id = user_doc.get("saas_pending_plan", "pro")
        plan = database.PLAN_DEFINITIONS.get(plan_id, database.PLAN_DEFINITIONS["pro"])
        file_id = None
        if message.photo:
            file_id = message.photo.file_id
        elif message.document:
            file_id = message.document.file_id

        from database.premium_store import create_upi_payment, set_upi_screenshot

        payment_id_str = await create_upi_payment(
            user_id=user_id,
            plan=f"saas_{plan_id}",
            amount_inr=plan["price_inr"],
        )
        payment = {"_id": payment_id_str}
        if file_id:
            await set_upi_screenshot(payment["_id"], message.id)

        await database.users_col.update_one(
            {"_id": user_id},
            {"$unset": {"state": "", "saas_pending_plan": ""}},
        )

        await message.reply_text(
            f"✅ **Payment screenshot received!**\n\n"
            f"Your **{plan['name']}** plan upgrade request is pending verification.\n"
            f"Our team will review and activate your subscription shortly.\n\n"
            f"Use `/saas` to check your dashboard."
        )

        # Notify admins
        admin_text = (
            f"📋 **New SaaS Subscription Request**\n\n"
            f"User: `{user_id}`\n"
            f"Plan: {plan['name']} (₹{plan['price_inr']}/mo)\n"
            f"Payment ID: `{payment['_id']}`\n"
            f"Status: Pending Verification\n\n"
            f"Use `/approve_upi {payment['_id']}` to activate."
        )
        for admin_id in config.ADMIN_IDS:
            try:
                if file_id:
                    await client.send_photo(admin_id, file_id, caption=admin_text)
                else:
                    await client.send_message(admin_id, admin_text)
            except Exception:
                pass
        return

    async with user_locks[user_id]:
        # 1. Check if user is entering a password to access a link
        entry_session = await database.get_password_entry_session(user_id)
        if entry_session:
            token = entry_session["code"]
            bypass_monetization = entry_session.get("bypass_monetization", False)

            file_doc = await database.get_file_link(token)
            if not file_doc:
                await database.delete_password_entry_session(user_id)
                await message.reply_text(
                    "❌ The file link you were trying to access no longer exists."
                )
                return

            # Check if expired
            expires_at = file_doc.get("expires_at")
            if expires_at and datetime.datetime.now(datetime.timezone.utc) > expires_at:
                await database.delete_password_entry_session(user_id)
                await message.reply_text("❌ This file link has expired.")
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
                    return

                # Deliver files!
                await deliver_files(
                    client,
                    message.chat.id,
                    file_doc,
                    bypass_monetization=bypass_monetization,
                )
            else:
                # Wrong password! Keep session open so they can try again
                await message.reply_text(
                    "❌ **Incorrect Password!** Access denied. Please try again."
                )
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
            return

        # 3. Check if user sent a campaign / funnel payload
        campaign_info = parse_campaign_payload(text)
        if campaign_info.get("campaign_id"):
            campaign_id = campaign_info["campaign_id"]
            campaign = await database.get_campaign(campaign_id)
            if campaign:
                source = campaign_info.get("source")
                if source and is_valid_source(source):
                    await database.log_source_visit(
                        user_id, source, campaign_id, campaign_info.get("ref")
                    )
                await show_campaign_detail(client, message, campaign_id)
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
                if (
                    expires_at
                    and datetime.datetime.now(datetime.timezone.utc) > expires_at
                ):
                    await message.reply_text("❌ This file link has expired.")
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
                    return

                # Deliver the files
                await deliver_files(
                    client,
                    message.chat.id,
                    file_doc,
                    bypass_monetization=bypass_monetization,
                )
                return

    # Fallback: unrecognized text
    await message.reply_text(
        "👋 **Hello!**\n\n"
        "I am the File Share Bot. I can generate permanent shareable links for files stored on Telegram.\n\n"
        "📤 **Send me a file** to generate a sharing link.\n"
        "📋 Use **/batch** to upload multiple files.\n"
        "💰 Use **/premium** to view subscription plans.\n"
        "🛍 Use **/store** to browse the premium catalog.\n\n"
        "Type **/start** to see all available commands."
    )
