import secrets
import logging
from bson import ObjectId
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from bot import app
import config
import database
from utils.helpers import banned_filter, extract_file_details
from utils.helpers import send_stars_invoice

logger = logging.getLogger(__name__)


def get_friendly_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


async def deliver_product_files(
    client: Client, chat_id: int, purchase: dict, product: dict
):
    """Deliver product files to user instantly and track downloads."""
    files = product.get("files", [])
    if not files:
        await client.send_message(
            chat_id, "❌ No files found for this product. Please contact support."
        )
        return

    await client.send_message(
        chat_id,
        f"🎁 **Delivering files for: {product['name']}**\n\n"
        f"Thank you for your purchase! Your files are sent below. "
        f"These will remain here permanently (no auto-deletion):",
    )

    for index, file_obj in enumerate(files):
        file_id = file_obj.get("file_id")
        caption = file_obj.get("caption", "")
        file_name = file_obj.get("file_name", f"file_{index + 1}")
        try:
            msg = await client.send_cached_media(
                chat_id=chat_id,
                file_id=file_id,
                caption=caption or f"File: {file_name}",
            )
            if msg:
                # Record the download in database
                await database.record_download(
                    purchase_id=purchase["_id"],
                    user_id=chat_id,
                    product_id=product["_id"],
                    file_id=file_id,
                )
        except Exception as e:
            logger.error(
                f"Failed to deliver product file index {index} to user {chat_id}: {e}"
            )
            await client.send_message(
                chat_id,
                f"❌ Failed to deliver file: **{file_name}** due to an internal error.",
            )


# ─── USER MARKETPLACE VIEW ──────────────────────────────────────────


@app.on_message(
    filters.command(["marketplace", "market", "shop_products"])
    & filters.private
    & ~banned_filter
)
async def marketplace_command_handler(client: Client, message: Message):
    """Enter the Digital Product Marketplace."""
    categories = await database.get_all_categories()
    if not categories:
        await database.seed_marketplace_categories()
        categories = await database.get_all_categories()

    msg = (
        "🏪 **Digital Product Marketplace** 🏪\n\n"
        "Explore premium assets, templates, overlays, and presets built to level up your content workflow.\n\n"
        "👇 Select a category to start browsing:"
    )

    buttons = []
    for cat in categories:
        buttons.append(
            [
                InlineKeyboardButton(
                    f"{cat['icon']} {cat['name']}",
                    callback_data=f"mkt_cat_{cat['slug']}",
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton("🛍 My Purchases", callback_data="mkt_my_purchases"),
            InlineKeyboardButton("🏪 My Store", callback_data="mkt_seller_dashboard"),
        ]
    )

    await message.reply_text(msg, reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^mkt_menu$") & ~banned_filter)
async def mkt_menu_callback(client: Client, callback_query: CallbackQuery):
    """Display the main marketplace categories."""
    categories = await database.get_all_categories()
    msg = (
        "🏪 **Digital Product Marketplace** 🏪\n\n"
        "Explore premium assets, templates, overlays, and presets built to level up your content workflow.\n\n"
        "👇 Select a category to start browsing:"
    )

    buttons = []
    for cat in categories:
        buttons.append(
            [
                InlineKeyboardButton(
                    f"{cat['icon']} {cat['name']}",
                    callback_data=f"mkt_cat_{cat['slug']}",
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton("🛍 My Purchases", callback_data="mkt_my_purchases"),
            InlineKeyboardButton("🏪 My Store", callback_data="mkt_seller_dashboard"),
        ]
    )

    await callback_query.answer()
    await callback_query.message.edit_text(
        msg, reply_markup=InlineKeyboardMarkup(buttons)
    )


@app.on_callback_query(filters.regex(r"^mkt_cat_([a-zA-Z0-9_]+)$") & ~banned_filter)
async def mkt_category_callback(client: Client, callback_query: CallbackQuery):
    """Display active products in a specific category."""
    category_slug = callback_query.matches[0].group(1)
    category = await database.get_category_by_slug(category_slug)
    if not category:
        await callback_query.answer("❌ Category not found.", show_alert=True)
        return

    products = await database.get_products(category_id=category["_id"], is_active=True)
    msg = f"{category['icon']} **Category: {category['name']}**\n\n"
    if category.get("description"):
        msg += f"_{category['description']}_\n\n"

    keyboard = []
    if not products:
        msg += "📭 No products listed in this category yet."
        keyboard.append(
            [
                InlineKeyboardButton(
                    "➕ Sell a Product", callback_data=f"mkt_add_cat_{category_slug}"
                )
            ]
        )
    else:
        msg += "Select a product to view details:"
        for p in products:
            price_label = ""
            if p.get("price", 0) > 0 and p.get("price_upi", 0.0) > 0.0:
                price_label = f"({p['price']} ⭐️ / ₹{p['price_upi']})"
            elif p.get("price", 0) > 0:
                price_label = f"({p['price']} ⭐️)"
            elif p.get("price_upi", 0.0) > 0.0:
                price_label = f"(₹{p['price_upi']})"
            else:
                price_label = "(Free)"

            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"📄 {p['name']} {price_label}",
                        callback_data=f"mkt_prod_{p['_id']}",
                    )
                ]
            )

    keyboard.append(
        [InlineKeyboardButton("🔙 Back to Categories", callback_data="mkt_menu")]
    )
    await callback_query.answer()
    await callback_query.message.edit_text(
        msg, reply_markup=InlineKeyboardMarkup(keyboard)
    )


