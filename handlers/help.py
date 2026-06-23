from __future__ import annotations

import logging
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from bot import app
import database
from utils.helpers import banned_filter

logger = logging.getLogger(__name__)


HELP_SECTIONS = {
    "upload": {
        "title": "📂 Upload Files",
        "text": (
            "**How to upload files:**\n\n"
            "• Send any file directly to generate a shareable link\n"
            "• Use `/batch` to upload multiple files at once\n"
            "• Use `/done` when finished uploading\n\n"
            "**Supported formats:** Photos, Videos, Documents, Audio, GIFs"
        ),
    },
    "posts": {
        "title": "📝 Create Posts",
        "text": (
            "**Post Builder Studio:**\n\n"
            "• `/newpost` or `/postbuilder` — Launch the visual Post Builder Web App\n"
            "• Select target channel(s)\n"
            "• Upload poster (JPG, PNG, WEBP)\n"
            "• Auto-Fit Image: Choose ratios (1:1, 9:16, 16:9, 4:5) with custom Blur Background or Center Crop\n"
            "• Add movie details & description\n"
            "• Build up to 8 redirect click-tracking buttons (deep links / URLs)\n"
            "• Publish directly, schedule for later, or enable recurring Auto-Reposts"
        ),
    },
    "movie": {
        "title": "🎬 Movie Metadata",
        "text": (
            "**Movie Channel Features:**\n\n"
            "• Auto-fetch movie metadata from TMDB\n"
            "• Generate quality-specific download buttons (480P/720P/1080P)\n"
            "• Deep-link protected downloads\n"
            "• Premium/password/paid access controls"
        ),
    },
    "schedule": {
        "title": "📅 Scheduling",
        "text": (
            "**Post Scheduling:**\n\n"
            "• Schedule posts for future publication\n"
            "• Timezone-aware (set in /settings)\n"
            "• `/schedule` — View/manage scheduled posts\n"
            "• Free users: max 24 hours ahead\n"
            "• Premium: unlimited scheduling"
        ),
    },
    "repost": {
        "title": "🔄 Auto Repost",
        "text": (
            "**Auto Reposting (Premium):**\n\n"
            "• Auto-repost at set intervals\n"
            "• Supports: 30min, 1h, 3h, 6h, 12h, 24h, or custom\n"
            "• Old message deleted before repost\n"
            "• `/reposts` — View/manage active jobs\n"
            "• Persistent — survives bot restart"
        ),
    },
    "premium": {
        "title": "💎 Premium",
        "text": (
            "**Premium Membership:**\n\n"
            "• `/premium` — View plans and subscribe\n"
            "• **Silver:** Zero timers, ad bypass, silver link access\n"
            "• **Gold:** All silver perks + gold links + priority speed\n"
            "• Pay with Telegram Stars or UPI\n"
            "• Refer friends for free premium via `/referral`"
        ),
    },
    "store": {
        "title": "🛒 Store",
        "text": (
            "**Premium Store:**\n\n"
            "• `/store` — Browse digital products\n"
            "• Featured, Newest, Top Selling sections\n"
            "• Pay with Stars or UPI\n"
            "• Instant delivery after purchase\n"
            "• Duplicate purchase check prevents double-pay"
        ),
    },
    "referral": {
        "title": "👥 Referral",
        "text": (
            "**Referral Program:**\n\n"
            "• `/referral` — Get your referral link\n"
            "• Share with friends to earn points\n"
            "• 5 pts = 3 Days Premium\n"
            "• 10 pts = 7 Days Premium\n"
            "• 30 pts = 30 Days Premium"
        ),
    },
    "settings": {
        "title": "⚙ Settings",
        "text": (
            "**User Settings:**\n\n"
            "• `/settings` — Open settings menu\n"
            "• Language selection\n"
            "• Notification preferences\n"
            "• Timezone configuration\n"
            "• Channel management"
        ),
    },
}


@app.on_message(filters.command("help") & filters.private & ~banned_filter)
async def help_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    if await database.is_banned(user_id):
        return
    await _show_help_menu(message)


async def _show_help_menu(message: Message):
    buttons = []
    for key, section in HELP_SECTIONS.items():
        buttons.append(
            [InlineKeyboardButton(section["title"], callback_data=f"help_{key}")]
        )

    await message.reply_text(
        "❓ **Help Menu**\n\n" "Select a topic below to learn more:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@app.on_callback_query(filters.regex(r"^help_(.+)$"))
async def help_callback_handler(client: Client, callback_query: CallbackQuery):
    section_key = callback_query.matches[0].group(1)

    if section_key == "back":
        buttons = []
        for key, section in HELP_SECTIONS.items():
            buttons.append(
                [InlineKeyboardButton(section["title"], callback_data=f"help_{key}")]
            )
        await callback_query.answer()
        await callback_query.message.edit_text(
            "❓ **Help Menu**\n\nSelect a topic below to learn more:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    section = HELP_SECTIONS.get(section_key)
    if not section:
        await callback_query.answer("Section not found.", show_alert=True)
        return

    buttons = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 Back to Help Menu", callback_data="help_back")]]
    )

    await callback_query.answer()
    await callback_query.message.edit_text(
        f"{section['title']}\n\n{section['text']}",
        reply_markup=buttons,
    )
