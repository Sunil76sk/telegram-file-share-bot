from __future__ import annotations

import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from bot import app
import database
from utils.helpers import banned_filter

logger = logging.getLogger(__name__)

# Temporary dict to hold template creation state in memory since it's simple
# Format: {user_id: {"name": ..., "type": ...}}
template_creation_drafts = {}


# ─── LISTING TEMPLATES ────────────────────────────────────────────────

@app.on_message(filters.command("templates") & filters.private & ~banned_filter)
async def templates_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    is_premium = await database.is_user_premium(user_id)
    if not is_premium:
        await message.reply_text(
            "❌ **Post Templates are a Premium Feature!**\n\n"
            "Please upgrade to Premium using `/premium` to save and load post templates."
        )
        return

    templates = await database.get_user_templates(user_id)
    
    text = "📋 **Post Templates Studio**\n\n"
    buttons = []
    
    if templates:
        text += "Your saved templates:\n"
        for index, temp in enumerate(templates, start=1):
            text += f"{index}. **{temp['name']}** ({temp['type'].capitalize()})\n"
            buttons.append([
                InlineKeyboardButton(f"📂 Load: {temp['name']}", callback_data=f"temp_load_{temp['_id']}"),
                InlineKeyboardButton(f"🗑 Delete", callback_data=f"temp_del_{temp['_id']}")
            ])
    else:
        text += "You don't have any templates saved yet. Create templates to speed up your post formatting!"

    buttons.append([InlineKeyboardButton("➕ Create Template", callback_data="temp_create_start")])
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


# ─── LOAD/DELETE TEMPLATE FOR POST BUILDER ───────────────────────────

