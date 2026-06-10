from __future__ import annotations

import logging
import datetime
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
from utils.helpers import send_stars_invoice
from utils.delivery import deliver_files

logger = logging.getLogger(__name__)


def get_stars_plan_price(tier: str, duration: str) -> int:
    """Get the Stars price for a subscription plan."""
    if tier == "gold":
        if duration == "weekly":
            return config.PREMIUM_GOLD_WEEKLY
        elif duration == "monthly":
            return config.PREMIUM_GOLD_MONTHLY
        elif duration == "lifetime":
            return config.PREMIUM_GOLD_LIFETIME
    else:  # silver
        if duration == "weekly":
            return config.PREMIUM_SILVER_WEEKLY
        elif duration == "monthly":
            return config.PREMIUM_SILVER_MONTHLY
    return 0


def get_upi_plan_price(tier: str, duration: str) -> float:
    """Get the UPI (INR) price for a subscription plan."""
    if tier == "gold":
        if duration == "weekly":
            return config.UPI_PRICE_WEEKLY
        elif duration == "monthly":
            return config.UPI_PRICE_MONTHLY
        elif duration == "lifetime":
            return config.UPI_PRICE_LIFETIME
    else:  # silver
        if duration == "weekly":
            return round(config.UPI_PRICE_WEEKLY * 0.6)
        elif duration == "monthly":
            return round(config.UPI_PRICE_MONTHLY * 0.66)
    return 0.0


# ─── PREMIUM MENU ──────────────────────────────────────────────────


@app.on_message(filters.command(["premium", "subscribe"]) & filters.private)
async def premium_command_handler(client: Client, message: Message):
    """Display Premium features and tier options."""
    user_id = message.from_user.id
    if await database.is_banned(user_id):
        return

    expiry_str = await database.get_premium_expiry_str(user_id)
    await database.get_user_premium_tier(user_id)

    benefits = (
        "🌟 **Premium Membership Perks:**\n\n"
        "🥈 **Silver Tier Perks:**\n"
        "• ⚡️ **Zero Waiting Timers:** Instant file delivery.\n"
        "• 🚫 **Ad/Shortener Bypass:** Skip shorteners and ads.\n"
        "• 📦 **Silver Link Access:** Access premium files up to Silver tier.\n\n"
        "👑 **Gold Tier Perks:**\n"
        "• 🌟 **All Silver Perks** included.\n"
        "• 💎 **Gold Link Access:** Unlock premium files up to Gold tier.\n"
        "• 🚀 **Priority Speed:** Highest priority delivery queue.\n\n"
        f"Current Status: **{expiry_str}**\n\n"
        "Select a premium tier below to see plans and pricing:"
    )

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🥈 View Silver Plans", callback_data="premium_tier_silver"
                ),
                InlineKeyboardButton(
                    "👑 View Gold Plans", callback_data="premium_tier_gold"
                ),
            ],
            [
                InlineKeyboardButton(
                    "🛍 Browse Content Store", callback_data="store_categories"
                ),
            ],
        ]
    )

    await message.reply_text(benefits, reply_markup=buttons)


