from __future__ import annotations

import logging

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from bot import app
import database
from utils.helpers import banned_filter
from utils.notification_center import (
    get_user_notification_preferences,
    set_user_notification_preference,
)
from utils.multi_lang import get_supported_languages, set_user_lang, get_user_lang

logger = logging.getLogger(__name__)


@app.on_message(filters.command("settings") & filters.private & ~banned_filter)
async def settings_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    await show_settings_menu(client, message, user_id)


async def show_settings_menu(client: Client, msg: Message, user_id: int):
    user = await database.get_user(user_id)
    notif_prefs = await get_user_notification_preferences(user_id)
    lang = await get_user_lang(user_id) or "en"
    is_premium = await database.is_user_premium(user_id)
    points = await database.get_user_points(user_id)

    text = (
        "⚙️ **User Settings**\n\n"
        f"🌐 **Language:** `{lang.upper()}`\n"
        f"🔔 **Notifications:** {'Enabled' if notif_prefs else 'Disabled'}\n"
        f"⭐ **Premium:** {'Yes' if is_premium else 'No'}\n"
        f"💰 **Points:** `{points}`\n\n"
        "Choose a setting to configure:"
    )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Language", callback_data="settings_lang")],
        [InlineKeyboardButton(f"🔔 Notifications: {'✅' if notif_prefs else '❌'}", callback_data="settings_notif")],
        [InlineKeyboardButton("🎫 Premium / Subscription", callback_data="premium_menu_home")],
        [InlineKeyboardButton("👥 Referral Program", callback_data="settings_referral")],
        [InlineKeyboardButton("📋 My Channels", callback_data="settings_channels")],
        [InlineKeyboardButton("🔄 Auto Delete Settings", callback_data="settings_autodel")],
    ])

    await msg.reply_text(text, reply_markup=buttons)


@app.on_callback_query(filters.regex(r"^settings_(lang|notif|referral|channels|autodel|menu)"))
async def settings_callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    action = callback_query.matches[0].group(1)

    if action == "lang":
        await callback_query.answer()
        langs = get_supported_languages()
        kb = []
        for code, name in langs.items():
            kb.append([InlineKeyboardButton(f"{name}", callback_data=f"setlang_{code}")])
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="settings_menu")])
        await callback_query.message.edit_text(
            "🌐 **Select Language**",
            reply_markup=InlineKeyboardMarkup(kb),
        )

    elif action == "notif":
        await callback_query.answer()
        prefs = await get_user_notification_preferences(user_id)
        new_prefs = not prefs
        await set_user_notification_preference(user_id, "all", new_prefs)
        await show_settings_menu(client, callback_query.message, user_id)

    elif action == "referral":
        await callback_query.answer()
        from handlers.referral import referral_command_handler
        await referral_command_handler(client, callback_query.message)
        await callback_query.message.delete()

    elif action == "channels":
        await callback_query.answer()
        from handlers.broadcast import my_channels_handler
        await my_channels_handler(client, callback_query.message)
        await callback_query.message.delete()

    elif action == "autodel":
        await callback_query.answer()
        await callback_query.message.edit_text(
            "🔄 **Auto Delete Settings**\n\n"
            "Auto-delete is configured via the `/start` link. "
            "Files are automatically deleted after the configured `AUTO_DELETE_SECONDS`.\n\n"
            "Contact the bot admin to change this setting.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="settings_menu")]
            ]),
        )

    elif action == "menu":
        await callback_query.answer()
        await show_settings_menu(client, callback_query.message, user_id)


@app.on_callback_query(filters.regex(r"^setlang_([a-z]{2}(_[A-Z]{2})?)$"))
async def set_lang_callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    lang_code = callback_query.matches[0].group(1)
    await callback_query.answer(f"Language set to {lang_code.upper()}!", show_alert=True)
    await set_user_lang(user_id, lang_code)
    await show_settings_menu(client, callback_query.message, user_id)
