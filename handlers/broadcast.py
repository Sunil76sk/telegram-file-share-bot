from __future__ import annotations

import asyncio
import logging
import time

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import (
    FloodWait,
    UserIsBlocked,
    InputUserDeactivated,
    PeerIdInvalid,
)
from bot import app
import database
import config
from utils.helpers import admin_filter
from utils.locks import broadcast_lock

logger = logging.getLogger(__name__)

is_broadcasting = False


async def premium_check(_, client: Client, message: Message):
    if not message or not message.from_user:
        return False
    return await database.is_user_premium(message.from_user.id)

premium_filter = filters.create(premium_check)


async def run_broadcast(
    client: Client,
    admin_chat_id: int,
    status_message_id: int,
    reply_message: Message,
    broadcast_text: str | None,
    all_users: list,
):
    global is_broadcasting
    total_users = len(all_users)
    success = 0
    failed = 0
    blocked = 0

    last_update_time = time.time()

    try:
        for index, user_id in enumerate(all_users):
            try:
                if reply_message:
                    await reply_message.copy(chat_id=user_id)
                else:
                    assert broadcast_text is not None
                    await client.send_message(chat_id=user_id, text=broadcast_text)
                success += 1
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
                try:
                    if reply_message:
                        await reply_message.copy(chat_id=user_id)
                    else:
                        assert broadcast_text is not None
                        await client.send_message(chat_id=user_id, text=broadcast_text)
                    success += 1
                except Exception as retry_err:
                    logger.error(f"Failed to retry broadcast to {user_id}: {retry_err}")
                    failed += 1
            except (UserIsBlocked, InputUserDeactivated):
                blocked += 1
                failed += 1
                # Deactivate user in DB
                await database.set_user_active_status(user_id, False)
            except PeerIdInvalid:
                failed += 1
            except Exception as err:
                logger.error(f"Broadcast error for user {user_id}: {err}")
                failed += 1

            # Update progress status message at most once every 3 seconds to avoid spamming the API
            now_time = time.time()
            if now_time - last_update_time >= 3.0 or index + 1 == total_users:
                last_update_time = now_time
                try:
                    await client.edit_message_text(
                        chat_id=admin_chat_id,
                        message_id=status_message_id,
                        text=(
                            f"📢 **Broadcasting in progress...**\n\n"
                            f"Progress: `{index + 1}/{total_users}`\n"
                            f"✅ Success: `{success}`\n"
                            f"❌ Failed: `{failed}`\n"
                            f"🚫 Blocked/Deactivated: `{blocked}` (Deactivated)"
                        ),
                    )
                except Exception:
                    pass

            # Brief yield to keep the Event Loop responsive
            await asyncio.sleep(0.05)

        # Final completion report
        try:
            await client.edit_message_text(
                chat_id=admin_chat_id,
                message_id=status_message_id,
                text=(
                    f"📢 **Broadcast Completed!**\n\n"
                    f"👥 **Total Target:** `{total_users}`\n"
                    f"✅ **Success:** `{success}`\n"
                    f"❌ **Failed:** `{failed}`\n"
                    f"🚫 **Blocked/Deactivated:** `{blocked}` (Deactivated)"
                ),
            )
        except Exception:
            await client.send_message(
                chat_id=admin_chat_id,
                text=(
                    f"📢 **Broadcast Completed!**\n\n"
                    f"👥 **Total Target:** `{total_users}`\n"
                    f"✅ **Success:** `{success}`\n"
                    f"❌ **Failed:** `{failed}`\n"
                    f"🚫 **Blocked/Deactivated:** `{blocked}` (Deactivated)"
                ),
            )
    except Exception as e:
        logger.error(f"Error in run_broadcast background task: {e}")
        try:
            await client.send_message(
                chat_id=admin_chat_id,
                text=f"❌ **Broadcast encountered an error:** {e}",
            )
        except Exception:
            pass
    finally:
        is_broadcasting = False