@app.on_callback_query(filters.regex(r"^mkt_prod_([a-fA-F0-9]{24})$") & ~banned_filter)
async def mkt_product_detail_callback(client: Client, callback_query: CallbackQuery):
    """Show details of a specific product."""
    user_id = callback_query.from_user.id
    prod_id = callback_query.matches[0].group(1)
    product = await database.get_product_by_id(ObjectId(prod_id))
    if not product:
        await callback_query.answer("❌ Product not found.", show_alert=True)
        return

    # Increment view count
    await database.increment_product_views(product["_id"])

    await callback_query.answer()
    await show_product_card(
        client,
        callback_query.message.chat.id,
        product,
        user_id,
        edit_message_id=callback_query.message.id,
    )


@app.on_callback_query(filters.regex(r"^mkt_dl_([a-fA-F0-9]{24})$") & ~banned_filter)
async def mkt_download_callback(client: Client, callback_query: CallbackQuery):
    """Deliver product files upon purchase verification."""
    user_id = callback_query.from_user.id
    prod_id = callback_query.matches[0].group(1)
    product = await database.get_product_by_id(ObjectId(prod_id))
    if not product:
        await callback_query.answer("❌ Product not found.", show_alert=True)
        return

    # Check permission
    is_owner = product["owner_id"] == user_id
    is_bot_admin = await database.is_admin(user_id, client)
    has_purchased = await database.verify_purchase(user_id, product["_id"])
    is_free = product.get("price", 0) == 0 and product.get("price_upi", 0.0) == 0.0

    if not (is_owner or is_bot_admin or has_purchased or is_free):
        await callback_query.answer(
            "⛔️ Access denied. Please purchase this product first.", show_alert=True
        )
        return

    await callback_query.answer("⚡ Delivering product files...")
    await callback_query.message.delete()

    # Since there is no purchase record for free/owner downloads, we can find/create a dummy purchase dict or pass None
    purchase = None
    if has_purchased:
        purchases = await database.get_user_purchases(user_id)
        for p in purchases:
            if p["product_id"] == product["_id"]:
                purchase = p
                break

    if not purchase:
        # Create a dummy purchase record if it's owner/admin/free download so tracking doesn't crash
        dummy_purchase_id = ObjectId()
        purchase = {"_id": dummy_purchase_id}

    await deliver_product_files(client, user_id, purchase, product)


# ─── PURCHASE CHECKS AND CHECOUT ACTIONS ───────────────────────────