@app.on_callback_query(filters.regex(r"^premium_tier_(silver|gold)$"))
async def premium_tier_callback(client: Client, callback_query: CallbackQuery):
    """Display sub-plans for the selected tier."""
    user_id = callback_query.from_user.id
    if await database.is_banned(user_id):
        await callback_query.answer("⛔️ You are banned.", show_alert=True)
        return

    tier = callback_query.matches[0].group(1)
    tier_title = "🥈 Silver Tier" if tier == "silver" else "👑 Gold Tier"

    msg = f"{tier_title} Subscriptions:\n\n" "Choose a plan duration below to continue:"

    keyboard = []
    if tier == "silver":
        w_stars = get_stars_plan_price("silver", "weekly")
        w_upi = get_upi_plan_price("silver", "weekly")
        m_stars = get_stars_plan_price("silver", "monthly")
        m_upi = get_upi_plan_price("silver", "monthly")
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"🎫 Weekly - {w_stars} ⭐️ / ₹{w_upi}",
                    callback_data="premium_plan_silver_weekly",
                )
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"📅 Monthly - {m_stars} ⭐️ / ₹{m_upi}",
                    callback_data="premium_plan_silver_monthly",
                )
            ]
        )
    else:  # gold
        w_stars = get_stars_plan_price("gold", "weekly")
        w_upi = get_upi_plan_price("gold", "weekly")
        m_stars = get_stars_plan_price("gold", "monthly")
        m_upi = get_upi_plan_price("gold", "monthly")
        l_stars = get_stars_plan_price("gold", "lifetime")
        l_upi = get_upi_plan_price("gold", "lifetime")
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"🎫 Weekly - {w_stars} ⭐️ / ₹{w_upi}",
                    callback_data="premium_plan_gold_weekly",
                )
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"📅 Monthly - {m_stars} ⭐️ / ₹{m_upi}",
                    callback_data="premium_plan_gold_monthly",
                )
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"👑 Lifetime - {l_stars} ⭐️ / ₹{l_upi}",
                    callback_data="premium_plan_gold_lifetime",
                )
            ]
        )

    keyboard.append(
        [InlineKeyboardButton("🔙 Back to Tiers", callback_data="premium_menu_home")]
    )

    await callback_query.answer()
    await callback_query.message.edit_text(
        msg, reply_markup=InlineKeyboardMarkup(keyboard)
    )


@app.on_callback_query(
    filters.regex(r"^premium_plan_(silver|gold)_(weekly|monthly|lifetime)$")
)
async def premium_plan_callback(client: Client, callback_query: CallbackQuery):
    """Show payment method options (Stars vs UPI) for the selected plan."""
    user_id = callback_query.from_user.id
    if await database.is_banned(user_id):
        await callback_query.answer("⛔️ You are banned.", show_alert=True)
        return

    match = callback_query.matches[0]
    tier = match.group(1)
    duration = match.group(2)

    stars_price = get_stars_plan_price(tier, duration)
    upi_price = get_upi_plan_price(tier, duration)

    msg = (
        f"💳 **Subscription checkout:**\n\n"
        f"**Tier:** {tier.capitalize()}\n"
        f"**Plan:** {duration.capitalize()}\n\n"
        f"• **Telegram Stars:** {stars_price} ⭐️ (Instant Activation)\n"
        f"• **UPI Transfer:** ₹{upi_price} (Manual Verification)\n\n"
        "Select your preferred payment method:"
    )

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"⭐️ Pay {stars_price} Stars",
                    callback_data=f"premium_pay_{tier}_{duration}_stars",
                ),
                InlineKeyboardButton(
                    f"💸 Pay ₹{upi_price} via UPI",
                    callback_data=f"premium_pay_{tier}_{duration}_upi",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔙 Back to Plans", callback_data=f"premium_tier_{tier}"
                ),
            ],
        ]
    )

    await callback_query.answer()
    await callback_query.message.edit_text(msg, reply_markup=buttons)


@app.on_callback_query(
    filters.regex(r"^premium_pay_(silver|gold)_(weekly|monthly|lifetime)_(stars|upi)$")
)
async def premium_pay_callback(client: Client, callback_query: CallbackQuery):
    """Handle chosen payment method for subscriptions."""
    user_id = callback_query.from_user.id
    if await database.is_banned(user_id):
        await callback_query.answer("⛔️ You are banned.", show_alert=True)
        return

    match = callback_query.matches[0]
    tier = match.group(1)
    duration = match.group(2)
    method = match.group(3)

    await callback_query.answer()

    if method == "stars":
        title = f"{tier.capitalize()} {duration.capitalize()} Premium"
        desc = f"Access to {tier.capitalize()} tier features for {duration} duration."
        if duration == "lifetime":
            desc = f"Permanent access to {tier.capitalize()} tier features."

        stars_price = get_stars_plan_price(tier, duration)
        payload = f"premium_{tier}_{duration}"

        try:
            await callback_query.message.delete()
            await send_stars_invoice(
                client=client,
                chat_id=user_id,
                title=title,
                description=desc,
                payload=payload,
                amount=stars_price,
            )
        except Exception as e:
            logger.error(f"Failed to send stars invoice to {user_id}: {e}")
            await client.send_message(
                chat_id=user_id,
                text="❌ **Failed to generate invoice.** Please try again or contact support.",
            )

    elif method == "upi":
        upi_price = get_upi_plan_price(tier, duration)
        plan_name = f"{tier}_{duration}"

        # Check for existing pending UPI payment
        existing = await database.get_pending_upi(user_id)
        if existing:
            await callback_query.message.edit_text(
                "⚠️ **You already have a pending UPI request!**\n\n"
                "Please complete the previous request or wait for an admin to process it.\n"
                "If you need to submit a new screenshot, just send it now."
            )
            return

        # Create pending UPI record
        await database.create_upi_payment(user_id, plan_name, upi_price)

        upi_instructions = (
            "💸 **UPI Payment Details:**\n\n"
            f"Please send **₹{upi_price}** to the UPI ID below:\n"
            f"`{config.UPI_ID}`\n\n"
            "⚠️ **Step 2:** After transferring the amount, take a screenshot of the transaction receipt "
            "and **send the screenshot (photo) directly to this bot**.\n\n"
            "Once received, our admins will verify the payment and activate your premium status."
        )

        # Send UPI instructions. If QR image is configured, send photo.
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


