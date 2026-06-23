from __future__ import annotations

import logging
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
)
from bot import app
import config
import database

logger = logging.getLogger(__name__)


@app.on_message(filters.command(["postbuilder", "newpost"]) & filters.private)
async def postbuilder_command_handler(client: Client, message: Message):
    """Serve the Advanced Post Builder WebApp button to the user."""
    user_id = message.from_user.id
    if await database.is_banned(user_id):
        return

    base_url = config.REDIRECT_BASE_URL
    if not base_url:
        await message.reply_text(
            "❌ Web App Redirect Server is not configured. Please contact the administrator."
        )
        return

    if not base_url.startswith("http"):
        base_url = "https://" + base_url

    web_app_url = f"{base_url.rstrip('/')}/postbuilder?user_id={user_id}"

    text = (
        "🚀 **Advanced Post Builder Studio** 🚀\n\n"
        "Welcome to the premium Post Builder! You can now design beautiful channel posts "
        "with correct aspect ratios, automated blurring, and custom redirect click-tracking buttons.\n\n"
        "Click the button below to launch the interactive Post Builder Web App inside Telegram."
    )

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🖥 Open Post Builder Studio",
                    web_app=WebAppInfo(url=web_app_url),
                )
            ]
        ]
    )

    await message.reply_text(text, reply_markup=buttons)
