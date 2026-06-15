from __future__ import annotations

import logging
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import MessageNotModified, FloodWait
from bot import app
import database
from utils.helpers import banned_filter
from utils.web_server import generate_short_link

logger = logging.getLogger(__name__)

# Helper to render the URL Buttons main menu text and keyboard
async def get_url_buttons_menu(draft: dict) -> tuple[str, InlineKeyboardMarkup]:
    buttons_list = draft.get("url_buttons", [])
    
    text = "🔗 **URL Buttons Editor**\n\n"
    if not buttons_list:
        text += "❌ No buttons added yet.\n"
    else:
        text += "━━━━━━━━━━━━━━━━━━━━━━\n"
        for idx, btn in enumerate(buttons_list, start=1):
            text += f"{idx}. {btn['text']}\n"
            text += f"   Original: {btn['url']}\n"
            if btn.get("shortened_url"):
                text += f"   Shortened: {btn['shortened_url']}\n"
            text += "\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━\n"
        
    kb_rows = []
    
    # Show Add button if under limit
    if len(buttons_list) < 8:
        kb_rows.append([InlineKeyboardButton("➕ Add Button", callback_data="url_btn_add")])
        
    if buttons_list:
        kb_rows.append([
            InlineKeyboardButton("✏️ Edit Button", callback_data="url_btn_edit_list"),
            InlineKeyboardButton("🗑 Delete Button", callback_data="url_btn_delete_list")
        ])
        
    kb_rows.append([InlineKeyboardButton("↩️ Back", callback_data="build_btn_back")])
    return text, InlineKeyboardMarkup(kb_rows)

# Callback: Open URL buttons menu
@app.on_callback_query(filters.regex(r"^builder_url_buttons$"))
async def builder_url_buttons_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    try:
        draft = await database.get_post_draft(user_id)
        if not draft:
            await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
            return
            
        if callback_query.from_user.id != draft.get("user_id"):
            await callback_query.answer("❌ Not your session", show_alert=True)
            return

        text, reply_markup = await get_url_buttons_menu(draft)
        await callback_query.message.edit_text(text, reply_markup=reply_markup)
        await callback_query.answer()
    except MessageNotModified:
        await callback_query.answer()
    except Exception as e:
        logger.error(f"Error in builder_url_buttons: {e}", exc_info=True)
        await callback_query.answer("⚠️ Error loading buttons menu", show_alert=True)

# Callback: Add Button clicked
@app.on_callback_query(filters.regex(r"^url_btn_add$"))
async def url_btn_add_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    try:
        draft = await database.get_post_draft(user_id)
        if not draft:
            await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
            return
            
        if callback_query.from_user.id != draft.get("user_id"):
            await callback_query.answer("❌ Not your session", show_alert=True)
            return
            
        if len(draft.get("url_buttons", [])) >= 8:
            await callback_query.answer("❌ Max 8 buttons allowed", show_alert=True)
            return

        draft["state"] = "awaiting_btn_text"
        await database.save_post_draft(user_id, draft)
        
        await callback_query.message.edit_text(
            "📝 **Add Button — Step 1**\n\n"
            "Enter the button text (label):\n"
            "Example: `📥 CLICK HERE TO DOWNLOAD 📥`\n\n"
            "Send /cancel to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="builder_url_buttons")]])
        )
        await callback_query.answer()
    except Exception as e:
        logger.error(f"Error in url_btn_add: {e}", exc_info=True)
        await callback_query.answer("⚠️ Error", show_alert=True)

