from __future__ import annotations

import logging
import datetime
import uuid
import io
import os
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    InputMediaPhoto
)
from pyrogram.errors import MessageNotModified, FloodWait
from bot import app
import database
from utils.helpers import banned_filter
from utils.tmdb_client import TMDBClient
from utils.image_converter import ImageConverter
from utils.publisher import publish_post

logger = logging.getLogger(__name__)
tmdb_client = TMDBClient()
image_converter = ImageConverter()

# List of default emojis for reactions toggle
DEFAULT_REACTIONS = ["❤️", "🔥", "😂", "👍", "🎉", "🤔"]

# Genres list & languages list for manual entry flows
MANUAL_GENRES = ["Action", "Comedy", "Drama", "Horror", "Romance", "Thriller", "Fantasy", "Animation", "Crime", "Adventure", "Sci-Fi", "Mystery"]
MANUAL_LANGUAGES = ["hi", "kn", "ta", "te", "ml", "en", "es", "fr", "ko", "ja"]

def generate_genre_keyboard(selected_genres: list[str]) -> InlineKeyboardMarkup:
    rows = []
    current_row = []
    for g in MANUAL_GENRES:
        status = "✅" if g in selected_genres else "❌"
        current_row.append(InlineKeyboardButton(f"{g} {status}", callback_data=f"manual_genre_toggle_{g}"))
        if len(current_row) == 3:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    rows.append([InlineKeyboardButton("✨ Confirm Genres", callback_data="manual_genre_confirm")])
    return InlineKeyboardMarkup(rows)

def generate_language_keyboard(selected_lang: str) -> InlineKeyboardMarkup:
    rows = []
    current_row = []
    for l in MANUAL_LANGUAGES:
        formatted = tmdb_client.format_language(l)
        status = "✅" if l == selected_lang else "❌"
        current_row.append(InlineKeyboardButton(f"{formatted} {status}", callback_data=f"manual_lang_select_{l}"))
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    rows.append([InlineKeyboardButton("❌ Skip Language", callback_data="manual_lang_skip")])
    return InlineKeyboardMarkup(rows)

# Callbacks for Genre & Language Selection in Manual Flow
@app.on_callback_query(filters.regex(r"^manual_genre_toggle_(.+)$"))
async def manual_genre_toggle_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    genre = callback_query.matches[0].group(1)
    
    draft = await database.get_post_draft(user_id)
    if not draft or callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Invalid session", show_alert=True)
        return
        
    genres = draft.get("genres") or []
    if genre in genres:
        genres.remove(genre)
    else:
        genres.append(genre)
        
    draft["genres"] = genres
    await database.save_post_draft(user_id, draft)
    await callback_query.answer()
    
    try:
        await callback_query.message.edit_reply_markup(reply_markup=generate_genre_keyboard(genres))
    except MessageNotModified:
        pass

@app.on_callback_query(filters.regex(r"^manual_genre_confirm$"))
async def manual_genre_confirm_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft or callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Invalid session", show_alert=True)
        return
        
    draft["state"] = "awaiting_manual_lang"
    await database.save_post_draft(user_id, draft)
    await callback_query.answer()
    
    await callback_query.message.edit_text(
        "🌐 **Select Movie Language**:\n"
        "Choose the primary language for this movie:",
        reply_markup=generate_language_keyboard(draft.get("language", ""))
    )

