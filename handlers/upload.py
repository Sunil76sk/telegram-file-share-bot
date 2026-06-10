import secrets
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot import app
import database
from utils.helpers import banned_filter, is_valid_token, extract_file_details
from utils.locks import user_locks, processing_counts
from utils.buttons import update_status_message, update_edit_ui

logger = logging.getLogger(__name__)


@app.on_message(filters.command("batch") & filters.private & ~banned_filter)
async def batch_start_cmd(client: Client, message: Message):
    user_id = message.from_user.id

    # Check if a custom token was provided
    args = message.text.split(None, 1)
    custom_token = None
    if len(args) > 1:
        custom_token = args[1].strip()
        if not is_valid_token(custom_token):
            await message.reply_text(
                "❌ **Invalid Custom Token!**\n\n"
                "A custom token must:\n"
                "• Be between 3 and 64 characters long.\n"
                "• Contain only letters, numbers, underscores (`_`), or hyphens (`-`)."
            )
            return

        # Check if the token is already in use
        existing = await database.get_file_link(custom_token)
        if existing:
            await message.reply_text(
                f"❌ **Token Already In Use!**\n\n"
                f"The token `{custom_token}` is already assigned to an existing file share link. "
                f"Please choose a different token."
            )
            return

    async with user_locks[user_id]:
        batch = await database.get_active_batch(user_id)
        if batch:
            await message.reply_text(
                "⚠️ You already have an active batch session! Send files to add them."
            )
            return

        await database.create_batch(user_id, custom_token)
        await update_status_message(client, user_id)


@app.on_message(filters.command("done") & filters.private & ~banned_filter)
async def batch_done_cmd(client: Client, message: Message):
    user_id = message.from_user.id

    # Check if a custom token was provided at finalization
    args = message.text.split(None, 1)
    custom_token = None
    if len(args) > 1:
        custom_token = args[1].strip()
        if not is_valid_token(custom_token):
            await message.reply_text(
                "❌ **Invalid Custom Token!**\n\n"
                "A custom token must:\n"
                "• Be between 3 and 64 characters long.\n"
                "• Contain only letters, numbers, underscores (`_`), or hyphens (`-`)."
            )
            return

        # Check if the token is already in use
        existing = await database.get_file_link(custom_token)
        if existing:
            await message.reply_text(
                f"❌ **Token Already In Use!**\n\n"
                f"The token `{custom_token}` is already assigned to an existing file share link. "
                f"Please choose a different token."
            )
            return

    async with user_locks[user_id]:
        batch = await database.get_active_batch(user_id)
        if not batch:
            await message.reply_text(
                "❌ You don't have an active batch session. Send a file to start one, or use `/batch`."
            )
            return

        files = batch.get("files", [])
        if not files:
            await message.reply_text(
                "⚠️ No files have been uploaded yet. Send files to this chat, or send `/cancel` to abort."
            )
            return

        # Determine the final token
        token = custom_token or batch.get("custom_token") or secrets.token_urlsafe(8)

        # Double check if token is already in use
        existing = await database.get_file_link(token)
        if existing:
            await message.reply_text(
                f"❌ **Token Already In Use!**\n\n"
                f"The token `{token}` is now in use. Please generate again by specifying a different token: `/done <new_token>`."
            )
            return

        bot = client.me or await client.get_me()
        await database.save_file_link(
            token=token,
            files=files,
            owner_id=user_id,
            bot_id=bot.id,
        )

        # Delete status message
        status_message_id = batch.get("batch_message_id")
        if status_message_id:
            try:
                await client.delete_messages(
                    chat_id=user_id, message_ids=status_message_id
                )
            except Exception:
                pass

        await database.delete_batch(user_id)

        bot = client.me or await client.get_me()
        username = bot.username or "bot"
        share_link = f"https://t.me/{username}?start={token}"

        await message.reply_text(
            f"✅ **Batch Share Link Generated successfully!**\n\n"
            f"📦 **Total Files:** {len(files)}\n"
            f"🔗 **Permanent Link:** `{share_link}`\n\n"
            f"🔒 Would you like to protect this link with a password?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔑 Yes, Set Password", callback_data=f"pw_ask_{token}"
                        ),
                        InlineKeyboardButton(
                            "❌ No, Skip", callback_data=f"pw_no_{token}"
                        ),
                    ]
                ]
            ),
        )


