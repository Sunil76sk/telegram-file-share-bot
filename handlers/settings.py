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

TIMEZONES = {
    "Asia/Kolkata": "IST (UTC+5:30)",
    "Asia/Dubai": "GST (UTC+4)",
    "Asia/Singapore": "SGT (UTC+8)",
    "Europe/London": "GMT/BST",
    "America/New_York": "EST/EDT",
    "America/Los_Angeles": "PST/PDT",
}

async def re_shorten_tutorial_url():
    """Re-shorten the global tutorial URL using the current best shortener."""
    try:
        settings = await database.get_settings()
        long_url = settings.get("tutorial_video_url")
        if not long_url:
            return
            
        shortener = await database.get_best_shortener()
        short_url = None
        if shortener:
            from utils.web_server import generate_short_link
            short_url = await generate_short_link(shortener, long_url)
            
        # Update settings
        await database.update_settings({
            "tutorial_shortened_url": short_url or long_url
        })
        logger.info(f"Re-shortened tutorial URL successfully. Shortened: {short_url or long_url}")
    except Exception as e:
        logger.error(f"Failed to re-shorten tutorial URL: {e}", exc_info=True)

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
    user_tz = (user or {}).get("timezone", "Asia/Kolkata")
    tz_label = TIMEZONES.get(user_tz, user_tz)

    text = (
        "⚙️ **User Settings**\n\n"
        f"🌐 **Language:** `{lang.upper()}`\n"
        f"🌍 **Timezone:** `{tz_label}`\n"
        f"🔔 **Notifications:** {'Enabled' if notif_prefs else 'Disabled'}\n"
        f"⭐ **Premium:** {'Yes' if is_premium else 'No'}\n"
        f"💰 **Points:** `{points}`\n\n"
        "Choose a setting to configure:"
    )

    kb_rows = [
        [InlineKeyboardButton("🌐 Language", callback_data="settings_lang")],
        [InlineKeyboardButton("🌍 Timezone", callback_data="settings_tz")],
        [InlineKeyboardButton(f"🔔 Notifications: {'✅' if notif_prefs else '❌'}", callback_data="settings_notif")],
        [InlineKeyboardButton("🎫 Premium / Subscription", callback_data="premium_menu_home")],
        [InlineKeyboardButton("👥 Referral Program", callback_data="settings_referral")],
        [InlineKeyboardButton("📋 My Channels", callback_data="settings_channels")],
        [InlineKeyboardButton("🔄 Auto Delete Settings", callback_data="settings_autodel")]
    ]

    # Add Admin Settings button if user is admin
    if await database.is_admin(user_id, client):
        kb_rows.append([InlineKeyboardButton("🛠 Global Admin Settings", callback_data="settings_admin_menu")])

    await msg.reply_text(text, reply_markup=InlineKeyboardMarkup(kb_rows))

async def show_admin_settings_menu(client: Client, msg: Message, user_id: int):
    settings = await database.get_settings()
    
    masked_key = "Set" if settings.get("tmdb_api_key") else "Not Set"
    append_status = "Enabled" if settings.get("tutorial_show_on_post") else "Disabled"
    
    text = (
        "🛠 **Global Bot Admin Settings**\n\n"
        f"🔑 **TMDB API Key:** `{masked_key}`\n"
        f"🌐 **TMDB Language:** `{settings.get('tmdb_default_language', 'en')}`\n"
        f"📹 **Tutorial Video URL:** `{settings.get('tutorial_video_url') or 'Not Set'}`\n"
        f"🔗 **Tutorial Shortened URL:** `{settings.get('tutorial_shortened_url') or 'Not Set'}`\n"
        f"🎥 **Auto-Append Tutorial:** `{append_status}`\n\n"
        "Configure bot-wide search and posting settings:"
    )
    
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔑 Update TMDB Key", callback_data="admin_set_tmdb_key"),
            InlineKeyboardButton("🌐 Default Lang", callback_data="admin_set_tmdb_lang")
        ],
        [
            InlineKeyboardButton("📹 Tutorial URL", callback_data="admin_set_tutorial_url"),
            InlineKeyboardButton(f"🎥 Append: {append_status}", callback_data="admin_toggle_tutorial_append")
        ],
        [
            InlineKeyboardButton("🔙 Back to User Settings", callback_data="settings_menu")
        ]
    ])
    
    if isinstance(msg, CallbackQuery):
        await msg.message.edit_text(text, reply_markup=kb)
    else:
        await msg.reply_text(text, reply_markup=kb)