@app.on_callback_query(filters.regex(r"^premium_menu_home$"))
async def premium_menu_home_callback(client: Client, callback_query: CallbackQuery):
    """Return to premium tier overview menu."""
    user_id = callback_query.from_user.id
    expiry_str = await database.get_premium_expiry_str(user_id)

    benefits = (
        "🌟 **Premium Membership Perks:**\n\n"
        "🥈 **Silver Tier Perks:**\n"
        "• ⚡️ **Zero Waiting Timers:** Instant file delivery.\n"
        "• 🚫 **Ad/Shortener Bypass:** Skip shorteners and ads.\n"
        "• 📦 **Silver Link Access:** Access premium files up to Silver tier.\n\n"
        "👑 **Gold Tier Perks:**\n"
        "• 🌟 **All Silver Perks** included.\n"
        "• 💎 **Gold Link Access:** Unlock premium files up to Gold tier.\n"
        "• 🚀 **Priority Speed:** Highest priority delivery queue.\n\n"
        f"Current Status: **{expiry_str}**\n\n"
        "Select a premium tier below to see plans and pricing:"
    )

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🥈 View Silver Plans", callback_data="premium_tier_silver"
                ),
                InlineKeyboardButton(
                    "👑 View Gold Plans", callback_data="premium_tier_gold"
                ),
            ],
            [
                InlineKeyboardButton(
                    "🛍 Browse Content Store", callback_data="store_categories"
                ),
            ],
        ]
    )

    await callback_query.answer()
    await callback_query.message.edit_text(benefits, reply_markup=buttons)


# ─── STORE / CATALOG BROWSER ────────────────────────────────────────


@app.on_message(filters.command(["store", "shop"]) & filters.private)
async def store_command_handler(client: Client, message: Message):
    """Enter the Premium Catalog store."""
    user_id = message.from_user.id
    if await database.is_banned(user_id):
        return

    msg = (
        "🛍 **Welcome to the Premium Content Store!**\n\n"
        "Browse our collection of curated premium assets. Select a category below to get started:"
    )

    buttons = []
    for cat_key, cat_name in config.PREMIUM_CATEGORIES.items():
        buttons.append(
            [InlineKeyboardButton(cat_name, callback_data=f"store_cat_{cat_key}")]
        )

    buttons.append(
        [InlineKeyboardButton("🔙 Premium Menu", callback_data="premium_menu_home")]
    )

    await message.reply_text(msg, reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^store_categories$"))
async def store_categories_callback(client: Client, callback_query: CallbackQuery):
    """Enter store categories from callback query."""
    user_id = callback_query.from_user.id
    if await database.is_banned(user_id):
        await callback_query.answer("⛔️ You are banned.", show_alert=True)
        return

    msg = "🛍 **Premium Content Store:**\n\n" "Select a category below to browse items:"

    buttons = []
    for cat_key, cat_name in config.PREMIUM_CATEGORIES.items():
        buttons.append(
            [InlineKeyboardButton(cat_name, callback_data=f"store_cat_{cat_key}")]
        )

    buttons.append(
        [InlineKeyboardButton("🔙 Premium Menu", callback_data="premium_menu_home")]
    )

    await callback_query.answer()
    await callback_query.message.edit_text(
        msg, reply_markup=InlineKeyboardMarkup(buttons)
    )


@app.on_callback_query(filters.regex(r"^store_cat_([a-zA-Z0-9_]+)$"))
async def store_category_callback(client: Client, callback_query: CallbackQuery):
    """Display active catalog items under a specific category."""
    user_id = callback_query.from_user.id
    if await database.is_banned(user_id):
        await callback_query.answer("⛔️ You are banned.", show_alert=True)
        return

    category = callback_query.matches[0].group(1)
    category_name = config.PREMIUM_CATEGORIES.get(
        category, category.replace("_", " ").title()
    )

    items = await database.get_catalog_by_category(category, active_only=True)

    if not items:
        await callback_query.answer(
            f"No items available in {category_name} right now.", show_alert=True
        )
        return

    msg = f"📂 **Category: {category_name}**\n\nSelect an item to view details:"
    keyboard = []
    for item in items:
        price_label = f"({item['price_stars']} ⭐️ / ₹{item['price_upi']})"
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"📄 {item['title']} {price_label}",
                    callback_data=f"store_item_{item['_id']}",
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                "🔙 Back to Categories", callback_data="store_categories"
            )
        ]
    )

    await callback_query.answer()
    await callback_query.message.edit_text(
        msg, reply_markup=InlineKeyboardMarkup(keyboard)
    )


