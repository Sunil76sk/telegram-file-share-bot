import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from bot import app
import database
from utils.helpers import admin_filter, banned_filter
from utils.locks import user_locks
from utils.buttons import update_edit_ui

logger = logging.getLogger(__name__)


@app.on_message(filters.command("editlink") & filters.private & ~banned_filter)
async def editlink_cmd_handler(client: Client, message: Message):
    user_id = message.from_user.id
    args = message.text.split(None, 1)

    if len(args) < 2:
        await message.reply_text(
            "⚠️ **Usage:**\n"
            "`/editlink <link_url_or_token>`\n\n"
            "Example: `/editlink https://t.me/bot?start=abc123`"
        )
        return

    payload = args[1].strip()
    if "start=" in payload:
        token = payload.split("start=")[1].split("&")[0]
    else:
        token = payload

    file_doc = await database.get_file_link(token)
    if not file_doc:
        await message.reply_text("❌ No share link found with that token.")
        return

    is_owner = file_doc.get("owner_id") == user_id
    is_admin = await database.is_admin(user_id)
    if not is_owner and not is_admin:
        await message.reply_text("❌ You do not have permission to edit this link.")
        return

    async with user_locks[user_id]:
        # Discard any active batch session to prevent collision
        await database.delete_batch(user_id)

        files = file_doc.get("files", [])

        await database.create_edit_session(
            user_id=user_id,
            token=token,
            files=files,
        )

        await update_edit_ui(client, user_id)


@app.on_message(filters.command("edit_link") & filters.private & admin_filter)
async def edit_link_handler(client: Client, message: Message):
    user_id = message.from_user.id
    async with user_locks[user_id]:
        args = message.text.split()
        if len(args) < 2:
            await message.reply_text(
                "🛠 **Link Editor**\n\n"
                "Usage:\n"
                "- View details: `/edit_link <token>`\n"
                "- Append files: `/edit_link <token> add`\n"
                "- Delete index: `/edit_link <token> del <index>`\n"
                "- Delete link: `/edit_link <token> delete`"
            )
            return

        token = args[1].strip()
        if "start=" in token:
            token = token.split("start=")[1].split("&")[0]
        file_doc = await database.get_file_link(token)

        if not file_doc:
            await message.reply_text(f"❌ Share link with token `{token}` not found.")
            return

        # Handle simple view
        if len(args) == 2:
            files = file_doc.get("files", [])

            bot = client.me or await client.get_me()
            username = bot.username or "bot"
            link = f"https://t.me/{username}?start={token}"

            text = (
                f"🔗 **Link Info (`{token}`)**\n"
                f"URL: `{link}`\n"
                f"👁 **Views/Downloads:** `{file_doc.get('views', 0)}`\n"
                f"📦 **Total Files:** `{len(files)}`\n\n"
                f"**File List:**\n"
            )

            for index, file_obj in enumerate(files, start=1):
                name = file_obj.get("file_name", "Unknown File")
                size = file_obj.get("file_size", 0)
                size_mb = round(size / (1024 * 1024), 2)
                media_type = file_obj.get("media_type", "unknown")
                text += f"`{index}.` **{name}** ({size_mb} MB) - _type: {media_type}_\n"

            text += (
                "\n🛠 **Actions:**\n"
                f"• Append file: `/edit_link {token} add`\n"
                f"• Delete file at index: `/edit_link {token} del <index>`\n"
                f"• Delete whole link: `/edit_link {token} delete`"
            )
            await message.reply_text(text)
            return

        action = args[2].lower().strip()

        # Handle complete delete
        if action == "delete":
            deleted = await database.delete_file_link(token)
            if deleted:
                await message.reply_text(
                    f"🗑 **Link `{token}` has been permanently deleted.**"
                )
            else:
                await message.reply_text("❌ Failed to delete the link.")
            return

        # Handle append request (add)
        if action == "add":
            admin_id = message.from_user.id
            files = file_doc.get("files", [])

            await database.create_edit_session(
                user_id=admin_id,
                token=token,
                files=files,
            )
            await message.reply_text(
                f"📥 **Link Append Active for `{token}`!**\n\n"
                "Send the next file you want to add. It will be added to the end of this permanent sharing link.\n"
                "Any file type is supported."
            )
            return

        # Handle delete single file inside batch (del <index>)
        if action == "del":
            if len(args) < 4:
                await message.reply_text(f"⚠️ Usage: `/edit_link {token} del <index>`")
                return

            try:
                index = int(args[3]) - 1  # 0-indexed internally
            except ValueError:
                await message.reply_text("❌ Index must be a valid number.")
                return

            files = file_doc.get("files", [])

            if index < 0 or index >= len(files):
                await message.reply_text(
                    f"❌ Invalid file index. Must be between 1 and {len(files)}."
                )
                return

            # Remove item at index
            removed_file = files.pop(index)
            removed_name = removed_file.get("file_name", "Unknown File")

            if not files:
                # If no files remain, delete the link
                await database.delete_file_link(token)
                await message.reply_text(
                    f"🗑 Removed `{removed_name}`. No files left, so the permanent link `{token}` has been deleted entirely."
                )
                return

            await database.update_file_link(
                token=token,
                files=files,
            )

            await message.reply_text(
                f"✅ **Removed file:** `{removed_name}`\n"
                f"📦 **Total Files remaining:** {len(files)}\n"
                f"🔗 Link remains permanent: `/edit_link {token}`"
            )
            return

        await message.reply_text(
            f"❌ Unknown action `{action}`. Run `/edit_link {token}` for instructions."
        )
