from __future__ import annotations

import logging
import datetime
import re
from zoneinfo import ZoneInfo

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    InputMediaPhoto,
    InputMediaVideo,
)
from pyrogram.errors import (
    ChatWriteForbidden,
    ChatAdminRequired,
    MessageTooLong,
    PeerIdInvalid,
    FloodWait,
    ChannelPrivate,
)

import config
from bot import app, INSTANCE_ID, current_update_info
import database
from utils.helpers import banned_filter, extract_file_details
from utils.caption_builder import build_telegram_caption_html
from utils.rate_limiter import check_rate_limit

logger = logging.getLogger(__name__)


# ─── BUTTON PARSING UTILITIES ─────────────────────────────────────────

def parse_button_string(button_str: str) -> list[list[dict]]:
    rows = []
    lines = button_str.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        row = []
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


# ─── COMMENTS URL (SAFE GETATTR PATTERN) ──────────────────────────────

async def get_comments_url(client: Client, channel_id: int) -> str:
    try:
        chat = await client.get_chat(channel_id)
        linked_chat = getattr(chat, "linked_chat", None)
        if linked_chat:
            username = getattr(linked_chat, "username", None)
            if username:
                return f"https://t.me/{username}"
            invite = getattr(linked_chat, "invite_link", None)
            if invite:
                return invite
            return f"https://t.me/c/{str(linked_chat.id).replace('-100', '')}"

        linked_chat_id = getattr(chat, "linked_chat_id", None)
        if linked_chat_id:
            return f"https://t.me/c/{str(linked_chat_id).replace('-100', '')}"
    except Exception as e:
        logger.debug(f"get_comments_url failed for {channel_id}: {e}")
    return ""


# ─── KEYBOARD BUILDER (LAYOUT-AWARE) ─────────────────────────────────

def build_post_keyboard(
    download_configs: list | None = None,
    custom_buttons: list | None = None,
    reactions: list | None = None,
    reaction_counts: dict | None = None,
    comments_url: str | None = None,
    layout_type: str = "layout_a",
    bot_username: str = "",
) -> InlineKeyboardMarkup | None:
    keyboard: list[list[InlineKeyboardButton]] = []
    download_configs = download_configs or []
    custom_buttons = custom_buttons or []
    reactions = reactions or []

    if layout_type == "layout_b" and len(download_configs) >= 3:
        row = []
        labels = ["480P", "720P", "1080P"]
        for i in range(3):
            cfg = download_configs[i]
            token = cfg.get("token") or cfg.get("config_id") or ""
            url = f"https://t.me/{bot_username}?start=dl_{token}" if bot_username and token else ""
            row.append(InlineKeyboardButton(text=labels[i], url=url))
        keyboard.append(row)

    elif layout_type == "layout_c" and len(download_configs) >= 3:
        labels = ["📥 Download", "🎬 Watch Online", "🎞️ Trailer"]
        for i in range(3):
            cfg = download_configs[i]
            token = cfg.get("token") or cfg.get("config_id") or ""
            url = f"https://t.me/{bot_username}?start=dl_{token}" if bot_username and token else ""
            keyboard.append([InlineKeyboardButton(text=labels[i], url=url)])

    elif layout_type == "layout_d":
        if download_configs:
            cfg = download_configs[0]
            token = cfg.get("token") or cfg.get("config_id") or ""
            url = f"https://t.me/{bot_username}?start=dl_{token}" if bot_username and token else ""
            keyboard.append([InlineKeyboardButton(text="📥 Download", url=url)])

    else:
        if download_configs:
            cfg = download_configs[0]
            token = cfg.get("token") or cfg.get("config_id") or ""
            url = f"https://t.me/{bot_username}?start=dl_{token}" if bot_username and token else ""
            keyboard.append([InlineKeyboardButton(text="📥 Download", url=url)])

    for row in custom_buttons:
        keyboard_row = []
        for btn in row:
            keyboard_row.append(InlineKeyboardButton(text=btn.get("text", ""), url=btn.get("url", "")))
        if keyboard_row:
            keyboard.append(keyboard_row)

    if reactions:
        reaction_row = []
        counts = reaction_counts or {}
        for emoji in reactions:
            count = counts.get(emoji, 0)
            btn_text = f"{emoji} {count}" if count > 0 else emoji
            reaction_row.append(InlineKeyboardButton(text=btn_text, callback_data=f"react_click_{emoji}"))
        keyboard.append(reaction_row)

    if layout_type == "layout_d" and comments_url:
        keyboard.append([InlineKeyboardButton("💬 Comments", url=comments_url)])
    elif comments_url:
        keyboard.append([InlineKeyboardButton("💬 Comments", url=comments_url)])

    return InlineKeyboardMarkup(keyboard) if keyboard else None


# ─── /newpost COMMAND ──────────────────────────────────────────────────

