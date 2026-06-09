from __future__ import annotations

import datetime
import logging
import re
import urllib.request
import json
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from bot import app
import database
import config
from utils.saas import saas_runner

logger = logging.getLogger(__name__)

TOKEN_PATTERN = re.compile(r"^\d+:[a-zA-Z0-9_-]{35}$")

PLAN_ICONS = {"starter": "🌱", "pro": "⭐️", "agency": "🚀"}
PLAN_LABELS = {"starter": "Starter", "pro": "Pro", "agency": "Agency"}


async def validate_bot_token(token: str) -> str | None:
    if not TOKEN_PATTERN.match(token):
        return None
    url = f"https://api.telegram.org/bot{token}/getMe"

    def _call():
        with urllib.request.urlopen(url, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    try:
        data = await asyncio.to_thread(_call)
        if data.get("ok"):
            return data["result"]["username"]
    except Exception as e:
        logger.error(f"Error validating token: {e}")
    return None


async def get_user_sub_summary(user_id: int) -> tuple[str, str, int, int, int]:
    plan_id = await database.get_user_plan(user_id)
    sub = await database.get_subscription_by_user(user_id)
    my_bots = await database.get_sub_bots_by_owner(user_id)
    bot_count = len(my_bots)
    max_bots = database.get_plan_max_bots(plan_id)
    price = database.PLAN_DEFINITIONS[plan_id]["price_inr"]
    return plan_id, sub, bot_count, max_bots, price


async def get_saas_dashboard_markup(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    plan_id, sub, bot_count, max_bots, price = await get_user_sub_summary(user_id)
    icon = PLAN_ICONS.get(plan_id, "🌱")
    plan_name = PLAN_LABELS.get(plan_id, "Starter")
    features = database.get_plan_features(plan_id)

    is_free_plan = plan_id == "starter" and not sub
    expires_str = ""
    if sub and sub.get("expires_at"):
        expires_str = f" — expires {sub['expires_at'].strftime('%d %b %Y')}"

    text = (
        f"🤖 **SaaS Bot Platform**\n\n"
        f"**Your Plan:** {icon} {plan_name}  |  ₹{price}/mo{expires_str}\n"
        f"**Bot Usage:** `{bot_count}/{max_bots}` bots\n\n"
    )

    if features:
        feature_lines = []
        feature_map = {
            "file_sharing": "📁 Basic File Sharing",
            "analytics": "📊 Analytics",
            "force_join": "🔗 Force Join",
            "premium_links": "⭐️ Premium Links",
            "branding": "🎨 Branding",
            "shortener_integration": "🔗 Shortener Integration",
            "multi_bot": "🤖 Multi-bot Management",
            "white_label": "🏷 White Label",
            "advanced_analytics": "📈 Advanced Analytics",
            "priority_support": "🆘 Priority Support",
        }
        for key, label in feature_map.items():
            enabled = features.get(key, False)
            if enabled:
                feature_lines.append(f"  ✅ {label}")
        if feature_lines:
            text += "**Features Included:**\n" + "\n".join(feature_lines) + "\n\n"

    if plan_id != "agency" or is_free_plan:
        upgrade_to = "agency" if plan_id == "pro" else "pro"
        up_name = PLAN_LABELS.get(upgrade_to, upgrade_to).capitalize()
        text += f"💡 *Want more? Upgrade to {icon} **{up_name}** for more bots and features.*\n\n"

    my_bots = await database.get_sub_bots_by_owner(user_id)
    buttons = []

    if my_bots:
        text += "📋 **Your Registered Bots:**\n"
        for index, bot_doc in enumerate(my_bots, start=1):
            username = bot_doc["username"]
            is_active = bot_doc["is_active"]
            status_emoji = "🟢 Running" if is_active else "🔴 Stopped"
            text += f"{index}. @{username} — {status_emoji}\n"
            if is_active:
                action_btn = InlineKeyboardButton("🛑 Stop", callback_data=f"saas_stop_{username}")
            else:
                action_btn = InlineKeyboardButton("▶️ Start", callback_data=f"saas_start_{username}")
            del_btn = InlineKeyboardButton("🗑 Delete", callback_data=f"saas_delete_{username}")
            buttons.append([InlineKeyboardButton(f"@{username}", url=f"https://t.me/{username}"), action_btn, del_btn])

    # Plan and subscription buttons
    plan_buttons = []
    if plan_id != "agency":
        plan_buttons.append(InlineKeyboardButton(f"⬆️ Upgrade Plan", callback_data="saas_plans"))
    if plan_id != "starter" or sub:
        plan_buttons.append(InlineKeyboardButton("📄 Manage Subscription", callback_data="saas_subscription"))
    if plan_buttons:
        buttons.append(plan_buttons)

    can_add = bot_count < max_bots
    if can_add:
        buttons.append([InlineKeyboardButton("➕ Add New Bot", callback_data="saas_add")])
    else:
        buttons.append([InlineKeyboardButton("🔒 Bot Limit Reached", callback_data="saas_limit_info")])

    return text, InlineKeyboardMarkup(buttons)


@app.on_message(filters.command(["createbot", "saas"]) & filters.private)
async def saas_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    if await database.is_banned(user_id):
        return
    text, markup = await get_saas_dashboard_markup(user_id)
    await message.reply_text(text, reply_markup=markup)


@app.on_callback_query(filters.regex(r"^saas_plans$"))
async def saas_plans_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    current_plan = await database.get_user_plan(user_id)

    text = "📋 **SaaS Plans**\n\nChoose the plan that fits your needs:\n\n"

    for plan_id in ["starter", "pro", "agency"]:
        plan = database.PLAN_DEFINITIONS[plan_id]
        icon = PLAN_ICONS[plan_id]
        label = plan["name"]
        is_current = plan_id == current_plan
        current_tag = "  ✅ **Current**" if is_current else ""
        text += (
            f"{icon} **{label}** — ₹{plan['price_inr']}/mo{current_tag}\n"
            f"  _{plan['description']}_\n"
            f"  Max bots: {plan['features']['max_bots']}\n\n"
        )

    buttons = []
    for plan_id in ["pro", "agency"]:
        if plan_id != current_plan:
            buttons.append([InlineKeyboardButton(
                f"⬆️ Upgrade to {PLAN_LABELS[plan_id]} — ₹{database.PLAN_DEFINITIONS[plan_id]['price_inr']}/mo",
                callback_data=f"saas_checkout_{plan_id}",
            )])

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="saas_dashboard")])
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^saas_checkout_(pro|agency)$"))
async def saas_checkout_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    plan_id = callback_query.matches[0].group(1)
    plan = database.PLAN_DEFINITIONS[plan_id]
    icon = PLAN_ICONS[plan_id]

    text = (
        f"{icon} **Confirm Upgrade — {plan['name']}**\n\n"
        f"**Plan:** {plan['name']}\n"
        f"**Price:** ₹{plan['price_inr']}/month\n"
        f"**Max Bots:** {plan['features']['max_bots']}\n"
        f"**Description:** {plan['description']}\n\n"
        f"💳 **Payment via UPI**\n"
        f"Pay ₹{plan['price_inr']} and send the screenshot for verification.\n"
    )

    upi_id = config.SAAS_UPI_ID or config.UPI_ID
    if upi_id:
        text += f"\n📱 **UPI ID:** `{upi_id}`"

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💳 I've Paid — Verify", callback_data=f"saas_pay_{plan_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="saas_plans")],
    ])
    await callback_query.message.edit_text(text, reply_markup=buttons)


