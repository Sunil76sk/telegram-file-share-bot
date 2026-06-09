from __future__ import annotations

import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from bot import app
import database

logger = logging.getLogger(__name__)


@app.on_message(filters.command("analytics") & filters.private)
async def analytics_handler(client: Client, message: Message):
    user_id = message.from_user.id
    args = message.text.split(None, 1)
    sub = args[1].strip().lower() if len(args) > 1 else ""

    if sub == "dau":
        await show_dau_mau(client, message)
    elif sub == "top":
        await show_top_files(client, message)
    elif sub == "geo":
        await show_geo_distribution(client, message)
    elif sub == "sources":
        await show_traffic_sources(client, message)
    elif sub == "funnel":
        await show_conversion_funnel(client, message)
    elif sub == "growth":
        await show_user_growth(client, message)
    else:
        await show_analytics_menu(client, message)


async def show_analytics_menu(client: Client, message: Message):
    text = (
        "📊 **Analytics Dashboard**\n\n"
        "Track your bot's performance and audience metrics.\n\n"
        "**Available Reports:**\n"
        "📈 `/analytics dau` — Daily & Monthly Active Users\n"
        "📈 `/analytics growth` — User Growth\n"
        "🏆 `/analytics top` — Top Performing Files\n"
        "🌍 `/analytics geo` — Geographic Distribution\n"
        "🔗 `/analytics sources` — Traffic Sources\n"
        "🔄 `/analytics funnel` — Conversion Funnel\n\n"
        "💼 **Advertiser Portal**\n"
        "`/advertise` — View audience stats and ad opportunities"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📈 DAU/MAU", callback_data="analytics_dau"),
         InlineKeyboardButton("🏆 Top Files", callback_data="analytics_top")],
        [InlineKeyboardButton("🌍 Geography", callback_data="analytics_geo"),
         InlineKeyboardButton("🔗 Sources", callback_data="analytics_sources")],
        [InlineKeyboardButton("🔄 Funnel", callback_data="analytics_funnel"),
         InlineKeyboardButton("📈 Growth", callback_data="analytics_growth")],
        [InlineKeyboardButton("💼 Advertiser Portal", callback_data="analytics_advertise")],
    ])
    await message.reply_text(text, reply_markup=buttons)


@app.on_callback_query(filters.regex(r"^analytics_(dau|top|geo|sources|funnel|growth|advertise|menu)$"))
async def analytics_callback(client: Client, callback_query: CallbackQuery):
    section = callback_query.matches[0].group(1)
    if section == "dau":
        await show_dau_mau(client, callback_query.message, edit=True)
    elif section == "top":
        await show_top_files(client, callback_query.message, edit=True)
    elif section == "geo":
        await show_geo_distribution(client, callback_query.message, edit=True)
    elif section == "sources":
        await show_traffic_sources(client, callback_query.message, edit=True)
    elif section == "funnel":
        await show_conversion_funnel(client, callback_query.message, edit=True)
    elif section == "growth":
        await show_user_growth(client, callback_query.message, edit=True)
    elif section == "advertise":
        await show_advertiser_portal(client, callback_query.message, edit=True)
    elif section == "menu":
        await show_analytics_menu(client, callback_query.message)
    await callback_query.answer()


async def show_dau_mau(client: Client, msg: Message, edit: bool = False):
    dau = await database.get_dau(1)
    mau = await database.get_mau(30)
    total_users = await database.get_users_count()

    text = (
        "📈 **Daily & Monthly Active Users**\n\n"
        f"👥 **Total Registered Users:** `{total_users}`\n"
        f"📅 **DAU (24h):** `{dau}`\n"
        f"📆 **MAU (30d):** `{mau}`\n\n"
        f"**Engagement Ratio:** `{(dau / mau * 100) if mau > 0 else 0:.1f}%` DAU/MAU\n\n"
        "📊 *Higher DAU/MAU ratio means better user retention.*"
    )
    buttons = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="analytics_menu")]])
    if edit:
        await msg.edit_text(text, reply_markup=buttons)
    else:
        await msg.reply_text(text, reply_markup=buttons)


async def show_user_growth(client: Client, msg: Message, edit: bool = False):
    growth = await database.get_user_growth(30)
    text = (
        "📈 **User Growth (Last 30 Days)**\n\n"
        f"🆕 **New Users:** `{growth['total_new']}`\n\n"
    )
    if growth["daily"]:
        text += "**Daily New Users:**\n"
        for entry in growth["daily"][-14:]:
            text += f"  `{entry['_id']}` — **+{entry['count']}**\n"

    buttons = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="analytics_menu")]])
    if edit:
        await msg.edit_text(text, reply_markup=buttons)
    else:
        await msg.reply_text(text, reply_markup=buttons)


async def show_top_files(client: Client, msg: Message, edit: bool = False):
    top_by_views = await database.get_top_files("views", 5)
    top_by_downloads = await database.get_top_files("downloads", 5)

    text = "🏆 **Top Performing Files**\n\n"

    text += "**Most Viewed:**\n"
    if top_by_views:
        for i, f in enumerate(top_by_views, 1):
            label = f.get("label") or f.get("token", "?").split("_")[0]
            text += f"  {i}. `{label}` — {f.get('views', 0)} views\n"
    else:
        text += "  _No data yet._\n"

    text += "\n**Most Downloaded:**\n"
    if top_by_downloads:
        for i, f in enumerate(top_by_downloads, 1):
            label = f.get("label") or f.get("token", "?").split("_")[0]
            text += f"  {i}. `{label}` — {f.get('downloads', 0)} downloads\n"
    else:
        text += "  _No data yet._\n"

    buttons = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="analytics_menu")]])
    if edit:
        await msg.edit_text(text, reply_markup=buttons)
    else:
        await msg.reply_text(text, reply_markup=buttons)


