from __future__ import annotations

import io
import uuid
import logging
import datetime
from typing import Optional

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from pyrogram.enums import ChatType, ParseMode

from bot import app
import database
import config
from utils.helpers import banned_filter
from utils.locks import user_locks
from utils.image_converter import ImageConverter
from utils.tmdb_client import TMDBClient

logger = logging.getLogger(__name__)

image_converter = ImageConverter()
tmdb_client = TMDBClient()

# ─── RATIO OPTIONS ────────────────────────────────────────────────────

RATIO_OPTIONS = {
    "original": "Original (no change)",
    "1:1": "Square (1:1)",
    "9:16": "Story (9:16)",
    "16:9": "Landscape (16:9)",
    "4:5": "Portrait (4:5)",
}

RATIO_STYLE_OPTIONS = {
    "crop": "Center Crop",
    "blur": "Blur Background",
}

# ─── BUTTON TYPES ──────────────────────────────────────────────────────

BUTTON_TYPES = {
    "deep_link": "Deep Link (/start)",
    "url": "Website URL",
    "channel": "Telegram Channel",
    "product": "Creator Store",
    "payment_upi": "UPI Payment",
    "payment_stars": "Telegram Stars",
    "payment_razorpay": "Razorpay",
}

# ─── LAYOUT TYPES ──────────────────────────────────────────────────────

LAYOUTS = {
    "layout_a": "Layout A - Single Download Button",
    "layout_b": "Layout B - Quality Buttons (480P/720P/1080P)",
    "layout_c": "Layout C - Download + Watch + Trailer",
    "layout_d": "Layout D - Download + Comments + Reactions",
}


# ═══════════════════════════════════════════════════════════════════════
#  /newpost COMMAND
# ═══════════════════════════════════════════════════════════════════════


@app.on_message(filters.command("newpost") & filters.private & ~banned_filter)
async def newpost_command(client: Client, message: Message):
    user_id = message.from_user.id

    async with user_locks[user_id]:
        channels = await database.get_creator_channels(user_id)
        if not channels:
            await message.reply_text(
                "⚠️ **No Channels Found**\n\n"
                "You need to add a channel first before creating posts.\n\n"
                "Use `/addchannel` to add your Telegram channel.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "➕ Add Channel", callback_data="pb_add_channel"
                            )
                        ]
                    ]
                ),
            )
            return

        # Check for existing draft
        draft = await database.get_post_draft(user_id)
        if draft and draft.get("state") not in ("idle", ""):
            buttons = [
                [
                    InlineKeyboardButton(
                        "📝 Continue Draft", callback_data="pb_continue_draft"
                    )
                ],
                [InlineKeyboardButton("🗑 Start Fresh", callback_data="pb_start_fresh")],
            ]
            await message.reply_text(
                "📝 **Existing Draft Found**\n\n"
                "You have an unfinished post draft. Would you like to continue it or start fresh?",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            return

        # Show channel selection
        await _show_channel_selection(message, channels)


async def _show_channel_selection(target, channels: list):
    buttons = []
    for ch in channels:
        ch_title = ch.get("channel_title") or ch.get("title") or "Unknown"
        ch_id = ch.get("channel_id", "")
        buttons.append(
            [InlineKeyboardButton(f"📢 {ch_title}", callback_data=f"pb_ch_{ch_id}")]
        )

    buttons.append(
        [InlineKeyboardButton("➕ Add Channel", callback_data="pb_add_channel")]
    )

    text = "📝 **New Post Builder**\n\nSelect the channel to publish to:"
    if hasattr(target, "reply_text"):
        await target.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await target.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))


# ═══════════════════════════════════════════════════════════════════════
#  DRAFT CONTINUATION / FRESH START
# ═══════════════════════════════════════════════════════════════════════


@app.on_callback_query(filters.regex(r"^pb_continue_draft$"))
async def continue_draft_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("No draft found.", show_alert=True)
        return

    await callback_query.answer()
    await _show_post_builder_menu(client, callback_query.message, user_id, draft)


@app.on_callback_query(filters.regex(r"^pb_start_fresh$"))
async def start_fresh_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    await database.delete_post_draft(user_id)
    await callback_query.answer()

    channels = await database.get_creator_channels(user_id)
    if not channels:
        await callback_query.message.edit_text(
            "⚠️ **No Channels Found**\n\nUse `/addchannel` to add your Telegram channel."
        )
        return

    await _show_channel_selection(callback_query.message, channels)


# ═══════════════════════════════════════════════════════════════════════
#  CHANNEL SELECTION
# ═══════════════════════════════════════════════════════════════════════


@app.on_callback_query(filters.regex(r"^pb_ch_(.+)$"))
async def select_channel_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    channel_id = callback_query.matches[0].group(1)

    # Try to parse channel_id as int
    try:
        channel_id_int = int(channel_id)
    except ValueError:
        channel_id_int = channel_id

    channel = await database.get_channel_by_id(channel_id_int)
    if not channel:
        await callback_query.answer("Channel not found.", show_alert=True)
        return

    await callback_query.answer()

    # Create new draft
    draft = {
        "user_id": user_id,
        "channel_id": channel_id_int,
        "channel_title": channel.get("channel_title")
        or channel.get("title", "Unknown"),
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
        "state": "awaiting_media",
        "image_ratio": None,
        "image_style": None,
    }
    await database.save_post_draft(user_id, draft)

    await _show_post_type_selection(callback_query.message, draft)


# ═══════════════════════════════════════════════════════════════════════
#  POST TYPE SELECTION
# ═══════════════════════════════════════════════════════════════════════


async def _show_post_type_selection(target, draft: dict):
    buttons = [
        [InlineKeyboardButton("📝 Text Post", callback_data="pb_type_text")],
        [InlineKeyboardButton("🖼 Photo Post", callback_data="pb_type_photo")],
        [InlineKeyboardButton("🎬 Video Post", callback_data="pb_type_video")],
        [InlineKeyboardButton("📄 Document Post", callback_data="pb_type_document")],
        [InlineKeyboardButton("🎬 Movie Template", callback_data="pb_movie_tmpl")],
        [InlineKeyboardButton("❌ Cancel", callback_data="pb_cancel")],
    ]

    text = (
        f"📢 **Channel:** {draft.get('channel_title', 'Unknown')}\n\n"
        "**Step 1:** Select post type:"
    )
    if hasattr(target, "edit_text"):
        await target.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await target.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^pb_type_(.+)$"))
