from __future__ import annotations

import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from bot import app
import database
from utils.helpers import banned_filter

logger = logging.getLogger(__name__)


# ─── LISTING CHANNELS FOR STATS ──────────────────────────────────────

@app.on_message(filters.command("channel_stats") & filters.private & ~banned_filter)
async def channel_stats_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    channels = await database.get_creator_channels(user_id)
    if not channels:
        await message.reply_text("❌ You don't have any channels added. Use `/add_channel` first.")
        return

    text = "📊 **Creator Channel Analytics Dashboard**\n\nSelect a channel below to view stats:"
    buttons = []
    for chan in channels:
        buttons.append([InlineKeyboardButton(chan["title"], callback_data=f"stat_view_{chan['_id']}")])

    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


# ─── VIEWING CHANNEL STATS ───────────────────────────────────────────

@app.on_callback_query(filters.regex(r"^stat_view_(.+)"))
async def stat_view_callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    channel_id = callback_query.matches[0].group(1)
    
    try:
        channel_id_val = int(channel_id)
    except ValueError:
        channel_id_val = channel_id
        
    channel = await database.get_channel_by_id(channel_id_val)
    if not channel or channel.get("user_id") != user_id:
        await callback_query.answer("❌ Channel not found or access denied.", show_alert=True)
        return

    await callback_query.answer()
    
    # Fetch stats logs for past 30 days
    logs = await database.get_channel_stats(channel_id_val, days=30)
    
    total_publishes = 0
    total_reposts = 0
    total_scheduled = 0
    total_clicks = 0
    
    for log in logs:
        total_publishes += log.get("publishes", 0)
        total_reposts += log.get("reposts", 0)
        total_scheduled += log.get("scheduled_posts", 0)
        total_clicks += log.get("button_clicks", 0)

    # Calculate click CTR if we track views (using views from static stats or estimates)
    text = (
        f"📊 **Analytics Report: {channel.get('title')}**\n"
        f"ID: `{channel['_id']}`\n"
        f"Period: **Past 30 Days**\n\n"
        f"📝 **Direct Posts Published:** `{total_publishes}`\n"
        f"📅 **Posts Scheduled:** `{total_scheduled}`\n"
        f"🔄 **Auto-Reposts Executed:** `{total_reposts}`\n"
        f"🔗 **URL Button Clicks:** `{total_clicks}`\n\n"
        f"📈 **Engagement Snapshot:**\n"
        f"• Total Actions: `{total_publishes + total_scheduled + total_reposts}`\n"
        f"• Avg Clicks/Action: `{total_clicks / (total_publishes or 1):.2f}`"
    )

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data=f"stat_view_{channel_id}"),
                InlineKeyboardButton("🔙 Dashboard", callback_data="stat_back"),
            ]
        ]
    )
    await callback_query.message.edit_text(text, reply_markup=buttons)


@app.on_callback_query(filters.regex(r"^stat_back$"))
async def stat_back_callback_handler(client: Client, callback_query: CallbackQuery):
    await callback_query.message.delete()
    message = callback_query.message
    message.from_user = callback_query.from_user
    await channel_stats_command_handler(client, message)