@app.on_message(filters.command("broadcast") & filters.private & admin_filter)
async def broadcast_handler(client: Client, message: Message):
    global is_broadcasting
    async with broadcast_lock:
        if is_broadcasting:
            await message.reply_text(
                "⚠️ Another broadcast is currently in progress. Please wait for it to complete."
            )
            return
        is_broadcasting = True

    # Determine what to broadcast (either the message replied to, or the text following the command)
    reply = message.reply_to_message
    broadcast_text = None
    if not reply:
        text_parts = message.text.split(None, 1)
        if len(text_parts) < 2:
            is_broadcasting = False
            await message.reply_text(
                "⚠️ Please reply to a message or provide text to broadcast.\nUsage: `/broadcast Hello Users` or reply to a post with `/broadcast`."
            )
            return
        broadcast_text = text_parts[1]

    all_users = await database.get_all_users()
    total_users = len(all_users)

    if total_users == 0:
        is_broadcasting = False
        await message.reply_text("❌ No registered users to broadcast to.")
        return

    status_msg = await message.reply_text(
        f"📢 **Starting broadcast...**\n"
        f"Target: `{total_users}` users.\n"
        f"This runs in the background. You will receive a completion message shortly."
    )

    asyncio.create_task(
        run_broadcast(
            client=client,
            admin_chat_id=message.chat.id,
            status_message_id=status_msg.id,
            reply_message=reply,
            broadcast_text=broadcast_text,
            all_users=all_users,
        )
    )