async def select_type_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    post_type = callback_query.matches[0].group(1)

    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer(
            "Session expired. Start again with /newpost.", show_alert=True
        )
        return

    await callback_query.answer()

    draft["media_type"] = post_type

    if post_type == "text":
        draft["state"] = "awaiting_caption"
        await database.save_post_draft(user_id, draft)
        await _prompt_caption_input(callback_query.message, draft)
    elif post_type in ("photo", "video", "document"):
        draft["state"] = "awaiting_media"
        await database.save_post_draft(user_id, draft)
        await _prompt_media_upload(callback_query.message, draft, post_type)
    elif post_type == "movie":
        await database.save_post_draft(user_id, draft)
        await _show_movie_template_form(callback_query.message, draft)


# ═══════════════════════════════════════════════════════════════════════
#  MEDIA UPLOAD PROMPT + RATIO SELECTION
# ═══════════════════════════════════════════════════════════════════════


async def _prompt_media_upload(target, draft: dict, media_type: str):
    type_label = {"photo": "🖼 Photo", "video": "🎬 Video", "document": "📄 Document"}[
        media_type
    ]
    buttons = [
        [InlineKeyboardButton("✅ Skip (no media)", callback_data="pb_skip_media")]
    ]

    text = (
        f"{type_label} Post\n\n"
        f"**Step 2:** Send me the {media_type} to use as your post media.\n\n"
        "You can also reply to a message that contains the media."
    )
    if hasattr(target, "edit_text"):
        await target.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await target.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^pb_skip_media$"))
async def skip_media_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    await callback_query.answer()
    draft["state"] = "awaiting_caption"
    await database.save_post_draft(user_id, draft)
    await _prompt_caption_input(callback_query.message, draft)


# ═══════════════════════════════════════════════════════════════════════
#  IMAGE RATIO SELECTION (after photo upload)
# ═══════════════════════════════════════════════════════════════════════


async def _show_ratio_selection(target, draft: dict):
    buttons = []
    for ratio_key, ratio_label in RATIO_OPTIONS.items():
        buttons.append(
            [InlineKeyboardButton(ratio_label, callback_data=f"pb_ratio_{ratio_key}")]
        )
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="pb_cancel")])

    text = "📐 **Image Ratio Selection**\n\n" "Choose how to fit the image:"
    if hasattr(target, "edit_text"):
        await target.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await target.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^pb_ratio_(.+)$"))
