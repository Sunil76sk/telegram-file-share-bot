from __future__ import annotations

import datetime
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot import app
import database
import config
from utils.helpers import get_not_subscribed_channels
from utils.locks import user_locks
from utils.security import verify_password, hash_password
from utils.delivery import deliver_files

logger = logging.getLogger(__name__)


@app.on_message(
    filters.command("start")
    & filters.private
    & ~filters.create(lambda _, __, m: m.text is None)
)
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id

    # 1. Add user to database
    await database.add_user(
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
    )

    # 2. Check if user is banned
    if await database.is_banned(user_id):
        await message.reply_text("⛔️ You have been banned from using this bot.")
        return

    # Parse arguments
    text_split = message.text.split(None, 1)

    # Simple /start with no payload
    if len(text_split) == 1:
        welcome_text = (
            f"👋 Hello {message.from_user.mention}!\n\n"
            "I am the **File Share Bot**.\n"
            "I can generate permanent shareable links for files stored on Telegram.\n\n"
            "📤 **How to use:**\n"
            "• Send me any file directly to generate a single-file sharing link.\n"
            "• Use `/batch` to start uploading multiple files, and `/done` when finished to generate a combined batch sharing link.\n"
            "• Use `/cancel` to abort an active batch session."
        )
        # Add admin helper text if user is admin
        if await database.is_admin(user_id):
            welcome_text += (
                "\n\n🛠 **Admin Commands:**\n"
                "• `/stats` - View bot statistics\n"
                "• `/broadcast` - Broadcast a message to all users\n"
                "• `/channels` - List force subscription channels\n"
                "• `/add_channel <channel_id_or_username> <invite_link>` - Add force-join channel\n"
                "• `/del_channel <channel_id_or_username>` - Remove force-join channel\n"
                "• `/edit_link <code>` - Edit/manage files in a shared link\n"
                "• `/add_admin <user_id>` - Add dynamic admin\n"
                "• `/del_admin <user_id>` - Remove dynamic admin"
            )

        await message.reply_text(welcome_text)
        return

    # Handle /start <token> payload
    token = text_split[1].strip()
    file_doc = await database.get_file_link(token)

    if not file_doc:
        await message.reply_text(
            "❌ The file link you followed is invalid, expired, or has been deleted by an administrator."
        )
        return

    # Check if expired
    expires_at = file_doc.get("expires_at")
    if expires_at and datetime.datetime.now(datetime.timezone.utc) > expires_at:
        await message.reply_text("❌ This file link has expired.")
        return

    # Increment view counter
    await database.increment_link_views(token, user_id)

    # Check if password protected
    password_hash = file_doc.get("password_hash")
    if password_hash:
        await database.create_password_entry_session(user_id, token)
        await message.reply_text(
            "🔒 **Password Protected Link**\n\n"
            "This link is protected by a password. Please enter the password below to access the files."
        )
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
        buttons.append(
            [InlineKeyboardButton("🔄 Try Again", callback_data=f"checksub_{token}")]
        )

        await message.reply_text(
            "⚠️ **Access Denied!**\n\n"
            "You must join our channel before you can download this file. "
            "Please join the channel below and click Try Again to proceed.",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    # 4. Deliver the files
    await deliver_files(client, message.chat.id, file_doc)

@app.on_message(
    filters.private
    & filters.text
    & ~filters.command(["start", "batch", "done", "cancel", "editlink", "edit_link"])
)
async def text_message_handler(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip()

    if await database.is_banned(user_id):
        return

    async with user_locks[user_id]:
        # 1. Check if user is entering a password to access a link
        entry_session = await database.get_password_entry_session(user_id)
        if entry_session:
            token = entry_session["code"]
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

                    buttons.append(
                        [
                            InlineKeyboardButton(
                                "🔄 Try Again", callback_data=f"checksub_{token}"
                            )
                        ]
                    )

                    await message.reply_text(
                        "⚠️ **Access Denied!**\n\n"
                        "Password verified successfully! However, you must join our channel before you can download this file. "
                        "Please join the channel below and click Try Again to proceed.",
                        reply_markup=InlineKeyboardMarkup(buttons),
                    )
                    return

                # Deliver files!
                await deliver_files(client, message.chat.id, file_doc)
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