@app.on_callback_query(filters.regex(r"^store_item_([a-fA-F0-9]{24})$"))
async def store_item_callback(client: Client, callback_query: CallbackQuery):
    """View details of a specific catalog item."""
    user_id = callback_query.from_user.id
    if await database.is_banned(user_id):
        await callback_query.answer("⛔️ You are banned.", show_alert=True)
        return

    item_id = callback_query.matches[0].group(1)
    item = await database.get_catalog_item(item_id)

    if not item:
        await callback_query.answer("❌ Item not found.", show_alert=True)
        return

    # Check if user already unlocked/owns this item, or has active premium tier to access it
    unlocked = await database.has_user_unlocked_link(user_id, item["token"])

    user_tier = await database.get_user_premium_tier(user_id)
    tier_unlocked = False

    if item["tier_required"]:
        # If item requires gold, user must have gold. If silver, silver/gold.
        if item["tier_required"] == "gold":
            tier_unlocked = user_tier == "gold"
        elif item["tier_required"] == "silver":
            tier_unlocked = user_tier in ["silver", "gold"]
    else:
        # No tier required specifically, but is it a general premium catalog item?
        # Standard rules apply: if user has ANY premium tier, they can access it.
        tier_unlocked = user_tier is not None

    msg = (
        f"📄 **{item['title']}**\n\n"
        f"📝 **Description:**\n{item['description']}\n\n"
        f"🏷 **Required Premium Tier:** {item['tier_required'].capitalize() if item['tier_required'] else 'Any Premium'}\n"
    )

    buttons = []

    if unlocked or tier_unlocked:
        msg += "\n✅ **You have access to this content!**"
        buttons.append(
            [
                InlineKeyboardButton(
                    "📥 Get Content / Deliver Files",
                    callback_data=f"store_deliver_{item_id}",
                )
            ]
        )
    else:
        msg += (
            f"\n💰 **Price:** {item['price_stars']} Stars / ₹{item['price_upi']} INR\n\n"
            "Choose a payment option below to unlock this item:"
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    f"⭐️ Buy ({item['price_stars']} Stars)",
                    callback_data=f"store_buy_{item_id}_stars",
                ),
                InlineKeyboardButton(
                    f"💸 Buy (₹{item['price_upi']} UPI)",
                    callback_data=f"store_buy_{item_id}_upi",
                ),
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                "🔙 Back to Category", callback_data=f"store_cat_{item['category']}"
            )
        ]
    )

    await callback_query.answer()
    await callback_query.message.edit_text(
        msg, reply_markup=InlineKeyboardMarkup(buttons)
    )