async def select_ratio_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    ratio = callback_query.matches[0].group(1)

    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    await callback_query.answer()

    if ratio == "original":
        # No conversion needed
        draft["image_ratio"] = "original"
        draft["image_style"] = None
        draft["state"] = "awaiting_caption"
        await database.save_post_draft(user_id, draft)
        await _prompt_caption_input(callback_query.message, draft)
    else:
        draft["image_ratio"] = ratio
        # Show style selection (crop vs blur)
        buttons = [
            [InlineKeyboardButton("✂️ Center Crop", callback_data="pb_style_crop")],
            [InlineKeyboardButton("🌫 Blur Background", callback_data="pb_style_blur")],
            [InlineKeyboardButton("❌ Cancel", callback_data="pb_cancel")],
        ]
        await callback_query.message.edit_text(
            f"📐 **Ratio:** {ratio}\n\n" "**Step 3:** Choose fit style:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )


@app.on_callback_query(filters.regex(r"^pb_style_(.+)$"))
async def select_style_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    style = callback_query.matches[0].group(1)

    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    await callback_query.answer()

    # Process image with selected ratio and style
    poster = draft.get("poster_media", {})
    if poster.get("file_id") and poster.get("type") == "photo":
        status_msg = await callback_query.message.edit_text("⏳ Processing image...")

        try:
            file_id = poster["file_id"]
            image_bytes = await client.download_media(file_id, in_memory=True)
            processed_bytes = await image_converter.fit_image(
                image_bytes, draft["image_ratio"], style
            )

            processed_io = io.BytesIO(processed_bytes)
            processed_io.name = "processed.jpg"

            await client.send_photo(
                user_id,
                processed_io,
                caption="✅ **Image processed!** Here's the preview:",
            )

            draft["image_style"] = style
            draft["state"] = "awaiting_caption"
            await database.save_post_draft(user_id, draft)
            await _prompt_caption_input(status_msg, draft)

        except Exception as e:
            logger.error(f"Image processing failed: {e}")
            draft["image_style"] = style
            draft["state"] = "awaiting_caption"
            await database.save_post_draft(user_id, draft)
            await _prompt_caption_input(callback_query.message, draft)
    else:
        draft["image_style"] = style
        draft["state"] = "awaiting_caption"
        await database.save_post_draft(user_id, draft)
        await _prompt_caption_input(callback_query.message, draft)


# ═══════════════════════════════════════════════════════════════════════
#  CAPTION INPUT
# ═══════════════════════════════════════════════════════════════════════


async def _prompt_caption_input(target, draft: dict):
    buttons = [
        [InlineKeyboardButton("➡️ Skip Caption", callback_data="pb_skip_caption")],
        [InlineKeyboardButton("❌ Cancel", callback_data="pb_cancel")],
    ]

    text = (
        "✍️ **Caption**\n\n"
        "**Step 4:** Type your post caption.\n\n"
        "Supports Markdown formatting:\n"
        "• `*bold*` — **Bold text**\n"
        "• `_italic_` — *Italic text*\n"
        "• `` `code` `` — `Code`\n"
        "• `[link](url)` — Hyperlink\n\n"
        "Send your caption now:"
    )
    if hasattr(target, "edit_text"):
        await target.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await target.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^pb_skip_caption$"))
async def skip_caption_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    await callback_query.answer()
    draft["state"] = "awaiting_buttons"
    await database.save_post_draft(user_id, draft)
    await _show_button_builder_menu(callback_query.message, draft)


# ═══════════════════════════════════════════════════════════════════════
#  TEXT INPUT HANDLER (caption, button text, button URL, etc.)
# ═══════════════════════════════════════════════════════════════════════


@app.on_message(
    filters.private
    & filters.text
    & ~filters.command(
        [
            "start",
            "batch",
            "done",
            "cancel",
            "newpost",
            "help",
            "settings",
            "premium",
            "referral",
            "upload",
            "stats",
            "broadcast",
            "shorteners",
            "ads",
            "adstats",
            "traffic",
            "analytics",
            "advertise",
            "channel_stats",
            "searchmovie",
            "diag",
            "diagnose",
            "store",
            "mychannels",
            "channelsettings",
            "addchannel",
            "delchannel",
            "schedule",
            "reposts",
        ]
    )
    & ~banned_filter,
    group=3,
)
async def post_builder_text_handler(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip()

    builder_ctx = await database.get_active_builder_context(user_id)
    if not builder_ctx["exists"] or not builder_ctx["is_builder_state"]:
        return

    draft = builder_ctx["draft"]
    state = builder_ctx["state"]

    # Handle different builder states
    if state == "awaiting_caption":
        await _handle_caption_input(client, message, user_id, draft, text)
    elif state == "awaiting_btn_text":
        await _handle_btn_text_input(client, message, user_id, draft, text)
    elif state == "awaiting_btn_url":
        await _handle_btn_url_input(client, message, user_id, draft, text)
    elif state == "awaiting_btn_edit_text":
        await _handle_btn_edit_text_input(client, message, user_id, draft, text)
    elif state == "awaiting_btn_edit_url":
        await _handle_btn_edit_url_input(client, message, user_id, draft, text)
    elif state == "awaiting_tmdb_search":
        await _handle_tmdb_search_input(client, message, user_id, draft, text)
    elif state == "awaiting_schedule_time":
        await _handle_schedule_time_input(client, message, user_id, draft, text)
    elif state == "awaiting_manual_caption":
        await _handle_caption_input(client, message, user_id, draft, text)
    elif state == "awaiting_custom_timezone":
        await _handle_timezone_input(client, message, user_id, draft, text)

    message.stop_propagation()


async def _handle_caption_input(
    client: Client, message: Message, user_id: int, draft: dict, text: str
):
    draft["caption"] = text
    draft["state"] = "awaiting_buttons"
    await database.save_post_draft(user_id, draft)
    await _show_button_builder_menu(message, draft)


async def _handle_btn_text_input(
    client: Client, message: Message, user_id: int, draft: dict, text: str
):
    # Store pending button text, move to awaiting URL
    draft["pending_btn_text"] = text
    draft["state"] = "awaiting_btn_url"
    await database.save_post_draft(user_id, draft)

    buttons = [[InlineKeyboardButton("❌ Cancel", callback_data="pb_cancel_btn")]]
    await message.reply_text(
        f"📝 **Button Text:** `{text}`\n\n"
        "**Now enter the URL or deep link token:**\n\n"
        "Examples:\n"
        "• `https://example.com` — Website URL\n"
        "• `/start kgfmovie` — Deep link\n"
        "• `@channelname` — Telegram channel\n"
        "• `upi://pay?...` — UPI payment link",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _handle_btn_url_input(
    client: Client, message: Message, user_id: int, draft: dict, text: str
):
    btn_text = draft.get("pending_btn_text", "Button")
    btn_type = draft.get("pending_btn_type", "url")

    # Build the button
    button = {
        "text": btn_text,
        "url": text,
        "type": btn_type,
        "id": uuid.uuid4().hex[:8],
    }

    custom_buttons = draft.get("custom_buttons", [])
    custom_buttons.append(button)
    draft["custom_buttons"] = custom_buttons
    draft["state"] = "awaiting_buttons"
    draft.pop("pending_btn_text", None)
    draft.pop("pending_btn_type", None)
    await database.save_post_draft(user_id, draft)

    await _show_button_builder_menu(message, draft)


async def _handle_btn_edit_text_input(
    client: Client, message: Message, user_id: int, draft: dict, text: str
):
    edit_idx = draft.get("editing_btn_index", -1)
    custom_buttons = draft.get("custom_buttons", [])
    if 0 <= edit_idx < len(custom_buttons):
        custom_buttons[edit_idx]["text"] = text
        draft["custom_buttons"] = custom_buttons
        draft["state"] = "awaiting_buttons"
        draft.pop("editing_btn_index", None)
        await database.save_post_draft(user_id, draft)
        await _show_button_builder_menu(message, draft)


async def _handle_btn_edit_url_input(
    client: Client, message: Message, user_id: int, draft: dict, text: str
):
    edit_idx = draft.get("editing_btn_index", -1)
    custom_buttons = draft.get("custom_buttons", [])
    if 0 <= edit_idx < len(custom_buttons):
        custom_buttons[edit_idx]["url"] = text
        draft["custom_buttons"] = custom_buttons
        draft["state"] = "awaiting_buttons"
        draft.pop("editing_btn_index", None)
        await database.save_post_draft(user_id, draft)
        await _show_button_builder_menu(message, draft)


async def _handle_tmdb_search_input(
    client: Client, message: Message, user_id: int, draft: dict, query: str
):
    status_msg = await message.reply_text(f"🔍 Searching TMDB for '**{query}**'...")

    results = await tmdb_client.search_movies(query)
    if not results:
        await status_msg.edit_text(
            "❌ No results found. Try a different search term.\n\n"
            "Type another movie name or /cancel to exit."
        )
        return

    buttons = []
    for idx, movie in enumerate(results):
        title = movie.get("title", "Unknown")
        year = movie.get("year", "")
        label = f"🎬 {title} ({year})" if year else f"🎬 {title}"
        buttons.append(
            [InlineKeyboardButton(label, callback_data=f"pb_tmdb_{movie['tmdb_id']}")]
        )
    buttons.append(
        [InlineKeyboardButton("🔍 Search Again", callback_data="pb_tmdb_again")]
    )
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="pb_cancel")])

    await status_msg.edit_text(
        f"🔍 **TMDB Results for:** `{query}`\n\nSelect a movie:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _handle_schedule_time_input(
    client: Client, message: Message, user_id: int, draft: dict, text: str
):
    try:
        # Parse datetime - expected format: DD-MM-YYYY HH:MM or YYYY-MM-DD HH:MM
        for fmt in (
            "%d-%m-%Y %H:%M",
            "%Y-%m-%d %H:%M",
            "%d/%m/%Y %H:%M",
            "%m/%d/%Y %H:%M",
        ):
            try:
                scheduled_time = datetime.datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError("Invalid format")

        # Make timezone-aware if needed
        if scheduled_time.tzinfo is None:
            scheduled_time = scheduled_time.replace(tzinfo=datetime.timezone.utc)

        if scheduled_time <= datetime.datetime.now(datetime.timezone.utc):
            await message.reply_text(
                "❌ **Invalid Time!**\n\nThe scheduled time must be in the future."
            )
            return

        await _publish_post(client, user_id, draft, scheduled_time=scheduled_time)

    except ValueError:
        await message.reply_text(
            "❌ **Invalid Format!**\n\n"
            "Use: `DD-MM-YYYY HH:MM` or `YYYY-MM-DD HH:MM`\n"
            "Example: `25-12-2026 18:00`"
        )


