from __future__ import annotations

import logging
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot import app
import database

logger = logging.getLogger(__name__)

@app.on_callback_query(filters.regex(r"^react_click_(.+)"))
async def react_click_callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    emoji = callback_query.matches[0].group(1)
    
    # Check if the message is in a channel or private chat
    message = callback_query.message
    if not message:
        await callback_query.answer("❌ Cannot process reaction.", show_alert=True)
        return
        
    chat_id = message.chat.id
    message_id = message.id
    
    # Toggle reaction in DB and get updated counts
    try:
        counts = await database.toggle_reaction(chat_id, message_id, user_id, emoji)
    except Exception as e:
        logger.error(f"Error toggling reaction: {e}")
        await callback_query.answer("❌ Error registering reaction.", show_alert=True)
        return
        
    # Rebuild keyboard from existing markup
    current_markup = message.reply_markup
    if not current_markup:
        await callback_query.answer()
        return
        
    new_keyboard = []
    for row in current_markup.inline_keyboard:
        new_row = []
        for btn in row:
            if btn.callback_data and btn.callback_data.startswith("react_click_"):
                btn_emoji = btn.callback_data.replace("react_click_", "", 1)
                count = counts.get(btn_emoji, 0)
                btn_text = f"{btn_emoji} {count}" if count > 0 else btn_emoji
                new_row.append(InlineKeyboardButton(text=btn_text, callback_data=btn.callback_data))
            else:
                # Copy existing button (e.g. URL button or Comments button)
                new_row.append(InlineKeyboardButton(text=btn.text, url=btn.url, callback_data=btn.callback_data))
        new_keyboard.append(new_row)
        
    try:
        await client.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=InlineKeyboardMarkup(new_keyboard)
        )
        await callback_query.answer("✅ Reaction updated!")
    except Exception as e:
        logger.error(f"Error editing reply markup for reactions: {e}")
        await callback_query.answer()
