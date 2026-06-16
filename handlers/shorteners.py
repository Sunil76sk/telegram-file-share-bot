from __future__ import annotations

import logging
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
import asyncio
from bot import app
import database
from handlers.settings import re_shorten_tutorial_url

logger = logging.getLogger(__name__)

# Predefined shortener API endpoints
PREDEFINED_SHORTENERS = {
    "TeraBoxLinks": "https://teraboxlinks.com/api",
    "GPLinks": "https://gplinks.in/api",
    "ShrinkEarn": "https://shrinkearn.com/api",
    "CTRSh": "https://ctrsh.net/api",
    "Linkvertise": "https://api.linkvertise.com/v1",
}


async def get_shorteners_dashboard(
    user_id: int, bot_id: int | None = None
) -> tuple[str, InlineKeyboardMarkup]:
    """Generate the admin dashboard for managing URL shorteners."""
    shorteners = await database.get_shorteners(bot_id=bot_id)

    text = (
        "💰 **URL Shortener Monetization Settings**\n\n"
        "Earn revenue from traffic by shortening your file download links. "
        "You can configure multiple shorteners and they will rotate using weighted random selection. "
        "You can also target specific countries.\n\n"
    )

    buttons = []

    if not shorteners:
        text += "❌ **No shorteners configured yet.**\n"
    else:
        text += "📋 **Active Shorteners:**\n"
        for index, sh in enumerate(shorteners, start=1):
            name = sh["name"]
            status = "🟢" if sh["status"] == "active" else "🔴"
            weight = sh["weight"]
            geo = ", ".join(sh.get("geo_countries", ["ALL"]))
            cpm = sh.get("cpm", 3.0)

            # Aggregate stats
            views = sh.get("views", 0)
            clicks = sh.get("clicks", 0)
            rev = sh.get("revenue", 0.0)
            ctr = (clicks / views * 100) if views > 0 else 0.0

            text += (
                f"**{index}. {status} {name}**\n"
                f"   • Weight: `{weight}` | CPM: `${cpm:.2f}`\n"
                f"   • Geo: `{geo}`\n"
                f"   • Views: `{views}` | Clicks: `{clicks}` | CTR: `{ctr:.1f}%`\n"
                f"   • Revenue: `${rev:.4f}`\n\n"
            )

            # Button to toggle and delete
            sh_id = str(sh["_id"])
            toggle_label = "🔴 Disable" if sh["status"] == "active" else "🟢 Enable"
            buttons.append(
                [
                    InlineKeyboardButton(
                        f"{name} ({weight})", callback_data=f"sh_info_{sh_id}"
                    ),
                    InlineKeyboardButton(
                        toggle_label, callback_data=f"sh_toggle_{sh_id}"
                    ),
                    InlineKeyboardButton(
                        "🗑 Delete", callback_data=f"sh_delete_{sh_id}"
                    ),
                ]
            )

    buttons.append(
        [InlineKeyboardButton("➕ Add New Shortener", callback_data="sh_add")]
    )
    buttons.append([InlineKeyboardButton("🚪 Close Menu", callback_data="sh_close")])

    return text, InlineKeyboardMarkup(buttons)


@app.on_message(filters.command("shorteners") & filters.private)
async def shorteners_command_handler(client: Client, message: Message):
    """Admin shortener dashboard entry command."""
    user_id = message.from_user.id
    if await database.is_banned(user_id):
        return

    # Check if admin
    if not await database.is_admin(user_id, client):
        await message.reply_text(
            "⛔️ You must be an administrator to manage shorteners."
        )
        return

    bot_id = None
    bot_me = client.me or await client.get_me()
    sub_bot = await database.sub_bots_col.find_one({"username": bot_me.username})
    if sub_bot:
        bot_id = bot_me.id

    text, markup = await get_shorteners_dashboard(user_id, bot_id=bot_id)
    await message.reply_text(text, reply_markup=markup)


@app.on_callback_query(filters.regex(r"^sh_close$"))
async def sh_close_callback(client: Client, callback_query: CallbackQuery):
    await callback_query.message.delete()