@app.on_callback_query(filters.regex(r"^settings_(lang|tz|notif|referral|channels|autodel|menu|admin_menu)$"))
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

    elif action == "tz":
        await callback_query.answer()
        buttons = []
        for tz, label in TIMEZONES.items():
            buttons.append([InlineKeyboardButton(label, callback_data=f"settz_{tz}")])
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="settings_menu")])
        await callback_query.message.edit_text(
            "🌍 **Select Your Timezone**\n\n"
            "This is used for scheduling posts at your local time.",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    elif action == "notif":
        await callback_query.answer()
        prefs = await get_user_notification_preferences(user_id)
        new_prefs = not prefs
        await set_user_notification_preference(user_id, "all", new_prefs)
        await callback_query.message.delete()
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
        await callback_query.message.delete()
        await show_settings_menu(client, callback_query.message, user_id)
        
    elif action == "admin_menu":
        if not await database.is_admin(user_id, client):
            await callback_query.answer("❌ Permission Denied", show_alert=True)
            return
        await callback_query.answer()
        await show_admin_settings_menu(client, callback_query, user_id)

# Callback Handlers for Admin Settings Settings
@app.on_callback_query(filters.regex(r"^admin_(set_tmdb_key|set_tmdb_lang|set_tutorial_url|toggle_tutorial_append)$"))
async def admin_settings_callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    action = callback_query.matches[0].group(1)
    
    if not await database.is_admin(user_id, client):
        await callback_query.answer("❌ Permission Denied", show_alert=True)
        return
        
    await callback_query.answer()
    
    if action == "set_tmdb_key":
        await database.users_col.update_one({"_id": user_id}, {"$set": {"state": "awaiting_tmdb_api_key"}})
        await callback_query.message.edit_text(
            "🔑 **Update TMDB API Key**\n\n"
            "Please send the new TMDB API Key now:\n"
            "Send /cancel to abort."
        )
        
    elif action == "set_tmdb_lang":
        await database.users_col.update_one({"_id": user_id}, {"$set": {"state": "awaiting_tmdb_default_language"}})
        await callback_query.message.edit_text(
            "🌐 **Set Default TMDB Language**\n\n"
            "Please send the default language code (e.g. `en`, `es`, `hi`, `fr`):\n"
            "Send /cancel to abort."
        )
        
    elif action == "set_tutorial_url":
        await database.users_col.update_one({"_id": user_id}, {"$set": {"state": "awaiting_tutorial_video_url"}})
        await callback_query.message.edit_text(
            "📹 **Update Tutorial Video URL**\n\n"
            "Please send the direct link to the tutorial video:\n"
            "Send /cancel to abort."
        )
        
    elif action == "toggle_tutorial_append":
        settings = await database.get_settings()
        new_val = not settings.get("tutorial_show_on_post", False)
        await database.update_settings({"tutorial_show_on_post": new_val})
        await show_admin_settings_menu(client, callback_query, user_id)

@app.on_callback_query(filters.regex(r"^settz_(.+)$"))
async def set_timezone_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    tz = callback_query.matches[0].group(1)
    if tz not in TIMEZONES:
        await callback_query.answer("Invalid timezone.", show_alert=True)
        return
    await database.users_col.update_one(
        {"_id": user_id},
        {"$set": {"timezone": tz}},
        upsert=True,
    )
    await callback_query.answer(f"Timezone set to {TIMEZONES[tz]}!", show_alert=True)
    await callback_query.message.delete()
    await show_settings_menu(client, callback_query.message, user_id)

@app.on_callback_query(filters.regex(r"^setlang_([a-z]{2}(_[A-Z]{2})?)$"))
async def set_lang_callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    lang_code = callback_query.matches[0].group(1)
    await callback_query.answer(f"Language set to {lang_code.upper()}!", show_alert=True)
    await set_user_lang(user_id, lang_code)
    await callback_query.message.delete()
    await show_settings_menu(client, callback_query.message, user_id)

# Message input handler for admin settings states
@app.on_message(filters.private & ~banned_filter, group=7)
async def settings_input_handler(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    
    user_doc = await database.get_user(user_id)
    if not user_doc:
        return
        
    state = user_doc.get("state")
    if not state or state not in ["awaiting_tmdb_api_key", "awaiting_tmdb_default_language", "awaiting_tutorial_video_url"]:
        return
        
    if not await database.is_admin(user_id, client):
        await database.users_col.update_one({"_id": user_id}, {"$unset": {"state": ""}})
        return

    if text.lower() == "/cancel":
        await database.users_col.update_one({"_id": user_id}, {"$unset": {"state": ""}})
        await message.reply_text("❌ Configuration cancelled.")
        await show_admin_settings_menu(client, message, user_id)
        message.stop_propagation()
        return

    if state == "awaiting_tmdb_api_key":
        if not text:
            await message.reply_text("❌ Key cannot be empty. Send TMDB API Key:")
            message.stop_propagation()
            return
            
        await database.update_settings({"tmdb_api_key": text})
        await database.users_col.update_one({"_id": user_id}, {"$unset": {"state": ""}})
        await message.reply_text("✅ TMDB API Key updated successfully!")
        await show_admin_settings_menu(client, message, user_id)
        message.stop_propagation()
        return

    elif state == "awaiting_tmdb_default_language":
        if not text or len(text) > 5:
            await message.reply_text("❌ Invalid language code. E.g. en, es, hi. Try again:")
            message.stop_propagation()
            return
            
        await database.update_settings({"tmdb_default_language": text.lower()})
        await database.users_col.update_one({"_id": user_id}, {"$unset": {"state": ""}})
        await message.reply_text(f"✅ TMDB Default Language set to `{text.lower()}` successfully!")
        await show_admin_settings_menu(client, message, user_id)
        message.stop_propagation()
        return

    elif state == "awaiting_tutorial_video_url":
        if not text.startswith("http"):
            await message.reply_text("❌ Invalid URL. Must start with http:// or https://. Try again:")
            message.stop_propagation()
            return
            
        # Try to shorten the URL
        shortener = await database.get_best_shortener()
        short_url = None
        if shortener:
            try:
                from utils.web_server import generate_short_link
                short_url = await generate_short_link(shortener, text)
            except Exception as e:
                logger.error(f"Failed to shorten tutorial URL on input: {e}")
                
        await database.update_settings({
            "tutorial_video_url": text,
            "tutorial_shortened_url": short_url or text
        })
        await database.users_col.update_one({"_id": user_id}, {"$unset": {"state": ""}})
        await message.reply_text("✅ Tutorial Video URL updated and shortened successfully!")
        await show_admin_settings_menu(client, message, user_id)
        message.stop_propagation()
        return
