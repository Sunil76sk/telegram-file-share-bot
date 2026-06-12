from __future__ import annotations

import logging
import datetime
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    InputMediaPhoto,
    InputMediaVideo,
)
from bot import app
import database
from utils.helpers import banned_filter, extract_file_details
from utils.caption_builder import build_telegram_caption_html


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

    # Check if they have an active draft to continue editing
    draft = await database.get_post_draft(user_id)
    if draft and draft.get("state") != "awaiting_media":
        channel = await database.get_channel_by_id(draft["channel_id"])
        channel_title = channel.get("channel_title") if channel else str(draft["channel_id"])
        await message.reply_text(
            f"📝 **Active Post Draft Found!**\n\n"
            f"You have an unfinished post draft for channel **{channel_title}**.\n"
            "Do you want to continue editing it or start a new post?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🔄 Continue Editing", callback_data="build_draft_continue"),
                        InlineKeyboardButton("🆕 Start New Post", callback_data="build_draft_new"),
                    ]
                ]
            )
        )
        return

    # Choose Target Channel
    buttons = []
    for chan in channels:
        if chan.get("service_enabled", True):
            buttons.append([InlineKeyboardButton(chan.get("channel_title") or chan.get("title") or str(chan["_id"]), callback_data=f"build_select_{chan['_id']}")])

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

    # Create empty draft matching exact PRD schema
    draft = {
        "draft_id": str(user_id),
        "user_id": user_id,
        "channel_id": channel_id_val,
        "media_type": "text",
        "file_id": None,
        "media_files": [],
        "caption": "",
        "buttons": [],
        "reactions": [],
        "reactions_enabled": False,
        "comments": False,
        "comments_enabled": False,
        "caption_above": False,
        "pin": False,
        "pin_message": False,
        "state": "awaiting_media",
        "created_at": datetime.datetime.now(datetime.timezone.utc),
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
    text = message.text.strip() if message.text else ""

    if text.lower() == "/cancel":
        draft = await database.get_post_draft(user_id)
        if draft:
            await database.delete_post_draft(user_id)
            await message.reply_text("❌ **Post builder session cancelled.**")
            message.stop_propagation()
            return

    draft = await database.get_post_draft(user_id)
    draft_exists = draft is not None
    draft_state = draft.get("state") if draft_exists else None
    
    # Requirements:
    # 1. user_id
    # 2. draft exists?
    # 3. full draft state
    # 4. draft document
    # 5. branch taken
    logger.info(f"[builder_input_handler] user_id={user_id}")
    logger.info(f"[builder_input_handler] draft exists={draft_exists}")
    logger.info(f"[builder_input_handler] state={draft_state}")
    logger.info(f"[builder_input_handler] draft doc={draft}")
    
    if not draft:
        logger.info(f"[builder_input_handler] ACTION=return | reason=no_draft")
        return

    state = draft.get("state")
    if not state or state not in ["awaiting_media", "awaiting_caption", "awaiting_buttons", "awaiting_reactions"]:
        logger.info(f"[builder_input_handler] ACTION=return | reason=invalid_state | state={state}")
        return

    # 1. Capture Media/Text Input
    if state == "awaiting_media":
        # Handle album (media group)
        if message.media_group_id:
            media_files = draft.get("media_files", [])
            file_id, file_unique_id, file_name, file_type, file_size, caption = extract_file_details(message)
            if file_id:
                media_type = "document"
                if file_type == "photo":
                    media_type = "photo"
                elif file_type in ["video", "animation"]:
                    media_type = "video"
                elif file_type in ["audio", "voice"]:
                    media_type = "audio"

                if not any(f["file_id"] == file_id for f in media_files):
                    media_files.append({"file_id": file_id, "media_type": media_type})
                
                draft["media_files"] = media_files
                draft["media_type"] = "album"
                draft["media_group_id"] = message.media_group_id
                if caption and not draft.get("caption"):
                    draft["caption"] = caption
                
                await database.save_post_draft(user_id, draft)

            # Schedule show menu after 1 second to gather all media group items
            if not draft.get("scheduled_menu"):
                draft["scheduled_menu"] = True
                await database.save_post_draft(user_id, draft)

                async def delayed_menu_show():
                    import asyncio
                    await asyncio.sleep(1.0)
                    latest_draft = await database.get_post_draft(user_id)
                    if latest_draft and latest_draft.get("state") == "awaiting_media":
                        latest_draft["state"] = "active"
                        latest_draft["scheduled_menu"] = False
                        await database.save_post_draft(user_id, latest_draft)
                        await show_builder_menu(client, message, user_id, latest_draft)

                import asyncio
                asyncio.create_task(delayed_menu_show())

            message.stop_propagation()
            return

        # Single message
        if message.text:
            if message.text.startswith("/") and not message.text.startswith("/cancel"):
                return  # Skip commands
            draft["media_type"] = "text"
            draft["caption"] = text
        else:
            file_id, file_unique_id, file_name, file_type, file_size, caption = extract_file_details(message)
            if not file_id:
                await message.reply_text("❌ Unsupported media format. Please send a photo, video, audio, document, or text.")
                message.stop_propagation()
                return
            
            # Map file type
            media_type = file_type
            if file_type == "animation":
                media_type = "animation"
            elif file_type == "photo":
                media_type = "photo"
            elif file_type == "video":
                media_type = "video"
            elif file_type == "audio":
                media_type = "audio"
            else:
                media_type = "document"

            draft["media_type"] = media_type
            draft["file_id"] = file_id
            draft["caption"] = caption or ""

        draft["state"] = "active"
        await database.save_post_draft(user_id, draft)
        await show_builder_menu(client, message, user_id, draft)
        message.stop_propagation()
        return

    # 2. Capture Caption Editing
    elif state == "awaiting_caption":
        logger.info("[builder_input_handler]\ndraft exists=True\nstate=awaiting_caption\nACTION=caption_updated")
        draft["caption"] = text
        draft["state"] = "active"
        await database.save_post_draft(user_id, draft)
        logger.info(f"[builder_input_handler] SENDING caption updated to user_id={user_id}")
        logger.info("✅ Caption updated!")
        await message.reply_text("✅ Caption updated!")
        await show_builder_menu(client, message, user_id, draft)
        message.stop_propagation()
        return

    # 3. Capture URL Buttons Input
    elif state == "awaiting_buttons":
        parsed = parse_button_string(text)
        is_premium = await database.is_user_premium(user_id)
        if not is_premium and len(parsed) > 1:
            await message.reply_text(
                "❌ **Multi-Row Buttons is a Premium Feature!**\n\n"
                "Free creators can only add a single row of buttons.\n"
                "Please upgrade to Premium using `/premium` or configure only 1 row of buttons."
            )
            message.stop_propagation()
            return
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
        is_premium = await database.is_user_premium(user_id)
        allowed_free_emojis = ["❤️", "🔥", "⚡", "👍", "😂", "🎉"]
        if not is_premium:
            invalid = [r for r in reactions if r not in allowed_free_emojis]
            if invalid:
                await message.reply_text(
                    "❌ **Custom Reactions is a Premium Feature!**\n\n"
                    "Free creators can only use: ❤️ 🔥 ⚡ 👍 😂 🎉\n"
                    "Please send emojis from this allowed list or upgrade to Premium."
                )
                message.stop_propagation()
                return
        draft["reactions"] = reactions
        draft["reactions_enabled"] = len(reactions) > 0
        draft["state"] = "active"
        await database.save_post_draft(user_id, draft)
        await message.reply_text("✅ Reactions configured!")
        await show_builder_menu(client, message, user_id, draft)
        message.stop_propagation()
        return


# ─── BUILDER MENU SYSTEM ─────────────────────────────────────────────

async def get_comments_url(client: Client, channel_id: int) -> str:
    try:
        chat = await client.get_chat(channel_id)
        if chat.linked_chat_id:
            try:
                linked_chat = await client.get_chat(chat.linked_chat_id)
                if linked_chat.username:
                    return f"https://t.me/{linked_chat.username}"
                elif linked_chat.invite_link:
                    return linked_chat.invite_link
                else:
                    return f"https://t.me/c/{str(chat.linked_chat_id).replace('-100', '')}"
            except Exception:
                return f"https://t.me/c/{str(chat.linked_chat_id).replace('-100', '')}"
    except Exception:
        pass
    return ""


def build_post_keyboard(buttons_spec: list, reactions: list, reaction_counts: dict = None, comments_url: str = None) -> InlineKeyboardMarkup | None:
    keyboard = []
    
    # 1. URL buttons
    if buttons_spec:
        for row in buttons_spec:
            keyboard_row = []
            for btn in row:
                keyboard_row.append(InlineKeyboardButton(text=btn["text"], url=btn["url"]))
            keyboard.append(keyboard_row)
            
    # 2. Reactions row
    if reactions:
        reaction_row = []
        counts = reaction_counts or {}
        for emoji in reactions:
            count = counts.get(emoji, 0)
            btn_text = f"{emoji} {count}" if count > 0 else emoji
            reaction_row.append(InlineKeyboardButton(text=btn_text, callback_data=f"react_click_{emoji}"))
        keyboard.append(reaction_row)
        
    # 3. Comments button
    if comments_url:
        keyboard.append([InlineKeyboardButton("💬 Comments", url=comments_url)])
        
    return InlineKeyboardMarkup(keyboard) if keyboard else None


# ─── BUILDER MENU SYSTEM ─────────────────────────────────────────────

async def show_builder_menu(client: Client, message: Message, user_id: int, draft: dict):
    # Retrieve channel info
    channel = await database.get_channel_by_id(draft["channel_id"])
    channel_title = channel.get("channel_title") if channel else str(draft["channel_id"])

    menu_text = (
        f"📝 **Post Builder Menu**\n\n"
        f"📢 **Target Channel:** {channel_title}\n"
        f"📦 **Media Type:** `{draft['media_type'].upper()}`\n"
        f"✏️ **Caption Length:** {len(draft.get('caption', ''))} characters\n"
        f"⬆️ **Caption Position:** {'Above Media ⬆️' if draft.get('caption_above') else 'Below Media ⬇️'}\n"
        f"🔗 **Buttons:** {len(draft.get('buttons', []))} rows\n"
        f"❤️ **Reactions:** {' '.join(draft.get('reactions', [])) or 'Disabled'}\n"
        f"💬 **Comments:** {'Enabled' if draft.get('comments_enabled') or draft.get('comments') else 'Disabled'}\n"
        f"📌 **Pin Message:** {'Yes' if draft.get('pin_message') or draft.get('pin') else 'No'}\n\n"
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
                InlineKeyboardButton(f"💬 Comments: {'✅' if draft.get('comments_enabled') or draft.get('comments') else '❌'}", callback_data="build_btn_comments"),
            ],
            [
                InlineKeyboardButton(f"📝 Pos: {'Above ⬆️' if draft.get('caption_above') else 'Below ⬇️'}", callback_data="build_btn_pos"),
                InlineKeyboardButton(f"📌 Pin: {'✅' if draft.get('pin_message') or draft.get('pin') else '❌'}", callback_data="build_btn_pin"),
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

    if action == "caption":
        await callback_query.answer()
        draft["state"] = "awaiting_caption"
        await database.save_post_draft(user_id, draft)
        await callback_query.message.reply_text(
            "📝 **Send the new caption text now.**\n"
            "You can use formatting like bold, italic, spoilers, and links.\n"
            "Send `/cancel` to abort."
        )

    elif action == "buttons":
        await callback_query.answer()
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
        await callback_query.answer()
        draft["state"] = "awaiting_reactions"
        await database.save_post_draft(user_id, draft)
        await callback_query.message.reply_text(
            "❤️ **Configure Reactions**\n\n"
            "Send emojis separated by spaces that users can click to react:\n"
            "Example: `❤️ 🔥 ⚡ 👍`"
        )

    elif action == "comments":
        channel_id = draft["channel_id"]
        try:
            chat_info = await client.get_chat(channel_id)
            if not chat_info.linked_chat_id:
                await callback_query.answer("❌ No Discussion Group Linked to this channel!", show_alert=True)
                return
            await callback_query.answer()
            new_comments = not (draft.get("comments_enabled") or draft.get("comments", False))
            draft["comments"] = new_comments
            draft["comments_enabled"] = new_comments
            await database.save_post_draft(user_id, draft)
            await callback_query.message.delete()
            await show_builder_menu(client, callback_query.message, user_id, draft)
        except Exception as e:
            logger.error(f"Error checking discussion group: {e}")
            await callback_query.answer(f"❌ Failed to verify comments status: {e}", show_alert=True)

    elif action == "pos":
        await callback_query.answer()
        draft["caption_above"] = not draft.get("caption_above", False)
        await database.save_post_draft(user_id, draft)
        await callback_query.message.delete()
        await show_builder_menu(client, callback_query.message, user_id, draft)

    elif action == "pin":
        await callback_query.answer()
        new_pin = not (draft.get("pin_message") or draft.get("pin", False))
        draft["pin"] = new_pin
        draft["pin_message"] = new_pin
        await database.save_post_draft(user_id, draft)
        await callback_query.message.delete()
        await show_builder_menu(client, callback_query.message, user_id, draft)

    elif action == "preview":
        await callback_query.answer()
        # Delete old menu and show live preview
        await callback_query.message.delete()
        await show_post_preview(client, user_id, draft)

    elif action == "send":
        await callback_query.answer()
        await callback_query.message.delete()
        sent = await send_post_now(client, user_id, draft)
        if sent:
            await client.send_message(user_id, "🚀 **Post sent successfully!**")
            await database.delete_post_draft(user_id)
        else:
            await client.send_message(user_id, "❌ **Failed to send post.** Please check bot permissions in the channel.")

    elif action == "schedule":
        await callback_query.answer()
        # Forward to scheduling state
        draft["state"] = "awaiting_schedule_time"
        await database.save_post_draft(user_id, draft)
        await callback_query.message.edit_text(
            "📅 **Post Scheduling**\n\n"
            "Please send the time to publish the post in the format:\n"
            "`YYYY-MM-DD HH:MM` (UTC time)\n\n"
            "Example: `2026-06-15 14:30`"
        )

    elif action == "repost":
        is_premium = await database.is_user_premium(user_id)
        if not is_premium:
            await callback_query.answer("❌ Auto Reposting is a Premium Feature!", show_alert=True)
            return
        await callback_query.answer()
        draft["state"] = "awaiting_repost_interval"
        await database.save_post_draft(user_id, draft)
        await callback_query.message.edit_text(
            "🔄 **Auto Reposting Setup**\n\n"
            "Please enter the **Repost Interval** (in minutes) after which the post should be auto-reposted:\n"
            "Example: `60` (for every 1 hour)"
        )

    elif action == "cancel":
        await callback_query.answer()
        await database.delete_post_draft(user_id)
        await callback_query.message.edit_text("❌ **Post builder session cancelled.**")

    elif action == "continue":
        await callback_query.answer()
        await callback_query.message.delete()
        await show_builder_menu(client, callback_query.message, user_id, draft)

    elif action == "new":
        await callback_query.answer()
        await database.delete_post_draft(user_id)
        # Select target channel from scratch
        channels = await database.get_creator_channels(user_id)
        buttons = []
        for chan in channels:
            if chan.get("service_enabled", True):
                buttons.append([InlineKeyboardButton(chan.get("channel_title") or chan.get("title") or str(chan["_id"]), callback_data=f"build_select_{chan['_id']}")])
        await callback_query.message.edit_text(
            "📝 **Creator Studio — Create New Post**\n\n"
            "Please select the target channel for this post:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )


# ─── PREVIEW & DELIVERY SYSTEM ───────────────────────────────────────

async def show_post_preview(client: Client, user_id: int, draft: dict):
    caption = draft.get("caption", "")
    comments_url = None
    if draft.get("comments") or draft.get("comments_enabled"):
        comments_url = await get_comments_url(client, draft["channel_id"])

    reply_markup = build_post_keyboard(
        buttons_spec=draft.get("buttons", []),
        reactions=draft.get("reactions", []),
        reaction_counts=None,
        comments_url=comments_url
    )

    await client.send_message(user_id, "👀 **POST PREVIEW:**\n━━━━━━━━━━━━━━━")

    media_type = draft["media_type"]
    file_id = draft["file_id"]

    try:
        if media_type == "text":
            await client.send_message(
                chat_id=user_id,
                text=build_telegram_caption_html(caption),
                reply_markup=reply_markup,
                parse_mode="html",
            )

        elif media_type == "album":
            media = []
            for file in draft.get("media_files", []):
                if file["media_type"] == "photo":
                    media.append(InputMediaPhoto(file["file_id"]))
                elif file["media_type"] in ["video", "animation"]:
                    media.append(InputMediaVideo(file["file_id"]))
            
            if media:
                await client.send_media_group(chat_id=user_id, media=media)
                await client.send_message(
                    chat_id=user_id,
                    text=build_telegram_caption_html(caption or "👇 Reactions/Buttons:"),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )


        else:
            if draft.get("caption_above"):
                # Send caption first, then media
                await client.send_message(
                    chat_id=user_id,
                    text=build_telegram_caption_html(caption),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )
                await client.send_cached_media(chat_id=user_id, file_id=file_id)
            else:
                await client.send_cached_media(
                    chat_id=user_id,
                    file_id=file_id,
                    caption=build_telegram_caption_html(caption),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )


    except Exception as e:
        logger.error(f"Error showing builder preview: {e}")
        await client.send_message(user_id, f"❌ **Error rendering preview:** {e}")

    await client.send_message(user_id, "━━━━━━━━━━━━━━━")
    # Send menu again
    await show_builder_menu(client, Message(id=0), user_id, draft)


async def send_post_now(client: Client, user_id: int, draft: dict) -> bool:
    channel_id = draft["channel_id"]
    caption = draft.get("caption", "")
    comments_url = None
    if draft.get("comments") or draft.get("comments_enabled"):
        comments_url = await get_comments_url(client, channel_id)

    reply_markup = build_post_keyboard(
        buttons_spec=draft.get("buttons", []),
        reactions=draft.get("reactions", []),
        reaction_counts=None,
        comments_url=comments_url
    )

    try:
        if draft["media_type"] == "text":
            msg = await client.send_message(
                chat_id=channel_id,
                text=build_telegram_caption_html(caption),
                reply_markup=reply_markup,
                parse_mode="html",
            )

        elif draft["media_type"] == "album":
            media = []
            for file in draft.get("media_files", []):
                if file["media_type"] == "photo":
                    media.append(InputMediaPhoto(file["file_id"]))
                elif file["media_type"] in ["video", "animation"]:
                    media.append(InputMediaVideo(file["file_id"]))
            
            if media:
                await client.send_media_group(chat_id=channel_id, media=media)
            msg = await client.send_message(
                chat_id=channel_id,
                text=build_telegram_caption_html(caption or "👇 Reactions/Buttons:"),
                reply_markup=reply_markup,
                parse_mode="html",
            )

        else:
            if draft.get("caption_above"):
                msg = await client.send_message(
                    chat_id=channel_id,
                    text=build_telegram_caption_html(caption),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )
                media_msg = await client.send_cached_media(chat_id=channel_id, file_id=draft["file_id"])

            else:
                msg = await client.send_cached_media(
                    chat_id=channel_id,
                    file_id=draft["file_id"],
                    caption=build_telegram_caption_html(caption),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )

        
        if draft.get("pin") or draft.get("pin_message") and msg:
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


# ─── CHANNEL SETTINGS COMMAND ────────────────────────────────────────

@app.on_message(filters.command("channel_settings") & filters.private & ~banned_filter)
async def channel_settings_command_handler(client: Client, message: Message):
    from handlers.broadcast import my_channels_handler
    await my_channels_handler(client, message)
