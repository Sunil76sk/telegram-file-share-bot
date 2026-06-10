from __future__ import annotations

import secrets
import datetime
import logging

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot import app
import database
from utils.helpers import get_not_subscribed_channels
from utils.locks import user_locks
from utils.buttons import update_edit_ui
from utils.delivery import deliver_files

logger = logging.getLogger(__name__)


@app.on_callback_query(filters.regex(r"^checksub_(.+)"))
async def check_sub_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    raw_token = callback_query.matches[0].group(1)
    bypass_monetization = False

    if raw_token.startswith("unl_"):
        raw_token = raw_token.replace("unl_", "", 1)
        bypass_monetization = True

    # Robust token parsing if the token in the callback_data contains a URL or parameter
    if "start=" in raw_token:
        token = raw_token.split("start=")[1].split("&")[0]
    elif "/" in raw_token:
        token = raw_token.split("/")[-1].split("?")[0]
    else:
        token = raw_token

    # Check if user is banned
    if await database.is_banned(user_id):
        await callback_query.answer("⛔️ You have been banned.", show_alert=True)
        return

    # Check subscription status again
    not_joined = await get_not_subscribed_channels(client, user_id)
    if not_joined:
        await callback_query.answer(
            "❌ Please join the channel first before trying again!", show_alert=True
        )
        return

    # User has joined all channels, proceed to deliver files
    file_doc = await database.get_file_link(token)
    if not file_doc:
        await callback_query.answer(
            "❌ This file link no longer exists.", show_alert=True
        )
        await callback_query.message.edit_text(
            "❌ The file link has been deleted or expired."
        )
        return

    # Check if expired
    expires_at = file_doc.get("expires_at")
    if expires_at and datetime.datetime.now(datetime.timezone.utc) > expires_at:
        await callback_query.answer("❌ This file link has expired.", show_alert=True)
        await callback_query.message.edit_text("❌ This file link has expired.")
        return

    # Acknowledge the callback
    await callback_query.answer("✅ Subscription verified! Delivering files...")

    # Delete the sub join message and send files
    await callback_query.message.delete()
    await deliver_files(
        client,
        callback_query.message.chat.id,
        file_doc,
        bypass_monetization=bypass_monetization,
    )