@app.on_message(filters.command("newpost") & filters.private & ~banned_filter)
async def newpost_command_handler(client: Client, message: Message):
    current_update_info.set({
        "handler": "newpost_command_handler",
        "update_id": message.id,
        "message_id": message.id,
    })
    user_id = message.from_user.id

    allowed = await check_rate_limit(user_id, "newpost_command", limit=5, window_seconds=60)
    if not allowed:
        await message.reply_text("Rate limit exceeded. You can only use /newpost 5 times per minute.")
        return

    channels = await database.get_creator_channels(user_id)
    if not channels:
        await message.reply_text(
            "No channels found.\n\n"
            "Add a channel first using:\n"
            "`/add_channel [channel_username_or_id]`"
        )
        return

    draft = await database.get_post_draft(user_id)
    if draft and draft.get("state") not in (None, "awaiting_media"):
        channel = await database.get_channel_by_id(draft["channel_id"])
        channel_title = channel.get("channel_title") if channel else str(draft["channel_id"])
        await message.reply_text(
            f"Active Post Draft Found\n\n"
            f"You have an unfinished draft for **{channel_title}**.\n"
            f"Continue editing or start fresh?",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Continue Editing", callback_data="build_btn_continue"),
                    InlineKeyboardButton("Start New Post", callback_data="build_btn_new"),
                ]
            ]),
        )
        return

    buttons = []
    for chan in channels:
        if chan.get("service_enabled", True):
            buttons.append([
                InlineKeyboardButton(
                    chan.get("channel_title") or chan.get("title") or str(chan["_id"]),
                    callback_data=f"build_select_{chan['_id']}",
                )
            ])

    if not buttons:
        await message.reply_text(
            "All your channels are disabled. Enable them in `/my_channels`."
        )
        return

    await message.reply_text(
        "Post Builder - Create New Post\n\n"
        "Select the target channel:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ─── CHANNEL SELECTION ────────────────────────────────────────────────

@app.on_callback_query(filters.regex(r"^build_select_(.+)"))
async def build_select_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    channel_id = callback_query.matches[0].group(1)
    try:
        channel_id_val = int(channel_id)
    except ValueError:
        channel_id_val = channel_id

    draft = {
        "draft_id": str(user_id),
        "user_id": user_id,
        "channel_id": channel_id_val,
        "media_type": "text",
        "file_id": None,
        "media_files": [],
        "caption": "",
        "custom_buttons": [],
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
        "state": "awaiting_media",
        "created_at": datetime.datetime.now(datetime.timezone.utc),
    }
    await database.save_post_draft(user_id, draft)
    await callback_query.answer()
    await callback_query.message.edit_text(
        "Channel Selected\n\n"
        "Send the media (Photo, Video, Audio, Document, GIF) or type the text message you want to post."
    )


# ─── /cancel SUPPORT ──────────────────────────────────────────────────

async def handle_cancel(client: Client, message: Message) -> bool:
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    if text.lower() == "/cancel":
        draft = await database.get_post_draft(user_id)
        if draft:
            await database.delete_post_draft(user_id)
            await message.reply_text("Post builder session cancelled.")
        return True
    return False


# ─── INPUT HANDLERS (group=5) ─────────────────────────────────────────

@app.on_message(filters.private & ~banned_filter, group=5)
async def builder_input_handler(client: Client, message: Message):
    current_update_info.set({
        "handler": "builder_input_handler",
        "update_id": message.id,
        "message_id": message.id,
    })
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""

    if await handle_cancel(client, message):
        message.stop_propagation()
        return

    draft = await database.get_post_draft(user_id)
    if not draft:
        return

    state = draft.get("state")
    valid_states = [
        "awaiting_media",
        "awaiting_caption",
        "awaiting_buttons",
        "awaiting_reactions",
        "awaiting_poster_photo",
        "awaiting_poster_video",
        "awaiting_download_files",
        "awaiting_schedule_time",
        "awaiting_repost_interval",
        "awaiting_delete_gap",
    ]
    if not state or state not in valid_states:
        return

    # ── awaiting_media ──
    if state == "awaiting_media":
        if message.media_group_id:
            media_files = draft.get("media_files", [])
            file_id, file_unique_id, file_name, file_type, file_size, caption = extract_file_details(message)
            if file_id:
                media_type = "document"
                if file_type == "photo":
                    media_type = "photo"
                elif file_type in ("video", "animation"):
                    media_type = "video"
                elif file_type in ("audio", "voice"):
                    media_type = "audio"
                if not any(f["file_id"] == file_id for f in media_files):
                    media_files.append({"file_id": file_id, "media_type": media_type})
                draft["media_files"] = media_files
                draft["media_type"] = "album"
                draft["media_group_id"] = message.media_group_id
                if caption and not draft.get("caption"):
                    draft["caption"] = caption
                await database.save_post_draft(user_id, draft)

            if not draft.get("_album_scheduled"):
                draft["_album_scheduled"] = True
                await database.save_post_draft(user_id, draft)

                async def _delayed_album_menu():
                    import asyncio
                    await asyncio.sleep(1.0)
                    latest = await database.get_post_draft(user_id)
                    if latest and latest.get("state") == "awaiting_media":
                        latest["state"] = "active"
                        latest["_album_scheduled"] = False
                        await database.save_post_draft(user_id, latest)
                        await show_builder_menu(client, message, user_id, latest)

                import asyncio
                asyncio.create_task(_delayed_album_menu())

            message.stop_propagation()
            return

        if message.text:
            if text.startswith("/") and text != "/cancel":
                return
            draft["media_type"] = "text"
            draft["caption"] = text
        else:
            file_id, file_unique_id, file_name, file_type, file_size, caption = extract_file_details(message)
            if not file_id:
                await message.reply_text("Unsupported media format. Send a photo, video, audio, document, or text.")
                message.stop_propagation()
                return
            media_type = file_type
            if file_type == "animation":
                media_type = "animation"
            draft["media_type"] = media_type
            draft["file_id"] = file_id
            draft["caption"] = caption or ""

        draft["state"] = "active"
        await database.save_post_draft(user_id, draft)
        await show_builder_menu(client, message, user_id, draft)
        message.stop_propagation()
        return

    # ── awaiting_caption ──
    if state == "awaiting_caption":
        draft["caption"] = text
        draft["state"] = "active"
        await database.save_post_draft(user_id, draft)
        await message.reply_text("Caption updated!")
        await show_builder_menu(client, message, user_id, draft)
        message.stop_propagation()
        return

    # ── awaiting_buttons ──
    if state == "awaiting_buttons":
        parsed = parse_button_string(text)
        is_premium = await database.is_user_premium(user_id)
        if not is_premium and len(parsed) > 1:
            await message.reply_text(
                "Multi-Row Buttons is a Premium Feature.\n"
                "Free creators can only add 1 row. Upgrade with `/premium`."
            )
            message.stop_propagation()
            return
        draft["custom_buttons"] = parsed
        draft["state"] = "active"
        await database.save_post_draft(user_id, draft)
        await message.reply_text("Buttons configured!")
        await show_builder_menu(client, message, user_id, draft)
        message.stop_propagation()
        return

    # ── awaiting_reactions ──
    if state == "awaiting_reactions":
        reactions = [r.strip() for r in text.split() if r.strip()]
        is_premium = await database.is_user_premium(user_id)
        allowed_free = ["\u2764\ufe0f", "\ud83d\udd25", "\u26a1", "\ud83d\udc4d", "\ud83d\ude02", "\ud83c\udf89"]
        if not is_premium:
            invalid = [r for r in reactions if r not in allowed_free]
            if invalid:
                await message.reply_text(
                    "Custom Reactions is a Premium Feature.\n"
                    "Free creators can only use: \u2764\ufe0f \ud83d\udd25 \u26a1 \ud83d\udc4d \ud83d\ude02 \ud83c\udf89"
                )
                message.stop_propagation()
                return
        draft["reactions"] = reactions
        draft["reactions_enabled"] = len(reactions) > 0
        draft["state"] = "active"
        await database.save_post_draft(user_id, draft)
        await message.reply_text("Reactions configured!")
        await show_builder_menu(client, message, user_id, draft)
        message.stop_propagation()
        return

    # ── awaiting_poster_photo ──
    if state == "awaiting_poster_photo":
        if not message.photo:
            await message.reply_text("Please send a photo. Send /cancel to abort.")
            message.stop_propagation()
            return
        draft["poster_media"] = {"type": "photo", "file_id": message.photo.file_id}
        draft["state"] = "active"
        await database.save_post_draft(user_id, draft)
        await message.reply_text("Photo poster set!")
        await show_builder_menu(client, message, user_id, draft)
        message.stop_propagation()
        return

    # ── awaiting_poster_video ──
    if state == "awaiting_poster_video":
        if not message.video:
            await message.reply_text("Please send a video. Send /cancel to abort.")
            message.stop_propagation()
            return
        draft["poster_media"] = {"type": "video", "file_id": message.video.file_id}
        draft["state"] = "active"
        await database.save_post_draft(user_id, draft)
        await message.reply_text("Video poster set!")
        await show_builder_menu(client, message, user_id, draft)
        message.stop_propagation()
        return

    # ── awaiting_download_files ──
    if state == "awaiting_download_files":
        if text.lower() == "done":
            draft["state"] = "active"
            await database.save_post_draft(user_id, draft)
            await message.reply_text(f"Download files configured: {len(draft.get('download_files', []))} file(s).")
            await show_builder_menu(client, message, user_id, draft)
            message.stop_propagation()
            return

        if not (message.document or message.video or message.audio or message.file):
            await message.reply_text(
                "Send a file (document/video/audio) to create a download button.\n"
                "Send `done` when finished."
            )
            message.stop_propagation()
            return

        file_id, file_unique_id, file_name, file_type, file_size, _ = extract_file_details(message)
        if not file_id:
            await message.reply_text("Could not extract file. Send a valid file.")
            message.stop_propagation()
            return

        try:
            from utils.movie_download_buttons import create_download_button_config
            config_id = await create_download_button_config(
                user_id=user_id,
                name=file_name or "download",
                button_label="\ud83d\udce5 Download",
                link_type="direct",
                link_url="",
                file_id=file_id,
            )
            token = config_id
            bot_username = getattr(config, "BOT_USERNAME", "") or ""
            download_files = draft.get("download_files", [])
            download_files.append({
                "config_id": config_id,
                "label": file_name or "Download",
                "token": token,
                "file_id": file_id,
            })
            draft["download_files"] = download_files
            await database.save_post_draft(user_id, draft)
            await message.reply_text(
                f"File added: `{file_name}`\n"
                f"Total download files: {len(draft['download_files'])}\n\n"
                f"Send another file or `done` to finish."
            )
        except Exception as e:
            logger.error(f"Failed to create download config: {e}")
            await message.reply_text(f"Error creating download button: {e}")

        message.stop_propagation()
        return

    # ── awaiting_schedule_time ──
    if state == "awaiting_schedule_time":
        try:
            user_doc = await database.get_user(user_id)
            user_tz = user_doc.get("timezone", "Asia/Kolkata") if user_doc else "Asia/Kolkata"
            tz = ZoneInfo(user_tz)
            local_time = datetime.datetime.strptime(text, "%Y-%m-%d %H:%M")
            local_time = local_time.replace(tzinfo=tz)
            utc_time = local_time.astimezone(datetime.timezone.utc)

            if utc_time <= datetime.datetime.now(datetime.timezone.utc):
                await message.reply_text("Scheduled time must be in the future. Try again.")
                message.stop_propagation()
                return

            draft["scheduled_time"] = utc_time.isoformat()
            draft["schedule_enabled"] = True
            draft["state"] = "active"
            await database.save_post_draft(user_id, draft)

            display_time = local_time.strftime("%Y-%m-%d %I:%M %p")
            await message.reply_text(f"Scheduled for {display_time} {user_tz}")
            await show_builder_menu(client, message, user_id, draft)
        except ValueError:
            await message.reply_text(
                "Invalid format. Send time as: `YYYY-MM-DD HH:MM`\n"
                "Example: `2026-06-15 14:30`"
            )
        except Exception as e:
            logger.error(f"Schedule time parse error: {e}")
            await message.reply_text(f"Error parsing time: {e}")

        message.stop_propagation()
        return

    # ── awaiting_repost_interval ──
    if state == "awaiting_repost_interval":
        try:
            interval = int(text)
            if interval < 1:
                raise ValueError
            draft["repost_interval"] = interval
            draft["auto_repost_enabled"] = True
            draft["state"] = "active"
            await database.save_post_draft(user_id, draft)
            await message.reply_text(f"Auto repost interval set: {interval} minutes")
            await show_builder_menu(client, message, user_id, draft)
        except ValueError:
            await message.reply_text("Enter a valid interval in minutes (e.g. `60`).")
        message.stop_propagation()
        return

    # ── awaiting_delete_gap ──
    if state == "awaiting_delete_gap":
        try:
            gap = int(text)
            if gap < 0:
                raise ValueError
            draft["delete_gap"] = gap
            draft["state"] = "active"
            await database.save_post_draft(user_id, draft)
            await message.reply_text(f"Delete gap set: {gap} minutes")
            await show_builder_menu(client, message, user_id, draft)
        except ValueError:
            await message.reply_text("Enter a valid number in minutes (e.g. `30`).")
        message.stop_propagation()
        return


# ─── SHOW BUILDER MENU ────────────────────────────────────────────────

async def show_builder_menu(client: Client, message: Message, user_id: int, draft: dict):
    channel = await database.get_channel_by_id(draft["channel_id"])
    channel_title = channel.get("channel_title") if channel else str(draft["channel_id"])
    poster = draft.get("poster_media") or {}
    poster_type = poster.get("type") or "None"
    layout = draft.get("layout_type", "layout_a")
    dl_count = len(draft.get("download_files", []))
    btn_count = len(draft.get("custom_buttons", []))
    reactions_str = " ".join(draft.get("reactions", [])) or "Disabled"
    comments_on = draft.get("comments_enabled", False)
    pin_on = draft.get("pin_message", False)

    menu_text = (
        f"Post Builder Menu\n\n"
        f"Channel: {channel_title}\n"
        f"Media: {draft['media_type'].upper()}\n"
        f"Caption: {len(draft.get('caption', ''))} chars\n"
        f"Poster: {poster_type}\n"
        f"Layout: {layout.upper()}\n"
        f"Downloads: {dl_count}\n"
        f"Buttons: {btn_count} rows\n"
        f"Reactions: {reactions_str}\n"
        f"Comments: {'On' if comments_on else 'Off'}\n"
        f"Pin: {'On' if pin_on else 'Off'}\n\n"
        f"Configure your post:"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Edit Caption", callback_data="build_btn_caption"),
            InlineKeyboardButton("Poster", callback_data="build_btn_poster"),
        ],
        [
            InlineKeyboardButton("URL Buttons", callback_data="build_btn_buttons"),
            InlineKeyboardButton("Reactions", callback_data="build_btn_reactions"),
        ],
        [
            InlineKeyboardButton(f"Comments: {'On' if comments_on else 'Off'}", callback_data="build_btn_comments"),
            InlineKeyboardButton(f"Layout: {layout.upper()}", callback_data="build_btn_layout"),
        ],
        [
            InlineKeyboardButton(f"Pin: {'On' if pin_on else 'Off'}", callback_data="build_btn_pin"),
            InlineKeyboardButton("Download Files", callback_data="build_btn_download_files"),
        ],
        [
            InlineKeyboardButton("Preview", callback_data="build_btn_preview"),
            InlineKeyboardButton("Send Now", callback_data="build_btn_send"),
        ],
        [
            InlineKeyboardButton("Schedule", callback_data="build_btn_schedule"),
            InlineKeyboardButton("Auto Repost", callback_data="build_btn_repost"),
        ],
        [
            InlineKeyboardButton("Cancel", callback_data="build_btn_cancel"),
        ],
    ])

    await client.send_message(chat_id=user_id, text=menu_text, reply_markup=keyboard)