@app.on_callback_query(
    filters.regex(r"^mkt_buy_(stars|upi)_([a-fA-F0-9]{24})$") & ~banned_filter
)
async def mkt_buy_callback(client: Client, callback_query: CallbackQuery):
    """Start checkout process for a product."""
    user_id = callback_query.from_user.id
    method = callback_query.matches[0].group(1)
    prod_id = callback_query.matches[0].group(2)

    product = await database.get_product_by_id(ObjectId(prod_id))
    if not product:
        await callback_query.answer("❌ Product not found.", show_alert=True)
        return

    await callback_query.answer()

    if method == "stars":
        title = product["name"]
        if len(title) > 30:
            title = title[:27] + "..."
        desc = f"Purchase product: {product['name']}"
        if len(desc) > 250:
            desc = desc[:247] + "..."

        payload = f"prod_buy_{prod_id}"

        try:
            await callback_query.message.delete()
            await send_stars_invoice(
                client=client,
                chat_id=user_id,
                title=title,
                description=desc,
                payload=payload,
                amount=product["price"],
            )
        except Exception as e:
            logger.error(
                f"Failed to send stars invoice for marketplace product {prod_id}: {e}"
            )
            await client.send_message(
                chat_id=user_id,
                text="❌ **Failed to generate invoice.** Please try again or contact support.",
            )

    elif method == "upi":
        # Check for existing pending UPI payment
        existing = await database.get_pending_upi(user_id)
        if existing:
            await callback_query.message.edit_text(
                "⚠️ **You already have a pending UPI request!**\n\n"
                "Please complete the previous request or wait for an admin to process it.\n"
                "If you need to submit a new screenshot, just send it now."
            )
            return

        plan_name = f"prod_{prod_id}"
        price_upi = product["price_upi"]
        await database.create_upi_payment(user_id, plan_name, price_upi)

        upi_instructions = (
            "💸 **UPI Payment Details:**\n\n"
            f"Please send **₹{price_upi}** to the UPI ID below to purchase **{product['name']}**:\n"
            f"`{config.UPI_ID}`\n\n"
            "⚠️ **Step 2:** After transferring the amount, take a screenshot of the transaction receipt "
            "and **send the screenshot (photo) directly to this bot**.\n\n"
            "Once received, our admins will verify the payment and unlock the product."
        )

        if config.UPI_QR_IMAGE:
            try:
                await callback_query.message.delete()
                await client.send_photo(
                    chat_id=user_id, photo=config.UPI_QR_IMAGE, caption=upi_instructions
                )
                return
            except Exception as e:
                logger.error(f"Failed to send UPI QR image: {e}")

        await callback_query.message.edit_text(upi_instructions)


# ─── SELLER DASHBOARD ───────────────────────────────────────────────


@app.on_callback_query(filters.regex(r"^mkt_seller_dashboard$") & ~banned_filter)
async def mkt_seller_dashboard_callback(client: Client, callback_query: CallbackQuery):
    """View creator seller stats and dashboard."""
    user_id = callback_query.from_user.id

    my_products = await database.get_products_by_owner(user_id)
    total_products = len(my_products)

    total_sales = 0
    total_revenue_upi = 0.0
    for p in my_products:
        total_sales += p.get("sales_count", 0)
        # Calculate revenue of this product from completed purchases
        purchases = await database.get_purchases_by_product(p["_id"])
        total_revenue_upi += sum(
            pur.get("amount_paid", 0)
            for pur in purchases
            if pur.get("status") == "completed"
        )

    msg = (
        "🏪 **Creator Store Dashboard** 🏪\n"
        "-------------------------------------\n"
        f"📦 **Listed Products:** {total_products}\n"
        f"📈 **Total Product Sales:** {total_sales} units\n"
        f"💰 **Total Revenue Generated:** ₹{total_revenue_upi:.2f} INR\n\n"
        "Manage your digital products, view detailed performance stats, or add new items below:"
    )

    buttons = [
        [InlineKeyboardButton("➕ Add New Product", callback_data="mkt_wizard_start")],
        (
            [
                InlineKeyboardButton(
                    "📦 My Products", callback_data="mkt_my_products_list"
                )
            ]
            if total_products > 0
            else []
        ),
        [InlineKeyboardButton("🔙 Back to Marketplace", callback_data="mkt_menu")],
    ]
    # Filter empty rows
    buttons = [b for b in buttons if b]

    await callback_query.answer()
    await callback_query.message.edit_text(
        msg, reply_markup=InlineKeyboardMarkup(buttons)
    )


