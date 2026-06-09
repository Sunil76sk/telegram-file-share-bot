import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from bot import app
import database

logger = logging.getLogger(__name__)


@app.on_message(filters.command("stats") & filters.private)
async def stats_handler(client: Client, message: Message):
    args = message.text.split(None, 1)
    user_id = message.from_user.id

    if len(args) < 2:
        # Check if user is admin to see global stats
        if await database.is_admin(user_id):
            users_count = await database.get_users_count()
            files_count = await database.get_files_count()
            stats_text = (
                "📊 **Bot Statistics**\n\n"
                f"👥 **Total Registered Users:** `{users_count}`\n"
                f"🔗 **Total Shared Links:** `{files_count}`"
            )
            await message.reply_text(stats_text)
        else:
            await message.reply_text(
                "⚠️ **Usage:**\n"
                "`/stats <link_url_or_token>`\n\n"
                "Example: `/stats https://t.me/bot?start=abc123`"
            )
        return

    payload = args[1].strip()
    if "start=" in payload:
        token = payload.split("start=")[1].split("&")[0]
    else:
        token = payload

    file_doc = await database.get_file_link(token)
    if not file_doc:
        await message.reply_text("❌ No share link found with that token/URL.")
        return

    is_owner = file_doc.get("owner_id") == user_id
    is_admin = await database.is_admin(user_id)

    if not is_owner and not is_admin:
        await message.reply_text(
            "❌ You do not have permission to view statistics for this link."
        )
        return

    bot = client.me or await client.get_me()
    username = bot.username or "bot"
    link_url = f"https://t.me/{username}?start={token}"

    created_at = file_doc.get("created_at")
    if created_at:
        created_str = created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    else:
        created_str = "Unknown"

    views = file_doc.get("views", 0)
    downloads = file_doc.get("downloads", 0)
    unique_users_count = len(file_doc.get("unique_users", []))
    total_files = len(file_doc.get("files", []))

    stats_text = (
        f"📊 **Link Engagement Statistics**\n\n"
        f"🔗 **Link:** `{link_url}`\n"
        f"📅 **Created Date:** `{created_str}`\n"
        f"📦 **Total Files:** `{total_files}`\n\n"
        f"👀 **Total Views:** `{views}`\n"
        f"📥 **Total Downloads:** `{downloads}`\n"
        f"👥 **Unique Users:** `{unique_users_count}`"
    )
    await message.reply_text(stats_text)