# ─── CALLBACK HANDLER ─────────────────────────────────────────────────

@app.on_callback_query(filters.regex(r"^build_btn_(.+)"))
async def builder_menu_callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    action = callback_query.matches[0].group(1)

    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired. Please start over.", show_alert=True)
        try:
            await callback_query.message.delete()
        except Exception:
            pass
        return

    bot_username = getattr(config, "BOT_USERNAME", "") or ""

    # ── caption ──
    if action == "caption":
        await callback_query.answer()
        draft["state"] = "awaiting_caption"
        await database.save_post_draft(user_id, draft)
        await callback_query.message.reply_text(
            "Send the new caption text now.\n"
            "You can use bold, italic, spoilers, and links.\n"
            "Send /cancel to abort."
        )

    # ── buttons ──
    elif action == "buttons":
        await callback_query.answer()
        draft["state"] = "awaiting_buttons"
        await database.save_post_draft(user_id, draft)
        await callback_query.message.reply_text(
            "Configure URL Buttons\n\n"
            "Format: `[Button Text | https://link.com]`\n"
            "Multiple in a row: `[Btn1 | link1] [Btn2 | link2]`\n\n"
            "Send /cancel to abort."
        )

    # ── reactions ──
    elif action == "reactions":
        await callback_query.answer()
        draft["state"] = "awaiting_reactions"
        await database.save_post_draft(user_id, draft)
        await callback_query.message.reply_text(
            "Configure Reactions\n\n"
            "Send emojis separated by spaces:\n"
            "Example: `\u2764\ufe0f \ud83d\udd25 \u26a1 \ud83d\udc4d`"
        )

    # ── comments ──
    elif action == "comments":
        comments_url = await get_comments_url(client, draft["channel_id"])
        if not comments_url:
            await callback_query.answer(
                "Comments unavailable. No linked discussion group found.",
                show_alert=True,
            )
            return
        await callback_query.answer()
        draft["comments_enabled"] = not draft.get("comments_enabled", False)
        await database.save_post_draft(user_id, draft)
        try:
            await callback_query.message.delete()
        except Exception:
            pass
        await show_builder_menu(client, callback_query.message, user_id, draft)

    # ── poster ──
    elif action == "poster":
        await callback_query.answer()
        poster = draft.get("poster_media") or {}
        has_poster = poster.get("file_id") is not None

        rows = [
            [InlineKeyboardButton("Upload Photo Poster", callback_data="build_poster_photo")],
            [InlineKeyboardButton("Upload Video Poster", callback_data="build_poster_video")],
        ]
        if has_poster:
            rows.append([InlineKeyboardButton("Change Poster", callback_data="build_poster_change")])
            rows.append([InlineKeyboardButton("Remove Poster", callback_data="build_poster_remove")])
        rows.append([InlineKeyboardButton("Back", callback_data="build_btn_back")])

        await callback_query.message.reply_text(
            f"Poster Settings\n\n"
            f"Current poster: {poster.get('type') or 'None'}\n\n"
            f"Choose an action:",
            reply_markup=InlineKeyboardMarkup(rows),
        )

    # ── layout ──
    elif action == "layout":
        await callback_query.answer()
        current = draft.get("layout_type", "layout_a")
        rows = [
            [
                InlineKeyboardButton(
                    f"{'>' if current == 'layout_a' else ''} Layout A (Single Download)",
                    callback_data="build_layout_layout_a",
                ),
            ],
            [
                InlineKeyboardButton(
                    f"{'>' if current == 'layout_b' else ''} Layout B (480p/720p/1080p)",
                    callback_data="build_layout_layout_b",
                ),
            ],
            [
                InlineKeyboardButton(
                    f"{'>' if current == 'layout_c' else ''} Layout C (Download/Watch/Trailer)",
                    callback_data="build_layout_layout_c",
                ),
            ],
            [
                InlineKeyboardButton(
                    f"{'>' if current == 'layout_d' else ''} Layout D (Download+Comments)",
                    callback_data="build_layout_layout_d",
                ),
            ],
            [InlineKeyboardButton("Back", callback_data="build_btn_back")],
        ]
        await callback_query.message.reply_text(
            "Select Layout Type\n\n"
            f"Current: {current.upper()}\n\n"
            "Layout A: Single Download button\n"
            "Layout B: 480p / 720p / 1080p quality buttons\n"
            "Layout C: Download / Watch Online / Trailer\n"
            "Layout D: Download + Comments row",
            reply_markup=InlineKeyboardMarkup(rows),
        )

    # ── pos ──
    elif action == "pos":
        await callback_query.answer()
        draft["caption_above"] = not draft.get("caption_above", False)
        await database.save_post_draft(user_id, draft)
        try:
            await callback_query.message.delete()
        except Exception:
            pass
        await show_builder_menu(client, callback_query.message, user_id, draft)

    # ── pin ──
    elif action == "pin":
        await callback_query.answer()
        draft["pin_message"] = not draft.get("pin_message", False)
        await database.save_post_draft(user_id, draft)
        try:
            await callback_query.message.delete()
        except Exception:
            pass
        await show_builder_menu(client, callback_query.message, user_id, draft)

    # ── download_files ──
    elif action == "download_files":
        await callback_query.answer()
        draft["state"] = "awaiting_download_files"
        await database.save_post_draft(user_id, draft)
        existing = len(draft.get("download_files", []))
        await callback_query.message.reply_text(
            f"Download Files\n\n"
            f"Current files: {existing}\n\n"
            f"Send a file (document/video/audio) to create a download button.\n"
            f"Send `done` when finished.\n"
            f"Send /cancel to abort."
        )

    # ── preview ──
    elif action == "preview":
        await callback_query.answer()
        try:
            await callback_query.message.delete()
        except Exception:
            pass
        await show_post_preview(client, user_id, draft)

    # ── send ──
    elif action == "send":
        await callback_query.answer()
        try:
            await callback_query.message.delete()
        except Exception:
            pass
        success, error_msg = await send_post_now(client, user_id, draft)
        if success:
            await client.send_message(user_id, "Post sent successfully!")
            await database.delete_post_draft(user_id)
        else:
            await client.send_message(
                user_id,
                f"Failed to send post.\n\nError: `{error_msg}`\n\nCheck bot permissions in the channel.",
            )

    # ── schedule ──
    elif action == "schedule":
        await callback_query.answer()
        draft["state"] = "awaiting_schedule_time"
        await database.save_post_draft(user_id, draft)
        user_doc = await database.get_user(user_id)
        user_tz = user_doc.get("timezone", "Asia/Kolkata") if user_doc else "Asia/Kolkata"
        await callback_query.message.edit_text(
            "Post Scheduling\n\n"
            "Send the time to publish in format:\n"
            "`YYYY-MM-DD HH:MM`\n\n"
            f"Your timezone: {user_tz}\n"
            "Example: `2026-06-15 14:30`"
        )

    # ── repost ──
    elif action == "repost":
        is_premium = await database.is_user_premium(user_id)
        if not is_premium:
            await callback_query.answer("Auto Reposting is a Premium Feature!", show_alert=True)
            return
        await callback_query.answer()
        draft["state"] = "awaiting_repost_interval"
        await database.save_post_draft(user_id, draft)
        await callback_query.message.edit_text(
            "Auto Reposting Setup\n\n"
            "Enter the repost interval in minutes:\n"
            "Example: `60` (for every 1 hour)"
        )

    # ── cancel ──
    elif action == "cancel":
        await callback_query.answer()
        await database.delete_post_draft(user_id)
        await callback_query.message.edit_text("Post builder session cancelled.")

    # ── continue ──
    elif action == "continue":
        await callback_query.answer()
        try:
            await callback_query.message.delete()
        except Exception:
            pass
        await show_builder_menu(client, callback_query.message, user_id, draft)

    # ── new ──
    elif action == "new":
        await callback_query.answer()
        await database.delete_post_draft(user_id)
        channels = await database.get_creator_channels(user_id)
        buttons = []
        for chan in channels:
            if chan.get("service_enabled", True):
                buttons.append([
                    InlineKeyboardButton(
                        chan.get("channel_title") or chan.get("title") or str(chan["_id"]),
                        callback_data=f"build_select_{chan['_id']}",
                    )
                ])
        await callback_query.message.edit_text(
            "Post Builder - Create New Post\n\n"
            "Select the target channel:",
            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
        )

    # ── back (from sub-menus) ──
    elif action == "back":
        await callback_query.answer()
        try:
            await callback_query.message.delete()
        except Exception:
            pass
        await show_builder_menu(client, callback_query.message, user_id, draft)