@app.on_message(filters.command("ban") & filters.private & admin_filter)
async def ban_handler(client: Client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("⚠️ Usage: `/ban [user_id]`")
        return

    try:
        user_id = int(args[1])
    except ValueError:
        await message.reply_text("❌ User ID must be an integer.")
        return

    if user_id == message.from_user.id:
        await message.reply_text("❌ You cannot ban yourself.")
        return

    await database.ban_user(user_id)
    await message.reply_text(f"✅ User `{user_id}` has been banned from using the bot.")


@app.on_message(filters.command("unban") & filters.private & admin_filter)
async def unban_handler(client: Client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("⚠️ Usage: `/unban [user_id]`")
        return

    try:
        user_id = int(args[1])
    except ValueError:
        await message.reply_text("❌ User ID must be an integer.")
        return

    await database.unban_user(user_id)
    await message.reply_text(f"✅ User `{user_id}` has been unbanned.")


def parse_channel_input(input_str: str):
    input_str = input_str.strip()
    
    # 1. Check if it is a numeric ID (integer)
    if input_str.startswith("-") or input_str.isdigit():
        try:
            return int(input_str), None
        except ValueError:
            pass

    # 2. Check if it is a Telegram URL/Link
    if "t.me/" in input_str or "telegram.me/" in input_str or input_str.startswith("https://") or input_str.startswith("http://"):
        clean = input_str.replace("https://", "").replace("http://", "")
        clean = clean.replace("telegram.me/", "").replace("t.me/", "")
        
        # Private invite links (e.g., https://t.me/+abc or https://t.me/joinchat/abc)
        if clean.startswith("+") or clean.startswith("joinchat/"):
            invite_link = f"https://t.me/{clean}"
            return invite_link, invite_link
            
        # Public channel links (e.g., https://t.me/channelname)
        username = clean.split("/")[0].split("?")[0].strip()
        if username:
            return f"@{username}", f"https://t.me/{username}"

    # 3. Usernames or raw strings
    username = input_str.replace("@", "").strip()
    return f"@{username}", f"https://t.me/{username}"


@app.on_message(filters.command("add_channel") & filters.private & premium_filter)
async def add_channel_handler(client: Client, message: Message):
    if "[channel_id_or_username]" in message.text or "[invite_link]" in message.text:
        await message.reply_text(
            "❌ **Error: You included the placeholder brackets!**\n\n"
            "Please do **not** write `[channel_id_or_username]` or `[invite_link]` in your command.\n"
            "You must **replace** them with your actual channel username/ID and invite link.\n\n"
            "**Correct Example:**\n"
            "`/add_channel @QuickAmazonFinds https://t.me/QuickAmazonFinds`\n\n"
            "**Another Example (with channel ID):**\n"
            "`/add_channel -1002471479638 https://t.me/+IbHLv5W4jpBkYzBl`"
        )
        return

    args = message.text.split(None, 2)
    if len(args) < 2:
        await message.reply_text(
            "⚠️ Usage: `/add_channel [channel_id_or_username] [invite_link]`"
        )
        return

    chat_raw = args[1].strip()
    chat_id, invite_link = parse_channel_input(chat_raw)

    try:
        # Check bot access and fetch title
        chat_info = await client.get_chat(chat_id)
        title = chat_info.title
        # If it successfully fetched chat info, use the resolved integer ID for consistency
        chat_id = chat_info.id
    except Exception as e:
        logger.error(f"Failed to access channel info for {chat_id}: {e}")
        await message.reply_text(
            "❌ **Invalid channel identifier or Bot is not in the channel.**\n\n"
            "Please make sure:\n"
            "1. You provided a valid channel ID, username, or invite link.\n"
            "2. You **added the bot to the channel as an Administrator** BEFORE running this command."
        )
        return

    # Verify bot is an administrator in the channel
    try:
        bot_member = await client.get_chat_member(chat_id, "me")
        bot_status = str(bot_member.status).split(".")[-1].lower()
        if bot_status not in ["administrator", "owner", "creator"]:
            await message.reply_text("❌ Bot is not an administrator in this channel.")
            return
    except Exception as e:
        logger.error(f"Failed to verify admin status of bot in channel {chat_id}: {e}")
        await message.reply_text("❌ Bot is not an administrator in this channel.")
        return

    # Determine invite link (optional override)
    if len(args) >= 3:
        invite_link = args[2].strip()
    else:
        if not invite_link:
            if getattr(chat_info, "username", None):
                invite_link = f"https://t.me/{chat_info.username}"
            elif getattr(chat_info, "invite_link", None):
                invite_link = chat_info.invite_link
            else:
                try:
                    invite_link = await client.export_chat_invite_link(chat_id)
                except Exception as e:
                    logger.warning(f"Could not export invite link for private channel {chat_id}: {e}")

    # Fallback default if still not found
    if not invite_link:
        invite_link = f"https://t.me/c/{str(chat_id).replace('-100', '')}/1"

    # Save to database (updates if exists, preventing duplicates)
    await database.add_force_sub_channel(chat_id, title, invite_link)
    
    await message.reply_text(
        f"✅ Channel Added\n"
        f"Channel ID: `{chat_id}`\n"
        f"Title: **{title}**\n"
        f"Invite Link: {invite_link}"
    )


@app.on_message(filters.command("del_channel") & filters.private & premium_filter)
async def del_channel_handler(client: Client, message: Message):
    if "[channel_id_or_username]" in message.text:
        await message.reply_text(
            "❌ **Error: You included the placeholder brackets!**\n\n"
            "Please do **not** write `[channel_id_or_username]` in your command.\n"
            "You must **replace** it with your actual channel username or ID.\n\n"
            "**Correct Example:**\n"
            "`/del_channel @QuickAmazonFinds`"
        )
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("⚠️ Usage: `/del_channel [channel_id_or_username]`")
        return

    chat_raw = args[1].strip()
    if chat_raw.startswith("-") or chat_raw.isdigit():
        try:
            chat_id = int(chat_raw)
        except ValueError:
            await message.reply_text("❌ Invalid ID format.")
            return
    else:
        chat_id = chat_raw
        if not chat_id.startswith("@"):
            chat_id = f"@{chat_id}"

    deleted = await database.delete_force_sub_channel(chat_id)
    if deleted:
        await message.reply_text(
            f"✅ Removed `{chat_id}` from force subscription channels."
        )
    else:
        await message.reply_text(f"❌ Channel `{chat_id}` not found in force sub list.")


@app.on_message(filters.command("channels") & filters.private & premium_filter)
async def list_channels_handler(client: Client, message: Message):
    db_channels = await database.get_force_sub_channels()
    static_channels = config.FORCE_SUB_CHATS

    text = "📢 **Force Subscription Channels List**\n\n"

    text += "🔹 **Dynamic Channels (Database):**\n"
    if db_channels:
        for channel in db_channels:
            text += f"• **{channel['title']}**\n  ID: `{channel['_id']}`\n  Link: [Join Here]({channel['invite_link']})\n"
    else:
        text += "• _None_\n"

    text += "\n🔸 **Static Channels (Config/Env):**\n"
    if static_channels:
        for index, chat in enumerate(static_channels, start=1):
            text += f"• `{chat}`\n"
    else:
        text += "• _None_\n"

    await message.reply_text(text, disable_web_page_preview=True)


@app.on_message(filters.command("add_admin") & filters.private & admin_filter)
async def add_admin_handler(client: Client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("⚠️ Usage: `/add_admin [user_id]`")
        return

    try:
        user_id = int(args[1])
    except ValueError:
        await message.reply_text("❌ User ID must be an integer.")
        return

    await database.add_admin(user_id)
    await message.reply_text(
        f"✅ User `{user_id}` promoted to bot administrator dynamically."
    )


@app.on_message(filters.command("del_admin") & filters.private & admin_filter)
async def del_admin_handler(client: Client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("⚠️ Usage: `/del_admin [user_id]`")
        return

    try:
        user_id = int(args[1])
    except ValueError:
        await message.reply_text("❌ User ID must be an integer.")
        return

    if user_id in config.ADMIN_IDS:
        await message.reply_text(
            "❌ Cannot remove static administrators configured in environment variables."
        )
        return

    deleted = await database.remove_admin(user_id)
    if deleted:
        await message.reply_text(f"✅ Dynamic admin `{user_id}` demoted.")
    else:
        await message.reply_text(
            f"❌ User `{user_id}` not found in dynamic admin list."
        )
