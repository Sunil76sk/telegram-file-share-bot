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
        if await database.is_admin(user_id, client):
            users_count = await database.get_users_count()
            files_count = await database.get_files_count()
            
            # Retrieve sub-bot ID if running as SaaS bot
            bot_id = None
            bot_me = client.me or await client.get_me()
            sub_bot = await database.sub_bots_col.find_one({"username": bot_me.username})
            if sub_bot:
                bot_id = bot_me.id
                
            shorteners = await database.get_shorteners(bot_id=bot_id)
            total_views = sum(sh.get("views", 0) for sh in shorteners)
            total_clicks = sum(sh.get("clicks", 0) for sh in shorteners)
            total_revenue = sum(sh.get("revenue", 0.0) for sh in shorteners)
            global_ctr = (total_clicks / total_views * 100) if total_views > 0 else 0.0

            stats_text = (
                "📊 **Bot Statistics**\n\n"
                f"👥 **Total Registered Users:** `{users_count}`\n"
                f"🔗 **Total Shared Links:** `{files_count}`\n\n"
                f"💰 **Monetization Overview:**\n"
                f"• Total Shortener Views: `{total_views}`\n"
                f"• Total Shortener Clicks: `{total_clicks}`\n"
                f"• Global CTR: `{global_ctr:.1f}%`\n"
                f"• Total Revenue: `${total_revenue:.4f}`"
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
    is_admin = await database.is_admin(user_id, client)

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

    # Monetization metrics
    m_views = file_doc.get("monetization_views", 0)
    m_clicks = file_doc.get("monetization_clicks", 0)
    m_rev = file_doc.get("monetization_revenue", 0.0)
    m_ctr = (m_clicks / m_views * 100) if m_views > 0 else 0.0

    stats_text = (
        f"📊 **Link Engagement Statistics**\n\n"
        f"🔗 **Link:** `{link_url}`\n"
        f"📅 **Created Date:** `{created_str}`\n"
        f"📦 **Total Files:** `{total_files}`\n\n"
        f"👀 **Total Views:** `{views}`\n"
        f"📥 **Total Downloads:** `{downloads}`\n"
        f"👥 **Unique Users:** `{unique_users_count}`\n\n"
        f"💰 **Monetization Metrics:**\n"
        f"• Shortener Views: `{m_views}`\n"
        f"• Shortener Clicks: `{m_clicks}`\n"
        f"• Click-Through Rate (CTR): `{m_ctr:.1f}%`\n"
        f"• Est. Revenue Generated: `${m_rev:.4f}`"
    )
    await message.reply_text(stats_text)