async def _handle_timezone_input(
    client: Client, message: Message, user_id: int, draft: dict, text: str
):
    # Validate timezone
    try:
        import pytz

        tz = pytz.timezone(text)
        draft["timezone"] = text
        await database.save_post_draft(user_id, draft)
        await message.reply_text(f"✅ Timezone set to: `{text}`")
        # Re-show schedule menu
        await _show_schedule_menu(message, draft)
    except Exception:
        await message.reply_text(
            "❌ **Invalid Timezone!**\n\n"
            "Example: `Asia/Kolkata`, `US/Eastern`, `UTC`"
        )


# ═══════════════════════════════════════════════════════════════════════
#  BUTTON BUILDER MENU
# ═══════════════════════════════════════════════════════════════════════


async def _show_button_builder_menu(target, draft: dict):
    custom_buttons = draft.get("custom_buttons", [])
    download_files = draft.get("download_files", [])

    btn_list = ""
    for i, btn in enumerate(custom_buttons):
        btn_list += f"  {i+1}. [{btn['text']}]({btn['url']})\n"
    if not btn_list:
        btn_list = "  _(None added yet)_\n"

    dl_list = ""
    for i, dl in enumerate(download_files):
        dl_list += f"  {i+1}. {dl.get('label', 'Download')} — `{dl.get('token', '')}`\n"
    if not dl_list:
        dl_list = "  _(None added yet)_\n"

    buttons = [
        [InlineKeyboardButton("🔗 Add Button", callback_data="pb_add_btn")],
        [InlineKeyboardButton("📥 Add Download File", callback_data="pb_add_dl")],
        [InlineKeyboardButton("📐 Select Layout", callback_data="pb_select_layout")],
        [InlineKeyboardButton("👁 Preview Post", callback_data="pb_preview")],
        [InlineKeyboardButton("💾 Save Draft", callback_data="pb_save_draft")],
        [InlineKeyboardButton("📅 Schedule", callback_data="pb_schedule")],
        [InlineKeyboardButton("🚀 Publish Now", callback_data="pb_publish")],
        [InlineKeyboardButton("❌ Cancel", callback_data="pb_cancel")],
    ]

    text = (
        "🔘 **Button Builder**\n\n"
        f"**Inline Buttons:**\n{btn_list}\n"
        f"**Download Files:**\n{dl_list}\n"
        "Choose an action:"
    )
    if hasattr(target, "edit_text"):
        await target.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await target.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


# ═══════════════════════════════════════════════════════════════════════
#  ADD BUTTON FLOW
# ═══════════════════════════════════════════════════════════════════════


@app.on_callback_query(filters.regex(r"^pb_add_btn$"))
async def add_btn_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    await callback_query.answer()

    buttons = [
        [InlineKeyboardButton("🌐 URL", callback_data="pb_bt_url")],
        [
            InlineKeyboardButton(
                "🔗 Deep Link (/start)", callback_data="pb_bt_deep_link"
            )
        ],
        [InlineKeyboardButton("📢 Channel Link", callback_data="pb_bt_channel")],
        [InlineKeyboardButton("🛒 Product Link", callback_data="pb_bt_product")],
        [InlineKeyboardButton("💳 UPI Payment", callback_data="pb_bt_payment_upi")],
        [
            InlineKeyboardButton(
                "⭐ Telegram Stars", callback_data="pb_bt_payment_stars"
            )
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="pb_cancel_btn")],
    ]

    await callback_query.message.edit_text(
        "🔗 **Add Button**\n\nSelect button type:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@app.on_callback_query(filters.regex(r"^pb_bt_(.+)$"))
async def btn_type_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    btn_type = callback_query.matches[0].group(1)

    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    await callback_query.answer()

    # Store button type and prompt for text
    draft["pending_btn_type"] = btn_type
    draft["state"] = "awaiting_btn_text"
    await database.save_post_draft(user_id, draft)

    type_label = BUTTON_TYPES.get(btn_type, btn_type)
    await callback_query.message.edit_text(
        f"🔗 **Add Button:** {type_label}\n\n"
        "**Enter the button text:**\n"
        "Example: `📥 Download Now` or `🎬 Watch Trailer`",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="pb_cancel_btn")]]
        ),
    )


@app.on_callback_query(filters.regex(r"^pb_cancel_btn$"))
async def cancel_btn_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    draft["state"] = "awaiting_buttons"
    draft.pop("pending_btn_text", None)
    draft.pop("pending_btn_type", None)
    draft.pop("editing_btn_index", None)
    await database.save_post_draft(user_id, draft)
    await callback_query.answer()
    await _show_button_builder_menu(callback_query.message, draft)