async def build_and_save_manual_caption(user_id: int, draft: dict):
    # Format manual details to the EXACT caption format
    caption_lines = []
    
    title = draft.get("movie_title")
    year = draft.get("movie_year")
    if title:
        year_str = f" [{year}]" if year and year != "N/A" else ""
        caption_lines.append(f"<b>Movie:</b> {title}{year_str}")
        
    aka = draft.get("also_known_as")
    if aka and aka != "N/A":
        caption_lines.append(f"<i>Also Known As:</i> {aka}")
        
    rating = draft.get("rating", 0.0)
    rating_count = draft.get("rating_count", 0)
    if rating > 0.0:
        caption_lines.append(f"<b>Rating</b> ⭐: {rating} / 10 ({rating_count} user ratings)")
        
    runtime = draft.get("runtime")
    if runtime and runtime != "N/A":
        caption_lines.append(f"<b>Runtime:</b> {runtime}")
        
    rel_info = draft.get("release_info")
    if rel_info and rel_info != "N/A":
        caption_lines.append(f"<b>Release Info:</b> {rel_info}")
        
    genres = draft.get("genres")
    if genres:
        genre_emojis = tmdb_client.format_genres(genres)
        if genre_emojis:
            caption_lines.append(f"<b>Genre:</b> {genre_emojis}")
            
    lang = draft.get("language")
    if lang and lang != "N/A":
        caption_lines.append(f"<b>Language:</b> {lang}")

    draft["caption_html"] = "\n".join(caption_lines)
    draft["state"] = "awaiting_poster_upload"
    await database.save_post_draft(user_id, draft)

@app.on_callback_query(filters.regex(r"^manual_lang_select_(.+)$"))
async def manual_lang_select_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    lang_code = callback_query.matches[0].group(1)
    
    draft = await database.get_post_draft(user_id)
    if not draft or callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Invalid session", show_alert=True)
        return
        
    draft["language"] = tmdb_client.format_language(lang_code)
    await build_and_save_manual_caption(user_id, draft)
    await callback_query.answer()
    
    await callback_query.message.edit_text(
        "🖼 **Post Builder — Upload Poster**\n\n"
        "Caption saved! Now, please upload the poster image (JPG/PNG):"
    )

@app.on_callback_query(filters.regex(r"^manual_lang_skip$"))
async def manual_lang_skip_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft or callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Invalid session", show_alert=True)
        return
        
    draft["language"] = "N/A"
    await build_and_save_manual_caption(user_id, draft)
    await callback_query.answer()
    
    await callback_query.message.edit_text(
        "🖼 **Post Builder — Upload Poster**\n\n"
        "Caption saved! Now, please upload the poster image (JPG/PNG):"
    )


# Helper: Show Main Builder Menu
async def show_builder_menu(client: Client, chat_id: int, draft: dict):
    channel_name = draft.get("channel_name") or "Unknown"
    movie_title = draft.get("movie_title") or "N/A"
    movie_year = draft.get("movie_year") or "N/A"
    has_poster = "✅" if draft.get("poster_file_id") else "❌"
    
    caption_length = len(draft.get("caption_html") or "")
    caption_status = f"✅ ({caption_length} chars)" if caption_length > 0 else "❌"
    
    button_count = len(draft.get("url_buttons", []))
    
    reactions = draft.get("reactions", [])
    reactions_status = " ".join(reactions) if reactions else "Disabled"
    
    comments_status = "Enabled" if draft.get("comments_enabled") else "Disabled"
    pin_status = "Enabled" if draft.get("pin_message") else "Disabled"
    
    menu_text = (
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📢 **POST BUILDER**\n\n"
        f"**Channel:** {channel_name}\n\n"
        f"🎬 **Movie:** {movie_title} [{movie_year}]\n"
        f"🖼 **Poster:** {has_poster}\n"
        f"📝 **Caption:** {caption_status}\n"
        f"🔗 **Buttons:** {button_count}\n"
        f"❤️ **Reactions:** {reactions_status}\n"
        f"💬 **Comments:** {comments_status}\n"
        f"📌 **Pin:** {pin_status}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📝 Edit Caption", callback_data="builder_edit_caption"),
            InlineKeyboardButton("🔗 URL Buttons", callback_data="builder_url_buttons")
        ],
        [
            InlineKeyboardButton("❤️ Reactions", callback_data="builder_reactions"),
            InlineKeyboardButton("💬 Comments", callback_data="builder_comments")
        ],
        [
            InlineKeyboardButton("📌 Pin Post", callback_data="builder_pin"),
            InlineKeyboardButton("👁 Preview", callback_data="builder_preview")
        ],
        [
            InlineKeyboardButton("🚀 Send Now", callback_data="builder_send_now"),
            InlineKeyboardButton("📅 Schedule", callback_data="builder_schedule")
        ],
        [
            InlineKeyboardButton("🔄 Auto Repost", callback_data="builder_repost")
        ],
        [
            InlineKeyboardButton("❌ Cancel", callback_data="builder_cancel")
        ]
    ])
    
    await client.send_message(chat_id=chat_id, text=menu_text, reply_markup=keyboard)

