from __future__ import annotations

import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from bot import app
import database

logger = logging.getLogger(__name__)


@app.on_message(filters.command(["referral", "share"]) & filters.private)
async def referral_command_handler(client: Client, message: Message):
    """Display user's referral details, leaderboard, and reward redemptions."""
    user_id = message.from_user.id
    if await database.is_banned(user_id):
        return

    bot_me = client.me or await client.get_me()
    ref_link = f"https://t.me/{bot_me.username}?start=ref_{user_id}"

    points = await database.get_user_points(user_id)
    referrals = await database.get_user_referrals(user_id)
    ref_count = len(referrals)

    text = (
        "👥 **Referral Program & Rewards**\n\n"
        "Invite your friends to use this bot and earn points to unlock Premium features for free!\n\n"
        f"🔗 **Your Referral Link:**\n`{ref_link}`\n\n"
        f"👥 **Total Referrals:** `{ref_count}`\n"
        f"💰 **Your Points:** `{points}` points\n\n"
        "🎁 **Redeem Rewards:**\n"
        "• 5 Points = 3 Days Premium\n"
        "• 10 Points = 7 Days Premium\n"
        "• 30 Points = 30 Days Premium\n\n"
    )

    try:
        leaderboard = await database.get_referral_leaderboard(5)
        if leaderboard:
            text += "🏆 **Top Referrers:**\n"
            for index, entry in enumerate(leaderboard, start=1):
                text += f"{index}. {entry['name']} — `{entry['count']}` invites\n"
            text += "\n"
    except Exception as e:
        logger.error(f"Error loading leaderboard: {e}")

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎁 Redeem 3 Days Premium (5 pts)", callback_data="redeem_prem_3d")
            ],
            [
                InlineKeyboardButton("🎁 Redeem 7 Days Premium (10 pts)", callback_data="redeem_prem_7d")
            ],
            [
                InlineKeyboardButton("🎁 Redeem 30 Days Premium (30 pts)", callback_data="redeem_prem_30d")
            ],
            [
                InlineKeyboardButton("📢 Share Referral Link", url=f"https://t.me/share/url?url={ref_link}&text=Hey!%20Check%20out%20this%20Telegram%20File%20Share%20Bot!")
            ]
        ]
    )

    await message.reply_text(text, reply_markup=buttons)


@app.on_callback_query(filters.regex(r"^redeem_prem_(3d|7d|30d)$"))
async def redeem_premium_callback(client: Client, callback_query: CallbackQuery):
    """Handle callback to exchange referral points for Premium days."""
    user_id = callback_query.from_user.id
    if await database.is_banned(user_id):
        await callback_query.answer("⛔️ You are banned.", show_alert=True)
        return

    option = callback_query.matches[0].group(1)
    points_cost = 0
    days = 0

    if option == "3d":
        points_cost = 5
        days = 3
    elif option == "7d":
        points_cost = 10
        days = 7
    elif option == "30d":
        points_cost = 30
        days = 30

    current_points = await database.get_user_points(user_id)
    if current_points < points_cost:
        await callback_query.answer(
            f"❌ Insufficient points! You need {points_cost} points (You have {current_points}).",
            show_alert=True
        )
        return

    # Deduct points and award Premium duration
    await database.add_user_points(user_id, -points_cost)
    await database.set_user_premium(user_id, days)

    new_points = current_points - points_cost
    expiry_str = await database.get_premium_expiry_str(user_id)

    await callback_query.answer("🎉 Reward redeemed successfully!", show_alert=True)
    await callback_query.message.edit_text(
        f"🎉 **Reward Redeemed Successfully!** 🎉\n\n"
        f"You have redeemed **{days} Days Premium** for **{points_cost} Points**.\n"
        f"Remaining Points: `{new_points}`\n"
        f"Premium Status: **{expiry_str}**\n\n"
        f"Thank you for sharing the bot with your friends!"
    )