@app.on_callback_query(filters.regex(r"^store_deliver_([a-fA-F0-9]{24})$"))
async def store_deliver_callback(client: Client, callback_query: CallbackQuery):
    """Deliver files associated with catalog item."""
    user_id = callback_query.from_user.id
    if await database.is_banned(user_id):
        await callback_query.answer("⛔️ You are banned.", show_alert=True)
        return

    item_id = callback_query.matches[0].group(1)
    item = await database.get_catalog_item(item_id)

    if not item:
        await callback_query.answer("❌ Item not found.", show_alert=True)
        return

    # Double check permission
    unlocked = await database.has_user_unlocked_link(user_id, item["token"])
    user_tier = await database.get_user_premium_tier(user_id)
    tier_unlocked = False
    if item["tier_required"]:
        if item["tier_required"] == "gold":
            tier_unlocked = user_tier == "gold"
        elif item["tier_required"] == "silver":
            tier_unlocked = user_tier in ["silver", "gold"]
    else:
        tier_unlocked = user_tier is not None

    if not (unlocked or tier_unlocked):
        await callback_query.answer(
            "⛔️ Access denied. Please purchase this item.", show_alert=True
        )
        return

    file_doc = await database.get_file_link(item["token"])
    if not file_doc:
        await callback_query.answer(
            "❌ The files for this item are no longer available in the bot.",
            show_alert=True,
        )
        return

    await callback_query.answer("⚡️ Delivering files now...")
    await callback_query.message.delete()

    # Log access view
    await database.log_access(
        user_id, item["token"], action="view", method="catalog", catalog_item_id=item_id
    )

    await deliver_files(client, user_id, file_doc, bypass_monetization=True)


@app.on_callback_query(filters.regex(r"^store_buy_([a-fA-F0-9]{24})_(stars|upi)$"))
async def store_buy_callback(client: Client, callback_query: CallbackQuery):
    """Process individual item purchase."""
    user_id = callback_query.from_user.id
    if await database.is_banned(user_id):
        await callback_query.answer("⛔️ You are banned.", show_alert=True)
        return

    item_id = callback_query.matches[0].group(1)
    method = callback_query.matches[0].group(2)

    item = await database.get_catalog_item(item_id)
    if not item:
        await callback_query.answer("❌ Item not found.", show_alert=True)
        return

    await callback_query.answer()

    if method == "stars":
        title = item["title"]
        # Limit title to 32 chars for Telegram Stars invoice rules
        if len(title) > 30:
            title = title[:27] + "..."
        desc = f"Unlock premium catalog item: {item['title']}"
        if len(desc) > 250:
            desc = desc[:247] + "..."

        payload = f"catalog_{item_id}"

        try:
            await callback_query.message.delete()
            await send_stars_invoice(
                client=client,
                chat_id=user_id,
                title=title,
                description=desc,
                payload=payload,
                amount=item["price_stars"],
            )
        except Exception as e:
            logger.error(f"Failed to send stars invoice for catalog item: {e}")
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

        plan_name = f"item_{item_id}"
        await database.create_upi_payment(user_id, plan_name, item["price_upi"])

        upi_instructions = (
            "💸 **UPI Payment Details:**\n\n"
            f"Please send **₹{item['price_upi']}** to the UPI ID below to unlock **{item['title']}**:\n"
            f"`{config.UPI_ID}`\n\n"
            "⚠️ **Step 2:** After transferring the amount, take a screenshot of the transaction receipt "
            "and **send the screenshot (photo) directly to this bot**.\n\n"
            "Once received, our admins will verify the payment and unlock the content."
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


# ─── UPI SCREENSHOT HANDLER ─────────────────────────────────────────


@app.on_message(filters.photo & filters.private, group=2)
async def upi_screenshot_handler(client: Client, message: Message):
    """Receive and forward UPI transaction screenshots to administrators."""
    user_id = message.from_user.id
    if await database.is_banned(user_id):
        return

    # Check if there is an active pending UPI payment without a screenshot
    pending = await database.get_pending_upi(user_id)
    if not pending or pending.get("screenshot_msg_id") is not None:
        # Fall through to default photo handler if not pending or screenshot already sent
        return

    payment_id = str(pending["_id"])

    # Save the message ID of the screenshot
    await database.set_upi_screenshot(payment_id, message.id)

    # Let the user know we received it
    await message.reply_text(
        "✅ **Payment screenshot received!**\n\n"
        "Our team is verifying the payment details. We will notify you once your premium access is activated "
        "or your purchased content is unlocked."
    )

    # Prepare notification for admins
    plan_desc = pending["plan"]
    if plan_desc.startswith("item_"):
        item_id = plan_desc.split("_")[1]
        item = await database.get_catalog_item(item_id)
        plan_desc = f"Store Item: {item['title']}" if item else f"Item ID {item_id}"
    elif plan_desc.startswith("prod_"):
        from bson import ObjectId

        product_id = plan_desc.split("_")[1]
        product = await database.get_product_by_id(ObjectId(product_id))
        plan_desc = (
            f"Marketplace Product: {product['name']}"
            if product
            else f"Product ID {product_id}"
        )
    else:
        plan_desc = f"Subscription: {plan_desc.replace('_', ' ').title()}"

    admin_msg = (
        "🔔 **New UPI Payment Submission:**\n\n"
        f"👤 **User:** {message.from_user.mention} (`{user_id}`)\n"
        f"📦 **Plan/Item:** `{plan_desc}`\n"
        f"💰 **Amount:** ₹{pending['amount_inr']}\n"
        f"🕒 **Submitted:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "Please review the attached screenshot and select an action:"
    )

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Approve ✅", callback_data=f"admin_upi_approve_{payment_id}"
                ),
                InlineKeyboardButton(
                    "Reject ❌", callback_data=f"admin_upi_reject_{payment_id}"
                ),
            ]
        ]
    )

    # Broadcast to all configure admins
    admin_notified = False
    for admin_id in config.ADMIN_IDS:
        try:
            await message.copy(
                chat_id=admin_id, caption=admin_msg, reply_markup=buttons
            )
            admin_notified = True
        except Exception as e:
            logger.error(f"Failed to forward UPI screenshot to admin {admin_id}: {e}")

    if not admin_notified:
        logger.error(
            "No admins could be notified of the pending UPI screenshot submission."
        )