# Command: /newpost (STATE 1: select_channel)
@app.on_message(filters.command("newpost") & filters.private & ~banned_filter)
async def newpost_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    channels = await database.get_creator_channels(user_id)
    if not channels:
        await message.reply_text(
            "❌ **No channels found.**\n\n"
            "Add a channel first using:\n"
            "`/add_channel [channel_username_or_id]`"
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
            "❌ All your channels are disabled. Enable them in `/my_channels`."
        )
        return

    await message.reply_text(
        "🎬 **Post Builder — Target Channel**\n\n"
        "Select the target channel for your post:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

# Callback: Target channel selected
@app.on_callback_query(filters.regex(r"^build_select_(.+)"))
async def build_select_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    channel_id_str = callback_query.matches[0].group(1)
    
    try:
        channel_id = int(channel_id_str)
    except ValueError:
        channel_id = channel_id_str

    channel = await database.get_channel_by_id(channel_id)
    channel_name = channel.get("channel_title") if channel else str(channel_id)

    draft = {
        "draft_id": str(uuid.uuid4()),
        "user_id": user_id,
        "channel_id": channel_id,
        "channel_name": channel_name,
        "tmdb_id": None,
        "movie_title": "N/A",
        "movie_year": "N/A",
        "also_known_as": "N/A",
        "rating": 0.0,
        "rating_count": 0,
        "runtime": "N/A",
        "release_info": "N/A",
        "genres": [],
        "language": "N/A",
        "tmdb_poster_url": "",
        "poster_file_id": None,
        "poster_processed": False,
        "poster_bg_style": None,
        "caption_html": "",
        "caption_edited": False,
        "url_buttons": [],
        "reactions_enabled": False,
        "reactions": [],
        "comments_enabled": False,
        "pin_message": False,
        "schedule_enabled": False,
        "scheduled_time": None,
        "schedule_timezone": "Asia/Kolkata",
        "repost_enabled": False,
        "repost_interval_minutes": None,
        "repost_delete_old": False,
        "state": "awaiting_tmdb_search",
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "updated_at": datetime.datetime.now(datetime.timezone.utc),
    }

    await database.save_post_draft(user_id, draft)
    await callback_query.answer()
    
    await callback_query.message.edit_text(
        "🎬 **Post Builder — Movie Search**\n\n"
        "Enter the movie name to search TMDB:\n"
        "Example: `Bhooth Bangla 2026`"
    )

# Callback: Skip TMDB (Manual caption)
@app.on_callback_query(filters.regex(r"^tmdb_skip$"))
async def tmdb_skip_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    draft["state"] = "awaiting_manual_movie_details"
    await database.save_post_draft(user_id, draft)
    await callback_query.answer()
    
    template_text = (
        "🎬 **Post Builder — Enter Movie Details**\n\n"
        "Copy the template below, fill it out, and send it back:\n\n"
        "```\n"
        "Title: Bhooth Bangla\n"
        "Year: 2026\n"
        "AKA: Ghost House\n"
        "Rating: 7.5\n"
        "Rating Count: 1240\n"
        "Runtime: 2h 30min\n"
        "Release: 15/5/2026 (India)\n"
        "```\n\n"
        "Send `/cancel` to abort."
    )
    await callback_query.message.edit_text(template_text)


# Callback: Movie selected
@app.on_callback_query(filters.regex(r"^tmdb_select_(\d+)$"))
async def tmdb_select_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    tmdb_id = int(callback_query.matches[0].group(1))
    
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    await callback_query.message.edit_text("⏳ Fetching movie details from TMDB...")
    await callback_query.answer()

    try:
        details = await tmdb_client.get_movie_details(tmdb_id)
        if not details:
            await callback_query.message.edit_text("❌ Failed to retrieve details. Try again or skip TMDB.")
            return

        # Update draft fields
        draft["tmdb_id"] = details["tmdb_id"]
        draft["movie_title"] = details["title"]
        draft["movie_year"] = details["year"]
        draft["also_known_as"] = details["also_known_as"]
        draft["rating"] = details["rating"]
        draft["rating_count"] = details["rating_count"]
        draft["runtime"] = details["runtime"]
        draft["release_info"] = details["release_info"]
        draft["genres"] = details["genres"]
        draft["language"] = tmdb_client.format_language(details["original_language"])
        draft["tmdb_poster_url"] = details["poster_url"]

        # Generate HTML Caption
        caption_lines = []
        
        imdb_id = details.get("imdb_id")
        title = details.get("title")
        year = details.get("year")
        if title:
            if imdb_id:
                title_link = f'<a href="https://www.imdb.com/title/{imdb_id}">{title}</a>'
            else:
                title_link = title
            year_str = f" [{year}]" if year else ""
            caption_lines.append(f"<b>Movie:</b> {title_link}{year_str}")
            
        aka = details.get("also_known_as")
        if aka and aka != "N/A":
            caption_lines.append(f"<i>Also Known As:</i> {aka}")
            
        rating = details.get("rating")
        rating_count = details.get("rating_count")
        if rating:
            caption_lines.append(f"<b>Rating</b> ⭐: {rating} / 10 ({rating_count} user ratings)")
            
        runtime = details.get("runtime")
        if runtime:
            caption_lines.append(f"<b>Runtime:</b> {runtime}")
            
        rel_info = details.get("release_info")
        if rel_info and "N/A" not in rel_info:
            caption_lines.append(f"<b>Release Info:</b> {rel_info}")
            
        genres = details.get("genres")
        if genres:
            genre_emojis = tmdb_client.format_genres(genres)
            if genre_emojis:
                caption_lines.append(f"<b>Genre:</b> {genre_emojis}")
                
        lang = details.get("original_language")
        if lang:
            lang_tag = tmdb_client.format_language(lang)
            caption_lines.append(f"<b>Language:</b> {lang_tag}")

        draft["caption_html"] = "\n".join(caption_lines)
        draft["state"] = "awaiting_poster_upload"
        await database.save_post_draft(user_id, draft)

        await callback_query.message.reply_text(
            "🖼 **Post Builder — Upload Poster**\n\n"
            "Please upload the poster image for this post (JPG/PNG).\n"
            "It will be automatically converted to a 1:1 square background."
        )
    except Exception as e:
        logger.error(f"Error handling tmdb selection: {e}", exc_info=True)
        await callback_query.message.reply_text("⚠️ Something went wrong while fetching details.")

# Callback: Background Poster Style Selection
@app.on_callback_query(filters.regex(r"^poster_style_(black|blur|white)$"))
async def poster_style_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    style = callback_query.matches[0].group(1)
    
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    await callback_query.answer(f"Processing {style} style...")
    
    original_fid = draft.get("original_photo_file_id")
    if not original_fid:
        await callback_query.message.reply_text("❌ Original poster not found. Please upload again.")
        return

    # Download original image
    temp_file = await client.download_media(original_fid)
    if not temp_file or not isinstance(temp_file, str):
        await callback_query.message.reply_text("❌ Failed to download original poster.")
        return

    try:
        with open(temp_file, "rb") as f:
            img_bytes = f.read()
            
        # Convert style
        processed_bytes = await image_converter.convert_to_square(img_bytes, style)
        
        # Upload processed photo
        sent_photo = await client.send_photo(
            chat_id=user_id,
            photo=io.BytesIO(processed_bytes)
        )
        if sent_photo and sent_photo.photo:
            processed_fid = sent_photo.photo.file_id
            await sent_photo.delete()
        else:
            raise Exception("Failed to send processed poster photo")

        # Update draft
        draft["poster_file_id"] = processed_fid
        draft["poster_bg_style"] = style
        await database.save_post_draft(user_id, draft)

        # Update preview message media
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"⬛ Black BG{' ✅' if style == 'black' else ''}", callback_data="poster_style_black"),
                InlineKeyboardButton(f"🌀 Blur BG{' ✅' if style == 'blur' else ''}", callback_data="poster_style_blur"),
                InlineKeyboardButton(f"⬜ White BG{' ✅' if style == 'white' else ''}", callback_data="poster_style_white")
            ],
            [
                InlineKeyboardButton("✅ Use This", callback_data="poster_confirm"),
                InlineKeyboardButton("🔄 Try Another Style", callback_data="poster_retry")
            ]
        ])
        
        await callback_query.message.edit_media(
            media=InputMediaPhoto(processed_fid, caption="Choose background style:"),
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error in poster style callback: {e}", exc_info=True)
        await callback_query.message.reply_text("⚠️ Image processing failed.")
    finally:
        if temp_file and os.path.exists(temp_file):
            os.remove(temp_file)

# Callback: Confirm Poster Selection
@app.on_callback_query(filters.regex(r"^poster_confirm$"))
async def poster_confirm_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    draft["poster_processed"] = True
    draft["state"] = "active"
    await database.save_post_draft(user_id, draft)
    await callback_query.answer("Poster confirmed!")
    
    await callback_query.message.delete()
    await show_builder_menu(client, user_id, draft)

# Callback: Retry Poster Upload
@app.on_callback_query(filters.regex(r"^poster_retry$"))
async def poster_retry_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    draft["state"] = "awaiting_poster_upload"
    await database.save_post_draft(user_id, draft)
    await callback_query.answer()
    
    await callback_query.message.delete()
    await callback_query.message.reply_text("🖼 Upload another poster image for the post:")

# Callback: Edit Caption (from Main Menu)
@app.on_callback_query(filters.regex(r"^builder_edit_caption$"))
async def builder_edit_caption_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    draft["state"] = "awaiting_edited_caption"
    await database.save_post_draft(user_id, draft)
    await callback_query.answer()
    
    current_cap = draft.get("caption_html") or ""
    await callback_query.message.edit_text(
        "📝 **Post Builder — Edit Caption**\n\n"
        f"**Current Caption:**\n{current_cap}\n\n"
        "Send your edited HTML caption now:\n"
        "Send /cancel to abort."
    )

# Callback: Reactions Config Menu
@app.on_callback_query(filters.regex(r"^builder_reactions$"))
async def builder_reactions_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    selected = draft.get("reactions", [])
    
    kb_rows = []
    # Create toggle buttons for emojis
    row = []
    for emoji in DEFAULT_REACTIONS:
        status = "✅" if emoji in selected else "❌"
        row.append(InlineKeyboardButton(f"{emoji} {status}", callback_data=f"react_toggle_{emoji}"))
        if len(row) == 3:
            kb_rows.append(row)
            row = []
    if row:
        kb_rows.append(row)
        
    kb_rows.append([
        InlineKeyboardButton("✅ Confirm & Save", callback_data="react_save_confirm")
    ])
    
    await callback_query.message.edit_text(
        "❤️ **Post Builder — Reactions Setup**\n\n"
        "Toggle reactions you want to enable for this post:",
        reply_markup=InlineKeyboardMarkup(kb_rows)
    )
    await callback_query.answer()

# Callback: Toggle Reaction Emoji
@app.on_callback_query(filters.regex(r"^react_toggle_(.+)$"))
async def react_toggle_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    emoji = callback_query.matches[0].group(1)
    
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    reactions = draft.get("reactions", [])
    if emoji in reactions:
        reactions.remove(emoji)
    else:
        reactions.append(emoji)
        
    draft["reactions"] = reactions
    draft["reactions_enabled"] = len(reactions) > 0
    await database.save_post_draft(user_id, draft)
    
    # Refresh menu
    selected = reactions
    kb_rows = []
    row = []
    for e in DEFAULT_REACTIONS:
        status = "✅" if e in selected else "❌"
        row.append(InlineKeyboardButton(f"{e} {status}", callback_data=f"react_toggle_{e}"))
        if len(row) == 3:
            kb_rows.append(row)
            row = []
    if row:
        kb_rows.append(row)
    kb_rows.append([
        InlineKeyboardButton("✅ Confirm & Save", callback_data="react_save_confirm")
    ])
    
    try:
        await callback_query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(kb_rows))
    except MessageNotModified:
        pass
    await callback_query.answer()