@app.on_callback_query(filters.regex(r"^mkt_my_products_list$") & ~banned_filter)
async def mkt_my_products_list_callback(client: Client, callback_query: CallbackQuery):
    """List products uploaded by this creator."""
    user_id = callback_query.from_user.id
    my_products = await database.get_products_by_owner(user_id)

    msg = "📦 **My Listed Products:**\n\nSelect a product to view detailed seller stats or delete it:"
    keyboard = []

    for p in my_products:
        status_symbol = "🟢" if p.get("is_active", True) else "🔴"
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{status_symbol} {p['name']}", callback_data=f"mkt_prod_{p['_id']}"
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                "🔙 Back to Dashboard", callback_data="mkt_seller_dashboard"
            )
        ]
    )
    await callback_query.answer()
    await callback_query.message.edit_text(
        msg, reply_markup=InlineKeyboardMarkup(keyboard)
    )


@app.on_callback_query(
    filters.regex(r"^mkt_pstats_([a-fA-F0-9]{24})$") & ~banned_filter
)
async def mkt_product_stats_callback(client: Client, callback_query: CallbackQuery):
    """Show detailed stats of a specific product to its seller/admin."""
    user_id = callback_query.from_user.id
    prod_id = callback_query.matches[0].group(1)
    product = await database.get_product_by_id(ObjectId(prod_id))
    if not product:
        await callback_query.answer("❌ Product not found.", show_alert=True)
        return

    # Check permission
    is_owner = product["owner_id"] == user_id
    is_bot_admin = await database.is_admin(user_id, client)
    if not (is_owner or is_bot_admin):
        await callback_query.answer("⛔️ Permission Denied.", show_alert=True)
        return

    stats = await database.get_product_stats(product["_id"])

    msg = (
        f"📊 **Product Performance Stats:**\n"
        f"📄 **Product Name:** {product['name']}\n"
        f"-----------------------------------------\n"
        f"👁️ **Total Views:** {stats.get('views', 0)}\n"
        f"📈 **Completed Sales:** {stats.get('sales_count', 0)} purchases\n"
        f"📥 **Total Downloads:** {stats.get('total_downloads', 0)} times\n"
        f"👥 **Unique Downloaders:** {stats.get('unique_downloaders', 0)} users\n"
        f"💰 **Total Revenue:** ₹{stats.get('total_revenue', 0.0):.2f} INR\n"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🔙 Back to Product Details", callback_data=f"mkt_prod_{prod_id}"
            )
        ]
    ]
    await callback_query.answer()
    await callback_query.message.edit_text(
        msg, reply_markup=InlineKeyboardMarkup(keyboard)
    )


@app.on_callback_query(filters.regex(r"^mkt_del_([a-fA-F0-9]{24})$") & ~banned_filter)
async def mkt_delete_product_callback(client: Client, callback_query: CallbackQuery):
    """Delete a product permanently."""
    user_id = callback_query.from_user.id
    prod_id = callback_query.matches[0].group(1)
    product = await database.get_product_by_id(ObjectId(prod_id))
    if not product:
        await callback_query.answer("❌ Product not found.", show_alert=True)
        return

    # Check permission
    is_owner = product["owner_id"] == user_id
    is_bot_admin = await database.is_admin(user_id, client)
    if not (is_owner or is_bot_admin):
        await callback_query.answer("⛔️ Permission Denied.", show_alert=True)
        return

    deleted = await database.delete_product(product["_id"])
    if deleted:
        await callback_query.answer("🗑️ Product deleted permanently!", show_alert=True)
        # Go back to store dashboard
        my_products = await database.get_products_by_owner(user_id)
        if my_products:
            await mkt_my_products_list_callback(client, callback_query)
        else:
            await mkt_seller_dashboard_callback(client, callback_query)
    else:
        await callback_query.answer("❌ Failed to delete product.", show_alert=True)


# ─── MY PURCHASES VIEW ──────────────────────────────────────────────


