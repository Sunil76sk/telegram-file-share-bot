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
from utils.helpers import banned_filter, extract_file_details

logger = logging.getLogger(__name__)

# Helper to format and parse buttons from text
# Input format: [Button Text | url] or [Button Text | deep_link], etc.
# Support multiple rows: newlines represent new rows
def parse_button_string(button_str: str) -> list[list[dict]]:
    rows = []
    lines = button_str.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        row = []
        # Find all brackets [...]
        import re
        matches = re.findall(r"\[(.*?)\]", line)
        for match in matches:
            parts = match.split("|")
            if len(parts) >= 2:
                text = parts[0].strip()
                url = "|".join(parts[1:]).strip()
                row.append({"text": text, "url": url})
        if row:
            rows.append(row)
    return rows

def build_inline_keyboard(parsed_buttons: list[list[dict]]) -> InlineKeyboardMarkup | None:
    if not parsed_buttons:
        return None
    keyboard = []
    for row in parsed_buttons:
        keyboard_row = []
        for btn in row:
            keyboard_row.append(InlineKeyboardButton(text=btn["text"], url=btn["url"]))
        keyboard.append(keyboard_row)
    return InlineKeyboardMarkup(keyboard)


# ─── BUILDER INITIATION ──────────────────────────────────────────────