# Message input handlers for adding buttons
@app.on_message(filters.private & ~banned_filter, group=12)
async def url_buttons_input_handler(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    
    if text.lower() == "/cancel":
        return  # Handled by post_builder cancel
        
    draft = await database.get_post_draft(user_id)
    if not draft:
        return
        
    state = draft.get("state")
    if not state or not state.startswith("awaiting_btn_"):
        return
        
    # State: awaiting_btn_text
    if state == "awaiting_btn_text":
        if not text:
            await message.reply_text("❌ Text cannot be empty. Enter button text:")
            return
        if len(text) > 64:
            await message.reply_text("❌ Button text too long. Max 64 characters. Try again:")
            return
            
        draft["pending_button"] = {"text": text}
        draft["state"] = "awaiting_btn_url"
        await database.save_post_draft(user_id, draft)
        
        await message.reply_text(
            "🔗 **Add Button — Step 2**\n\n"
            f"Button label: `{text}`\n\n"
            "Enter the URL for this button:\n"
            "Example: `https://google.com`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="builder_url_buttons")]])
        )
        message.stop_propagation()
        return

    # State: awaiting_btn_url
    elif state == "awaiting_btn_url":
        if not text.startswith("http"):
            await message.reply_text("❌ Invalid URL. Must start with http:// or https://. Try again:")
            return
        if len(text) > 512:
            await message.reply_text("❌ URL too long. Max 512 characters. Try again:")
            return
            
        pending = draft.get("pending_button", {})
        pending["url"] = text
        
        # Shorten URL
        short_url = None
        try:
            # Get best shortener
            shortener = await database.get_best_shortener()
            if shortener:
                short_url = await generate_short_link(shortener, text)
        except Exception as e:
            logger.error(f"Shortener failed: {e}")
            
        pending["shortened_url"] = short_url or text
        draft["pending_button"] = pending
        draft["state"] = "active" # Reset builder state
        await database.save_post_draft(user_id, draft)
        
        preview_text = (
            "🔍 **Button Preview & Confirmation**\n\n"
            f"**Button label:** {pending['text']}\n"
            f"**Original URL:** {pending['url']}\n"
            f"**Shortened URL:** {pending['shortened_url']}\n\n"
            "Do you want to save this button?"
        )
        
        await message.reply_text(
            preview_text,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Save", callback_data="url_btn_save_confirm"),
                    InlineKeyboardButton("❌ Cancel", callback_data="builder_url_buttons")
                ]
            ])
        )
        message.stop_propagation()
        return

    # State: awaiting_btn_edit_text_{index}
    elif state.startswith("awaiting_btn_edit_text_"):
        idx = int(state.split("_")[-1])
        if not text:
            await message.reply_text("❌ Text cannot be empty. Enter new text:")
            return
        if len(text) > 64:
            await message.reply_text("❌ Button text too long. Max 64 characters. Try again:")
            return
            
        buttons_list = draft.get("url_buttons", [])
        if idx < 0 or idx >= len(buttons_list):
            await message.reply_text("❌ Invalid index.")
            return
            
        buttons_list[idx]["text"] = text
        draft["url_buttons"] = buttons_list
        draft["state"] = "active"
        await database.save_post_draft(user_id, draft)
        
        await message.reply_text("✅ Button text updated!")
        
        # Display menu again
        menu_text, menu_markup = await get_url_buttons_menu(draft)
        await message.reply_text(menu_text, reply_markup=menu_markup)
        message.stop_propagation()
        return

    # State: awaiting_btn_edit_url_{index}
    elif state.startswith("awaiting_btn_edit_url_"):
        idx = int(state.split("_")[-1])
        if not text.startswith("http"):
            await message.reply_text("❌ Invalid URL. Must start with http:// or https://. Try again:")
            return
        if len(text) > 512:
            await message.reply_text("❌ URL too long. Max 512 characters. Try again:")
            return
            
        buttons_list = draft.get("url_buttons", [])
        if idx < 0 or idx >= len(buttons_list):
            await message.reply_text("❌ Invalid index.")
            return
            
        buttons_list[idx]["url"] = text
        
        # Re-shorten
        short_url = None
        try:
            shortener = await database.get_best_shortener()
            if shortener:
                short_url = await generate_short_link(shortener, text)
        except Exception as e:
            logger.error(f"Shortener failed: {e}")
            
        buttons_list[idx]["shortened_url"] = short_url or text
        draft["url_buttons"] = buttons_list
        draft["state"] = "active"
        await database.save_post_draft(user_id, draft)
        
        await message.reply_text("✅ Button URL updated and shortened!")
        
        # Display menu again
        menu_text, menu_markup = await get_url_buttons_menu(draft)
        await message.reply_text(menu_text, reply_markup=menu_markup)
        message.stop_propagation()
        return