# ═══════════════════════════════════════════════════════════════════════
#  ADD DOWNLOAD FILE (Deep Link)
# ═══════════════════════════════════════════════════════════════════════


@app.on_callback_query(filters.regex(r"^pb_add_dl$"))
async def add_dl_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    await callback_query.answer()

    # Generate a deep link token
    token = f"dl_{uuid.uuid4().hex[:16]}"

    download_files = draft.get("download_files", [])
    download_files.append(
        {
            "label": "Download",
            "token": token,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
    )
    draft["download_files"] = download_files
    await database.save_post_draft(user_id, draft)

    buttons = [
        [
            InlineKeyboardButton(
                "✏️ Edit Label", callback_data=f"pb_dl_edit_{len(download_files)-1}"
            )
        ],
        [InlineKeyboardButton("➕ Add Another", callback_data="pb_add_dl")],
        [InlineKeyboardButton("✅ Done", callback_data="pb_done_dl")],
    ]

    await callback_query.message.edit_text(
        f"📥 **Download File Added!**\n\n"
        f"**Label:** Download\n"
        f"**Deep Link Token:** `{token}`\n"
        f"**Full URL:** `https://t.me/{config.BOT_USERNAME}?start={token}`\n\n"
        "This token will be used to deliver files when users click the button.",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@app.on_callback_query(filters.regex(r"^pb_done_dl$"))
async def done_dl_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    draft["state"] = "awaiting_buttons"
    await database.save_post_draft(user_id, draft)
    await callback_query.answer()
    await _show_button_builder_menu(callback_query.message, draft)


# ═══════════════════════════════════════════════════════════════════════
#  LAYOUT SELECTION
# ═══════════════════════════════════════════════════════════════════════


@app.on_callback_query(filters.regex(r"^pb_select_layout$"))
async def select_layout_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    await callback_query.answer()

    current_layout = draft.get("layout_type", "layout_a")
    buttons = []
    for layout_key, layout_label in LAYOUTS.items():
        marker = "✅ " if layout_key == current_layout else ""
        buttons.append(
            [
                InlineKeyboardButton(
                    f"{marker}{layout_label}", callback_data=f"pb_layout_{layout_key}"
                )
            ]
        )
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="pb_back_to_btns")])

    await callback_query.message.edit_text(
        "📐 **Select Layout**\n\n" "Choose how your post buttons appear:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@app.on_callback_query(filters.regex(r"^pb_layout_(.+)$"))
async def layout_selected_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    layout = callback_query.matches[0].group(1)

    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    draft["layout_type"] = layout
    await database.save_post_draft(user_id, draft)
    await callback_query.answer(f"Layout set to {layout}")
    await _show_button_builder_menu(callback_query.message, draft)


@app.on_callback_query(filters.regex(r"^pb_back_to_btns$"))
async def back_to_btns_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    await callback_query.answer()
    await _show_button_builder_menu(callback_query.message, draft)


# ═══════════════════════════════════════════════════════════════════════
#  POST PREVIEW
# ═══════════════════════════════════════════════════════════════════════


@app.on_callback_query(filters.regex(r"^pb_preview$"))
async def preview_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    await callback_query.answer()
    await _send_preview(client, user_id, draft)


async def _send_preview(client: Client, user_id: int, draft: dict):
    caption = draft.get("caption", "")
    media_type = draft.get("media_type", "text")
    poster = draft.get("poster_media", {})
    custom_buttons = draft.get("custom_buttons", [])
    download_files = draft.get("download_files", [])
    layout_type = draft.get("layout_type", "layout_a")

    # Build inline keyboard
    keyboard = _build_post_keyboard(custom_buttons, download_files, layout_type)

    preview_text = (
        f"👁 **POST PREVIEW**\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"📢 **Channel:** {draft.get('channel_title', 'Unknown')}\n"
        f"📝 **Type:** {media_type.title()}\n"
        f"📐 **Layout:** {layout_type}\n"
    )

    if caption:
        preview_text += f"\n**Caption:**\n{caption}\n"

    if custom_buttons:
        preview_text += f"\n**Buttons ({len(custom_buttons)}):**\n"
        for btn in custom_buttons:
            preview_text += f"  • [{btn['text']}]({btn['url']})\n"

    if download_files:
        preview_text += f"\n**Download Files ({len(download_files)}):**\n"
        for dl in download_files:
            preview_text += (
                f"  • {dl.get('label', 'Download')} — `{dl.get('token', '')}`\n"
            )

    preview_text += "\n━━━━━━━━━━━━━━━━━\n_Preview of how the post will appear_"

    # Send preview
    if poster.get("file_id") and poster.get("type") == "photo":
        try:
            await client.send_photo(
                user_id,
                poster["file_id"],
                caption=caption,
                reply_markup=keyboard if keyboard.inline_keyboard else None,
            )
        except Exception:
            await client.send_message(user_id, preview_text, reply_markup=keyboard)
    elif poster.get("file_id") and poster.get("type") == "video":
        try:
            await client.send_video(
                user_id,
                poster["file_id"],
                caption=caption,
                reply_markup=keyboard if keyboard.inline_keyboard else None,
            )
        except Exception:
            await client.send_message(user_id, preview_text, reply_markup=keyboard)
    else:
        await client.send_message(user_id, preview_text, reply_markup=keyboard)

    # Show action buttons
    action_buttons = [
        [InlineKeyboardButton("🚀 Publish Now", callback_data="pb_publish")],
        [InlineKeyboardButton("📅 Schedule", callback_data="pb_schedule")],
        [InlineKeyboardButton("💾 Save Draft", callback_data="pb_save_draft")],
        [InlineKeyboardButton("🔙 Back to Editor", callback_data="pb_back_to_btns")],
    ]
    await client.send_message(
        user_id,
        "⬆️ **Above is your post preview**\n\nWhat would you like to do?",
        reply_markup=InlineKeyboardMarkup(action_buttons),
    )


def _build_post_keyboard(
    custom_buttons: list, download_files: list, layout_type: str
) -> InlineKeyboardMarkup:
    keyboard_rows = []

    # Add download files based on layout
    if download_files:
        if layout_type == "layout_a":
            # Single download button
            dl = download_files[0]
            keyboard_rows.append(
                [
                    InlineKeyboardButton(
                        f"📥 {dl.get('label', 'Download')}",
                        url=f"https://t.me/{config.BOT_USERNAME}?start={dl['token']}",
                    )
                ]
            )
        elif layout_type == "layout_b":
            # Quality buttons
            row = []
            for dl in download_files[:3]:
                row.append(
                    InlineKeyboardButton(
                        dl.get("label", "Download"),
                        url=f"https://t.me/{config.BOT_USERNAME}?start={dl['token']}",
                    )
                )
            keyboard_rows.append(row)
        elif layout_type == "layout_c":
            # Download + Watch + Trailer
            for dl in download_files[:3]:
                keyboard_rows.append(
                    [
                        InlineKeyboardButton(
                            dl.get("label", "Download"),
                            url=f"https://t.me/{config.BOT_USERNAME}?start={dl['token']}",
                        )
                    ]
                )
        elif layout_type == "layout_d":
            # Download + Comments + Reactions
            dl = download_files[0]
            keyboard_rows.append(
                [
                    InlineKeyboardButton(
                        f"📥 {dl.get('label', 'Download')}",
                        url=f"https://t.me/{config.BOT_USERNAME}?start={dl['token']}",
                    )
                ]
            )

    # Add custom buttons
    for btn in custom_buttons:
        keyboard_rows.append([InlineKeyboardButton(btn["text"], url=btn["url"])])

    if not keyboard_rows:
        return InlineKeyboardMarkup([])

    return InlineKeyboardMarkup(keyboard_rows)


# ═══════════════════════════════════════════════════════════════════════
#  PUBLISH POST
# ═══════════════════════════════════════════════════════════════════════


@app.on_callback_query(filters.regex(r"^pb_publish$"))
async def publish_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    await callback_query.answer("Publishing...")
    await _publish_post(client, user_id, draft)


async def _publish_post(
    client: Client,
    user_id: int,
    draft: dict,
    scheduled_time: datetime.datetime | None = None,
):
    channel_id = draft.get("channel_id")
    caption = draft.get("caption", "")
    media_type = draft.get("media_type", "text")
    poster = draft.get("poster_media", {})
    custom_buttons = draft.get("custom_buttons", [])
    download_files = draft.get("download_files", [])
    layout_type = draft.get("layout_type", "layout_a")

    keyboard = _build_post_keyboard(custom_buttons, download_files, layout_type)

    status_msg_text = (
        "📅 Scheduling post..." if scheduled_time else "🚀 Publishing post..."
    )

    try:
        sent_message = None

        if poster.get("file_id") and poster.get("type") == "photo":
            sent_message = await client.send_photo(
                channel_id,
                poster["file_id"],
                caption=caption,
                reply_markup=keyboard if keyboard.inline_keyboard else None,
            )
        elif poster.get("file_id") and poster.get("type") == "video":
            sent_message = await client.send_video(
                channel_id,
                poster["file_id"],
                caption=caption,
                reply_markup=keyboard if keyboard.inline_keyboard else None,
            )
        else:
            sent_message = await client.send_message(
                channel_id,
                caption or "📝 New post",
                reply_markup=keyboard if keyboard.inline_keyboard else None,
            )

        if sent_message:
            # Record in post history
            await database.record_post(
                channel_id=channel_id,
                user_id=user_id,
                message_id=sent_message.id,
                media_type=media_type,
                caption=caption,
                buttons=custom_buttons,
            )

            # Increment channel stats
            await database.increment_channel_stat(channel_id, "published_posts", 1)

            # Clean up draft
            await database.delete_post_draft(user_id)

            success_text = (
                f"✅ **Post Published Successfully!**\n\n"
                f"📢 **Channel:** {draft.get('channel_title', 'Unknown')}\n"
                f"🆔 **Message ID:** `{sent_message.id}`\n"
                f"📝 **Type:** {media_type.title()}\n"
            )
            if scheduled_time:
                success_text = (
                    f"📅 **Post Scheduled Successfully!**\n\n"
                    f"📢 **Channel:** {draft.get('channel_title', 'Unknown')}\n"
                    f"🕒 **Scheduled For:** {scheduled_time.strftime('%Y-%m-%d %H:%M UTC')}\n"
                )

            buttons = [
                [
                    InlineKeyboardButton(
                        "📝 Create New Post", callback_data="pb_new_post"
                    )
                ]
            ]
            await client.send_message(
                user_id, success_text, reply_markup=InlineKeyboardMarkup(buttons)
            )

    except Exception as e:
        error_text = str(e).lower()
        if "admin" in error_text:
            await client.send_message(
                user_id,
                "❌ **Publish Failed!**\n\n"
                "The bot is not an admin in the target channel. "
                "Please add the bot as an admin with posting permissions.",
            )
        elif "forbidden" in error_text:
            await client.send_message(
                user_id,
                "❌ **Publish Failed!**\n\n"
                "The bot doesn't have permission to post in this channel.",
            )
        elif "long" in error_text:
            await client.send_message(
                user_id,
                "❌ **Publish Failed!**\n\n"
                "The message is too long. Please shorten your caption.",
            )
        else:
            await client.send_message(
                user_id, f"❌ **Publish Failed!**\n\nError: `{str(e)[:200]}`"
            )
        logger.error(f"Post publish failed: {e}")


@app.on_callback_query(filters.regex(r"^pb_new_post$"))
async def new_post_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    await database.delete_post_draft(user_id)
    await callback_query.answer()

    channels = await database.get_creator_channels(user_id)
    if not channels:
        await callback_query.message.edit_text(
            "⚠️ **No Channels Found**\n\nUse `/addchannel` to add your Telegram channel."
        )
        return

    await _show_channel_selection(callback_query.message, channels)


# ═══════════════════════════════════════════════════════════════════════
#  SAVE DRAFT
# ═══════════════════════════════════════════════════════════════════════


@app.on_callback_query(filters.regex(r"^pb_save_draft$"))
async def save_draft_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    draft["state"] = "idle"
    draft["saved_at"] = datetime.datetime.now(datetime.timezone.utc)
    await database.save_post_draft(user_id, draft)

    await callback_query.answer("Draft saved!")
    await callback_query.message.edit_text(
        "💾 **Draft Saved!**\n\n"
        "Your post has been saved as a draft.\n"
        "Use `/newpost` to continue editing or create a new post."
    )


# ═══════════════════════════════════════════════════════════════════════
#  SCHEDULE POST
# ═══════════════════════════════════════════════════════════════════════


@app.on_callback_query(filters.regex(r"^pb_schedule$"))
async def schedule_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    await callback_query.answer()
    await _show_schedule_menu(callback_query.message, draft)


async def _show_schedule_menu(target, draft: dict):
    buttons = [
        [InlineKeyboardButton("⏰ In 1 Hour", callback_data="pb_sched_1h")],
        [InlineKeyboardButton("🕐 In 3 Hours", callback_data="pb_sched_3h")],
        [InlineKeyboardButton("🕕 In 6 Hours", callback_data="pb_sched_6h")],
        [InlineKeyboardButton("🕐 In 12 Hours", callback_data="pb_sched_12h")],
        [InlineKeyboardButton("📅 Tomorrow", callback_data="pb_sched_24h")],
        [InlineKeyboardButton("✏️ Custom Time", callback_data="pb_sched_custom")],
        [InlineKeyboardButton("🔙 Back", callback_data="pb_back_to_btns")],
    ]

    text = (
        "📅 **Schedule Post**\n\n"
        f"**Current Timezone:** `{draft.get('timezone', 'UTC')}`\n\n"
        "Select schedule time:"
    )
    if hasattr(target, "edit_text"):
        await target.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await target.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^pb_sched_(\d+)h$"))
async def schedule_quick_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    hours = int(callback_query.matches[0].group(1))

    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    await callback_query.answer()
    scheduled_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        hours=hours
    )
    await _publish_post(client, user_id, draft, scheduled_time=scheduled_time)