@app.on_message(filters.command("newpost") & filters.private & ~banned_filter)
async def newpost_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    channels = await database.get_creator_channels(user_id)
    if not channels:
        await message.reply_text(
            "❌ **No channels found!**\n\n"
            "You must first add a channel to Creator Studio using:\n"
            "`/add_channel [channel_username_or_id]`"
        )
        return

    # Choose Target Channel
    buttons = []
    for chan in channels:
        if chan.get("service_enabled", True):
            buttons.append([InlineKeyboardButton(chan["title"], callback_data=f"build_select_{chan['_id']}")])

    if not buttons:
        await message.reply_text("❌ All your added channels are currently disabled. Please enable them in `/my_channels` settings.")
        return

    await message.reply_text(
        "📝 **Creator Studio — Create New Post**\n\n"
        "Please select the target channel for this post:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


@app.on_callback_query(filters.regex(r"^build_select_(.+)"))
async def build_select_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    channel_id = callback_query.matches[0].group(1)
    try:
        channel_id_val = int(channel_id)
    except ValueError:
        channel_id_val = channel_id

    # Create empty draft
    draft = {
        "channel_id": channel_id_val,
        "media_type": "text",
        "file_id": None,
        "caption": "",
        "buttons": [],
        "reactions": [],
        "comments": False,
        "pin": False,
        "state": "awaiting_media"
    }
    await database.save_post_draft(user_id, draft)
    await callback_query.answer()
    await callback_query.message.edit_text(
        "📥 **Channel Selected!**\n\n"
        "Please send the media (Photo, Video, Audio, Document, GIF) or type the raw text message you want to post."
    )


# ─── CAPTURING MEDIA & TEXT ──────────────────────────────────────────

@app.on_message(filters.private & ~banned_filter, group=5)
async def builder_input_handler(client: Client, message: Message):
    user_id = message.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft or draft.get("state") not in ["awaiting_media", "awaiting_caption", "awaiting_buttons", "awaiting_reactions"]:
        return

    state = draft.get("state")
    text = message.text.strip() if message.text else ""

    if text.lower() == "/cancel":
        await database.delete_post_draft(user_id)
        await message.reply_text("❌ **Post builder session cancelled.**")
        message.stop_propagation()
        return

    # 1. Capture Media/Text Input
    if state == "awaiting_media":
        if message.text:
            draft["media_type"] = "text"
            draft["caption"] = text
        else:
            file_id, file_unique_id, file_name, file_type, file_size, caption = extract_file_details(message)
            if not file_id:
                await message.reply_text("❌ Unsupported media format. Please send a photo, video, audio, document, or text.")
                message.stop_propagation()
                return
            draft["media_type"] = file_type
            draft["file_id"] = file_id
            draft["caption"] = caption or ""

        draft["state"] = "active"
        await database.save_post_draft(user_id, draft)
        await show_builder_menu(client, message, user_id, draft)
        message.stop_propagation()
        return

    # 2. Capture Caption Editing
    elif state == "awaiting_caption":
        draft["caption"] = text
        draft["state"] = "active"
        await database.save_post_draft(user_id, draft)
        await message.reply_text("✅ Caption updated!")
        await show_builder_menu(client, message, user_id, draft)
        message.stop_propagation()
        return

    # 3. Capture URL Buttons Input
    elif state == "awaiting_buttons":
        parsed = parse_button_string(text)
        draft["buttons"] = parsed
        draft["state"] = "active"
        await database.save_post_draft(user_id, draft)
        await message.reply_text("✅ Buttons configured!")
        await show_builder_menu(client, message, user_id, draft)
        message.stop_propagation()
        return

    # 4. Capture Reactions Selection
    elif state == "awaiting_reactions":
        reactions = [r.strip() for r in text.split() if r.strip()]
        draft["reactions"] = reactions
        draft["state"] = "active"
        await database.save_post_draft(user_id, draft)
        await message.reply_text("✅ Reactions configured!")
        await show_builder_menu(client, message, user_id, draft)
        message.stop_propagation()
        return


# ─── BUILDER MENU SYSTEM ─────────────────────────────────────────────

async def show_builder_menu(client: Client, message: Message, user_id: int, draft: dict):
    # Retrieve channel info
    channel = await database.get_channel_by_id(draft["channel_id"])
    channel_title = channel.get("title") if channel else str(draft["channel_id"])

    menu_text = (
        f"📝 **Post Builder Menu**\n\n"
        f"📢 **Target Channel:** {channel_title}\n"
        f"📦 **Media Type:** `{draft['media_type'].upper()}`\n"
        f"✏️ **Caption Length:** {len(draft.get('caption', ''))} characters\n"
        f"🔗 **Buttons:** {len(draft.get('buttons', []))} rows\n"
        f"❤️ **Reactions:** {' '.join(draft.get('reactions', [])) or 'Disabled'}\n"
        f"📌 **Pin Message:** {'Yes' if draft.get('pin') else 'No'}\n\n"
        f"Configure your post using the buttons below:"
    )

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📝 Edit Caption", callback_data="build_btn_caption"),
                InlineKeyboardButton("🔗 URL Buttons", callback_data="build_btn_buttons"),
            ],
            [
                InlineKeyboardButton("❤️ Reactions", callback_data="build_btn_reactions"),
                InlineKeyboardButton(f"📌 Pin: {'✅' if draft.get('pin') else '❌'}", callback_data="build_btn_pin"),
            ],
            [
                InlineKeyboardButton("👀 Preview", callback_data="build_btn_preview"),
                InlineKeyboardButton("🚀 Send Now", callback_data="build_btn_send"),
            ],
            [
                InlineKeyboardButton("📅 Schedule", callback_data="build_btn_schedule"),
                InlineKeyboardButton("🔄 Auto Repost", callback_data="build_btn_repost"),
            ],
            [
                InlineKeyboardButton("❌ Cancel", callback_data="build_btn_cancel"),
            ]
        ]
    )

    await client.send_message(chat_id=user_id, text=menu_text, reply_markup=buttons)


