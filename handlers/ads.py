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
from utils.helpers import admin_filter

logger = logging.getLogger(__name__)

AD_TYPE_ICONS = {
    "broadcast": "📢",
    "pinned": "📌",
    "force_join": "🔗",
    "sponsored_page": "🖼",
}


@app.on_message(filters.command("ads") & filters.private & admin_filter)
async def ads_menu_handler(client: Client, message: Message):
    text = (
        "💼 **Sponsored Promotions Dashboard**\n\n"
        "Choose an ad type to manage, or view reports:\n\n"
        "📢 **Broadcast Ads** — Send promotions to all users\n"
        "📌 **Pinned Ads** — Permanent channel placements\n"
        "🔗 **Force Join Ads** — Sponsored channel placements\n"
        "🖼 **Sponsored Download Pages** — Brand visibility during file access\n"
    )
    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📢 Broadcast Ads", callback_data="ads_list_broadcast"
                )
            ],
            [InlineKeyboardButton("📌 Pinned Ads", callback_data="ads_list_pinned")],
            [
                InlineKeyboardButton(
                    "🔗 Force Join Ads", callback_data="ads_list_force_join"
                )
            ],
            [
                InlineKeyboardButton(
                    "🖼 Sponsored Pages", callback_data="ads_list_sponsored_page"
                )
            ],
            [InlineKeyboardButton("📊 Revenue Reports", callback_data="ads_revenue")],
            [InlineKeyboardButton("➕ Create New Ad", callback_data="ads_create_menu")],
        ]
    )
    await message.reply_text(text, reply_markup=buttons)


@app.on_callback_query(filters.regex(r"^ads_list_(\w+)$"))
async def ads_list_callback(client: Client, callback_query: CallbackQuery):
    ad_type = callback_query.matches[0].group(1)
    ads = await database.get_all_ads(ad_type=ad_type)
    icon = AD_TYPE_ICONS.get(ad_type, "📌")

    if not ads:
        await callback_query.answer()
        text = f"{icon} **No {ad_type.replace('_', ' ').title()} Ads**\n\nCreate one with the button below."
        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "➕ Create Ad", callback_data=f"ads_create_{ad_type}"
                    )
                ],
                [InlineKeyboardButton("🔙 Back", callback_data="ads_main_menu")],
            ]
        )
        await callback_query.message.edit_text(text, reply_markup=buttons)
        return

    text = f"{icon} **{ad_type.replace('_', ' ').title()} Ads**\n\n"
    for ad in ads:
        status_icon = (
            "🟢"
            if ad.get("status") == "active"
            else "🔴" if ad.get("status") == "paused" else "⏸"
        )
        text += (
            f"{status_icon} **{ad['title']}**\n"
            f"  Impressions: {ad.get('impressions', 0)} | "
            f"Clicks: {ad.get('clicks', 0)} | "
            f"Revenue: ${ad.get('revenue', 0):.4f}\n"
            f"  `/ad_{ad['_id']}`\n\n"
        )

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "➕ Create Ad", callback_data=f"ads_create_{ad_type}"
                )
            ],
            [InlineKeyboardButton("🔙 Back", callback_data="ads_main_menu")],
        ]
    )
    await callback_query.message.edit_text(text, reply_markup=buttons)


@app.on_message(filters.regex(r"^/ad_([a-f0-9]{24})$") & filters.private & admin_filter)
async def ad_detail_cmd(client: Client, message: Message):
    ad_id = message.matches[0].group(1)
    ad = await database.get_ad(ad_id)
    if not ad:
        await message.reply_text("❌ Ad not found.")
        return
    await show_ad_detail(message, ad)