@app.on_callback_query(filters.regex(r"^mkt_my_purchases$") & ~banned_filter)
async def mkt_my_purchases_callback(client: Client, callback_query: CallbackQuery):
    """View products purchased by user."""
    user_id = callback_query.from_user.id
    purchases = await database.get_user_purchases(user_id)

    msg = "🛍 **My Purchased Products:**\n\nClick on a product to view details and download files:"
    keyboard = []

    product_ids_seen = set()
    for p in purchases:
        if p.get("status") == "completed" and p["product_id"] not in product_ids_seen:
            product_ids_seen.add(p["product_id"])
            product = await database.get_product_by_id(p["product_id"])
            if product:
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"🎁 {product['name']}",
                            callback_data=f"mkt_prod_{product['_id']}",
                        )
                    ]
                )

    if not keyboard:
        msg = "🛍 **My Purchased Products:**\n\nYou haven't purchased any products yet."

    keyboard.append(
        [InlineKeyboardButton("🔙 Back to Marketplace", callback_data="mkt_menu")]
    )
    await callback_query.answer()
    await callback_query.message.edit_text(
        msg, reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ─── INTERACTIVE ADD PRODUCT FLOW WIZARD ────────────────────────────


@app.on_message(
    filters.command(["add_product", "sell"]) & filters.private & ~banned_filter
)
async def add_product_command_handler(client: Client, message: Message):
    """Start interactive product addition flow."""
    categories = await database.get_all_categories()
    if not categories:
        await database.seed_marketplace_categories()
        categories = await database.get_all_categories()

    msg = (
        "➕ **List New Product for Sale**\n\n"
        "Please select a category for the digital product:"
    )

    buttons = []
    for cat in categories:
        buttons.append(
            [
                InlineKeyboardButton(
                    f"{cat['icon']} {cat['name']}",
                    callback_data=f"mkt_wizard_cat_{cat['slug']}",
                )
            ]
        )
    buttons.append(
        [InlineKeyboardButton("❌ Cancel", callback_data="mkt_wizard_cancel")]
    )

    await message.reply_text(msg, reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^mkt_wizard_start$") & ~banned_filter)
async def mkt_wizard_start_callback(client: Client, callback_query: CallbackQuery):
    """Start wizard via callback."""
    categories = await database.get_all_categories()
    msg = (
        "➕ **List New Product for Sale**\n\n"
        "Please select a category for the digital product:"
    )
    buttons = []
    for cat in categories:
        buttons.append(
            [
                InlineKeyboardButton(
                    f"{cat['icon']} {cat['name']}",
                    callback_data=f"mkt_wizard_cat_{cat['slug']}",
                )
            ]
        )
    buttons.append(
        [InlineKeyboardButton("❌ Cancel", callback_data="mkt_wizard_cancel")]
    )

    await callback_query.answer()
    await callback_query.message.edit_text(
        msg, reply_markup=InlineKeyboardMarkup(buttons)
    )


@app.on_callback_query(
    filters.regex(r"^mkt_wizard_cat_([a-zA-Z0-9_]+)$") & ~banned_filter
)
async def mkt_wizard_cat_callback(client: Client, callback_query: CallbackQuery):
    """Save category and request product title."""
    user_id = callback_query.from_user.id
    category_slug = callback_query.matches[0].group(1)

    draft = {"category": category_slug, "files": []}
    await database.users_col.update_one(
        {"_id": user_id},
        {"$set": {"state": "market_awaiting_name", "marketplace_draft": draft}},
    )

    await callback_query.answer()
    await callback_query.message.edit_text(
        "📝 **Step 2: Enter Product Name**\n\n"
        "Type the name of your product (e.g., `Cinematic Teal & Orange LUTs`):",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="mkt_wizard_cancel")]]
        ),
    )


@app.on_callback_query(filters.regex(r"^mkt_wizard_cancel$") & ~banned_filter)
async def mkt_wizard_cancel_callback(client: Client, callback_query: CallbackQuery):
    """Cancel the wizard."""
    user_id = callback_query.from_user.id
    await database.users_col.update_one(
        {"_id": user_id}, {"$unset": {"state": "", "marketplace_draft": ""}}
    )
    await callback_query.answer("Wizard cancelled.")
    await callback_query.message.edit_text("❌ Product creation cancelled.")


