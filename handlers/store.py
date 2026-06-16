from __future__ import annotations

import logging

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from bson import ObjectId
from bot import app
from database.products import (
    get_all_categories,
    get_products,
    get_product_by_id,
    get_featured_products,
    get_newest_products,
    get_top_selling_products,
    PRODUCT_TYPE_NAMES,
    PRODUCT_TYPE_ICONS,
)
from utils.helpers import banned_filter
from utils.text_safety import escape_markdown
import database

logger = logging.getLogger(__name__)


@app.on_message(filters.command("store") & filters.private & ~banned_filter)
async def store_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    args = message.text.split(None, 1)
    sub = args[1].strip() if len(args) > 1 else ""

    if sub == "featured":
        await show_featured_products(client, message, user_id)
    elif sub == "new":
        await show_newest_products(client, message, user_id)
    elif sub == "top":
        await show_top_products(client, message, user_id)
    elif sub == "categories":
        await show_categories_menu(client, message, user_id)
    else:
        await show_store_home(client, message, user_id)


async def show_store_home(client: Client, msg: Message, user_id: int):
    text = (
        "🛍️ **Premium Store**\n\n"
        "Browse digital products available for purchase.\n\n"
        "**Commands:**\n"
        "• `/store featured` — Featured products\n"
        "• `/store new` — Newest arrivals\n"
        "• `/store top` — Top selling\n"
        "• `/store categories` — Browse by category\n\n"
        "Select an option below:"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Featured", callback_data="store_featured")],
        [InlineKeyboardButton("🆕 Newest", callback_data="store_new")],
        [InlineKeyboardButton("🏆 Top Selling", callback_data="store_top")],
        [InlineKeyboardButton("📂 Categories", callback_data="store_categories")],
    ])
    await msg.reply_text(text, reply_markup=buttons)


@app.on_callback_query(filters.regex(r"^store_(featured|new|top|categories|back)$"))
async def store_callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    action = callback_query.matches[0].group(1)

    if action == "featured":
        await show_featured_products(client, callback_query.message, user_id, edit=True)
    elif action == "new":
        await show_newest_products(client, callback_query.message, user_id, edit=True)
    elif action == "top":
        await show_top_products(client, callback_query.message, user_id, edit=True)
    elif action == "categories":
        await show_categories_menu(client, callback_query.message, user_id, edit=True)
    elif action == "back":
        await show_store_home(client, callback_query.message, user_id)

    await callback_query.answer()


async def show_featured_products(client: Client, msg: Message, user_id: int, edit: bool = False):
    products = await get_featured_products(limit=10)
    text = "⭐ **Featured Products**\n\n"
    buttons = []
    if products:
        for i, p in enumerate(products, 1):
            icon = PRODUCT_TYPE_ICONS.get(p.get("product_type", ""), "📦")
            text += f"{i}. {icon} **{escape_markdown(p['name'])}** — {p['price']} ⭐️\n"
            buttons.append([InlineKeyboardButton(f"🛒 Buy {p['name']}", callback_data=f"buy_prod_{p['_id']}")])
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="store_back")])
    else:
        text += "_No featured products yet._"
        buttons = [[InlineKeyboardButton("🔙 Back", callback_data="store_back")]]

    reply_markup = InlineKeyboardMarkup(buttons)
    if edit:
        await msg.edit_text(text, reply_markup=reply_markup)
    else:
        await msg.reply_text(text, reply_markup=reply_markup)


async def show_newest_products(client: Client, msg: Message, user_id: int, edit: bool = False):
    products = await get_newest_products(limit=10)
    text = "🆕 **Newest Products**\n\n"
    buttons = []
    if products:
        for i, p in enumerate(products, 1):
            icon = PRODUCT_TYPE_ICONS.get(p.get("product_type", ""), "📦")
            text += f"{i}. {icon} **{escape_markdown(p['name'])}** — {p['price']} ⭐️\n"
            buttons.append([InlineKeyboardButton(f"🛒 Buy {p['name']}", callback_data=f"buy_prod_{p['_id']}")])
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="store_back")])
    else:
        text += "_No products yet._"
        buttons = [[InlineKeyboardButton("🔙 Back", callback_data="store_back")]]

    reply_markup = InlineKeyboardMarkup(buttons)
    if edit:
        await msg.edit_text(text, reply_markup=reply_markup)
    else:
        await msg.reply_text(text, reply_markup=reply_markup)


async def show_top_products(client: Client, msg: Message, user_id: int, edit: bool = False):
    products = await get_top_selling_products(limit=10)
    text = "🏆 **Top Selling Products**\n\n"
    buttons = []
    if products:
        for i, p in enumerate(products, 1):
            icon = PRODUCT_TYPE_ICONS.get(p.get("product_type", ""), "📦")
            text += f"{i}. {icon} **{escape_markdown(p['name'])}** — {p['price']} ⭐️ ({p.get('sales_count', 0)} sold)\n"
            buttons.append([InlineKeyboardButton(f"🛒 Buy {p['name']}", callback_data=f"buy_prod_{p['_id']}")])
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="store_back")])
    else:
        text += "_No sales data yet._"
        buttons = [[InlineKeyboardButton("🔙 Back", callback_data="store_back")]]

    reply_markup = InlineKeyboardMarkup(buttons)
    if edit:
        await msg.edit_text(text, reply_markup=reply_markup)
    else:
        await msg.reply_text(text, reply_markup=reply_markup)


async def show_categories_menu(client: Client, msg: Message, user_id: int, edit: bool = False):
    categories = await get_all_categories()
    text = "📂 **Product Categories**\n\n"
    buttons = []
    for cat in categories:
        icon = cat.get("icon", "📁")
        buttons.append([InlineKeyboardButton(f"{icon} {cat['name']}", callback_data=f"store_cat_{cat['_id']}")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="store_back")])

    reply_markup = InlineKeyboardMarkup(buttons)
    if edit:
        await msg.edit_text(text, reply_markup=reply_markup)
    else:
        await msg.reply_text(text, reply_markup=reply_markup)


@app.on_callback_query(filters.regex(r"^store_cat_(.+)"))
async def store_category_callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    cat_id = callback_query.matches[0].group(1)
    await callback_query.answer()

    try:
        products = await get_products(category_id=ObjectId(cat_id), limit=20)
    except Exception:
        products = []

    text = "📂 **Category Products**\n\n"
    buttons = []
    if products:
        for i, p in enumerate(products, 1):
            icon = PRODUCT_TYPE_ICONS.get(p.get("product_type", ""), "📦")
            text += f"{i}. {icon} **{escape_markdown(p['name'])}** — {p['price']} ⭐️\n"
            buttons.append([InlineKeyboardButton(f"🛒 Buy {p['name']}", callback_data=f"buy_prod_{p['_id']}")])
        buttons.append([InlineKeyboardButton("🔙 Back to Categories", callback_data="store_categories")])
    else:
        text += "_No products in this category._"
        buttons = [[InlineKeyboardButton("🔙 Back to Categories", callback_data="store_categories")]]

    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