@app.on_callback_query(filters.regex(r"^pb_sched_24h$"))
async def schedule_tomorrow_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id

    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    await callback_query.answer()
    scheduled_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        days=1
    )
    await _publish_post(client, user_id, draft, scheduled_time=scheduled_time)


@app.on_callback_query(filters.regex(r"^pb_sched_custom$"))
async def schedule_custom_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    draft["state"] = "awaiting_schedule_time"
    await database.save_post_draft(user_id, draft)

    await callback_query.answer()
    await callback_query.message.edit_text(
        "📅 **Custom Schedule**\n\n"
        f"**Timezone:** `{draft.get('timezone', 'UTC')}`\n\n"
        "Enter the date and time to publish:\n\n"
        "**Format:** `DD-MM-YYYY HH:MM`\n"
        "Example: `25-12-2026 18:00`\n\n"
        "Or use: `YYYY-MM-DD HH:MM`",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="pb_cancel")]]
        ),
    )


# ═══════════════════════════════════════════════════════════════════════
#  MOVIE TEMPLATE
# ═══════════════════════════════════════════════════════════════════════


@app.on_callback_query(filters.regex(r"^pb_movie_tmpl$"))
async def movie_template_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id

    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    await callback_query.answer()

    buttons = [
        [InlineKeyboardButton("🔍 Search TMDB", callback_data="pb_tmdb_search")],
        [InlineKeyboardButton("✏️ Enter Manually", callback_data="pb_movie_manual")],
        [InlineKeyboardButton("🔙 Back", callback_data="pb_back_to_type")],
    ]

    await callback_query.message.edit_text(
        "🎬 **Movie Post Template**\n\n" "How would you like to add movie data?",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@app.on_callback_query(filters.regex(r"^pb_tmdb_search$"))
async def tmdb_search_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id

    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    draft["state"] = "awaiting_tmdb_search"
    await database.save_post_draft(user_id, draft)

    await callback_query.answer()
    await callback_query.message.edit_text(
        "🔍 **TMDB Search**\n\n" "Enter the movie name to search:",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="pb_cancel")]]
        ),
    )