@app.on_callback_query(filters.regex(r"^saas_pay_(pro|agency)$"))
async def saas_pay_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    plan_id = callback_query.matches[0].group(1)
    plan = database.PLAN_DEFINITIONS[plan_id]
    upi_id = config.SAAS_UPI_ID or config.UPI_ID

    upi_link = f"upi://pay?pa={upi_id}&pn=SaaS%20{plan['name']}&am={plan['price_inr']}&cu=INR&tn=SaaS%20{plan['name']}%20Plan"

    await database.users_col.update_one(
        {"_id": user_id},
        {"$set": {"state": "saas_awaiting_screenshot", "saas_pending_plan": plan_id}},
    )

    text = (
        f"💳 **Payment Instructions**\n\n"
        f"1. Open any UPI app (Google Pay, PhonePe, Paytm)\n"
        f"2. Pay **₹{plan['price_inr']}** to `{upi_id}`\n"
        f"3. Tap the button below to open the UPI app\n"
        f"4. After payment, **send the screenshot** here\n\n"
        f"__Your subscription will be activated after verification.__"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Pay via UPI", url=upi_link)],
        [InlineKeyboardButton("❌ Cancel", callback_data="saas_dashboard")],
    ])
    await callback_query.message.edit_text(text, reply_markup=buttons)


