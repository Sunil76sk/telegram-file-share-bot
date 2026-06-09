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
            await message.reply_text(
                "⚠️ Please reply to a message or provide text to broadcast.\nUsage: `/broadcast Hello Users` or reply to a post with `/broadcast`."
            )
            return
        broadcast_text = text_parts[1]

    all_users = await database.get_all_users()
    total_users = len(all_users)

    if total_users == 0:
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
        await message.reply_text("⚠️ Usage: `/ban <user_id>`")
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
        await message.reply_text("⚠️ Usage: `/unban <user_id>`")
        return

    try:
        user_id = int(args[1])
    except ValueError:
        await message.reply_text("❌ User ID must be an integer.")
        return

    await database.unban_user(user_id)
    await message.reply_text(f"✅ User `{user_id}` has been unbanned.")


@app.on_message(filters.command("add_channel") & filters.private & admin_filter)
async def add_channel_handler(client: Client, message: Message):
    args = message.text.split(None, 2)
    if len(args) < 3:
        await message.reply_text(
            "⚠️ Usage: `/add_channel <channel_id_or_username> <invite_link>`"
        )
        return

    chat_raw = args[1].strip()
    invite_link = args[2].strip()

    # Standardize chat ID/username
    if chat_raw.startswith("-") or chat_raw.isdigit():
        try:
            chat_id = int(chat_raw)
        except ValueError:
            await message.reply_text("❌ Invalid channel ID format.")
            return
    else:
        chat_id = chat_raw
        if not chat_id.startswith("@"):
            chat_id = f"@{chat_id}"

    try:
        # Check bot access and fetch title
        chat_info = await client.get_chat(chat_id)
        title = chat_info.title
    except Exception as e:
        await message.reply_text(
            f"❌ Failed to access channel info. Make sure the bot is an administrator in the channel.\nError: {e}"
        )
        return

    await database.add_force_sub_channel(chat_id, title, invite_link)
    await message.reply_text(
        f"✅ Added **{title}** (`{chat_id}`) to the force subscription channels list."
    )


@app.on_message(filters.command("del_channel") & filters.private & admin_filter)
async def del_channel_handler(client: Client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("⚠️ Usage: `/del_channel <channel_id_or_username>`")
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


@app.on_message(filters.command("channels") & filters.private & admin_filter)
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
        await message.reply_text("⚠️ Usage: `/add_admin <user_id>`")
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
        await message.reply_text("⚠️ Usage: `/del_admin <user_id>`")
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