# ─── POSTER SUB-MENU CALLBACKS ────────────────────────────────────────

@app.on_callback_query(filters.regex(r"^build_poster_(photo|video|change|remove)$"))
async def poster_menu_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    sub = callback_query.matches[0].group(1)
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    if sub == "photo":
        await callback_query.answer()
        draft["state"] = "awaiting_poster_photo"
        await database.save_post_draft(user_id, draft)
        await callback_query.message.reply_text(
            "Send a photo to use as the poster.\nSend /cancel to abort."
        )

    elif sub == "video":
        await callback_query.answer()
        draft["state"] = "awaiting_poster_video"
        await database.save_post_draft(user_id, draft)
        await callback_query.message.reply_text(
            "Send a video to use as the poster.\nSend /cancel to abort."
        )

    elif sub == "change":
        await callback_query.answer()
        poster = draft.get("poster_media") or {}
        rows = [
            [InlineKeyboardButton("Upload Photo Poster", callback_data="build_poster_photo")],
            [InlineKeyboardButton("Upload Video Poster", callback_data="build_poster_video")],
            [InlineKeyboardButton("Remove Poster", callback_data="build_poster_remove")],
            [InlineKeyboardButton("Back", callback_data="build_btn_back")],
        ]
        await callback_query.message.reply_text(
            f"Current poster: {poster.get('type') or 'None'}\nChoose new type:",
            reply_markup=InlineKeyboardMarkup(rows),
        )

    elif sub == "remove":
        await callback_query.answer()
        draft["poster_media"] = {"type": None, "file_id": None}
        draft["state"] = "active"
        await database.save_post_draft(user_id, draft)
        try:
            await callback_query.message.delete()
        except Exception:
            pass
        await callback_query.message.reply_text("Poster removed!")
        await show_builder_menu(client, callback_query.message, user_id, draft)