# Callback: Confirm Reactions
@app.on_callback_query(filters.regex(r"^react_save_confirm$"))
async def react_save_confirm_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    await callback_query.answer("Reactions configured!")
    await callback_query.message.delete()
    await show_builder_menu(client, user_id, draft)

# Callback: Comments Toggle
@app.on_callback_query(filters.regex(r"^builder_comments$"))
async def builder_comments_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    draft["comments_enabled"] = not draft.get("comments_enabled", False)
    await database.save_post_draft(user_id, draft)
    await callback_query.answer(f"Comments {'Enabled' if draft['comments_enabled'] else 'Disabled'}")
    
    await callback_query.message.delete()
    await show_builder_menu(client, user_id, draft)

# Callback: Pin Toggle
@app.on_callback_query(filters.regex(r"^builder_pin$"))
async def builder_pin_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    draft["pin_message"] = not draft.get("pin_message", False)
    await database.save_post_draft(user_id, draft)
    await callback_query.answer(f"Pin Post {'Enabled' if draft['pin_message'] else 'Disabled'}")
    
    await callback_query.message.delete()
    await show_builder_menu(client, user_id, draft)

# Callback: Show Live Preview
@app.on_callback_query(filters.regex(r"^builder_preview$"))
async def builder_preview_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    await callback_query.answer("Generating preview...")
    
    caption = draft.get("caption_html") or ""
    poster_fid = draft.get("poster_file_id")
    
    # Build URL buttons keyboard
    buttons = []
    for btn in draft.get("url_buttons", []):
        buttons.append(
            InlineKeyboardButton(
                text=btn["text"],
                url=btn.get("shortened_url") or btn["url"]
            )
        )
        
    # Append Tutorial button if enabled
    settings = await database.get_settings()
    if settings.get("tutorial_show_on_post") and settings.get("tutorial_shortened_url"):
        buttons.append(
            InlineKeyboardButton(
                text="🎥 Tutorial Video",
                url=settings["tutorial_shortened_url"]
            )
        )
        
    keyboard = InlineKeyboardMarkup([buttons[i:i+1] for i in range(len(buttons))])

    await client.send_message(user_id, "👁 **LIVE PREVIEW**")
    try:
        kwargs = {}
        if buttons:
            kwargs["reply_markup"] = keyboard
        if poster_fid:
            await client.send_photo(
                chat_id=user_id,
                photo=poster_fid,
                caption=caption,
                parse_mode=ParseMode.HTML,
                **kwargs
            )
        else:
            await client.send_message(
                chat_id=user_id,
                text=caption,
                parse_mode=ParseMode.HTML,
                **kwargs
            )
    except Exception as e:
        logger.error(f"Failed to render preview: {e}", exc_info=True)
        await client.send_message(user_id, f"⚠️ Error rendering preview: {e}")
        
    await show_builder_menu(client, user_id, draft)