async def handle_marketplace_state(
    client: Client, message: Message, user_id: int, state: str, user_doc: dict
):
    """Handle text and file inputs for the marketplace upload wizard."""
    text = message.text.strip() if message.text else ""
    draft = user_doc.get("marketplace_draft", {})

    if state == "market_awaiting_name":
        if not text:
            await message.reply_text(
                "❌ Product name cannot be empty. Please send a valid name:"
            )
            return

        draft["name"] = text
        await database.users_col.update_one(
            {"_id": user_id},
            {"$set": {"state": "market_awaiting_desc", "marketplace_draft": draft}},
        )
        await message.reply_text(
            "📝 **Step 3: Enter Product Description**\n\n"
            "Provide a description explaining what this product is and what is included in the package:"
        )

    elif state == "market_awaiting_desc":
        if not text:
            await message.reply_text(
                "❌ Description cannot be empty. Please send a valid description:"
            )
            return

        draft["description"] = text
        await database.users_col.update_one(
            {"_id": user_id},
            {
                "$set": {
                    "state": "market_awaiting_price_stars",
                    "marketplace_draft": draft,
                }
            },
        )
        await message.reply_text(
            "⭐️ **Step 4: Price in Telegram Stars**\n\n"
            "Send the price of this item in Telegram Stars (must be a positive integer, e.g. `100`).\n"
            "Type `0` to disable Telegram Stars purchase option:"
        )

    elif state == "market_awaiting_price_stars":
        try:
            price = int(text)
            if price < 0:
                raise ValueError
        except ValueError:
            await message.reply_text(
                "❌ Price must be a positive integer. Enter Price in Stars:"
            )
            return

        draft["price_stars"] = price
        await database.users_col.update_one(
            {"_id": user_id},
            {
                "$set": {
                    "state": "market_awaiting_price_upi",
                    "marketplace_draft": draft,
                }
            },
        )
        await message.reply_text(
            "💸 **Step 5: Price in INR (UPI)**\n\n"
            "Send the price of this item in Indian Rupees (INR) for UPI payments (e.g. `49` or `99`).\n"
            "Type `0` to disable UPI purchase option:"
        )

    elif state == "market_awaiting_price_upi":
        try:
            price_upi = float(text)
            if price_upi < 0.0:
                raise ValueError
        except ValueError:
            await message.reply_text(
                "❌ Price must be a positive decimal number. Enter UPI Price:"
            )
            return

        if draft.get("price_stars", 0) == 0 and price_upi == 0.0:
            await message.reply_text(
                "❌ Both Stars price and UPI price cannot be 0. Please enter a valid UPI price higher than 0.0:"
            )
            return

        draft["price_upi"] = price_upi
        draft["files"] = []
        await database.users_col.update_one(
            {"_id": user_id},
            {"$set": {"state": "market_awaiting_files", "marketplace_draft": draft}},
        )
        await message.reply_text(
            "📁 **Step 6: Send Product Files**\n\n"
            "Send/upload the files (presets, templates, overlays, etc.) that you want to attach to this product. "
            "You can upload multiple files.\n\n"
            "Once you have uploaded all your files, click the **✅ Done** button below to list your product.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ Done Uploading", callback_data="mkt_wizard_done"
                        )
                    ]
                ]
            ),
        )

    elif state == "market_awaiting_files":
        # Check if the user sent a file media message
        file_id, file_unique_id, file_name, file_type, file_size, caption = (
            extract_file_details(message)
        )
        if not file_id:
            await message.reply_text(
                "❌ Please send a valid file (Document, Video, Audio, Photo, etc.)."
            )
            return

        media_type = "document"
        if file_type == "photo":
            media_type = "photo"
        elif file_type in ["video", "animation"]:
            media_type = "video"
        elif file_type in ["audio", "voice"]:
            media_type = "audio"

        files = draft.get("files", [])
        # Prevent duplicates
        for f in files:
            if f.get("file_unique_id") == file_unique_id:
                return

        new_file = {
            "file_id": file_id,
            "file_unique_id": file_unique_id,
            "media_type": media_type,
            "caption": caption or None,
            "file_name": file_name,
            "file_size": file_size,
        }
        files.append(new_file)
        draft["files"] = files

        await database.users_col.update_one(
            {"_id": user_id}, {"$set": {"marketplace_draft": draft}}
        )

        friendly_size = get_friendly_size(file_size)
        await message.reply_text(
            f"📎 **File Added Successfully!**\n"
            f"📄 **Name:** `{file_name}`\n"
            f"⚖️ **Size:** {friendly_size}\n\n"
            f"Total files uploaded: **{len(files)}**.\n"
            f"Upload more files, or click the button below to finish:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ Done Uploading", callback_data="mkt_wizard_done"
                        )
                    ]
                ]
            ),
        )