# ─── LAYOUT SELECTION CALLBACKS ───────────────────────────────────────

@app.on_callback_query(filters.regex(r"^build_layout_(.+)$"))
async def layout_select_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    layout_type = callback_query.matches[0].group(1)
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    valid_layouts = ["layout_a", "layout_b", "layout_c", "layout_d"]
    if layout_type not in valid_layouts:
        await callback_query.answer("Invalid layout.", show_alert=True)
        return

    draft["layout_type"] = layout_type
    draft["state"] = "active"
    await database.save_post_draft(user_id, draft)
    await callback_query.answer()
    try:
        await callback_query.message.delete()
    except Exception:
        pass
    await callback_query.message.reply_text(f"Layout set to {layout_type.upper()}")
    await show_builder_menu(client, callback_query.message, user_id, draft)


# ─── PREVIEW ──────────────────────────────────────────────────────────

async def show_post_preview(client: Client, user_id: int, draft: dict):
    caption = draft.get("caption", "")
    comments_url = None
    if draft.get("comments_enabled"):
        comments_url = await get_comments_url(client, draft["channel_id"])

    layout_type = draft.get("layout_type", "layout_a")
    bot_username = getattr(config, "BOT_USERNAME", "") or ""
    reply_markup = build_post_keyboard(
        download_configs=draft.get("download_files", []),
        custom_buttons=draft.get("custom_buttons", []),
        reactions=draft.get("reactions", []),
        reaction_counts=None,
        comments_url=comments_url,
        layout_type=layout_type,
        bot_username=bot_username,
    )

    poster = draft.get("poster_media") or {}
    poster_type = poster.get("type")
    poster_file_id = poster.get("file_id")
    media_type = draft.get("media_type", "text")
    file_id = draft.get("file_id")

    await client.send_message(user_id, "POST PREVIEW")
    await client.send_message(user_id, "---")

    try:
        if poster_type == "photo" and poster_file_id:
            if caption and draft.get("caption_above"):
                await client.send_message(
                    chat_id=user_id,
                    text=build_telegram_caption_html(caption),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )
                await client.send_photo(
                    chat_id=user_id,
                    photo=poster_file_id,
                )
            elif caption:
                await client.send_photo(
                    chat_id=user_id,
                    photo=poster_file_id,
                    caption=build_telegram_caption_html(caption),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )
            else:
                await client.send_photo(
                    chat_id=user_id,
                    photo=poster_file_id,
                    reply_markup=reply_markup,
                )

        elif poster_type == "video" and poster_file_id:
            if caption and draft.get("caption_above"):
                await client.send_message(
                    chat_id=user_id,
                    text=build_telegram_caption_html(caption),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )
                await client.send_video(
                    chat_id=user_id,
                    video=poster_file_id,
                )
            elif caption:
                await client.send_video(
                    chat_id=user_id,
                    video=poster_file_id,
                    caption=build_telegram_caption_html(caption),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )
            else:
                await client.send_video(
                    chat_id=user_id,
                    video=poster_file_id,
                    reply_markup=reply_markup,
                )

        elif media_type == "text":
            await client.send_message(
                chat_id=user_id,
                text=build_telegram_caption_html(caption) if caption else "",
                reply_markup=reply_markup,
                parse_mode="html",
            )

        elif media_type == "album":
            media = []
            for file in draft.get("media_files", []):
                if file["media_type"] == "photo":
                    media.append(InputMediaPhoto(file["file_id"]))
                elif file["media_type"] in ("video", "animation"):
                    media.append(InputMediaVideo(file["file_id"]))
            if media:
                await client.send_media_group(chat_id=user_id, media=media)
                await client.send_message(
                    chat_id=user_id,
                    text=build_telegram_caption_html(caption or ""),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )

        elif media_type in ("photo",) and file_id:
            if caption and draft.get("caption_above"):
                await client.send_message(
                    chat_id=user_id,
                    text=build_telegram_caption_html(caption),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )
                await client.send_cached_media(chat_id=user_id, file_id=file_id)
            elif caption:
                await client.send_cached_media(
                    chat_id=user_id,
                    file_id=file_id,
                    caption=build_telegram_caption_html(caption),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )
            else:
                await client.send_cached_media(chat_id=user_id, file_id=file_id)

        elif media_type in ("video", "animation") and file_id:
            if caption and draft.get("caption_above"):
                await client.send_message(
                    chat_id=user_id,
                    text=build_telegram_caption_html(caption),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )
                await client.send_cached_media(chat_id=user_id, file_id=file_id)
            elif caption:
                await client.send_cached_media(
                    chat_id=user_id,
                    file_id=file_id,
                    caption=build_telegram_caption_html(caption),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )
            else:
                await client.send_cached_media(chat_id=user_id, file_id=file_id)

        elif media_type in ("audio", "document") and file_id:
            await client.send_cached_media(
                chat_id=user_id,
                file_id=file_id,
                caption=build_telegram_caption_html(caption) if caption else "",
                reply_markup=reply_markup,
                parse_mode="html" if caption else None,
            )

        else:
            if caption:
                await client.send_message(
                    chat_id=user_id,
                    text=build_telegram_caption_html(caption),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )

    except Exception as e:
        logger.error(f"Error showing preview: {e}", exc_info=True)
        await client.send_message(user_id, f"Error rendering preview: {e}")

    await client.send_message(user_id, "---")
    await show_builder_menu(client, Message(id=0), user_id, draft)


