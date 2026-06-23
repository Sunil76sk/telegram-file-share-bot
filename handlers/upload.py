import secrets
import logging
import config
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
                f"The token `{token}` is now in use. Please generate again by specifying a different token: `/done [new_token]`."
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

        from utils.helpers import get_share_link

        share_link = await get_share_link(client, token)

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
        # Delete batch status message if exists
        batch = await database.get_active_batch(user_id)
        if batch:
            status_message_id = batch.get("batch_message_id")
            if status_message_id:
                try:
                    await client.delete_messages(
                        chat_id=user_id, message_ids=status_message_id
                    )
                except Exception:
                    pass

        # Clear upload batches
        await database.delete_batch(user_id)

        # Clear ad drafts
        await database.clear_ad_draft(user_id)

        # Clear post builder (creator studio) drafts
        await database.delete_post_draft(user_id)

        # Clear edit sessions, password settings, password entries
        await database.delete_edit_session(user_id)
        await database.delete_password_setting_session(user_id)
        await database.delete_password_entry_session(user_id)

        # Clear template creation drafts
        from handlers.templates import template_creation_drafts

        if user_id in template_creation_drafts:
            try:
                del template_creation_drafts[user_id]
            except KeyError:
                pass

        # Clear state/catalog drafts/shorteners/marketplace/saas states in user document
        await database.users_col.update_one(
            {"_id": user_id},
            {
                "$unset": {
                    "state": "",
                    "catalog_draft": "",
                    "marketplace_draft": "",
                    "shortener_draft": "",
                    "saas_pending_plan": "",
                }
            },
        )

        await message.reply_text("✅ Current operation cancelled.")
        message.stop_propagation()


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

    # Creator Studio bypass: Only let the post builder handle it if they are actively in a capturing state
    draft = await database.get_post_draft(user_id)
    if draft and draft.get("state") in [
        "awaiting_media",
        "awaiting_caption",
        "awaiting_buttons",
        "awaiting_reactions",
    ]:
        return

    user_doc = await database.get_user(user_id)

    # 1. Intercept premium UPI screenshot upload
    import datetime

    pending = await database.get_pending_upi(user_id)
    state = user_doc.get("state", "") if user_doc else ""
    is_awaiting_upi = state.startswith("awaiting_upi_screenshot") or (
        pending and pending.get("screenshot_msg_id") is None
    )

    if is_awaiting_upi:
        is_valid = False
        if message.photo:
            is_valid = True
        elif message.document:
            file_name = message.document.file_name or ""
            ext = file_name.split(".")[-1].lower() if "." in file_name else ""
            if ext in ["jpg", "jpeg", "png"]:
                is_valid = True

        if not is_valid:
            await message.reply_text(
                "❌ **Invalid File Format!**\n\n"
                "Please upload only image files (`.jpg`, `.jpeg`, `.png`) as UPI payment screenshots.\n"
                "Files like `.apk`, `.exe`, `.zip`, or `.mp4` are not accepted."
            )
            message.stop_propagation()
            return

        file_id = None
        if message.photo:
            file_id = message.photo.file_id
        elif message.document:
            file_id = message.document.file_id

        if file_id:
            payment_id = (
                str(pending["_id"])
                if pending
                else state.replace("awaiting_upi_screenshot_", "")
            )
            payment = await database.get_upi_payment(payment_id)
            if not payment:
                payment = pending
                if not payment:
                    await message.reply_text(
                        "❌ No pending UPI payment found. Please type /premium or /store to checkout."
                    )
                    await database.users_col.update_one(
                        {"_id": user_id}, {"$unset": {"state": ""}}
                    )
                    message.stop_propagation()
                    return
                payment_id = str(payment["_id"])

            await database.set_upi_screenshot(payment_id, message.id)

            # Clear state
            await database.users_col.update_one(
                {"_id": user_id}, {"$unset": {"state": ""}}
            )

            await message.reply_text(
                "✅ **Payment screenshot received!**\n\n"
                "Our team is verifying the payment details. We will notify you once your purchase/premium access is activated."
            )

            plan_desc = payment["plan"]
            if plan_desc.startswith("prod_"):
                prod_id = plan_desc.replace("prod_", "", 1)
                try:
                    from bson import ObjectId

                    product = await database.get_product_by_id(ObjectId(prod_id))
                    plan_desc = (
                        f"Product: {product['name']}"
                        if product
                        else f"Product ID: {prod_id}"
                    )
                except Exception:
                    plan_desc = f"Product ID: {prod_id}"
            else:
                plan_desc = f"Subscription: {plan_desc.replace('_', ' ').title()}"

            admin_msg = (
                "🔔 **New UPI Payment Submission:**\n\n"
                f"👤 **User:** {message.from_user.mention} (`{user_id}`)\n"
                f"📦 **Plan/Item:** `{plan_desc}`\n"
                f"💰 **Amount:** ₹{payment['amount_inr']}\n"
                f"🕒 **Submitted:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                "Please review the attached screenshot and select an action:"
            )

            buttons = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "Approve ✅",
                            callback_data=f"admin_upi_approve_{payment_id}",
                        ),
                        InlineKeyboardButton(
                            "Reject ❌", callback_data=f"admin_upi_reject_{payment_id}"
                        ),
                    ]
                ]
            )

            for admin_id in config.ADMIN_IDS:
                try:
                    await message.copy(
                        chat_id=admin_id, caption=admin_msg, reply_markup=buttons
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to forward UPI screenshot to admin {admin_id}: {e}"
                    )
            message.stop_propagation()
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
