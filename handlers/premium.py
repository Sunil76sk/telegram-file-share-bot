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
        ]
    )

    await callback_query.answer()
    await callback_query.message.edit_text(benefits, reply_markup=buttons)


# ─── UPI ADMIN REVIEW HANDLERS ──────────────────────────────────────


@app.on_callback_query(filters.regex(r"^admin_upi_(approve|reject)_(.+)"))
async def admin_upi_callback_handler(client: Client, callback_query: CallbackQuery):
    admin_id = callback_query.from_user.id
    if not await database.is_admin(admin_id, client):
        await callback_query.answer("⛔️ Access denied.", show_alert=True)
        return

    action = callback_query.matches[0].group(1)
    payment_id = callback_query.matches[0].group(2)

    payment = await database.get_upi_payment(payment_id)
    if not payment:
        await callback_query.answer("❌ Payment record not found.", show_alert=True)
        return

    if payment.get("status") != "pending":
        await callback_query.answer(f"⚠️ Already {payment.get('status')}.", show_alert=True)
        return

    user_id = payment["user_id"]
    plan_name = payment["plan"]
    amount = payment["amount_inr"]

    if action == "approve":
        success = await database.approve_upi(payment_id, admin_id)
        if success:
            if plan_name.startswith("prod_"):
                prod_id = plan_name.split("_")[1]
                from bson import ObjectId
                try:
                    product = await database.get_product_by_id(ObjectId(prod_id))
                except Exception:
                    product = None

                if product:
                    # Issue 7: Prevent duplicate purchases
                    if not await database.verify_purchase(user_id, product["_id"]):
                        await database.record_purchase(
                            user_id=user_id,
                            product_id=product["_id"],
                            product_token=product.get("token", ""),
                            amount_paid=int(amount),
                            payment_id=payment_id,
                            status="completed",
                            files_delivered=product.get("files", [])
                        )
                        await database.increment_product_sales(product["_id"])

                    from handlers.marketplace import deliver_product_files
                    await deliver_product_files(client, user_id, payment, product)
                else:
                    await client.send_message(
                        chat_id=user_id,
                        text="❌ **UPI Payment Approved, but the product could not be found.** Please contact support."
                    )
            else:
                parts = plan_name.split("_")
                tier = parts[0]
                duration = parts[1]
                days = 0
                if duration == "weekly":
                    days = 7
                elif duration == "monthly":
                    days = 30
                elif duration == "lifetime":
                    days = 0

                await database.set_user_premium(user_id, days, tier)
                await database.log_access(
                    user_id,
                    token="",
                    action="subscription_activate",
                    method="upi",
                    amount=amount,
                    extra=plan_name,
                )

                expiry_str = await database.get_premium_expiry_str(user_id)
                try:
                    await client.send_message(
                        chat_id=user_id,
                        text=(
                            f"🌟 **Premium Membership Activated!** 🌟\n\n"
                            f"Your UPI payment of **₹{amount}** for the **{tier.capitalize()} {duration.capitalize()}** plan has been approved.\n"
                            f"Status: **{expiry_str}**\n\n"
                            f"Thank you for your support!"
                        ),
                    )
                except Exception as e:
                    logger.error(f"Failed to notify user {user_id} of UPI approval: {e}")

            await callback_query.answer("✅ UPI Payment Approved!", show_alert=True)
            try:
                await callback_query.message.edit_reply_markup(None)
                await callback_query.message.reply_text(
                    f"✅ **Approved** by {callback_query.from_user.mention}"
                )
            except Exception:
                pass
        else:
            await callback_query.answer("❌ Failed to approve payment.", show_alert=True)

    elif action == "reject":
        success = await database.reject_upi(payment_id, admin_id)
        if success:
            try:
                clean_plan_name = plan_name
                if plan_name.startswith("prod_"):
                    prod_id = plan_name.split("_")[1]
                    from bson import ObjectId
                    try:
                        product = await database.get_product_by_id(ObjectId(prod_id))
                        if product:
                            clean_plan_name = product["name"]
                    except Exception:
                        pass
                else:
                    clean_plan_name = plan_name.replace('_', ' ').title()

                await client.send_message(
                    chat_id=user_id,
                    text=(
                        "❌ **UPI Payment Rejected**\n\n"
                        f"Your UPI payment verification request for **{clean_plan_name}** was rejected.\n"
                        "Please verify your payment screenshot and try again, or contact support."
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to notify user {user_id} of UPI rejection: {e}")

            await callback_query.answer("❌ UPI Payment Rejected!", show_alert=True)
            try:
                await callback_query.message.edit_reply_markup(None)
                await callback_query.message.reply_text(
                    f"❌ **Rejected** by {callback_query.from_user.mention}"
                )
            except Exception:
                pass
        else:
            await callback_query.answer("❌ Failed to reject payment.", show_alert=True)


@app.on_message(filters.command(["upi_pending", "pending_upi"]) & filters.private)
async def upi_pending_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    if not await database.is_admin(user_id, client):
        return

    pending_list = await database.get_all_pending_upi()
    if not pending_list:
        await message.reply_text("✅ **No pending UPI payments to verify.**")
        return

    await message.reply_text(f"⏳ **Found {len(pending_list)} pending UPI payment verification requests:**")

    for payment in pending_list:
        pay_id = str(payment["_id"])
        user_info = f"User ID: `{payment['user_id']}`"
        plan_name = payment["plan"]
        if plan_name.startswith("prod_"):
            prod_id = plan_name.split("_")[1]
            try:
                from bson import ObjectId
                product = await database.get_product_by_id(ObjectId(prod_id))
                plan_desc = f"Product: `{product['name']}`" if product else f"Product ID: `{prod_id}`"
            except Exception:
                plan_desc = f"Product ID: `{prod_id}`"
        else:
            plan_desc = f"Plan: `{plan_name.replace('_', ' ').title()}`"

        amount_desc = f"Amount: `₹{payment['amount_inr']}`"
        created_str = payment["created_at"].strftime("%Y-%m-%d %H:%M:%S UTC")
        
        caption = (
            f"🔔 **Pending UPI Payment Request**\n\n"
            f"👤 **User:** {user_info}\n"
            f"📦 **Plan:** {plan_desc}\n"
            f"💰 **Amount:** {amount_desc}\n"
            f"🕒 **Submitted:** {created_str}\n"
        )
        
        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Approve ✅", callback_data=f"admin_upi_approve_{pay_id}"),
                    InlineKeyboardButton("Reject ❌", callback_data=f"admin_upi_reject_{pay_id}"),
                ]
            ]
        )
        
        msg_id = payment.get("screenshot_msg_id")
        if msg_id:
            try:
                await client.copy_message(
                    chat_id=user_id,
                    from_chat_id=payment["user_id"],
                    message_id=msg_id,
                    caption=caption,
                    reply_markup=buttons,
                )
                continue
            except Exception as e:
                logger.error(f"Failed to copy screenshot for pending payment {pay_id}: {e}")
                
        await message.reply_text(caption, reply_markup=buttons)

