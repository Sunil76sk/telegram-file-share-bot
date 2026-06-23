from __future__ import annotations

import logging
import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
from bot import app, INSTANCE_ID
import database
from utils.helpers import banned_filter, admin_filter
from utils.rate_limiter import check_rate_limit
from utils.movie_metadata import (
    search_movies,
    fetch_movie_from_api,
    save_movie_metadata,
)
from utils.diagnostics import check_system_health

logger = logging.getLogger(__name__)

# ─── MODULE 4: MOVIE SEARCH COMMAND ─────────────────────────────────


@app.on_message(filters.command("searchmovie") & filters.private & ~banned_filter)
async def search_movie_command_handler(client: Client, message: Message):
    user_id = message.from_user.id

    # Enforce Rate Limit: Movie Search (20/min)
    allowed = await check_rate_limit(
        user_id, "movie_search", limit=20, window_seconds=60
    )
    if not allowed:
        await message.reply_text(
            "❌ **Rate limit exceeded!**\nYou can only perform 20 movie searches per minute."
        )
        return

    args = message.text.split(None, 1)
    if len(args) < 2:
        await message.reply_text(
            "⚠️ **Usage:** `/searchmovie [movie_title]`\nExample: `/searchmovie Avatar`"
        )
        return

    query = args[1].strip()
    status_msg = await message.reply_text(f"🔍 Searching metadata for '**{query}**'...")

    # 1. Search locally in database
    results = await search_movies(query, limit=1)
    movie = results[0] if results else None

    # 2. If not found locally, fetch from TMDB/OMDB API
    if not movie:
        movie = await fetch_movie_from_api(query)
        if movie:
            # Save to local database for future caching
            await save_movie_metadata(movie)

    if not movie:
        await status_msg.edit_text(
            "❌ No movie metadata found. Please try a different title or search query."
        )
        return

    # 3. Present formatted movie metadata
    details_text = (
        f"🎬 **Movie Metadata Found:**\n\n"
        f"🎥 **Title:** {movie.get('title')}\n"
        f"📅 **Year:** {movie.get('year') or 'N/A'}\n"
        f"⭐ **Rating:** {movie.get('rating') or 'N/A'}/10\n"
        f"🎭 **Genre:** {movie.get('genre') or 'N/A'}\n"
        f"🌍 **Language:** {movie.get('language', 'en').upper()}\n"
        f"⏱ **Duration:** {movie.get('duration_minutes') or 'N/A'} min\n"
        f"🎬 **Director:** {movie.get('director') or 'N/A'}\n\n"
        f"📝 **Overview:**\n{movie.get('description', 'No description available.')}"
    )

    await status_msg.delete()
    if movie.get("poster_url"):
        try:
            await message.reply_photo(photo=movie["poster_url"], caption=details_text)
        except Exception:
            await message.reply_text(details_text)
    else:
        await message.reply_text(details_text)


# ─── MODULE 17: SYSTEM DIAGNOSTICS COMMAND ──────────────────────────


@app.on_message(filters.command(["diag", "diagnose"]) & filters.private & admin_filter)
async def diag_command_handler(client: Client, message: Message):
    user_id = message.from_user.id

    # Enforce Rate Limit: Diagnostics (10/min)
    allowed = await check_rate_limit(user_id, "diagnose", limit=10, window_seconds=60)
    if not allowed:
        await message.reply_text("❌ Rate limit exceeded.")
        return

    status_msg = await message.reply_text("⚙️ Running system diagnostics...")
    try:
        health = await check_system_health()

        issues_str = (
            "\n".join([f"• 🚨 {issue}" for issue in health.get("issues", [])])
            or "• None ✅"
        )
        warnings_str = (
            "\n".join([f"• ⚠️ {warn}" for warn in health.get("warnings", [])])
            or "• None ✅"
        )

        db_info = health.get("db_info", {})
        db_str = (
            f"  - Collections: `{db_info.get('collections', 0)}`\n"
            f"  - Documents: `{db_info.get('documents', 0)}`\n"
            f"  - Data Size: `{db_info.get('data_size_mb', 0)} MB`"
        )

        workers = health.get("workers", [])
        worker_str = ""
        for w in workers:
            worker_str += f"  - `{w.get('name')}`: **{w.get('status')}** (Processed: {w.get('tasks_processed')})\n"

        report = (
            f"🛠 **System Diagnostics & Health Report**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🖥 **Instance ID:** `{INSTANCE_ID}`\n"
            f"🕒 **Time:** `{health.get('timestamp')}`\n"
            f"📈 **Memory Usage:** `{health.get('memory_mb')} MB`\n\n"
            f"🚨 **Critical Issues:**\n{issues_str}\n\n"
            f"⚠️ **Warnings:**\n{warnings_str}\n\n"
            f"🗄 **Database Stats:**\n{db_str}\n\n"
            f"🤖 **Background Workers:**\n{worker_str or '  - None'}"
        )
        await status_msg.edit_text(report)
    except Exception as e:
        logger.error(f"Diagnostics failed: {e}")
        await status_msg.edit_text(f"❌ **Diagnostics failed:** {e}")


# ─── MODULE 1: CHANNEL COMMANDS ALIASES ─────────────────────────────


@app.on_message(filters.command("addchannel") & filters.private & ~banned_filter)
async def add_channel_alias(client: Client, message: Message):
    from handlers.broadcast import add_channel_handler

    await add_channel_handler(client, message)


@app.on_message(filters.command("delchannel") & filters.private & ~banned_filter)
async def del_channel_alias(client: Client, message: Message):
    from handlers.broadcast import del_channel_handler

    await del_channel_handler(client, message)


@app.on_message(
    filters.command(["mychannels", "channelsettings"])
    & filters.private
    & ~banned_filter
)
async def my_channels_alias(client: Client, message: Message):
    from handlers.broadcast import my_channels_handler

    await my_channels_handler(client, message)
