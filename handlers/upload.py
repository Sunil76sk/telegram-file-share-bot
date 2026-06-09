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

        await database.save_file_link(
            token=token,
            files=files,
            owner_id=user_id,
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
    )
)
async def file_uploader(client: Client, message: Message):
    user_id = message.from_user.id

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
                file_unique_ids = [f.get("file_unique_id") for f in files if f.get("file_unique_id")]

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
            file_unique_ids = [f.get("file_unique_id") for f in files if f.get("file_unique_id")]
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