@app.on_callback_query(filters.regex(r"^mkt_wizard_done$") & ~banned_filter)
async def mkt_wizard_done_callback(client: Client, callback_query: CallbackQuery):
    """Finalize product creation and save to database."""
    user_id = callback_query.from_user.id
    user_doc = await database.get_user(user_id)
    if not user_doc or user_doc.get("state") != "market_awaiting_files":
        await callback_query.answer(
            "⚠️ No active creation wizard session.", show_alert=True
        )
        return

    draft = user_doc.get("marketplace_draft", {})
    files = draft.get("files", [])
    if not files:
        await callback_query.answer(
            "❌ You must upload at least one file before finishing!", show_alert=True
        )
        return

    await callback_query.answer("🔨 Creating product link...")

    # Generate token
    token = secrets.token_urlsafe(8)
    # Ensure token uniqueness
    while await database.get_product_by_token(token):
        token = secrets.token_urlsafe(8)

    # Get category ObjectId
    category = await database.get_category_by_slug(draft["category"])
    cat_id = category["_id"] if category else None

    # Save product
    product = await database.create_product(
        token=token,
        name=draft["name"],
        description=draft["description"],
        price=draft["price_stars"],
        owner_id=user_id,
        category_id=cat_id,
        product_type=draft["category"],
        files=files,
        price_upi=draft["price_upi"],
    )

    # Clear state
    await database.users_col.update_one(
        {"_id": user_id}, {"$unset": {"state": "", "marketplace_draft": ""}}
    )

    bot_me = client.me or await client.get_me()
    product_link = f"https://t.me/{bot_me.username}?start=prod_{token}"

    success_msg = (
        "🎉 **Digital Product Listed Successfully!**\n\n"
        f"🆔 **Product ID:** `{product['_id']}`\n"
        f"📄 **Name:** {draft['name']}\n"
        f"📁 **Category:** {category['name'] if category else draft['category']}\n"
        f"⭐️ **Stars Price:** {draft['price_stars']} Stars\n"
        f"💸 **UPI Price:** ₹{draft['price_upi']} INR\n"
        f"📦 **Attached Files:** {len(files)} file(s)\n\n"
        f"🔗 **Product Share Link:**\n`{product_link}`\n\n"
        f"Share this link directly with your audience! They will be prompted to purchase and instantly unlock the files."
    )

    await callback_query.message.edit_text(success_msg)


async def show_product_card(
    client: Client,
    chat_id: int,
    product: dict,
    user_id: int,
    edit_message_id: int = None,
):
    """Render and display product details card to the user."""
    # Determine product type display name and icon
    type_name = database.PRODUCT_TYPE_NAMES.get(
        product["product_type"], product["product_type"].replace("_", " ").title()
    )
    type_icon = database.PRODUCT_TYPE_ICONS.get(product["product_type"], "📁")

    creator_name = "Creator"
    creator = await database.get_user(product["owner_id"])
    if creator:
        creator_name = (
            f"@{creator.get('username')}"
            if creator.get("username")
            else creator.get("first_name", "Creator")
        )

    msg = (
        f"{type_icon} **{product['name']}**\n"
        f"-----------------------------------------\n"
        f"📝 **Description:**\n{product['description']}\n\n"
        f"📁 **Product Type:** {type_name}\n"
        f"👤 **Seller:** {creator_name}\n"
        f"📈 **Popularity:** {product.get('sales_count', 0)} sales | {product.get('views', 0)} views\n"
        f"📦 **Files count:** {len(product.get('files', []))} item(s)\n"
    )

    buttons = []

    # Check if the user is the creator or an admin
    is_owner = product["owner_id"] == user_id
    is_bot_admin = await database.is_admin(user_id, client)

    # Check if purchased
    has_purchased = await database.verify_purchase(user_id, product["_id"])

    if is_owner or is_bot_admin or has_purchased:
        if is_owner or is_bot_admin:
            msg += "\n⭐ **You are the Seller / Admin of this product.**"
        else:
            msg += "\n✅ **You already own this product!**"

        buttons.append(
            [
                InlineKeyboardButton(
                    "📥 Download Product Files",
                    callback_data=f"mkt_dl_{product['_id']}",
                )
            ]
        )
        if is_owner or is_bot_admin:
            buttons.append(
                [
                    InlineKeyboardButton(
                        "📊 Stats", callback_data=f"mkt_pstats_{product['_id']}"
                    ),
                    InlineKeyboardButton(
                        "🗑 Delete Product", callback_data=f"mkt_del_{product['_id']}"
                    ),
                ]
            )
    else:
        stars_price = product.get("price", 0)
        upi_price = product.get("price_upi", 0.0)

        if stars_price == 0 and upi_price == 0.0:
            msg += "\n🎁 **This product is free!**"
            buttons.append(
                [
                    InlineKeyboardButton(
                        "📥 Download Product Files",
                        callback_data=f"mkt_dl_{product['_id']}",
                    )
                ]
            )
        else:
            msg += "\n💳 **Purchase Options:**\n"
            buy_row = []
            if stars_price > 0:
                msg += f"• **Telegram Stars:** {stars_price} ⭐️\n"
                buy_row.append(
                    InlineKeyboardButton(
                        f"⭐️ Buy ({stars_price} Stars)",
                        callback_data=f"mkt_buy_stars_{product['_id']}",
                    )
                )
            if upi_price > 0.0:
                msg += f"• **UPI Transfer:** ₹{upi_price} INR\n"
                buy_row.append(
                    InlineKeyboardButton(
                        f"💸 Buy (₹{upi_price} UPI)",
                        callback_data=f"mkt_buy_upi_{product['_id']}",
                    )
                )

            buttons.append(buy_row)

    cat_slug = product["product_type"]
    buttons.append(
        [InlineKeyboardButton("🔙 Back to List", callback_data=f"mkt_cat_{cat_slug}")]
    )

    if edit_message_id:
        try:
            await client.edit_message_text(
                chat_id=chat_id,
                message_id=edit_message_id,
                text=msg,
                reply_markup=InlineKeyboardMarkup(buttons),
            )
        except Exception:
            await client.send_message(
                chat_id=chat_id, text=msg, reply_markup=InlineKeyboardMarkup(buttons)
            )
    else:
        await client.send_message(
            chat_id=chat_id, text=msg, reply_markup=InlineKeyboardMarkup(buttons)
        )