@app.on_message(filters.command("cancel") & filters.private & ~banned_filter)
async def batch_cancel_cmd(client: Client, message: Message):
    user_id = message.from_user.id

    async with user_locks[user_id]:
        # Cancel any active wizards or pending states first
        user_doc = await database.get_user(user_id)
        if user_doc and user_doc.get("state"):
            state = user_doc["state"]
            if state.startswith("catalog_"):
                await database.users_col.update_one(
                    {"_id": user_id}, {"$unset": {"state": "", "catalog_draft": ""}}
                )
                await message.reply_text("❌ Catalog item creation cancelled.")
                return
            elif state.startswith("market_"):
                await database.users_col.update_one(
                    {"_id": user_id}, {"$unset": {"state": "", "marketplace_draft": ""}}
                )
                await message.reply_text("❌ Product creation cancelled.")
                return
            elif state.startswith("sh_"):
                await database.users_col.update_one(
                    {"_id": user_id}, {"$unset": {"state": "", "shortener_draft": ""}}
                )
                await message.reply_text("❌ Shortener configuration cancelled.")
                return
            elif state in ("awaiting_token", "saas_awaiting_token"):
                await database.users_col.update_one(
                    {"_id": user_id}, {"$unset": {"state": ""}}
                )
                await message.reply_text("❌ Registration cancelled.")
                return
            elif state == "saas_awaiting_screenshot":
                await database.users_col.update_one(
                    {"_id": user_id}, {"$unset": {"state": "", "saas_pending_plan": ""}}
                )
                await message.reply_text("❌ SaaS upgrade cancelled.")
                return

        # Fallback to standard batch cancel
        batch = await database.get_active_batch(user_id)
        if not batch:
            await message.reply_text("❌ You do not have an active batch session.")
            return

        # Delete status message
        status_message_id = batch.get("batch_message_id")
        if status_message_id:
            try:
                await client.delete_messages(
                    chat_id=user_id, message_ids=status_message_id
                )
            except Exception:
                pass

        await database.delete_batch(user_id)
        await message.reply_text(
            "🗑 **Batch session cancelled.** All uploaded temporary files have been cleared."
        )