@app.on_callback_query(filters.regex(r"^saas_subscription$"))
async def saas_subscription_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    plan_id, sub, bot_count, max_bots, price = await get_user_sub_summary(user_id)
    icon = PLAN_ICONS.get(plan_id, "🌱")
    plan_name = PLAN_LABELS.get(plan_id, "Starter")

    if not sub:
        text = (
            f"📄 **Subscription**\n\n"
            f"You are on the **{icon} {plan_name}** plan (free tier).\n"
            f"Upgrade to Pro or Agency for more features and bots."
        )
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬆️ View Plans", callback_data="saas_plans")],
            [InlineKeyboardButton("🔙 Back", callback_data="saas_dashboard")],
        ])
        await callback_query.message.edit_text(text, reply_markup=buttons)
        return

    expiry = sub.get("expires_at")
    expiry_str = expiry.strftime("%d %b %Y") if expiry else "N/A"

    text = (
        f"📄 **Active Subscription**\n\n"
        f"**Plan:** {icon} {plan_name}\n"
        f"**Price:** ₹{price}/mo\n"
        f"**Status:** ✅ Active\n"
        f"**Expires:** {expiry_str}\n"
        f"**Bot Usage:** {bot_count}/{max_bots}\n\n"
    )

    buttons = [
        [InlineKeyboardButton(f"⬆️ Upgrade Plan", callback_data="saas_plans")],
        [InlineKeyboardButton("❌ Cancel Subscription", callback_data="saas_cancel_sub")],
        [InlineKeyboardButton("🔙 Back", callback_data="saas_dashboard")],
    ]
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^saas_cancel_sub$"))
async def saas_cancel_sub_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    cancelled = await database.cancel_subscription(user_id)
    if cancelled:
        await callback_query.answer("✅ Subscription cancelled.")
    else:
        await callback_query.answer("❌ No active subscription found.", show_alert=True)
    text, markup = await get_saas_dashboard_markup(user_id)
    await callback_query.message.edit_text(text, reply_markup=markup)


@app.on_callback_query(filters.regex(r"^saas_dashboard$"))
async def saas_dashboard_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    text, markup = await get_saas_dashboard_markup(user_id)
    await callback_query.message.edit_text(text, reply_markup=markup)


@app.on_callback_query(filters.regex(r"^saas_limit_info$"))
async def saas_limit_callback(client: Client, callback_query: CallbackQuery):
    await callback_query.answer(
        "🔒 Upgrade your plan to add more bots! Use /saas to see plans.",
        show_alert=True,
    )


@app.on_callback_query(filters.regex(r"^saas_add$"))
async def saas_add_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if await database.is_banned(user_id):
        await callback_query.answer("⛔️ You are banned.", show_alert=True)
        return

    plan_id = await database.get_user_plan(user_id)
    max_bots = database.get_plan_max_bots(plan_id)
    my_bots = await database.get_sub_bots_by_owner(user_id)

    if len(my_bots) >= max_bots:
        await callback_query.answer(
            f"🔒 Bot limit reached ({max_bots}). Upgrade your plan to add more.",
            show_alert=True,
        )
        return

    await database.users_col.update_one(
        {"_id": user_id},
        {"$set": {"state": "saas_awaiting_token"}},
    )

    await callback_query.answer()
    await callback_query.message.edit_text(
        "🤖 **Add New Bot**\n\n"
        "Please follow these steps:\n"
        "1. Go to @BotFather and create a new bot.\n"
        "2. Copy the **HTTP API Token** (e.g. `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`).\n"
        "3. Paste and send the token here as a direct message.\n\n"
        "Type `/cancel` to abort.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="saas_cancel_add")]]),
    )


@app.on_callback_query(filters.regex(r"^saas_cancel_add$"))
async def saas_cancel_add_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    await database.users_col.update_one(
        {"_id": user_id},
        {"$unset": {"state": "", "saas_pending_plan": ""}},
    )
    await callback_query.answer("Cancelled.")
    text, markup = await get_saas_dashboard_markup(user_id)
    await callback_query.message.edit_text(text, reply_markup=markup)


@app.on_callback_query(filters.regex(r"^saas_(stop|start|delete)_(.+)$"))
async def saas_manage_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if await database.is_banned(user_id):
        await callback_query.answer("⛔️ You are banned.", show_alert=True)
        return

    action = callback_query.matches[0].group(1)
    username = callback_query.matches[0].group(2)

    bot_doc = await database.sub_bots_col.find_one({"username": username, "owner_id": user_id})
    if not bot_doc:
        await callback_query.answer("❌ Bot config not found or permission denied.", show_alert=True)
        return

    bot_token = bot_doc["bot_token"]

    if action == "stop":
        await database.set_sub_bot_active(bot_token, False)
        await saas_runner.stop_bot(bot_token)
        await callback_query.answer(f"🛑 Stopped bot @{username}")
    elif action == "start":
        await database.set_sub_bot_active(bot_token, True)
        success = await saas_runner.start_bot(bot_token, username)
        if success:
            await callback_query.answer(f"🟢 Started bot @{username}")
        else:
            await callback_query.answer("❌ Failed to start bot. Token might be invalid.", show_alert=True)
    elif action == "delete":
        await saas_runner.stop_bot(bot_token)
        await database.remove_sub_bot(user_id, bot_token)
        await callback_query.answer(f"🗑 Deleted bot @{username}")

    text, markup = await get_saas_dashboard_markup(user_id)
    await callback_query.message.edit_text(text, reply_markup=markup)