async def show_ad_detail(msg_or_query, ad: dict):
    ad_id = str(ad["_id"])
    icon = AD_TYPE_ICONS.get(ad["type"], "📌")
    status_icon = "🟢" if ad.get("status") == "active" else "🔴"
    type_display = ad["type"].replace("_", " ").title()

    text = (
        f"{icon} **Ad Detail**\n\n"
        f"**Title:** {ad['title']}\n"
        f"**Type:** {type_display}\n"
        f"**Status:** {status_icon} {ad.get('status', 'unknown')}\n"
        f"**Description:** {ad.get('description', 'N/A')}\n"
        f"**Brand:** {ad.get('brand_name', 'N/A')}\n"
        f"**CPM:** ${ad.get('cpm', 5.0):.2f}\n\n"
        f"📊 **Performance**\n"
        f"Impressions: {ad.get('impressions', 0)}\n"
        f"Clicks: {ad.get('clicks', 0)}\n"
        f"Revenue: ${ad.get('revenue', 0):.4f}\n"
    )

    if ad.get("schedule_start") or ad.get("schedule_end"):
        text += "\n📅 **Schedule**\n"
        if ad.get("schedule_start"):
            text += f"Start: {ad['schedule_start'].strftime('%Y-%m-%d %H:%M UTC')}\n"
        if ad.get("schedule_end"):
            text += f"End: {ad['schedule_end'].strftime('%Y-%m-%d %H:%M UTC')}\n"

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔄 Toggle Active/Paused", callback_data=f"ad_toggle_{ad_id}"
                )
            ],
            [InlineKeyboardButton("🗑 Delete", callback_data=f"ad_delete_{ad_id}")],
            [
                InlineKeyboardButton(
                    "🔙 Back to List", callback_data=f"ads_list_{ad['type']}"
                )
            ],
        ]
    )

    if isinstance(msg_or_query, CallbackQuery):
        await msg_or_query.message.edit_text(text, reply_markup=buttons)
    else:
        await msg_or_query.reply_text(text, reply_markup=buttons)


@app.on_callback_query(filters.regex(r"^ad_toggle_([a-f0-9]{24})$"))
async def ad_toggle_callback(client: Client, callback_query: CallbackQuery):
    ad_id = callback_query.matches[0].group(1)
    ad = await database.get_ad(ad_id)
    if not ad:
        await callback_query.answer("Ad not found.", show_alert=True)
        return
    new_status = "paused" if ad.get("status") == "active" else "active"
    await database.update_ad(ad_id, {"status": new_status})
    await callback_query.answer(f"Ad is now {new_status}.")
    ad["status"] = new_status
    await show_ad_detail(callback_query, ad)


@app.on_callback_query(filters.regex(r"^ad_delete_([a-f0-9]{24})$"))
async def ad_delete_callback(client: Client, callback_query: CallbackQuery):
    ad_id = callback_query.matches[0].group(1)
    ad = await database.get_ad(ad_id)
    if not ad:
        await callback_query.answer("Ad not found.", show_alert=True)
        return
    await database.delete_ad(ad_id)
    await callback_query.answer("Ad deleted.", show_alert=True)
    await callback_query.message.edit_text(f"🗑 Ad `{ad['title']}` has been deleted.")


@app.on_callback_query(filters.regex(r"^ads_create_menu$"))
async def ads_create_menu_callback(client: Client, callback_query: CallbackQuery):
    text = "**➕ Create New Sponsored Ad**\n\nChoose ad type:"
    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📢 Broadcast Ad", callback_data="ads_create_broadcast"
                )
            ],
            [InlineKeyboardButton("📌 Pinned Ad", callback_data="ads_create_pinned")],
            [
                InlineKeyboardButton(
                    "🔗 Force Join Ad", callback_data="ads_create_force_join"
                )
            ],
            [
                InlineKeyboardButton(
                    "🖼 Sponsored Download Page",
                    callback_data="ads_create_sponsored_page",
                )
            ],
            [InlineKeyboardButton("🔙 Back", callback_data="ads_main_menu")],
        ]
    )
    await callback_query.message.edit_text(text, reply_markup=buttons)