# Callback: Save confirm
@app.on_callback_query(filters.regex(r"^url_btn_save_confirm$"))
async def url_btn_save_confirm_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    try:
        draft = await database.get_post_draft(user_id)
        if not draft:
            await callback_query.answer("❌ Session expired", show_alert=True)
            return
            
        if callback_query.from_user.id != draft.get("user_id"):
            await callback_query.answer("❌ Not your session", show_alert=True)
            return
            
        pending = draft.get("pending_button")
        if pending:
            buttons_list = draft.get("url_buttons", [])
            buttons_list.append(pending)
            draft["url_buttons"] = buttons_list
            draft.pop("pending_button", None)
            await database.save_post_draft(user_id, draft)
            await callback_query.answer("✅ Button added successfully!")
        else:
            await callback_query.answer("❌ No pending button found", show_alert=True)
            
        text, reply_markup = await get_url_buttons_menu(draft)
        await callback_query.message.edit_text(text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error in url_btn_save_confirm: {e}", exc_info=True)
        await callback_query.answer("⚠️ Error", show_alert=True)

# Callback: Show list of buttons to edit
@app.on_callback_query(filters.regex(r"^url_btn_edit_list$"))
async def url_btn_edit_list_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    try:
        draft = await database.get_post_draft(user_id)
        if not draft:
            await callback_query.answer("❌ Session expired", show_alert=True)
            return
            
        if callback_query.from_user.id != draft.get("user_id"):
            await callback_query.answer("❌ Not your session", show_alert=True)
            return
            
        buttons_list = draft.get("url_buttons", [])
        if not buttons_list:
            await callback_query.answer("❌ No buttons to edit", show_alert=True)
            return
            
        kb_rows = []
        for idx, btn in enumerate(buttons_list):
            kb_rows.append([InlineKeyboardButton(f"✏️ {btn['text']}", callback_data=f"url_btn_edit_{idx}")])
        kb_rows.append([InlineKeyboardButton("↩️ Back", callback_data="builder_url_buttons")])
        
        await callback_query.message.edit_text(
            "✏️ **Select button to edit:**",
            reply_markup=InlineKeyboardMarkup(kb_rows)
        )
        await callback_query.answer()
    except Exception as e:
        logger.error(f"Error in url_btn_edit_list: {e}", exc_info=True)
        await callback_query.answer("⚠️ Error", show_alert=True)

# Callback: Edit specific button
@app.on_callback_query(filters.regex(r"^url_btn_edit_(\d+)$"))
async def url_btn_edit_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    idx = int(callback_query.matches[0].group(1))
    try:
        draft = await database.get_post_draft(user_id)
        if not draft:
            await callback_query.answer("❌ Session expired", show_alert=True)
            return
            
        if callback_query.from_user.id != draft.get("user_id"):
            await callback_query.answer("❌ Not your session", show_alert=True)
            return
            
        buttons_list = draft.get("url_buttons", [])
        if idx < 0 or idx >= len(buttons_list):
            await callback_query.answer("❌ Invalid index", show_alert=True)
            return
            
        btn = buttons_list[idx]
        await callback_query.message.edit_text(
            f"✏️ **Editing Button #{idx+1}**\n\n"
            f"**Label:** `{btn['text']}`\n"
            f"**URL:** `{btn['url']}`\n\n"
            "Choose what you want to edit:",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📝 Edit Text", callback_data=f"url_btn_edit_txt_{idx}"),
                    InlineKeyboardButton("🔗 Edit URL", callback_data=f"url_btn_edit_url_{idx}")
                ],
                [InlineKeyboardButton("↩️ Cancel", callback_data="builder_url_buttons")]
            ])
        )
        await callback_query.answer()
    except Exception as e:
        logger.error(f"Error in url_btn_edit: {e}", exc_info=True)
        await callback_query.answer("⚠️ Error", show_alert=True)