@app.on_callback_query(filters.regex(r"^batch_(add|close|generate)$"))
async def batch_callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id

    # Check if user is banned
    if await database.is_banned(user_id):
        await callback_query.answer("⛔️ You have been banned.", show_alert=True)
        return

    action = callback_query.data.split("_")[1]  # type: ignore[union-attr]

    if action == "add":
        await callback_query.answer(
            "📥 Send more files directly to this chat.", show_alert=True
        )
        return

    async with user_locks[user_id]:
        batch = await database.get_active_batch(user_id)
        if not batch:
            await callback_query.answer(
                "❌ No active batch session found.", show_alert=True
            )
            try:
                await callback_query.message.delete()
            except Exception:
                pass
            return

        if action == "close":
            await database.delete_batch(user_id)
            await callback_query.answer("🗑 Batch session discarded.")
            try:
                await callback_query.message.delete()
            except Exception:
                pass
            await client.send_message(
                chat_id=user_id,
                text="🗑 **Batch session cancelled.** All uploaded temporary files have been cleared.",
            )

        elif action == "generate":
            files = batch.get("files", [])
            if not files:
                await callback_query.answer(
                    "⚠️ No files have been uploaded yet. Please send some files.",
                    show_alert=True,
                )
                return

            custom_token = batch.get("custom_token")
            if custom_token:
                # Double check if token is already in use
                existing = await database.get_file_link(custom_token)
                if existing:
                    await callback_query.answer(
                        f"❌ The custom token '{custom_token}' is now in use. Please use /done [new_token] to finalize.",
                        show_alert=True,
                    )
                    return
                token = custom_token
            else:
                token = secrets.token_urlsafe(8)

            bot = client.me or await client.get_me()
            await database.save_file_link(
                token=token,
                files=files,
                owner_id=user_id,
                bot_id=bot.id,
            )
            await database.delete_batch(user_id)
            await callback_query.answer("✅ Share link generated successfully!")

            try:
                await callback_query.message.delete()
            except Exception:
                pass

            username = bot.username or "bot"
            share_link = f"https://t.me/{username}?start={token}"
            await client.send_message(
                chat_id=user_id,
                text=(
                    f"✅ **Batch Share Link Generated successfully!**\n\n"
                    f"📦 **Total Files:** {len(files)}\n"
                    f"🔗 **Permanent Link:** `{share_link}`\n\n"
                    f"🔒 Would you like to protect this link with a password?"
                ),
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


@app.on_callback_query(filters.regex(r"^pw_(ask|no)_(.+)"))
async def pw_callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id

    if await database.is_banned(user_id):
        await callback_query.answer("⛔️ You have been banned.", show_alert=True)
        return

    action = callback_query.matches[0].group(1)
    token = callback_query.matches[0].group(2)

    file_doc = await database.get_file_link(token)
    if not file_doc:
        await callback_query.answer("❌ This link no longer exists.", show_alert=True)
        await callback_query.message.delete()
        return

    if action == "no":
        await callback_query.answer("Skipped password protection.")
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
        await callback_query.message.edit_text(
            "⏱ **Choose Link Expiry**\n\n"
            "Please choose how long this share link should remain valid:",
            reply_markup=buttons,
        )
    elif action == "ask":
        await database.create_password_setting_session(user_id, token)
        await callback_query.answer("Send the password now.")
        await callback_query.message.edit_text(
            "🔒 **Set Password**\n\n"
            "Please send the password you want to set for this link directly as a text message."
        )


@app.on_callback_query(filters.regex(r"^exp_(1h|1d|7d|perm)_(.+)"))
async def exp_callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if await database.is_banned(user_id):
        await callback_query.answer("⛔️ You have been banned.", show_alert=True)
        return
    option = callback_query.matches[0].group(1)
    token = callback_query.matches[0].group(2)
    file_doc = await database.get_file_link(token)
    if not file_doc:
        await callback_query.answer("❌ This link no longer exists.", show_alert=True)
        await callback_query.message.delete()
        return
    expires_at = None
    expiry_text = "Permanent"
    now = datetime.datetime.now(datetime.timezone.utc)
    if option == "1h":
        expires_at = now + datetime.timedelta(hours=1)
        expiry_text = "1 Hour"
    elif option == "1d":
        expires_at = now + datetime.timedelta(days=1)
        expiry_text = "1 Day"
    elif option == "7d":
        expires_at = now + datetime.timedelta(days=7)
        expiry_text = "7 Days"
    await database.set_link_expiry(token, expires_at)
    await callback_query.answer(f"Expiry set to {expiry_text}.")
    bot = client.me or await client.get_me()
    username = bot.username or "bot"
    share_link = f"https://t.me/{username}?start={token}"
    pw_protected = "Yes" if file_doc.get("password_hash") else "No"
    await callback_query.message.edit_text(
        f"✅ **Batch Share Link Finalized successfully!**\n\n"
        f"📦 **Total Files:** {len(file_doc.get('files', []))}\n"
        f"🔗 **Permanent Link:** `{share_link}`\n"
        f"🔒 **Password Protected:** `{pw_protected}`\n"
        f"⏱ **Expiry:** `{expiry_text}`\n\n"
        f"You can share this link with users."
    )


@app.on_callback_query(filters.regex(r"^edit_(del_\d+|save|exit)$"))
async def edit_callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id

    # Check if user is banned
    if await database.is_banned(user_id):
        await callback_query.answer("⛔️ You have been banned.", show_alert=True)
        return

    action_parts = callback_query.data.split("_")  # type: ignore[union-attr]
    action = action_parts[1]

    async with user_locks[user_id]:
        session = await database.get_edit_session(user_id)
        if not session:
            await callback_query.answer(
                "❌ No active edit session found.", show_alert=True
            )
            try:
                await callback_query.message.delete()
            except Exception:
                pass
            return

        if action == "del":
            index = int(action_parts[2])
            files = session.get("files", [])
            pending_deletes = session.get("pending_deletes", [])

            if index < 0 or index >= len(files):
                await callback_query.answer("❌ Invalid file index.", show_alert=True)
                return

            removed_file = files.pop(index)
            removed_name = removed_file.get("file_name", "Unknown File")

            file_unique_id = removed_file.get("file_unique_id")
            if file_unique_id and file_unique_id not in pending_deletes:
                pending_deletes.append(file_unique_id)

            await database.update_edit_session_files(
                user_id=user_id,
                files=files,
                pending_deletes=pending_deletes,
            )

            await callback_query.answer(f"❌ Removed file: {removed_name}")
            await update_edit_ui(client, user_id)

        elif action == "exit":
            await database.delete_edit_session(user_id)
            await callback_query.answer("🚪 Edit mode exited.")
            try:
                await callback_query.message.delete()
            except Exception:
                pass
            await client.send_message(
                chat_id=user_id,
                text="❌ **Edit session exited.** Pending changes were discarded and the live link remains unchanged.",
            )

        elif action == "save":
            files = session.get("files", [])
            if not files:
                await callback_query.answer(
                    "⚠️ You cannot save an empty link! Please add some files or exit.",
                    show_alert=True,
                )
                return

            token = session["token"]
            # Atomic commit to live share link record
            await database.update_file_link(
                token=token,
                files=files,
            )
            await database.delete_edit_session(user_id)
            await callback_query.answer("✅ Changes saved successfully!")

            try:
                await callback_query.message.delete()
            except Exception:
                pass

            bot = client.me or await client.get_me()
            username = bot.username or "bot"
            share_link = f"https://t.me/{username}?start={token}"
            await client.send_message(
                chat_id=user_id,
                text=(
                    f"✅ **Changes saved atomically!**\n\n"
                    f"📦 **Total Files now:** {len(files)}\n"
                    f"🔗 **Link:** `{share_link}`"
                ),
            )