@app.on_callback_query(filters.regex(r"^pb_tmdb_(\d+)$"))
async def tmdb_select_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    tmdb_id = int(callback_query.matches[0].group(1))

    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    await callback_query.answer("Fetching movie details...")
    status_msg = await callback_query.message.edit_text(
        "⏳ Fetching movie details from TMDB..."
    )

    movie = await tmdb_client.get_movie_details(tmdb_id)
    if not movie:
        await status_msg.edit_text("❌ Failed to fetch movie details. Try again.")
        return

    # Build caption from movie data
    genres_str = ", ".join(movie.get("genres", []))
    caption = (
        f"🎬 **{movie.get('title', 'Unknown')}**\n\n"
        f"⭐ **Rating:** {movie.get('rating', 'N/A')}/10\n"
        f"🌍 **Language:** {movie.get('original_language', 'N/A').upper()}\n"
        f"🎭 **Genre:** {genres_str}\n"
        f"📅 **Release:** {movie.get('release_date', 'N/A')}\n"
        f"⏱ **Runtime:** {movie.get('runtime', 'N/A')}\n\n"
        f"📝 {movie.get('description', 'No description available.')}"
    )

    # Store movie data in draft
    draft["caption"] = caption
    draft["movie_data"] = {
        "tmdb_id": movie.get("tmdb_id"),
        "title": movie.get("title"),
        "rating": movie.get("rating"),
        "genres": movie.get("genres", []),
        "language": movie.get("original_language"),
        "poster_url": movie.get("poster_url"),
        "release_date": movie.get("release_date"),
    }
    draft["state"] = "awaiting_buttons"
    await database.save_post_draft(user_id, draft)

    # If poster URL exists, offer to use it
    buttons = [
        [InlineKeyboardButton("🖼 Use TMDB Poster", callback_data="pb_use_tmdb_poster")],
        [
            InlineKeyboardButton(
                "📤 Upload Custom Poster", callback_data="pb_upload_poster"
            )
        ],
        [InlineKeyboardButton("➡️ Skip Poster", callback_data="pb_skip_poster")],
    ]

    await status_msg.edit_text(
        f"🎬 **Movie Found!**\n\n"
        f"**{movie.get('title', 'Unknown')}** ({movie.get('year', '')})\n"
        f"⭐ {movie.get('rating', 'N/A')}/10\n\n"
        f"Caption has been auto-generated.\n\n"
        "Would you like to add a poster?",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@app.on_callback_query(filters.regex(r"^pb_use_tmdb_poster$"))
async def use_tmdb_poster_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    movie_data = draft.get("movie_data", {})
    poster_url = movie_data.get("poster_url")

    if not poster_url:
        await callback_query.answer("No poster URL available.", show_alert=True)
        return

    await callback_query.answer()
    draft["poster_media"] = {"type": "photo", "file_id": poster_url, "is_url": True}
    await database.save_post_draft(user_id, draft)

    await _show_button_builder_menu(callback_query.message, draft)


@app.on_callback_query(filters.regex(r"^pb_upload_poster$"))
async def upload_poster_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    draft["state"] = "awaiting_media"
    await database.save_post_draft(user_id, draft)

    await callback_query.answer()
    await callback_query.message.edit_text(
        "🖼 **Upload Poster**\n\n" "Send me the movie poster image:",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("➡️ Skip", callback_data="pb_skip_poster")]]
        ),
    )