@app.on_callback_query(filters.regex(r"^sh_add$"))
async def sh_add_callback(client: Client, callback_query: CallbackQuery):
    """Start shortener registration process."""
    user_id = callback_query.from_user.id
    if not await database.is_admin(user_id, client):
        await callback_query.answer("⛔️ Permission Denied", show_alert=True)
        return

    # Buttons for predefined shorteners
    buttons = []
    for name in PREDEFINED_SHORTENERS.keys():
        buttons.append([InlineKeyboardButton(name, callback_data=f"sh_select_{name}")])
    buttons.append(
        [InlineKeyboardButton("Custom Network", callback_data="sh_select_Custom")]
    )
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="sh_cancel")])

    await callback_query.answer()
    await callback_query.message.edit_text(
        "➕ **Add New Shortener**\n\n" "Please select a shortener network:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@app.on_callback_query(filters.regex(r"^sh_select_(.+)$"))
async def sh_select_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await database.is_admin(user_id, client):
        await callback_query.answer("⛔️ Access denied.", show_alert=True)
        return
    name = callback_query.matches[0].group(1)

    # Initialize draft in user settings
    draft = {"name": name}
    if name in PREDEFINED_SHORTENERS:
        draft["api_url"] = PREDEFINED_SHORTENERS[name]
        next_state = "sh_awaiting_key"
        prompt_text = (
            f"🔗 Selected **{name}**\n\n"
            f"Please send your **API Key / Token** from your {name} dashboard:\n"
            f"Format: alphanumeric string."
        )
    else:
        next_state = "sh_awaiting_url"
        prompt_text = (
            "🔗 Custom Network Selected\n\n"
            "Please send the shortener's **API URL Endpoint**:\n"
            "Example: `https://gplinks.in/api`"
        )

    await database.users_col.update_one(
        {"_id": user_id}, {"$set": {"state": next_state, "shortener_draft": draft}}
    )

    await callback_query.answer()
    await callback_query.message.edit_text(
        prompt_text,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="sh_cancel")]]
        ),
    )


@app.on_callback_query(filters.regex(r"^sh_cancel$"))
async def sh_cancel_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    await database.users_col.update_one(
        {"_id": user_id}, {"$unset": {"state": "", "shortener_draft": ""}}
    )

    bot_id = None
    bot_me = client.me or await client.get_me()
    sub_bot = await database.sub_bots_col.find_one({"username": bot_me.username})
    if sub_bot:
        bot_id = bot_me.id

    text, markup = await get_shorteners_dashboard(user_id, bot_id=bot_id)
    await callback_query.message.edit_text(text, reply_markup=markup)


@app.on_callback_query(filters.regex(r"^sh_toggle_(.+)$"))
async def sh_toggle_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await database.is_admin(user_id, client):
        await callback_query.answer("⛔️ Access denied.", show_alert=True)
        return
    sh_id = callback_query.matches[0].group(1)

    sh = await database.get_shortener_by_id(sh_id)
    if not sh:
        await callback_query.answer("❌ Shortener not found", show_alert=True)
        return

    new_status = "inactive" if sh["status"] == "active" else "active"
    await database.update_shortener(sh_id, {"status": new_status})
    asyncio.create_task(re_shorten_tutorial_url())
    await callback_query.answer(f"Status changed to {new_status}!")

    bot_id = None
    bot_me = client.me or await client.get_me()
    sub_bot = await database.sub_bots_col.find_one({"username": bot_me.username})
    if sub_bot:
        bot_id = bot_me.id

    text, markup = await get_shorteners_dashboard(user_id, bot_id=bot_id)
    await callback_query.message.edit_text(text, reply_markup=markup)


@app.on_callback_query(filters.regex(r"^sh_delete_(.+)$"))
async def sh_delete_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not await database.is_admin(user_id, client):
        await callback_query.answer("⛔️ Access denied.", show_alert=True)
        return
    sh_id = callback_query.matches[0].group(1)

    deleted = await database.delete_shortener(sh_id)
    if deleted:
        asyncio.create_task(re_shorten_tutorial_url())
        await callback_query.answer("🗑 Shortener deleted successfully!")
    else:
        await callback_query.answer("❌ Failed to delete shortener", show_alert=True)

    bot_id = None
    bot_me = client.me or await client.get_me()
    sub_bot = await database.sub_bots_col.find_one({"username": bot_me.username})
    if sub_bot:
        bot_id = bot_me.id

    text, markup = await get_shorteners_dashboard(user_id, bot_id=bot_id)
    await callback_query.message.edit_text(text, reply_markup=markup)