# ─── SEND POST NOW ────────────────────────────────────────────────────

async def send_post_now(client: Client, user_id: int, draft: dict) -> tuple[bool, str | None]:
    channel_id = draft["channel_id"]
    caption = draft.get("caption", "")
    comments_url = None
    if draft.get("comments_enabled"):
        comments_url = await get_comments_url(client, channel_id)

    layout_type = draft.get("layout_type", "layout_a")
    bot_username = getattr(config, "BOT_USERNAME", "") or ""
    reply_markup = build_post_keyboard(
        download_configs=draft.get("download_files", []),
        custom_buttons=draft.get("custom_buttons", []),
        reactions=draft.get("reactions", []),
        reaction_counts=None,
        comments_url=comments_url,
        layout_type=layout_type,
        bot_username=bot_username,
    )

    poster = draft.get("poster_media") or {}
    poster_type = poster.get("type")
    poster_file_id = poster.get("file_id")
    media_type = draft.get("media_type", "text")
    file_id = draft.get("file_id")

    try:
        msg = None

        if poster_type == "photo" and poster_file_id:
            if caption and draft.get("caption_above"):
                await client.send_message(
                    chat_id=channel_id,
                    text=build_telegram_caption_html(caption),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )
                msg = await client.send_photo(
                    chat_id=channel_id,
                    photo=poster_file_id,
                )
            elif caption:
                msg = await client.send_photo(
                    chat_id=channel_id,
                    photo=poster_file_id,
                    caption=build_telegram_caption_html(caption),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )
            else:
                msg = await client.send_photo(
                    chat_id=channel_id,
                    photo=poster_file_id,
                    reply_markup=reply_markup,
                )

        elif poster_type == "video" and poster_file_id:
            if caption and draft.get("caption_above"):
                await client.send_message(
                    chat_id=channel_id,
                    text=build_telegram_caption_html(caption),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )
                msg = await client.send_video(
                    chat_id=channel_id,
                    video=poster_file_id,
                )
            elif caption:
                msg = await client.send_video(
                    chat_id=channel_id,
                    video=poster_file_id,
                    caption=build_telegram_caption_html(caption),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )
            else:
                msg = await client.send_video(
                    chat_id=channel_id,
                    video=poster_file_id,
                    reply_markup=reply_markup,
                )

        elif media_type == "text":
            msg = await client.send_message(
                chat_id=channel_id,
                text=build_telegram_caption_html(caption) if caption else "",
                reply_markup=reply_markup,
                parse_mode="html",
            )

        elif media_type == "album":
            media = []
            for file in draft.get("media_files", []):
                if file["media_type"] == "photo":
                    media.append(InputMediaPhoto(file["file_id"]))
                elif file["media_type"] in ("video", "animation"):
                    media.append(InputMediaVideo(file["file_id"]))
            if media:
                await client.send_media_group(chat_id=channel_id, media=media)
            msg = await client.send_message(
                chat_id=channel_id,
                text=build_telegram_caption_html(caption or ""),
                reply_markup=reply_markup,
                parse_mode="html",
            )

        elif media_type in ("photo",) and file_id:
            if caption and draft.get("caption_above"):
                await client.send_message(
                    chat_id=channel_id,
                    text=build_telegram_caption_html(caption),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )
                msg = await client.send_cached_media(chat_id=channel_id, file_id=file_id)
            elif caption:
                msg = await client.send_cached_media(
                    chat_id=channel_id,
                    file_id=file_id,
                    caption=build_telegram_caption_html(caption),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )
            else:
                msg = await client.send_cached_media(chat_id=channel_id, file_id=file_id)

        elif media_type in ("video", "animation") and file_id:
            if caption and draft.get("caption_above"):
                await client.send_message(
                    chat_id=channel_id,
                    text=build_telegram_caption_html(caption),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )
                msg = await client.send_cached_media(chat_id=channel_id, file_id=file_id)
            elif caption:
                msg = await client.send_cached_media(
                    chat_id=channel_id,
                    file_id=file_id,
                    caption=build_telegram_caption_html(caption),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )
            else:
                msg = await client.send_cached_media(chat_id=channel_id, file_id=file_id)

        elif media_type in ("audio", "document") and file_id:
            msg = await client.send_cached_media(
                chat_id=channel_id,
                file_id=file_id,
                caption=build_telegram_caption_html(caption) if caption else "",
                reply_markup=reply_markup,
                parse_mode="html" if caption else None,
            )

        else:
            if caption:
                msg = await client.send_message(
                    chat_id=channel_id,
                    text=build_telegram_caption_html(caption),
                    reply_markup=reply_markup,
                    parse_mode="html",
                )

        if draft.get("pin_message") and msg:
            try:
                await client.pin_chat_message(chat_id=channel_id, message_id=msg.id)
            except (ChatAdminRequired, ChatWriteForbidden) as pin_err:
                logger.warning(f"Failed to pin post: {pin_err}")

        await database.increment_channel_stat(channel_id, "publishes", 1)
        return (True, None)

    except ChatWriteForbidden:
        return (False, "Bot cannot write to this channel. Check permissions.")
    except ChatAdminRequired:
        return (False, "Bot is not an admin in this channel.")
    except MessageTooLong:
        return (False, "Message is too long. Shorten the caption.")
    except PeerIdInvalid:
        return (False, "Invalid channel ID. Re-add the channel.")
    except ChannelPrivate:
        return (False, "Channel is private or bot has been removed.")
    except FloodWait as e:
        return (False, f"Telegram rate limit. Wait {e.value} seconds and try again.")
    except Exception as e:
        logger.error(f"Error publishing post: {e}", exc_info=True)
        return (False, str(e))


# ─── CHANNEL SETTINGS COMMAND ────────────────────────────────────────

@app.on_message(filters.command("channel_settings") & filters.private & ~banned_filter)
async def channel_settings_command_handler(client: Client, message: Message):
    from handlers.broadcast import my_channels_handler
    await my_channels_handler(client, message)