@app.on_callback_query(filters.regex(r"^build_btn_(.+)"))
async def builder_menu_callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    action = callback_query.matches[0].group(1)

    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Please start over.", show_alert=True)
        try:
            await callback_query.message.delete()
        except Exception:
            pass
        return

    await callback_query.answer()

    if action == "caption":
        draft["state"] = "awaiting_caption"
        await database.save_post_draft(user_id, draft)
        await callback_query.message.reply_text(
            "📝 **Send the new caption text now.**\n"
            "You can use formatting like bold, italic, spoilers, and links.\n"
            "Send `/cancel` to abort."
        )

    elif action == "buttons":
        draft["state"] = "awaiting_buttons"
        await database.save_post_draft(user_id, draft)
        await callback_query.message.reply_text(
            "🔗 **Configure URL Buttons**\n\n"
            "Send buttons in the following format:\n"
            "`[Button Text | https://link1.com]`\n"
            "For multiple buttons in a single row, separate them:\n"
            "`[Button 1 | link1] [Button 2 | link2]`\n\n"
            "Send `/cancel` to abort."
        )

    elif action == "reactions":
        draft["state"] = "awaiting_reactions"
        await database.save_post_draft(user_id, draft)
        await callback_query.message.reply_text(
            "❤️ **Configure Reactions**\n\n"
            "Send emojis separated by spaces that users can click to react:\n"
            "Example: `❤️ 🔥 ⚡ 👍`"
        )

    elif action == "pin":
        draft["pin"] = not draft.get("pin", False)
        await database.save_post_draft(user_id, draft)
        await callback_query.message.delete()
        await show_builder_menu(client, callback_query.message, user_id, draft)

    elif action == "preview":
        # Delete old menu and show live preview
        await callback_query.message.delete()
        await show_post_preview(client, user_id, draft)

    elif action == "send":
        await callback_query.message.delete()
        sent = await send_post_now(client, user_id, draft)
        if sent:
            await client.send_message(user_id, "🚀 **Post sent successfully!**")
            await database.delete_post_draft(user_id)
        else:
            await client.send_message(user_id, "❌ **Failed to send post.** Please check bot permissions in the channel.")

    elif action == "schedule":
        # Forward to scheduling state
        draft["state"] = "awaiting_schedule_time"
        await database.save_post_draft(user_id, draft)
        await callback_query.message.edit_text(
            "📅 **Post Scheduling**\n\n"
            "Please send the time to publish the post in the format:\n"
            "`YYYY-MM-DD HH:MM` (UTC time)\n\n"
            "Example: `2026-06-15 14:30`"
        )

    elif action == "cancel":
        await database.delete_post_draft(user_id)
        await callback_query.message.edit_text("❌ **Post builder session cancelled.**")


# ─── PREVIEW & DELIVERY SYSTEM ───────────────────────────────────────

async def show_post_preview(client: Client, user_id: int, draft: dict):
    caption = draft.get("caption", "")
    reactions_str = " ".join(draft.get("reactions", []))
    if reactions_str:
        caption += f"\n\nReactions: {reactions_str}"

    reply_markup = build_inline_keyboard(draft.get("buttons", []))

    await client.send_message(user_id, "👀 **POST PREVIEW:**\n━━━━━━━━━━━━━━━")

    # Send matching media
    media_type = draft["media_type"]
    file_id = draft["file_id"]

    try:
        if media_type == "text":
            await client.send_message(chat_id=user_id, text=caption, reply_markup=reply_markup)
        else:
            await client.send_cached_media(chat_id=user_id, file_id=file_id, caption=caption, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error showing builder preview: {e}")
        await client.send_message(user_id, f"❌ **Error rendering preview:** {e}")

    await client.send_message(user_id, "━━━━━━━━━━━━━━━")
    # Send menu again
    await show_builder_menu(client, Message(id=0), user_id, draft)


async def send_post_now(client: Client, user_id: int, draft: dict) -> bool:
    channel_id = draft["channel_id"]
    caption = draft.get("caption", "")
    reply_markup = build_inline_keyboard(draft.get("buttons", []))

    # Add reaction mock string to caption if reactions are configured
    reactions = draft.get("reactions", [])
    if reactions:
        # Note: True reaction callbacks can be supported if custom buttons are used
        pass

    try:
        if draft["media_type"] == "text":
            msg = await client.send_message(chat_id=channel_id, text=caption, reply_markup=reply_markup)
        else:
            msg = await client.send_cached_media(chat_id=channel_id, file_id=draft["file_id"], caption=caption, reply_markup=reply_markup)
        
        if draft.get("pin") and msg:
            try:
                await client.pin_chat_message(chat_id=channel_id, message_id=msg.id)
            except Exception as pin_err:
                logger.warning(f"Failed to pin post: {pin_err}")

        # Update stats
        await database.increment_channel_stat(channel_id, "publishes", 1)
        return True
    except Exception as e:
        logger.error(f"Error publishing post: {e}")
        return False