@app.on_callback_query(filters.regex(r"^ads_create_(\w+)$"))
async def ads_create_callback(client: Client, callback_query: CallbackQuery):
    ad_type = callback_query.matches[0].group(1)
    ad_type_display = ad_type.replace("_", " ").title()

    usage = (
        f"**➕ Create {ad_type_display} Ad**\n\n"
        f"Reply with the ad details in this format:\n\n"
    )

    if ad_type == "broadcast":
        usage += (
            "`<title> | <description> | <cpm>`\n\n"
            "Example:\n"
            "`Summer Sale | Check out our premium plans! | 5.0`\n\n"
            "You can also reply to a message with media (photo/video/document) to attach it."
        )
    elif ad_type == "pinned":
        usage += (
            "`<title> | <description> | <channel_id> | <invite_link> | <cpm>`\n\n"
            "Example:\n"
            "`Sponsored Channel | Best tech news daily | -100123456789 | https://t.me/joinchat/... | 3.0`"
        )
    elif ad_type == "force_join":
        usage += (
            "`<title> | <description> | <channel_id> | <invite_link> | <cpm>`\n\n"
            "Example:\n"
            "`Premium Group | Join our exclusive group | -100123456789 | https://t.me/joinchat/... | 4.0`"
        )
    elif ad_type == "sponsored_page":
        usage += (
            "`<title> | <description> | <brand_name> | <brand_message> | <cpm>`\n\n"
            "Example:\n"
            "`Acme Corp | Powered by Acme | Acme Corp | Thanks for using our service! | 5.0`"
        )

    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔙 Back", callback_data="ads_create_menu")],
        ]
    )
    await callback_query.message.edit_text(usage, reply_markup=buttons)

    # Store the ad type being created in a simple waiting session
    # We'll use a state approach: set a temp session via DB
    user_id = callback_query.from_user.id
    await database.upsert_ad_draft(
        user_id, {"step": "awaiting_details", "ad_type": ad_type}
    )


