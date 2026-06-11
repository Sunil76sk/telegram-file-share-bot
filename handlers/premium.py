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
