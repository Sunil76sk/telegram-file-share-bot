import logging
from pyrogram import Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import database
from utils.helpers import format_size

logger = logging.getLogger(__name__)


async def update_status_message(client: Client, user_id: int):
    """Retrieve state and send/update the single status message for the batch."""
    batch = await database.get_active_batch(user_id)
    if not batch:
        return

    files = batch.get("files", [])
    count = len(files)

    if count == 0:
        file_list_text = "*(No files added yet)*"
    else:
        file_list_text = ""
        for i in range(min(10, count)):
            file_obj = files[i]
            name = file_obj.get("file_name", "Unknown File")
            size = file_obj.get("file_size", 0)
            size_str = format_size(size)
            file_list_text += f"{i+1}. `{name}` ({size_str})\n"

        if count > 10:
            file_list_text += f"• ... and {count - 10} more files.\n"

    custom_token = batch.get("custom_token")
    custom_token_text = f"Custom Token: `{custom_token}`\n\n" if custom_token else ""

    status_text = (
        f"📦 **Batch Upload Session**\n\n"
        f"You have uploaded **{count}** file(s) to this batch.\n"
        f"{custom_token_text}"
        f"📂 **Files in this batch:**\n"
        f"{file_list_text}\n"
        f"💬 Send more files directly to this chat to add them, or use the buttons below to manage."
    )

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ Add More Files", callback_data="batch_add"),
                InlineKeyboardButton("❌ Close Batch", callback_data="batch_close"),
            ],
            [InlineKeyboardButton("🔗 Generate Link", callback_data="batch_generate")],
        ]
    )

    status_message_id = batch.get("batch_message_id")
    if status_message_id:
        try:
            await client.delete_messages(chat_id=user_id, message_ids=status_message_id)
        except Exception:
            pass

    try:
        new_msg = await client.send_message(
            chat_id=user_id, text=status_text, reply_markup=buttons
        )
        await database.update_batch_status_message(user_id, new_msg.id)
    except Exception as e:
        logger.error(f"Failed to send batch status message: {e}")


async def update_edit_ui(client: Client, user_id: int):
    """Retrieve active edit session and send/update the inline editor keyboard."""
    session = await database.get_edit_session(user_id)
    if not session:
        return

    token = session["token"]
    files = session.get("files", [])
    count = len(files)

    bot = client.me or await client.get_me()
    username = bot.username or "bot"

    status_text = (
        f"🛠 **Link Editor Mode**\n\n"
        f"Editing Link: https://t.me/{username}?start={token}\n"
        f"Total files: **{count}**\n\n"
        f"📥 **Upload new files** to this chat to merge/append them, or click `❌ Delete` below to remove individual files.\n\n"
        f"⚠️ **Note:** Changes will not be live until you click **Save Changes**."
    )

    buttons = []
    # Display up to 10 files with a delete button next to each
    for i in range(min(10, count)):
        file_obj = files[i]
        name = file_obj.get("file_name", "Unknown File")
        display_name = name[:20] + "..." if len(name) > 23 else name
        buttons.append(
            [
                InlineKeyboardButton(f"📄 {display_name}", callback_data="none"),
                InlineKeyboardButton("❌ Delete", callback_data=f"edit_del_{i}"),
            ]
        )

    if count > 10:
        buttons.append(
            [
                InlineKeyboardButton(
                    f"• ... and {count - 10} more files", callback_data="none"
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton("✅ Save Changes", callback_data="edit_save"),
            InlineKeyboardButton("🚪 Exit Edit Mode", callback_data="edit_exit"),
        ]
    )

    status_message_id = session.get("status_message_id")
    if status_message_id:
        try:
            await client.delete_messages(chat_id=user_id, message_ids=status_message_id)
        except Exception:
            pass

    try:
        new_msg = await client.send_message(
            chat_id=user_id,
            text=status_text,
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        await database.update_edit_session_status_message(user_id, new_msg.id)
    except Exception as e:
        logger.error(f"Failed to send edit UI message: {e}")