@app.on_message(
    filters.private
    & ~banned_filter
    & (
        filters.document
        | filters.video
        | filters.audio
        | filters.photo
        | filters.voice
        | filters.animation
    ),
    group=1,
)
async def file_uploader(client: Client, message: Message):
    user_id = message.from_user.id

    user_doc = await database.get_user(user_id)

    # 1. Intercept SaaS screenshot upload
    if user_doc and user_doc.get("state") == "saas_awaiting_screenshot":
        plan_id = user_doc.get("saas_pending_plan", "pro")
        plan = database.PLAN_DEFINITIONS.get(plan_id, database.PLAN_DEFINITIONS["pro"])
        
        file_id = None
        if message.photo:
            file_id = message.photo.file_id
        elif message.document:
            file_id = message.document.file_id
            
        if not file_id:
            await message.reply_text(
                "📸 **Please send a screenshot** of your UPI payment as a photo or document."
            )
            return

        from database.premium_store import create_upi_payment, set_upi_screenshot

        payment_id_str = await create_upi_payment(
            user_id=user_id,
            plan=f"saas_{plan_id}",
            amount_inr=plan["price_inr"],
        )
        await set_upi_screenshot(payment_id_str, file_id)

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
            f"Payment ID: `{payment_id_str}`\n"
            f"Status: Pending Verification\n\n"
            f"Use `/approve_upi {payment_id_str}` to activate."
        )
        for admin_id in config.ADMIN_IDS:
            try:
                await client.send_photo(admin_id, file_id, caption=admin_text)
            except Exception:
                try:
                    await client.send_message(admin_id, admin_text)
                except Exception:
                    pass
        return

    # 2. Intercept premium/store UPI screenshot upload
    import datetime
    import config
    from bson import ObjectId
    pending = await database.get_pending_upi(user_id)
    if pending and pending.get("screenshot_msg_id") is None:
        file_id = None
        if message.photo:
            file_id = message.photo.file_id
        elif message.document:
            file_id = message.document.file_id

        if file_id:
            payment_id = str(pending["_id"])
            await database.set_upi_screenshot(payment_id, message.id)

            await message.reply_text(
                "✅ **Payment screenshot received!**\n\n"
                "Our team is verifying the payment details. We will notify you once your premium access is activated "
                "or your purchased content is unlocked."
            )

            plan_desc = pending["plan"]
            if plan_desc.startswith("item_"):
                item_id = plan_desc.split("_")[1]
                item = await database.get_catalog_item(item_id)
                plan_desc = f"Store Item: {item['title']}" if item else f"Item ID {item_id}"
            elif plan_desc.startswith("prod_"):
                product_id = plan_desc.split("_")[1]
                product = await database.get_product_by_id(ObjectId(product_id))
                plan_desc = f"Marketplace Product: {product['name']}" if product else f"Product ID {product_id}"
            else:
                plan_desc = f"Subscription: {plan_desc.replace('_', ' ').title()}"

            admin_msg = (
                "🔔 **New UPI Payment Submission:**\n\n"
                f"👤 **User:** {message.from_user.mention} (`{user_id}`)\n"
                f"📦 **Plan/Item:** `{plan_desc}`\n"
                f"💰 **Amount:** ₹{pending['amount_inr']}\n"
                f"🕒 **Submitted:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                "Please review the attached screenshot and select an action:"
            )

            buttons = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Approve ✅", callback_data=f"admin_upi_approve_{payment_id}"),
                        InlineKeyboardButton("Reject ❌", callback_data=f"admin_upi_reject_{payment_id}"),
                    ]
                ]
            )

            for admin_id in config.ADMIN_IDS:
                try:
                    await message.copy(chat_id=admin_id, caption=admin_msg, reply_markup=buttons)
                except Exception as e:
                    logger.error(f"Failed to forward UPI screenshot to admin {admin_id}: {e}")
            return

    # 3. Intercept marketplace product upload files
    if user_doc and user_doc.get("state", "").startswith("market_"):
        from handlers.marketplace import handle_marketplace_state

        await handle_marketplace_state(
            client, message, user_id, user_doc["state"], user_doc
        )
        return

    # Extract file details
    file_id, file_unique_id, file_name, file_type, file_size, caption = (
        extract_file_details(message)
    )
    if not file_id:
        await message.reply_text(
            "❌ Could not extract file information from this message."
        )
        return

    # Map file_type to compliant media_type
    media_type = "document"
    if file_type == "photo":
        media_type = "photo"
    elif file_type in ["video", "animation"]:
        media_type = "video"
    elif file_type in ["audio", "voice"]:
        media_type = "audio"

    # Increment processing count before lock
    processing_counts[user_id] += 1

    try:
        async with user_locks[user_id]:
            # 1. Check if there is an active edit/append session
            edit_session = await database.get_edit_session(user_id)
            if edit_session:
                files = edit_session.get("files", [])
                file_unique_ids = [
                    f.get("file_unique_id") for f in files if f.get("file_unique_id")
                ]

                # Prevent duplicate uploads within the same edit session
                if file_unique_id and file_unique_id in file_unique_ids:
                    return

                new_file = {
                    "file_id": file_id,
                    "file_unique_id": file_unique_id,
                    "media_type": media_type,
                    "caption": caption or None,
                    "file_name": file_name,
                    "file_size": file_size,
                }
                files.append(new_file)

                await database.update_edit_session_files(
                    user_id=user_id,
                    files=files,
                )
                return

            # 2. Batch upload logic
            batch = await database.get_active_batch(user_id)
            if not batch:
                await database.create_batch(user_id)
                batch = await database.get_active_batch(user_id)

            files = batch.get("files", [])  # type: ignore[union-attr]
            file_unique_ids = [
                f.get("file_unique_id") for f in files if f.get("file_unique_id")
            ]
            if file_unique_id and file_unique_id in file_unique_ids:
                return

            # Add to batch
            await database.add_to_batch(
                user_id=user_id,
                file_id=file_id,
                file_unique_id=file_unique_id,
                media_type=media_type,
                caption=caption or None,
                file_name=file_name,
                file_size=file_size,
            )
    except Exception as e:
        logger.error(f"Error handling file upload: {e}")
    finally:
        processing_counts[user_id] -= 1

        # When all concurrent messages have been processed, update/send the correct status message
        if processing_counts[user_id] == 0:
            async with user_locks[user_id]:
                if processing_counts[user_id] == 0:
                    edit_session = await database.get_edit_session(user_id)
                    if edit_session:
                        await update_edit_ui(client, user_id)
                    else:
                        await update_status_message(client, user_id)