# Callback: Send Now
@app.on_callback_query(filters.regex(r"^builder_send_now$"))
async def builder_send_now_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    if not draft.get("poster_file_id"):
        await callback_query.answer("❌ Please upload a poster first", show_alert=True)
        return

    await callback_query.message.edit_text("🚀 Sending post now...")
    await callback_query.answer()

    try:
        await publish_post(draft, client)
        await client.send_message(user_id, "🎉 **Post published successfully!**")
    except Exception as e:
        logger.error(f"Failed to publish post: {e}", exc_info=True)
        await client.send_message(user_id, f"❌ **Publish failed:** `{e}`")

# Callback: Cancel Post Builder
@app.on_callback_query(filters.regex(r"^builder_cancel$"))
async def builder_cancel_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("Session expired.", show_alert=True)
        try:
            await callback_query.message.delete()
        except:
            pass
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    await database.delete_post_draft(user_id)
    await callback_query.answer("Post cancelled.")
    await callback_query.message.edit_text("❌ **Post builder session cancelled.**")

# Callback: Back to builder menu (from sub-menus)
@app.on_callback_query(filters.regex(r"^build_btn_back$"))
async def build_btn_back_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    draft = await database.get_post_draft(user_id)
    if not draft:
        await callback_query.answer("❌ Session expired. Use /newpost", show_alert=True)
        return
        
    if callback_query.from_user.id != draft.get("user_id"):
        await callback_query.answer("❌ Not your session", show_alert=True)
        return

    draft["state"] = "active"
    await database.save_post_draft(user_id, draft)
    await callback_query.answer()
    
    await callback_query.message.delete()
    await show_builder_menu(client, user_id, draft)