# ─── ADMIN APPROVAL / REJECTION ACTIONS ──────────────────────────────


@app.on_callback_query(filters.regex(r"^admin_upi_(approve|reject)_([a-fA-F0-9]{24})$"))
async def admin_upi_action_callback(client: Client, callback_query: CallbackQuery):
    """Handle admin actions for pending UPI payment screenshots."""
    admin_id = callback_query.from_user.id

    # Check admin privileges
    if not await database.is_admin(admin_id):
        await callback_query.answer("⛔️ Access denied. Admin only.", show_alert=True)
        return

    action = callback_query.matches[0].group(1)
    payment_id = callback_query.matches[0].group(2)

    payment = await database.get_upi_payment(payment_id)
    if not payment:
        await callback_query.answer("❌ Payment record not found.", show_alert=True)
        return

    if payment.get("status") != "pending":
        await callback_query.answer(
            f"⚠️ This payment has already been processed as {payment['status'].upper()}.",
            show_alert=True,
        )
        return

    target_user_id = payment["user_id"]
    plan = payment["plan"]

    if action == "approve":
        success = await database.approve_upi(payment_id, admin_id)
        if not success:
            await callback_query.answer("❌ Database update failed.", show_alert=True)
            return

        # Handle activation
        if plan.startswith("saas_"):
            saas_plan_id = plan.replace("saas_", "", 1)
            sub = await database.create_subscription(
                user_id=target_user_id,
                plan_id=saas_plan_id,
                payment_method="upi",
                payment_ref=str(payment_id),
                months=1,
            )
            if sub:
                await database.log_access(
                    target_user_id,
                    token="",
                    action="saas_subscription_activate",
                    method="upi",
                    amount=payment["amount_inr"],
                    extra=plan,
                )
                try:
                    await client.send_message(
                        chat_id=target_user_id,
                        text=(
                            f"🚀 **SaaS Plan Activated!** 🚀\n\n"
                            f"Your **{database.PLAN_DEFINITIONS[saas_plan_id]['name']}** plan is now active.\n"
                            f"Payment of **₹{payment['amount_inr']}** verified.\n\n"
                            f"Use `/saas` to manage your bots and subscription."
                        ),
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to notify user {target_user_id} of SaaS approval: {e}"
                    )
        elif plan.startswith("item_"):
            # Individual Item Purchase
            item_id = plan.split("_")[1]
            item = await database.get_catalog_item(item_id)
            if item:
                token = item["token"]
                await database.unlock_link_for_user(target_user_id, token)
                await database.increment_catalog_purchases(item_id, 0)
                await database.log_access(
                    target_user_id,
                    token,
                    action="purchase",
                    method="upi",
                    catalog_item_id=item_id,
                    amount=payment["amount_inr"],
                )

                try:
                    await client.send_message(
                        chat_id=target_user_id,
                        text=(
                            f"🔓 **UPI Purchase Approved!**\n\n"
                            f"Your payment of **₹{payment['amount_inr']}** for **{item['title']}** has been verified and approved.\n"
                            "We are delivering your content now..."
                        ),
                    )
                    file_doc = await database.get_file_link(token)
                    if file_doc:
                        await deliver_files(
                            client, target_user_id, file_doc, bypass_monetization=True
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to notify user {target_user_id} of approved UPI catalog purchase: {e}"
                    )
        elif plan.startswith("prod_"):
            # Individual Product Purchase
            from bson import ObjectId

            product_id = plan.split("_")[1]
            product = await database.get_product_by_id(ObjectId(product_id))
            if product:
                purchase = await database.record_purchase(
                    user_id=target_user_id,
                    product_id=product["_id"],
                    product_token=product["token"],
                    amount_paid=payment["amount_inr"],
                    payment_id=str(payment_id),
                    status="completed",
                    files_delivered=product["files"],
                )
                await database.increment_product_sales(product["_id"])

                try:
                    await client.send_message(
                        chat_id=target_user_id,
                        text=(
                            f"🎉 **UPI Purchase Approved!**\n\n"
                            f"Your payment of **₹{payment['amount_inr']}** for **{product['name']}** has been verified and approved.\n"
                            "We are delivering your product now..."
                        ),
                    )
                    from handlers.marketplace import deliver_product_files

                    await deliver_product_files(
                        client, target_user_id, purchase, product
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to notify user {target_user_id} of approved UPI product purchase: {e}"
                    )
        else:
            # Subscription purchase (format: tier_duration)
            parts = plan.split("_")
            tier = parts[0]
            duration = parts[1]

            days = 0
            if duration == "weekly":
                days = 7
            elif duration == "monthly":
                days = 30
            elif duration == "lifetime":
                days = 0

            await database.set_user_premium(target_user_id, days, tier)
            await database.log_access(
                target_user_id,
                token="",
                action="subscription_activate",
                method="upi",
                amount=payment["amount_inr"],
                extra=plan,
            )

            expiry_str = await database.get_premium_expiry_str(target_user_id)
            try:
                await client.send_message(
                    chat_id=target_user_id,
                    text=(
                        f"🌟 **UPI Premium Activation!** 🌟\n\n"
                        f"Your payment of **₹{payment['amount_inr']}** has been verified.\n"
                        f"Status: **{expiry_str}**\n\n"
                        f"Thank you for your support! You now have full access to your Premium perks."
                    ),
                )
            except Exception as e:
                logger.error(
                    f"Failed to notify user {target_user_id} of approved UPI subscription: {e}"
                )

        await callback_query.answer("Payment Approved successfully!", show_alert=True)
        # Update admin message
        await callback_query.message.edit_reply_markup(reply_markup=None)
        await callback_query.message.reply_text(
            f"✅ **UPI Payment Approved** by {callback_query.from_user.mention} (`{admin_id}`).",
            quote=True,
        )

    elif action == "reject":
        success = await database.reject_upi(payment_id, admin_id)
        if not success:
            await callback_query.answer("❌ Database update failed.", show_alert=True)
            return

        try:
            await client.send_message(
                chat_id=target_user_id,
                text=(
                    f"❌ **UPI Payment Rejected**\n\n"
                    f"Your payment of **₹{payment['amount_inr']}** could not be verified by our team.\n"
                    "If you believe this is an error, please contact support and provide payment proof."
                ),
            )
        except Exception as e:
            logger.error(f"Failed to notify user {target_user_id} of rejected UPI: {e}")

        await callback_query.answer("Payment Rejected successfully.", show_alert=True)
        # Update admin message
        await callback_query.message.edit_reply_markup(reply_markup=None)
        await callback_query.message.reply_text(
            f"❌ **UPI Payment Rejected** by {callback_query.from_user.mention} (`{admin_id}`).",
            quote=True,
        )