@app.on_callback_query(filters.regex(r"^temp_load_(.+)"))
async def load_template_callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    temp_id = callback_query.matches[0].group(1)
    
    template = await database.get_template(temp_id)
    if not template or template.get("user_id") != user_id:
        await callback_query.answer("❌ Template not found.", show_alert=True)
        return
        
    # Get active draft
    draft = await database.get_post_draft(user_id)
    if not draft:
        # Load creator channels
        channels = await database.get_creator_channels(user_id)
        if not channels:
            await callback_query.answer("❌ No channels found! Add a channel first using /add_channel.", show_alert=True)
            return

        # Save template ID in user state to apply after channel selection
        await database.users_col.update_one(
            {"_id": user_id},
            {"$set": {"state": f"temp_apply_{temp_id}"}}
        )

        # Ask user to choose channel
        buttons = []
        for chan in channels:
            if chan.get("service_enabled", True):
                buttons.append([
                    InlineKeyboardButton(
                        chan.get("channel_title") or chan.get("title") or str(chan["_id"]),
                        callback_data=f"temp_select_{chan['_id']}"
                    )
                ])

        if not buttons:
            await callback_query.answer("❌ Please enable at least one channel in settings first.", show_alert=True)
            return

        await callback_query.message.edit_text(
            "📝 **Choose Target Channel**\n\n"
            "Please select the target channel to apply this template to:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return
        
    # Apply template to draft
    draft["caption"] = template.get("caption", "")
    draft["custom_buttons"] = template.get("buttons", [])
    await database.save_post_draft(user_id, draft)
    
    await callback_query.answer("✅ Template loaded into your draft!", show_alert=True)
    await callback_query.message.delete()
    from handlers.post_builder import show_builder_menu
    await show_builder_menu(client, callback_query.message, user_id, draft)


@app.on_callback_query(filters.regex(r"^temp_select_(.+)"))
async def temp_select_callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    channel_id = callback_query.matches[0].group(1)
    try:
        channel_id_val = int(channel_id)
    except ValueError:
        channel_id_val = channel_id
        
    user_doc = await database.get_user(user_id)
    state = user_doc.get("state") if user_doc else None
    if not state or not state.startswith("temp_apply_"):
        await callback_query.answer("❌ Selection expired. Please start over.", show_alert=True)
        return
        
    temp_id = state.replace("temp_apply_", "", 1)
    template = await database.get_template(temp_id)
    if not template:
        await callback_query.answer("❌ Template not found.", show_alert=True)
        return
        
    # Clear state
    await database.users_col.update_one(
        {"_id": user_id},
        {"$unset": {"state": ""}}
    )
    
    import datetime
    # Create draft automatically
    draft = {
        "draft_id": str(user_id),
        "user_id": user_id,
        "channel_id": channel_id_val,
        "media_type": "text",
        "file_id": None,
        "media_files": [],
        "caption": template.get("caption", ""),
        "custom_buttons": template.get("buttons", []),
        "reactions": [],
        "reactions_enabled": False,
        "comments_enabled": False,
        "caption_above": False,
        "pin_message": False,
        "poster_media": {"type": None, "file_id": None},
        "download_files": [],
        "layout_type": "layout_a",
        "timezone": "Asia/Kolkata",
        "schedule_enabled": False,
        "scheduled_time": None,
        "auto_repost_enabled": False,
        "repost_interval": None,
        "delete_gap": None,
        "state": "active",
        "created_at": datetime.datetime.now(datetime.timezone.utc),
    }
    await database.save_post_draft(user_id, draft)
    
    await callback_query.answer("✅ Template loaded into your draft!", show_alert=True)
    await callback_query.message.delete()
    from handlers.post_builder import show_builder_menu
    await show_builder_menu(client, callback_query.message, user_id, draft)


@app.on_callback_query(filters.regex(r"^temp_del_(.+)"))
async def delete_template_callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    temp_id = callback_query.matches[0].group(1)
    
    deleted = await database.delete_template(temp_id)
    if deleted:
        await callback_query.answer("🗑 Template deleted.", show_alert=True)
        try:
            await callback_query.message.delete()
        except Exception:
            pass
        # Refresh templates list
        message = callback_query.message
        message.from_user = callback_query.from_user
        await templates_command_handler(client, message)
    else:
        await callback_query.answer("❌ Failed to delete template.", show_alert=True)


# ─── CREATING NEW TEMPLATES ──────────────────────────────────────────

@app.on_callback_query(filters.regex(r"^temp_create_start$"))
async def create_template_callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    await callback_query.answer()
    
    # Save transient state in database user doc
    await database.users_col.update_one({"_id": user_id}, {"$set": {"state": "awaiting_template_name"}})
    await callback_query.message.edit_text(
        "➕ **Create Template**\n\n"
        "Please enter a name for your template (e.g. `Movie Review` or `Sponsor Promo`):"
    )


@app.on_message(filters.private & ~banned_filter, group=7)
async def template_creation_input_handler(client: Client, message: Message):
    user_id = message.from_user.id
    user_doc = await database.get_user(user_id)
    if not user_doc or user_doc.get("state") not in ["awaiting_template_name", "awaiting_template_content"]:
        return

    state = user_doc["state"]
    text = message.text.strip() if message.text else ""

    if text.lower() == "/cancel":
        await database.users_col.update_one({"_id": user_id}, {"$unset": {"state": ""}})
        if user_id in template_creation_drafts:
            del template_creation_drafts[user_id]
        await message.reply_text("❌ Template creation cancelled.")
        message.stop_propagation()
        return

    # 1. Capture Template Name
    if state == "awaiting_template_name":
        template_creation_drafts[user_id] = {"name": text}
        
        # Ask for Template Type
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎬 Movie Review", callback_data="temp_type_movie"),
                InlineKeyboardButton("💸 Affiliate Promotion", callback_data="temp_type_affiliate"),
            ],
            [
                InlineKeyboardButton("🛍 Store Promotion", callback_data="temp_type_store"),
                InlineKeyboardButton("🌟 Premium Promotion", callback_data="temp_type_premium"),
            ],
            [
                InlineKeyboardButton("👥 Referral Promotion", callback_data="temp_type_referral"),
                InlineKeyboardButton("📦 Custom Template", callback_data="temp_type_custom"),
            ]
        ])
        
        await database.users_col.update_one({"_id": user_id}, {"$set": {"state": "awaiting_template_type"}})
        await message.reply_text(
            f"📋 Template Name: **{text}**\n\n"
            "Please select the type of template:",
            reply_markup=buttons
        )
        message.stop_propagation()
        return

    # 2. Capture Template Content (Caption + Buttons)
    elif state == "awaiting_template_content":
        draft = template_creation_drafts.get(user_id)
        if not draft:
            await database.users_col.update_one({"_id": user_id}, {"$unset": {"state": ""}})
            await message.reply_text("❌ Session expired. Please start over.")
            message.stop_propagation()
            return
            
        # Parse buttons and extract clean caption
        from handlers.post_builder import parse_button_string
        buttons = parse_button_string(text)
        
        # Clean caption by removing button tags
        import re
        caption = re.sub(r"\[.*?\]", "", text).strip()
        
        # Save to DB
        await database.save_template(
            user_id=user_id,
            name=draft["name"],
            template_type=draft["type"],
            caption=caption,
            buttons=buttons
        )
        
        # Clear transient state
        await database.users_col.update_one({"_id": user_id}, {"$unset": {"state": ""}})
        if user_id in template_creation_drafts:
            del template_creation_drafts[user_id]
            
        await message.reply_text("✅ **Template saved successfully!** You can now load it from `/templates` inside the post builder.")
        message.stop_propagation()
        return


@app.on_callback_query(filters.regex(r"^temp_type_(.+)"))
async def template_type_callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    temp_type = callback_query.matches[0].group(1)
    
    draft = template_creation_drafts.get(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Please try again.", show_alert=True)
        return
        
    await callback_query.answer()
    draft["type"] = temp_type
    
    await database.users_col.update_one({"_id": user_id}, {"$set": {"state": "awaiting_template_content"}})
    await callback_query.message.edit_text(
        f"📝 **Template: {draft['name']} ({temp_type.capitalize()})**\n\n"
        "Please send the template text content (caption) now.\n"
        "You can include formatting and inline buttons at the end of the text like this:\n\n"
        "⭐ *Checkout this Movie!*\n"
        "[🎬 Watch Now | https://t.me/watch]\n"
        "[🔥 Reviews | https://t.me/reviews]"
    )