@app.on_message(
    filters.command(["seller", "store_dashboard", "seller_dashboard"])
    & filters.private
    & ~banned_filter
)
async def seller_dashboard_command_handler(client: Client, message: Message):
    """View creator seller stats and dashboard via command."""
    user_id = message.from_user.id
    my_products = await database.get_products_by_owner(user_id)
    total_products = len(my_products)

    total_sales = 0
    total_revenue_upi = 0.0
    for p in my_products:
        total_sales += p.get("sales_count", 0)
        purchases = await database.get_purchases_by_product(p["_id"])
        total_revenue_upi += sum(
            pur.get("amount_paid", 0)
            for pur in purchases
            if pur.get("status") == "completed"
        )

    msg = (
        "🏪 **Creator Store Dashboard** 🏪\n"
        "-------------------------------------\n"
        f"📦 **Listed Products:** {total_products}\n"
        f"📈 **Total Product Sales:** {total_sales} units\n"
        f"💰 **Total Revenue Generated:** ₹{total_revenue_upi:.2f} INR\n\n"
        "Manage your digital products, view detailed performance stats, or add new items below:"
    )

    buttons = [
        [InlineKeyboardButton("➕ Add New Product", callback_data="mkt_wizard_start")],
        (
            [
                InlineKeyboardButton(
                    "📦 My Products", callback_data="mkt_my_products_list"
                )
            ]
            if total_products > 0
            else []
        ),
        [InlineKeyboardButton("🔙 Back to Marketplace", callback_data="mkt_menu")],
    ]
    buttons = [b for b in buttons if b]

    await message.reply_text(msg, reply_markup=InlineKeyboardMarkup(buttons))


@app.on_message(filters.command("my_products") & filters.private & ~banned_filter)
async def my_products_command_handler(client: Client, message: Message):
    """List products uploaded by this creator via command."""
    user_id = message.from_user.id
    my_products = await database.get_products_by_owner(user_id)

    msg = "📦 **My Listed Products:**\n\nSelect a product to view detailed seller stats or delete it:"
    keyboard = []

    for p in my_products:
        status_symbol = "🟢" if p.get("is_active", True) else "🔴"
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{status_symbol} {p['name']}", callback_data=f"mkt_prod_{p['_id']}"
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                "🔙 Back to Dashboard", callback_data="mkt_seller_dashboard"
            )
        ]
    )
    await message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