# Message input router for Post Builder State Machine (excluding scheduler time inputs)
@app.on_message(filters.private & ~banned_filter, group=5)
async def builder_input_handler(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""

    if text.lower() == "/cancel":
        draft = await database.get_post_draft(user_id)
        if draft:
            await database.delete_post_draft(user_id)
            await message.reply_text("❌ **Post builder session cancelled.**")
            return

    draft = await database.get_post_draft(user_id)
    if not draft:
        return

    state = draft.get("state")
    if not state or state in ["awaiting_schedule_time", "awaiting_repost_interval", "awaiting_delete_gap", "awaiting_manual_genre", "awaiting_manual_lang"]:
        # Exclude scheduler, repost, and manual genre/language query states
        message.continue_propagation()
        return

    # STATE 2: awaiting_tmdb_search
    if state == "awaiting_tmdb_search":
        if not text:
            await message.reply_text("❌ Please send a valid movie name:")
            return

        typing_msg = await message.reply_text("🔍 Searching TMDB...")
        try:
            results = await tmdb_client.search_movies(text)
            if not results:
                await typing_msg.edit_text("❌ No results found. Try a different name:")
                return

            # Render movie options
            kb_rows = []
            for item in results:
                kb_rows.append([
                    InlineKeyboardButton(
                        f"🎬 {item['title']} ({item['year']}) - {item['language']}",
                        callback_data=f"tmdb_select_{item['tmdb_id']}"
                    )
                ])
            kb_rows.append([
                InlineKeyboardButton("❌ Skip TMDB - Manual Caption", callback_data="tmdb_skip")
            ])
            
            await typing_msg.edit_text(
                "🎬 **Search Results:**\nSelect the correct movie:",
                reply_markup=InlineKeyboardMarkup(kb_rows)
            )
        except Exception as e:
            logger.error(f"TMDB search failed: {e}", exc_info=True)
            await typing_msg.edit_text("⚠️ TMDB unavailable. Skip or try again:", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Skip TMDB - Manual Caption", callback_data="tmdb_skip")]
            ]))
        message.stop_propagation()
        return

    # STATE 2 Alternative: awaiting_manual_movie_details
    elif state == "awaiting_manual_movie_details":
        if not text:
            await message.reply_text("❌ Input cannot be empty.")
            return

        import re
        lines = text.split("\n")
        data = {}
        for line in lines:
            if ":" in line:
                key, val = line.split(":", 1)
                data[key.strip().lower()] = val.strip()

        title = data.get("title") or data.get("movie title")
        if not title:
            await message.reply_text("❌ Title is required. Please follow the template format exactly.")
            return

        year = data.get("year", "N/A")
        aka = data.get("aka", "N/A")
        rating_str = data.get("rating", "0.0")
        try:
            rating = float(rating_str)
        except ValueError:
            rating = 0.0
        rating_count_str = data.get("rating count", "0")
        try:
            rating_count = int(rating_count_str)
        except ValueError:
            rating_count = 0

        runtime = data.get("runtime", "N/A")
        release = data.get("release", "N/A")

        draft.update({
            "movie_title": title,
            "movie_year": year,
            "also_known_as": aka,
            "rating": rating,
            "rating_count": rating_count,
            "runtime": runtime,
            "release_info": release,
            "genres": [],
            "language": "N/A"
        })

        draft["state"] = "awaiting_manual_genre"
        await database.save_post_draft(user_id, draft)

        # Show Genre selection buttons
        kb = generate_genre_keyboard([])
        await message.reply_text(
            "🎭 **Select Movie Genre(s)**:\n"
            "You can select multiple. Click Confirm when finished.",
            reply_markup=kb
        )
        message.stop_propagation()
        return


    # STATE 3: awaiting_poster_upload
    elif state == "awaiting_poster_upload":
        if not message.photo:
            await message.reply_text("❌ Please send a photo (JPG/PNG).")
            return
            
        # Check size (max 10MB)
        file_size = message.photo.file_size or 0
        if file_size > 10 * 1024 * 1024:
            await message.reply_text("❌ Image too large. Max 10MB allowed.")
            return

        progress_msg = await message.reply_text("🔄 Processing image...")

        temp_file = None
        try:
            # Download photo bytes
            temp_file = await message.download()
            if not temp_file or not isinstance(temp_file, str):
                raise Exception("Failed to download poster photo file")

            with open(temp_file, "rb") as f:
                img_bytes = f.read()

            # Process with default black style
            processed_bytes = await image_converter.convert_to_square(img_bytes, "black")
            
            # Upload processed photo
            sent_photo = await client.send_photo(
                chat_id=user_id,
                photo=io.BytesIO(processed_bytes)
            )
            if sent_photo and sent_photo.photo:
                processed_fid = sent_photo.photo.file_id
                await sent_photo.delete()
            else:
                raise Exception("Failed to send processed poster photo")

            # Save to draft
            draft["original_photo_file_id"] = message.photo.file_id
            draft["poster_file_id"] = processed_fid
            draft["poster_bg_style"] = "black"
            draft["state"] = "active"
            await database.save_post_draft(user_id, draft)

            await progress_msg.delete()

            # Show preview and style selection
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⬛ Black BG ✅", callback_data="poster_style_black"),
                    InlineKeyboardButton("🌀 Blur BG", callback_data="poster_style_blur"),
                    InlineKeyboardButton("⬜ White BG", callback_data="poster_style_white")
                ],
                [
                    InlineKeyboardButton("✅ Use This", callback_data="poster_confirm"),
                    InlineKeyboardButton("🔄 Try Another Style", callback_data="poster_retry")
                ]
            ])
            await client.send_photo(
                chat_id=user_id,
                photo=processed_fid,
                caption="Choose background style:",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Poster processing failed: {e}", exc_info=True)
            await progress_msg.edit_text("⚠️ Processing failed. Using original.")
            
            draft["poster_file_id"] = message.photo.file_id
            draft["poster_processed"] = False
            draft["state"] = "active"
            await database.save_post_draft(user_id, draft)
            await show_builder_menu(client, user_id, draft)
        finally:
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)

        message.stop_propagation()
        return

    # STATE 4: awaiting_edited_caption
    elif state == "awaiting_edited_caption":
        if not text:
            await message.reply_text("❌ Caption cannot be empty:")
            return

        draft["caption_html"] = text
        draft["caption_edited"] = True
        draft["state"] = "active"
        await database.save_post_draft(user_id, draft)

        await message.reply_text("✅ Caption updated successfully!")
        await show_builder_menu(client, user_id, draft)
        message.stop_propagation()
        return
