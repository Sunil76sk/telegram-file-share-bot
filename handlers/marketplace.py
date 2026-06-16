from __future__ import annotations

import logging
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bson import ObjectId
from bot import app
import database
import config
from utils.helpers import send_stars_invoice
from utils.text_safety import escape_markdown

logger = logging.getLogger(__name__)


async def deliver_product_files(client: Client, user_id: int, purchase: dict, product: dict):
    """Deliver product files to the user via send_cached_media."""
    files = product.get("files", [])
    if not files:
        await client.send_message(user_id, "⚠️ **No files associated with this product.**")
        return

    await client.send_message(user_id, f"📦 **Delivering files for {product['name']}:**")
    for file in files:
        try:
            # Deliver each file safely using Pyrogram's send_cached_media
            await client.send_cached_media(
                chat_id=user_id,
                file_id=file["file_id"],
                caption=f"📁 **File:** {file.get('file_name', 'Product File')}"
            )
        except Exception as e:
            logger.error(f"Failed to deliver product file {file.get('file_id')} to {user_id}: {e}")
            await client.send_message(user_id, f"❌ Failed to deliver: {file.get('file_name', 'Product File')}")


@app.on_callback_query(filters.regex(r"^buy_prod_(.+)"))
async def buy_product_callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    prod_id = callback_query.matches[0].group(1)

    try:
        product = await database.get_product_by_id(ObjectId(prod_id))
    except Exception:
        product = None

    if not product:
        await callback_query.answer("❌ Product not found.", show_alert=True)
        return

    # Issue 7: Prevent duplicate purchases
    from database.mongo import purchases_col
    if await database.verify_purchase(user_id, product["_id"]):
        await callback_query.answer("⚠️ You already purchased this product! Delivering files...", show_alert=True)
        purchase = await purchases_col.find_one({"user_id": user_id, "product_id": product["_id"], "status": "completed"})
        await deliver_product_files(client, user_id, purchase, product)
        return

    text = (
        f"🛒 **Checkout Product**\n\n"
        f"📦 **Name:** {escape_markdown(product['name'])}\n"
        f"📝 **Description:** {escape_markdown(product.get('description', ''))}\n\n"
        f"💵 **Stars Price:** {product['price']} ⭐️\n"
        f"💰 **UPI Price:** ₹{product.get('price_upi', 0.0)} INR\n\n"
        f"Choose your payment method below:"
    )

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⭐️ Telegram Stars", callback_data=f"pay_stars_prod_{prod_id}"),
            InlineKeyboardButton("📲 UPI Transfer", callback_data=f"pay_upi_prod_{prod_id}"),
        ],
        [InlineKeyboardButton("🔙 Back to Catalog", callback_data="store_back")]
    ])
    await callback_query.message.edit_text(text, reply_markup=buttons)


@app.on_callback_query(filters.regex(r"^pay_stars_prod_(.+)"))
async def pay_stars_product_callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    prod_id = callback_query.matches[0].group(1)

    try:
        product = await database.get_product_by_id(ObjectId(prod_id))
    except Exception:
        product = None

    if not product:
        await callback_query.answer("❌ Product not found.", show_alert=True)
        return

    await callback_query.answer()
    try:
        await send_stars_invoice(
            client=client,
            chat_id=user_id,
            title=product["name"],
            description=f"Purchase {product['name']} for {product['price']} Telegram Stars.",
            payload=f"prod_buy_{prod_id}",
            amount=int(product["price"]),
        )
    except Exception as e:
        logger.error(f"Failed to send stars invoice for product {prod_id}: {e}")
        await callback_query.message.reply_text("❌ **Failed to generate Stars payment invoice.** Please try again later.")


@app.on_callback_query(filters.regex(r"^pay_upi_prod_(.+)"))
async def pay_upi_product_callback_handler(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    prod_id = callback_query.matches[0].group(1)

    try:
        product = await database.get_product_by_id(ObjectId(prod_id))
    except Exception:
        product = None

    if not product:
        await callback_query.answer("❌ Product not found.", show_alert=True)
        return

    await callback_query.answer()

    amount_inr = product.get("price_upi", 0.0)
    if amount_inr <= 0:
        amount_inr = float(product["price"]) / 2.0  # fallback conversion rate

    # Create pending UPI payment in database
    payment_id = await database.create_upi_payment(
        user_id=user_id,
        plan=f"prod_{prod_id}",
        amount_inr=amount_inr
    )

    text = (
        f"📲 **UPI Payment Checkout**\n\n"
        f"📦 **Product:** {escape_markdown(product['name'])}\n"
        f"💰 **Amount:** ₹{amount_inr} INR\n"
        f"🔑 **UPI ID:** `{config.UPI_ID}`\n\n"
        f"⚠️ **Step 2:** After transferring the amount, take a screenshot of the transaction receipt "
        f"and **send the screenshot (photo) directly to this bot** to complete your order."
    )

    # Set user state to awaiting_upi_screenshot with payment id
    await database.users_col.update_one(
        {"_id": user_id},
        {"$set": {"state": f"awaiting_upi_screenshot_{payment_id}"}}
    )

    if config.UPI_QR_IMAGE:
        await client.send_photo(chat_id=user_id, photo=config.UPI_QR_IMAGE, caption=text)
    else:
        await client.send_message(chat_id=user_id, text=text)