@app.on_message(filters.text & filters.private & admin_filter)
async def ad_create_text_handler(client: Client, message: Message):
    user_id = message.from_user.id
    draft = await database.get_ad_draft(user_id)
    if not draft or draft.get("step") != "awaiting_details":
        from pyrogram import ContinuePropagation
        raise ContinuePropagation

    ad_type = draft.get("ad_type")
    text = message.text.strip()
    parts = [p.strip() for p in text.split("|")]

    if ad_type == "broadcast":
        if len(parts) < 3:
            await message.reply_text("❌ Need at least: `title | description | cpm`")
            return
        title, description, cpm_raw = parts[0], parts[1], parts[2]
        try:
            cpm = float(cpm_raw)
        except ValueError:
            await message.reply_text("❌ CPM must be a number.")
            return
        media = None
        if message.reply_to_message and message.reply_to_message.media:
            media = getattr(
                message.reply_to_message, message.reply_to_message.media.value, {}
            ).get("file_id")

        ad = await database.create_ad(
            ad_type="broadcast",
            title=title,
            description=description,
            created_by=user_id,
            media=media,
            cpm=cpm,
        )
        await message.reply_text(
            f"✅ **Broadcast Ad Created!**\n\nID: `{ad['_id']}`\nTitle: {title}"
        )
        await database.clear_ad_draft(user_id)

    elif ad_type == "pinned":
        if len(parts) < 5:
            await message.reply_text(
                "❌ Need: `title | description | channel_id | invite_link | cpm`"
            )
            return
        title, description, channel_raw, invite_link, cpm_raw = (
            parts[0],
            parts[1],
            parts[2],
            parts[3],
            parts[4],
        )
        try:
            cpm = float(cpm_raw)
        except ValueError:
            await message.reply_text("❌ CPM must be a number.")
            return
        try:
            channel_id = (
                int(channel_raw) if channel_raw.lstrip("-").isdigit() else channel_raw
            )
        except ValueError:
            channel_id = channel_raw

        ad = await database.create_ad(
            ad_type="pinned",
            title=title,
            description=description,
            created_by=user_id,
            channel_id=channel_id,
            channel_link=invite_link,
            cpm=cpm,
        )
        await message.reply_text(
            f"✅ **Pinned Ad Created!**\n\nID: `{ad['_id']}`\nTitle: {title}"
        )
        await database.clear_ad_draft(user_id)

    elif ad_type == "force_join":
        if len(parts) < 5:
            await message.reply_text(
                "❌ Need: `title | description | channel_id | invite_link | cpm`"
            )
            return
        title, description, channel_raw, invite_link, cpm_raw = (
            parts[0],
            parts[1],
            parts[2],
            parts[3],
            parts[4],
        )
        try:
            cpm = float(cpm_raw)
        except ValueError:
            await message.reply_text("❌ CPM must be a number.")
            return
        try:
            channel_id = (
                int(channel_raw) if channel_raw.lstrip("-").isdigit() else channel_raw
            )
        except ValueError:
            channel_id = channel_raw

        ad = await database.create_ad(
            ad_type="force_join",
            title=title,
            description=description,
            created_by=user_id,
            channel_id=channel_id,
            channel_link=invite_link,
            cpm=cpm,
        )
        await message.reply_text(
            f"✅ **Force Join Ad Created!**\n\nID: `{ad['_id']}`\nTitle: {title}"
        )
        await database.clear_ad_draft(user_id)

    elif ad_type == "sponsored_page":
        if len(parts) < 5:
            await message.reply_text(
                "❌ Need: `title | description | brand_name | brand_message | cpm`"
            )
            return
        title, description, brand_name, brand_message, cpm_raw = (
            parts[0],
            parts[1],
            parts[2],
            parts[3],
            parts[4],
        )
        try:
            cpm = float(cpm_raw)
        except ValueError:
            await message.reply_text("❌ CPM must be a number.")
            return

        ad = await database.create_ad(
            ad_type="sponsored_page",
            title=title,
            description=description,
            created_by=user_id,
            brand_name=brand_name,
            brand_message=brand_message,
            cpm=cpm,
        )
        await message.reply_text(
            f"✅ **Sponsored Page Ad Created!**\n\nID: `{ad['_id']}`\nTitle: {title}"
        )
        await database.clear_ad_draft(user_id)


@app.on_callback_query(filters.regex(r"^ads_revenue$"))
async def ads_revenue_callback(client: Client, callback_query: CallbackQuery):
    report = await database.get_ad_revenue_report()
    text = (
        "📊 **Sponsored Promotions Revenue Report**\n\n"
        f"**Total Ads:** {report['total_ads']}\n"
        f"**Total Impressions:** {report['total_impressions']}\n"
        f"**Total Clicks:** {report['total_clicks']}\n"
        f"**Total Revenue:** `${report['total_revenue']:.4f}`\n\n"
    )

    if report["by_type"]:
        text += "**Breakdown by Type:**\n"
        type_labels = {
            "broadcast": "📢 Broadcast",
            "pinned": "📌 Pinned",
            "force_join": "🔗 Force Join",
            "sponsored_page": "🖼 Sponsored Page",
        }
        for ad_type, data in report["by_type"].items():
            label = type_labels.get(ad_type, ad_type)
            text += (
                f"  {label}: {data['count']} ads, "
                f"{data['impressions']} impressions, "
                f"{data['clicks']} clicks, "
                f"${data['revenue']:.4f}\n"
            )

    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔙 Back", callback_data="ads_main_menu")],
        ]
    )
    await callback_query.message.edit_text(text, reply_markup=buttons)


@app.on_callback_query(filters.regex(r"^ads_main_menu$"))
async def ads_main_menu_callback(client: Client, callback_query: CallbackQuery):
    await ads_menu_handler(client, callback_query.message)