# Callback: Edit Text of specific button
@app.on_callback_query(filters.regex(r"^url_btn_edit_txt_(\d+)$"))
async def url_btn_edit_txt_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    idx = int(callback_query.matches[0].group(1))
    try:
        draft = await database.get_post_draft(user_id)
        if not draft:
            await callback_query.answer("❌ Session expired", show_alert=True)
            return
            
        if callback_query.from_user.id != draft.get("user_id"):
            await callback_query.answer("❌ Not your session", show_alert=True)
            return
            
        draft["state"] = f"awaiting_btn_edit_text_{idx}"
        await database.save_post_draft(user_id, draft)
        
        await callback_query.message.edit_text(
            f"📝 **Edit Button #{idx+1} Text**\n\n"
            "Send the new text for this button:\n"
            "Send /cancel to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="builder_url_buttons")]])
        )
        await callback_query.answer()
    except Exception as e:
        logger.error(f"Error in url_btn_edit_txt: {e}", exc_info=True)
        await callback_query.answer("⚠️ Error", show_alert=True)

# Callback: Edit URL of specific button
@app.on_callback_query(filters.regex(r"^url_btn_edit_url_(\d+)$"))
async def url_btn_edit_url_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    idx = int(callback_query.matches[0].group(1))
    try:
        draft = await database.get_post_draft(user_id)
        if not draft:
            await callback_query.answer("❌ Session expired", show_alert=True)
            return
            
        if callback_query.from_user.id != draft.get("user_id"):
            await callback_query.answer("❌ Not your session", show_alert=True)
            return
            
        draft["state"] = f"awaiting_btn_edit_url_{idx}"
        await database.save_post_draft(user_id, draft)
        
        await callback_query.message.edit_text(
            f"🔗 **Edit Button #{idx+1} URL**\n\n"
            "Send the new URL for this button:\n"
            "Send /cancel to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="builder_url_buttons")]])
        )
        await callback_query.answer()
    except Exception as e:
        logger.error(f"Error in url_btn_edit_url: {e}", exc_info=True)
        await callback_query.answer("⚠️ Error", show_alert=True)

# Callback: Show list of buttons to delete
@app.on_callback_query(filters.regex(r"^url_btn_delete_list$"))
async def url_btn_delete_list_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    try:
        draft = await database.get_post_draft(user_id)
        if not draft:
            await callback_query.answer("❌ Session expired", show_alert=True)
            return
            
        if callback_query.from_user.id != draft.get("user_id"):
            await callback_query.answer("❌ Not your session", show_alert=True)
            return
            
        buttons_list = draft.get("url_buttons", [])
        if not buttons_list:
            await callback_query.answer("❌ No buttons to delete", show_alert=True)
            return
            
        kb_rows = []
        for idx, btn in enumerate(buttons_list):
            kb_rows.append([InlineKeyboardButton(f"🗑 {btn['text']}", callback_data=f"url_btn_delete_{idx}")])
        kb_rows.append([InlineKeyboardButton("↩️ Back", callback_data="builder_url_buttons")])
        
        await callback_query.message.edit_text(
            "🗑 **Select button to delete:**",
            reply_markup=InlineKeyboardMarkup(kb_rows)
        )
        await callback_query.answer()
    except Exception as e:
        logger.error(f"Error in url_btn_delete_list: {e}", exc_info=True)
        await callback_query.answer("⚠️ Error", show_alert=True)

# Callback: Delete specific button
@app.on_callback_query(filters.regex(r"^url_btn_delete_(\d+)$"))
async def url_btn_delete_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    idx = int(callback_query.matches[0].group(1))
    try:
        draft = await database.get_post_draft(user_id)
        if not draft:
            await callback_query.answer("❌ Session expired", show_alert=True)
            return
            
        if callback_query.from_user.id != draft.get("user_id"):
            await callback_query.answer("❌ Not your session", show_alert=True)
            return
            
        buttons_list = draft.get("url_buttons", [])
        if idx < 0 or idx >= len(buttons_list):
            await callback_query.answer("❌ Invalid index", show_alert=True)
            return
            
        removed = buttons_list.pop(idx)
        draft["url_buttons"] = buttons_list
        await database.save_post_draft(user_id, draft)
        await callback_query.answer(f"🗑 Deleted button: {removed['text']}")
        
        text, reply_markup = await get_url_buttons_menu(draft)
        await callback_query.message.edit_text(text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error in url_btn_delete: {e}", exc_info=True)
        await callback_query.answer("⚠️ Error", show_alert=True)