@app.on_callback_query(filters.regex(r"^sh_info_(.+)$"))
async def sh_info_callback(client: Client, callback_query: CallbackQuery):
    if not await database.is_admin(callback_query.from_user.id, client):
        await callback_query.answer("⛔️ Access denied.", show_alert=True)
        return
    sh_id = callback_query.matches[0].group(1)
    sh = await database.get_shortener_by_id(sh_id)
    if not sh:
        await callback_query.answer("❌ Shortener not found", show_alert=True)
        return

    views = sh.get("views", 0)
    clicks = sh.get("clicks", 0)
    rev = sh.get("revenue", 0.0)
    ctr = (clicks / views * 100) if views > 0 else 0.0

    info_text = (
        f"ℹ️ **Shortener Details**\n\n"
        f"**Name:** {sh['name']}\n"
        f"**API Endpoint:** `{sh['api_url']}`\n"
        f"**API Key:** `{sh['api_key'][:8]}********`\n"
        f"**Status:** `{sh['status'].upper()}`\n"
        f"**Rotation Weight:** `{sh['weight']}`\n"
        f"**Estimated CPM:** `${sh.get('cpm', 3.0):.2f}`\n"
        f"**Geo-Targeting:** `{', '.join(sh.get('geo_countries', ['ALL']))}`\n\n"
        f"📊 **Performance Statistics:**\n"
        f"• Views: `{views}`\n"
        f"• Clicks (Completions): `{clicks}`\n"
        f"• Click-Through Rate (CTR): `{ctr:.2f}%`\n"
        f"• Total Revenue: `${rev:.4f}`"
    )

    await callback_query.answer()
    await callback_query.message.edit_text(
        info_text,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 Back to Dashboard", callback_data="sh_cancel")]]
        ),
    )


async def handle_shortener_state(
    client: Client, message: Message, user_id: int, state: str, user_doc: dict
):
    """Process text message input for the shortener configuration wizard."""
    text = message.text.strip()
    draft = user_doc.get("shortener_draft", {})

    bot_me = client.me or await client.get_me()
    bot_id = None
    sub_bot = await database.sub_bots_col.find_one({"username": bot_me.username})
    if sub_bot:
        bot_id = bot_me.id

    if state == "sh_awaiting_url":
        if not text.startswith("http"):
            await message.reply_text(
                "❌ Please enter a valid URL beginning with http:// or https://"
            )
            return
        draft["api_url"] = text
        await database.users_col.update_one(
            {"_id": user_id},
            {"$set": {"state": "sh_awaiting_key", "shortener_draft": draft}},
        )
        await message.reply_text(
            "🔑 API Endpoint set!\n\n"
            "Now, send your **API Key / Token** for this network:"
        )

    elif state == "sh_awaiting_key":
        if not text:
            await message.reply_text("❌ Key cannot be empty.")
            return
        draft["api_key"] = text
        await database.users_col.update_one(
            {"_id": user_id},
            {"$set": {"state": "sh_awaiting_weight", "shortener_draft": draft}},
        )
        await message.reply_text(
            "⚖️ API Key set!\n\n"
            "Enter the **rotation weight** (Integer from 1 to 100, default is 1).\n"
            "Higher weight means this shortener is selected more frequently."
        )

    elif state == "sh_awaiting_weight":
        try:
            weight = int(text)
            if weight < 1 or weight > 100:
                raise ValueError
        except ValueError:
            await message.reply_text(
                "❌ Weight must be an integer between 1 and 100. Try again:"
            )
            return

        draft["weight"] = weight
        await database.users_col.update_one(
            {"_id": user_id},
            {"$set": {"state": "sh_awaiting_geo", "shortener_draft": draft}},
        )
        await message.reply_text(
            "🌍 Weight set successfully!\n\n"
            "Enter target **country codes** (comma-separated, e.g. `US,GB,IN`) for geo-targeting, "
            "or enter `ALL` to match traffic from all countries:"
        )

    elif state == "sh_awaiting_geo":
        countries = [c.strip().upper() for c in text.split(",")]
        draft["geo_countries"] = countries
        await database.users_col.update_one(
            {"_id": user_id},
            {"$set": {"state": "sh_awaiting_cpm", "shortener_draft": draft}},
        )
        await message.reply_text(
            "💰 Geolocation targeting set!\n\n"
            "Enter the **Estimated CPM** for this shortener (Revenue per 1000 views in USD, e.g., `5.0` or `3.50`):"
        )

    elif state == "sh_awaiting_cpm":
        try:
            cpm = float(text)
            if cpm < 0.0:
                raise ValueError
        except ValueError:
            await message.reply_text(
                "❌ CPM must be a valid positive decimal number. Try again:"
            )
            return

        draft["cpm"] = cpm

        # Save to database
        await database.add_shortener(
            name=draft["name"],
            api_url=draft["api_url"],
            api_key=draft["api_key"],
            weight=draft.get("weight", 1),
            geo_countries=draft.get("geo_countries"),
            cpm=draft["cpm"],
            bot_id=bot_id,
        )
        asyncio.create_task(re_shorten_tutorial_url())

        # Clear state
        await database.users_col.update_one(
            {"_id": user_id}, {"$unset": {"state": "", "shortener_draft": ""}}
        )

        await message.reply_text("🎉 **Shortener Added successfully!**")

        # Display updated dashboard
        dash_text, dash_markup = await get_shorteners_dashboard(user_id, bot_id=bot_id)
        await message.reply_text(dash_text, reply_markup=dash_markup)