async def show_geo_distribution(client: Client, msg: Message, edit: bool = False):
    geo = await database.get_geo_distribution(30)
    text = "🌍 **Geographic Distribution (Last 30 Days)**\n\n"
    if geo:
        total = sum(g["count"] for g in geo)
        for g in geo:
            pct = g["count"] / total * 100 if total > 0 else 0
            flag = country_flag(g["_id"])
            text += f"  {flag} **{g['_id']}** — {g['count']} ({pct:.1f}%)\n"
    else:
        text += "  _No geographic data collected yet._\n\n"
        text += "🌐 *Geographic data is collected when users access files through the web server.*"

    buttons = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="analytics_menu")]])
    if edit:
        await msg.edit_text(text, reply_markup=buttons)
    else:
        await msg.reply_text(text, reply_markup=buttons)


async def show_traffic_sources(client: Client, msg: Message, edit: bool = False):
    sources = await database.get_traffic_sources(30)
    text = "🔗 **Traffic Sources (Last 30 Days)**\n\n"
    if sources:
        total = sum(s["count"] for s in sources)
        for s in sources:
            pct = s["count"] / total * 100 if total > 0 else 0
            src_name = s["_id"].replace("_", " ").title() if s.get("_id") else "Direct"
            text += f"  • **{src_name}** — {s['count']} visits ({pct:.1f}%)\n"
    else:
        text += "  _No traffic source data collected._\n\n"
        text += "🔗 *Sources are tracked via funnel campaigns and web server referrals.*"

    buttons = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="analytics_menu")]])
    if edit:
        await msg.edit_text(text, reply_markup=buttons)
    else:
        await msg.reply_text(text, reply_markup=buttons)


async def show_conversion_funnel(client: Client, msg: Message, edit: bool = False):
    funnel = await database.get_conversion_funnel(30)
    text = (
        "🔄 **Conversion Funnel (Last 30 Days)**\n\n"
        f"👁 **Shortener Views:** `{funnel['shortener_view']}`\n"
        f"👇 **Shortener Clicks:** `{funnel['shortener_click']}`\n"
        f"📂 **File Views:** `{funnel['file_view']}`\n"
        f"📥 **File Downloads:** `{funnel['file_download']}`\n\n"
        f"**Conversion Rates:**\n"
        f"  View → Click: `{funnel['view_to_click_ctr']:.1f}%`\n"
        f"  Click → Download: `{funnel['click_to_download_rate']:.1f}%`\n"
    )
    buttons = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="analytics_menu")]])
    if edit:
        await msg.edit_text(text, reply_markup=buttons)
    else:
        await msg.reply_text(text, reply_markup=buttons)


@app.on_message(filters.command("advertise") & filters.private)
async def advertise_handler(client: Client, message: Message):
    await show_advertiser_portal(client, message)


async def show_advertiser_portal(client: Client, msg: Message, edit: bool = False):
    stats = await database.get_advertiser_analytics(0)

    text = (
        "💼 **Advertiser Portal**\n\n"
        "Promote your brand to our engaged audience.\n\n"
        "📊 **Platform Reach**\n"
        f"👥 Total Users: `{stats['total_users']}`\n"
        f"📅 Daily Active: `{stats['dau']}`\n"
        f"📆 Monthly Active: `{stats['mau']}`\n"
        f"📂 Total Files: `{stats['total_files']}`\n"
        f"👁 Total Views: `{stats['total_views']}`\n"
        f"📥 Total Downloads: `{stats['total_downloads']}`\n\n"
    )

    if stats["geo_distribution"]:
        text += "🌍 **Top Countries:**\n"
        for g in stats["geo_distribution"][:5]:
            flag = country_flag(g["_id"])
            text += f"  {flag} {g['_id']}: {g['count']} events\n"

    text += "\n**Available Ad Placements:**\n"
    text += "📢 Broadcast Ads — Reach all users\n"
    text += "📌 Pinned Ads — Permanent channel placement\n"
    text += "🖼 Sponsored Pages — Brand on download pages\n\n"
    text += "📩 *Contact the bot admin to purchase ad placements.*"

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Full Analytics", callback_data="analytics_menu")],
        [InlineKeyboardButton("📢 View Ad Types", callback_data="ads_main_menu")],
    ])

    if edit:
        await msg.edit_text(text, reply_markup=buttons)
    else:
        await msg.reply_text(text, reply_markup=buttons)


def country_flag(code: str) -> str:
    flags = {
        "US": "🇺🇸", "IN": "🇮🇳", "GB": "🇬🇧", "CA": "🇨🇦", "AU": "🇦🇺",
        "DE": "🇩🇪", "FR": "🇫🇷", "BR": "🇧🇷", "JP": "🇯🇵", "KR": "🇰🇷",
        "RU": "🇷🇺", "CN": "🇨🇳", "SG": "🇸🇬", "AE": "🇦🇪", "SA": "🇸🇦",
        "NL": "🇳🇱", "IT": "🇮🇹", "ES": "🇪🇸", "SE": "🇸🇪", "NO": "🇳🇴",
    }
    return flags.get(code, "🌍")