@app.on_callback_query(filters.regex(r"^pb_skip_poster$"))
async def skip_poster_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    draft["state"] = "awaiting_buttons"
    await database.save_post_draft(user_id, draft)
    await callback_query.answer()
    await _show_button_builder_menu(callback_query.message, draft)


@app.on_callback_query(filters.regex(r"^pb_movie_manual$"))
async def movie_manual_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    draft["state"] = "awaiting_manual_caption"
    await database.save_post_draft(user_id, draft)

    await callback_query.answer()
    await callback_query.message.edit_text(
        "✏️ **Manual Movie Post**\n\n"
        "Type the movie caption in this format:\n\n"
        "```\n"
        "🎬 Movie Name\n\n"
        "⭐ Rating: 8.5\n"
        "🌍 Language: Hindi\n"
        "🎭 Genre: Action, Drama\n"
        "📅 Release: 2026\n\n"
        "📝 Description text here\n"
        "```\n\n"
        "Send your caption now:",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="pb_cancel")]]
        ),
        parse_mode=ParseMode.MARKDOWN,
    )


@app.on_callback_query(filters.regex(r"^pb_back_to_type$"))
async def back_to_type_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    await callback_query.answer()
    await _show_post_type_selection(callback_query.message, draft)


# ═══════════════════════════════════════════════════════════════════════
#  CANCEL / CLEANUP
# ═══════════════════════════════════════════════════════════════════════


@app.on_callback_query(filters.regex(r"^pb_cancel$"))
async def cancel_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    await database.delete_post_draft(user_id)
    await callback_query.answer("Post builder cancelled.")
    await callback_query.message.edit_text(
        "❌ **Post Builder Cancelled.**\n\nUse `/newpost` to start again."
    )


@app.on_callback_query(filters.regex(r"^pb_add_channel$"))
async def add_channel_redirect(client: Client, callback_query: CallbackQuery):
    await callback_query.answer()
    await callback_query.message.edit_text(
        "➕ **Add Channel**\n\n"
        "Use the `/addchannel` command to add your Telegram channel.\n\n"
        "**Steps:**\n"
        "1. Add the bot as an admin in your channel\n"
        "2. Send `/addchannel` with your channel username or ID\n\n"
        "Example: `/addchannel @mychannel`"
    )


@app.on_callback_query(filters.regex(r"^pb_dont_have_channel$"))
async def no_channel_callback(client: Client, callback_query: CallbackQuery):
    await callback_query.answer()
    await callback_query.message.edit_text(
        "📢 **Create a Channel First**\n\n"
        "To use the Post Builder, you need a Telegram channel.\n\n"
        "**How to create a channel:**\n"
        "1. Open Telegram\n"
        "2. Tap New Message → New Channel\n"
        "3. Follow the setup steps\n"
        "4. Add this bot as an admin\n"
        "5. Use `/addchannel` to register it"
    )


# ═══════════════════════════════════════════════════════════════════════
#  MEDIA HANDLER INTEGRATION
# ═══════════════════════════════════════════════════════════════════════


@app.on_message(
    filters.private
    & ~banned_filter
    & (filters.photo | filters.video | filters.document),
    group=4,
)
async def post_builder_media_handler(client: Client, message: Message):
    """Handle media uploads when in post builder media capture state."""
    user_id = message.from_user.id

    builder_ctx = await database.get_active_builder_context(user_id)
    if not builder_ctx["exists"]:
        return

    state = builder_ctx["state"]
    draft = builder_ctx["draft"]

    if state != "awaiting_media":
        return

    # Capture the media
    file_id = None
    media_type = None

    if message.photo:
        file_id = message.photo.file_id
        media_type = "photo"
    elif message.video:
        file_id = message.video.file_id
        media_type = "video"
    elif message.document:
        # Check if it's an image document
        file_name = message.document.file_name or ""
        ext = file_name.split(".")[-1].lower() if "." in file_name else ""
        if ext in ("jpg", "jpeg", "png", "webp", "gif"):
            file_id = message.document.file_id
            media_type = "photo"
        else:
            file_id = message.document.file_id
            media_type = "document"

    if not file_id:
        return

    draft["file_id"] = file_id
    draft["poster_media"] = {"type": media_type, "file_id": file_id}
    draft["media_type"] = media_type

    # Show ratio selection for photos
    if media_type == "photo":
        draft["state"] = "awaiting_media"  # Keep state while selecting ratio
        await database.save_post_draft(user_id, draft)
        await _show_ratio_selection(message, draft)
    else:
        draft["state"] = "awaiting_caption"
        await database.save_post_draft(user_id, draft)
        await _prompt_caption_input(message, draft)

    message.stop_propagation()
