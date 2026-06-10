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
import config
import database

logger = logging.getLogger(__name__)


# ─── ADD CATALOG ITEM INTERACTIVE WIZARD ────────────────────────────


@app.on_message(filters.command("addcatalog") & filters.private)
async def addcatalog_command_handler(client: Client, message: Message):
    """Start the interactive catalog item addition flow."""
    user_id = message.from_user.id
    if await database.is_banned(user_id):
        return

    if not await database.is_admin(user_id, client):
        await message.reply_text(
            "⛔️ You must be an administrator to add catalog items."
        )
        return

    msg = (
        "🛍 **Add New Content Catalog Item**\n\n"
        "Please select a category for the new item:"
    )

    buttons = []
    for cat_key, cat_name in config.PREMIUM_CATEGORIES.items():
        buttons.append(
            [
                InlineKeyboardButton(
                    cat_name, callback_data=f"admin_catalog_select_cat_{cat_key}"
                )
            ]
        )
    buttons.append(
        [InlineKeyboardButton("❌ Cancel", callback_data="admin_catalog_cancel")]
    )

    await message.reply_text(msg, reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters.regex(r"^admin_catalog_select_cat_([a-zA-Z0-9_]+)$"))
async def admin_catalog_select_cat_callback(
    client: Client, callback_query: CallbackQuery
):
    """Save category selection and prompt for Title."""
    user_id = callback_query.from_user.id
    if not await database.is_admin(user_id, client):
        await callback_query.answer("⛔️ Permission Denied", show_alert=True)
        return

    category = callback_query.matches[0].group(1)

    draft = {"category": category}
    await database.users_col.update_one(
        {"_id": user_id},
        {"$set": {"state": "catalog_awaiting_title", "catalog_draft": draft}},
    )

    await callback_query.answer()
    await callback_query.message.edit_text(
        "📝 **Step 2: Enter Item Title**\n\n"
        "Send the title for the premium content item (e.g. `Advanced Adobe Course`):",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="admin_catalog_cancel")]]
        ),
    )


@app.on_callback_query(filters.regex(r"^admin_catalog_cancel$"))
async def admin_catalog_cancel_callback(client: Client, callback_query: CallbackQuery):
    """Cancel interactive catalog addition wizard."""
    user_id = callback_query.from_user.id
    await database.users_col.update_one(
        {"_id": user_id}, {"$unset": {"state": "", "catalog_draft": ""}}
    )
    await callback_query.answer("Cancelled.")
    await callback_query.message.edit_text(
        "❌ Catalog item creation has been cancelled."
    )


async def handle_catalog_state(
    client: Client, message: Message, user_id: int, state: str, user_doc: dict
):
    """Process text inputs during the catalog addition wizard."""
    text = message.text.strip()
    draft = user_doc.get("catalog_draft", {})

    if state == "catalog_awaiting_title":
        if not text:
            await message.reply_text(
                "❌ Title cannot be empty. Please send a valid title:"
            )
            return

        draft["title"] = text
        await database.users_col.update_one(
            {"_id": user_id},
            {"$set": {"state": "catalog_awaiting_desc", "catalog_draft": draft}},
        )
        await message.reply_text(
            "📝 **Step 3: Enter Description**\n\n"
            "Send a description detailing what this item contains:"
        )

    elif state == "catalog_awaiting_desc":
        if not text:
            await message.reply_text(
                "❌ Description cannot be empty. Please send a valid description:"
            )
            return

        draft["description"] = text
        await database.users_col.update_one(
            {"_id": user_id},
            {"$set": {"state": "catalog_awaiting_token", "catalog_draft": draft}},
        )
        await message.reply_text(
            "🔗 **Step 4: Enter File Link Token**\n\n"
            "Send the exact file link token associated with this premium content. "
            "*(This token should match an existing shared link in the database)*:"
        )

    elif state == "catalog_awaiting_token":
        file_doc = await database.get_file_link(text)
        if not file_doc:
            await message.reply_text(
                "❌ **Invalid Token.** No matching file link found in the database. "
                "Please enter a valid file token:"
            )
            return

        draft["token"] = text
        await database.users_col.update_one(
            {"_id": user_id},
            {"$set": {"state": "catalog_awaiting_price_stars", "catalog_draft": draft}},
        )
        await message.reply_text(
            "⭐️ **Step 5: Enter Price in Stars**\n\n"
            "Send the price of this item in Telegram Stars (must be a positive integer, e.g. `100`):"
        )

    elif state == "catalog_awaiting_price_stars":
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
            {"$set": {"state": "catalog_awaiting_price_upi", "catalog_draft": draft}},
        )
        await message.reply_text(
            "💸 **Step 6: Enter Price in INR (UPI)**\n\n"
            "Send the price of this item in Indian Rupees (INR) for UPI payments (e.g. `49.00` or `99`):"
        )

    elif state == "catalog_awaiting_price_upi":
        try:
            price_upi = float(text)
            if price_upi < 0.0:
                raise ValueError
        except ValueError:
            await message.reply_text(
                "❌ Price must be a positive decimal number. Enter UPI Price:"
            )
            return

        draft["price_upi"] = price_upi
        await database.users_col.update_one(
            {"_id": user_id},
            {"$set": {"state": "catalog_awaiting_tier", "catalog_draft": draft}},
        )
        await message.reply_text(
            "🏷 **Step 7: Enter Required Premium Tier**\n\n"
            "Select the minimum user premium tier required to access this content for free.\n"
            "Type `none` (any premium user), `silver` (silver and gold tiers), or `gold` (gold tier only):"
        )

    elif state == "catalog_awaiting_tier":
        tier_input = text.lower()
        if tier_input not in ["none", "silver", "gold"]:
            await message.reply_text(
                "❌ Invalid input. Please enter `none`, `silver`, or `gold`:"
            )
            return

        tier_required = None if tier_input == "none" else tier_input

        # All inputs received, create catalog item
        item_id = await database.add_catalog_item(
            title=draft["title"],
            description=draft["description"],
            category=draft["category"],
            token=draft["token"],
            price_stars=draft["price_stars"],
            price_upi=draft["price_upi"],
            tier_required=tier_required,
            created_by=user_id,
        )

        # Clear state
        await database.users_col.update_one(
            {"_id": user_id}, {"$unset": {"state": "", "catalog_draft": ""}}
        )

        cat_name = config.PREMIUM_CATEGORIES.get(draft["category"], draft["category"])

        success_msg = (
            "🎉 **Content Catalog Item Added Successfully!**\n\n"
            f"🆔 **ID:** `{item_id}`\n"
            f"📄 **Title:** {draft['title']}\n"
            f"📂 **Category:** {cat_name}\n"
            f"🔗 **File Token:** `{draft['token']}`\n"
            f"⭐️ **Stars Price:** {draft['price_stars']} Stars\n"
            f"💸 **UPI Price:** ₹{draft['price_upi']}\n"
            f"🏷 **Required Tier:** {tier_input.upper()}"
        )
        await message.reply_text(success_msg)


# ─── BROWSE/MANAGE CATALOG (ADMIN) ──────────────────────────────────


@app.on_message(filters.command("catalog") & filters.private)
async def catalog_command_handler(client: Client, message: Message):
    """List and manage catalog items."""
    user_id = message.from_user.id
    if await database.is_banned(user_id):
        return

    if not await database.is_admin(user_id, client):
        await message.reply_text(
            "⛔️ You must be an administrator to manage the catalog."
        )
        return

    items = await database.get_all_catalog_items(active_only=False)

    if not items:
        await message.reply_text(
            "🛍 **Premium Catalog is empty.**\n"
            "Use /addcatalog to add a new premium content item."
        )
        return

    await message.reply_text("📋 **Premium Catalog Items:**\n*(Admin Panel)*")

    for item in items:
        status_symbol = "🟢" if item.get("is_active", True) else "🔴"
        "Active" if item.get("is_active", True) else "Inactive"
        req_tier = item.get("tier_required") or "None"

        info = (
            f"{status_symbol} **{item['title']}**\n"
            f"🆔 ID: `{item['_id']}`\n"
            f"📂 Category: `{item['category']}` | Token: `{item['token']}`\n"
            f"⭐️ Price: `{item['price_stars']}` Stars | UPI: `₹{item['price_upi']}`\n"
            f"🏷 Tier Required: `{req_tier.upper()}`\n"
            f"📈 Sales: `{item.get('total_purchases', 0)}` purchases | `{item.get('total_revenue_stars', 0)}` Stars"
        )

        item_id = str(item["_id"])
        toggle_label = "🔴 Disable" if item.get("is_active", True) else "🟢 Enable"

        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        toggle_label, callback_data=f"admin_catalog_toggle_{item_id}"
                    ),
                    InlineKeyboardButton(
                        "🗑 Delete", callback_data=f"admin_catalog_delete_{item_id}"
                    ),
                ]
            ]
        )

        await message.reply_text(info, reply_markup=buttons)


@app.on_callback_query(
    filters.regex(r"^admin_catalog_(toggle|delete)_([a-fA-F0-9]{24})$")
)
async def admin_catalog_manage_callback(client: Client, callback_query: CallbackQuery):
    """Handle enable/disable toggling and deletion of catalog items."""
    user_id = callback_query.from_user.id
    if not await database.is_admin(user_id, client):
        await callback_query.answer("⛔️ Permission Denied", show_alert=True)
        return

    action = callback_query.matches[0].group(1)
    item_id = callback_query.matches[0].group(2)

    if action == "toggle":
        new_status = await database.toggle_catalog_item(item_id)
        if new_status is None:
            await callback_query.answer(
                "❌ Failed to update catalog item.", show_alert=True
            )
            return

        status_str = "ENABLED" if new_status else "DISABLED"
        await callback_query.answer(f"Item {status_str} successfully!")

        # Refresh status on message
        item = await database.get_catalog_item(item_id)
        if item:
            status_symbol = "🟢" if item.get("is_active", True) else "🔴"
            req_tier = item.get("tier_required") or "None"
            info = (
                f"{status_symbol} **{item['title']}**\n"
                f"🆔 ID: `{item['_id']}`\n"
                f"📂 Category: `{item['category']}` | Token: `{item['token']}`\n"
                f"⭐️ Price: `{item['price_stars']}` Stars | UPI: `₹{item['price_upi']}`\n"
                f"🏷 Tier Required: `{req_tier.upper()}`\n"
                f"📈 Sales: `{item.get('total_purchases', 0)}` purchases | `{item.get('total_revenue_stars', 0)}` Stars"
            )
            toggle_label = "🔴 Disable" if item.get("is_active", True) else "🟢 Enable"
            buttons = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            toggle_label,
                            callback_data=f"admin_catalog_toggle_{item_id}",
                        ),
                        InlineKeyboardButton(
                            "🗑 Delete", callback_data=f"admin_catalog_delete_{item_id}"
                        ),
                    ]
                ]
            )
            await callback_query.message.edit_text(info, reply_markup=buttons)

    elif action == "delete":
        deleted = await database.delete_catalog_item(item_id)
        if deleted:
            await callback_query.answer("🗑 Item deleted permanently!")
            await callback_query.message.delete()
        else:
            await callback_query.answer("❌ Failed to delete item.", show_alert=True)


# ─── VIEW PENDING UPI REQUESTS ──────────────────────────────────────


@app.on_message(filters.command("upi_pending") & filters.private)
async def upi_pending_command_handler(client: Client, message: Message):
    """List all pending UPI payments awaiting admin confirmation."""
    user_id = message.from_user.id
    if await database.is_banned(user_id):
        return

    if not await database.is_admin(user_id, client):
        await message.reply_text(
            "⛔️ You must be an administrator to view pending UPI payments."
        )
        return

    pending_list = await database.get_all_pending_upi(limit=50)

    if not pending_list:
        await message.reply_text(
            "💸 **No pending UPI payments awaiting verification.**"
        )
        return

    await message.reply_text(f"📋 **Pending UPI Submissions ({len(pending_list)}):**")

    for payment in pending_list:
        pay_id = str(payment["_id"])
        user_info = f"`{payment['user_id']}`"

        plan_desc = payment["plan"]
        if plan_desc.startswith("item_"):
            item_id = plan_desc.split("_")[1]
            item = await database.get_catalog_item(item_id)
            plan_desc = f"Store Item: {item['title']}" if item else f"Item ID {item_id}"
        else:
            plan_desc = f"Subscription: {plan_desc.replace('_', ' ').title()}"

        info = (
            f"👤 User: {user_info}\n"
            f"📦 Plan: `{plan_desc}`\n"
            f"💰 Amount: ₹`{payment['amount_inr']}`\n"
            f"🕒 Created: {payment['created_at'].strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )

        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Approve ✅", callback_data=f"admin_upi_approve_{pay_id}"
                    ),
                    InlineKeyboardButton(
                        "Reject ❌", callback_data=f"admin_upi_reject_{pay_id}"
                    ),
                ]
            ]
        )

        # If user has attached a screenshot, we can forward or link it
        msg_id = payment.get("screenshot_msg_id")
        if msg_id:
            try:
                # Retrieve the screenshot message from the database channel or directly copy it
                await client.copy_message(
                    chat_id=user_id,
                    from_chat_id=payment["user_id"],
                    message_id=msg_id,
                    caption=info,
                    reply_markup=buttons,
                )
                continue
            except Exception:
                info += "\n⚠️ *(Unable to display screenshot directly - user might have cleared chat)*"

        await message.reply_text(info, reply_markup=buttons)


# ─── ACCESS LOGS AUDITING ───────────────────────────────────────────


@app.on_message(filters.command("accesslogs") & filters.private)
async def accesslogs_command_handler(client: Client, message: Message):
    """View and search content access logs."""
    user_id = message.from_user.id
    if await database.is_banned(user_id):
        return

    if not await database.is_admin(user_id, client):
        await message.reply_text(
            "⛔️ You must be an administrator to view access logs."
        )
        return

    args = message.text.split(maxsplit=1)

    if len(args) == 1:
        # Show general log statistics
        stats = await database.get_access_log_stats()
        by_action_str = "\n".join(
            [
                f"• `{action}`: {count}"
                for action, count in stats.get("by_action", {}).items()
            ]
        )

        msg = (
            "📊 **Content Access Log Statistics:**\n\n"
            f"• **Total Logged Events:** {stats.get('total', 0)}\n\n"
            "**By Action:**\n"
            f"{by_action_str or '• None'}\n\n"
            "🔍 **To search logs:**\n"
            "• Search by User ID: `/accesslogs [user_id]`\n"
            "• Search by File Token: `/accesslogs [token]`"
        )
        await message.reply_text(msg)
        return

    query = args[1].strip()

    # Determine if query is a user_id (integer) or a file token
    if query.isdigit():
        target_user_id = int(query)
        logs = await database.get_access_logs(target_user_id, limit=30)
        title = f"👤 **Access Logs for User `{target_user_id}` (Last 30):**\n\n"
    else:
        logs = await database.get_access_logs_by_token(query, limit=30)
        title = f"🔗 **Access Logs for Token `{query}` (Last 30):**\n\n"

    if not logs:
        await message.reply_text(f"❌ No access logs found for query: `{query}`")
        return

    log_lines = []
    for log in logs:
        ts = log["timestamp"].strftime("%m-%d %H:%M")
        action = log["action"].upper()
        method = log.get("method", "direct").upper()
        amount_str = f" (${log['amount']})" if log.get("amount") else ""

        # Shorten token/item details
        token_info = log["token"][:8] + "..." if log["token"] else "N/A"

        line = (
            f"🕒 `{ts}` | `{action}` via `{method}` | Token: `{token_info}`{amount_str}"
        )
        if log.get("user_id") and not query.isdigit():
            line += f" | User: `{log['user_id']}`"

        log_lines.append(line)

    await message.reply_text(title + "\n".join(log_lines))


# ─── MANUAL PREMIUM GRANTS / REVOCATION ──────────────────────────────


@app.on_message(filters.command("grantpremium") & filters.private)
async def grantpremium_command_handler(client: Client, message: Message):
    """Manually grant premium status to a user."""
    user_id = message.from_user.id
    if not await database.is_admin(user_id, client):
        await message.reply_text("⛔️ Admin only command.")
        return

    args = message.text.split()
    if len(args) < 3:
        await message.reply_text(
            "💡 **Usage:** `/grantpremium [user_id] [days] [tier (silver/gold)]`\nExample: `/grantpremium 1234567 30 silver`"
        )
        return

    try:
        target_user = int(args[1])
        days = int(args[2])
    except ValueError:
        await message.reply_text("❌ User ID and days must be integers.")
        return

    tier = "gold"
    if len(args) >= 4:
        tier_input = args[3].lower()
        if tier_input not in ["silver", "gold"]:
            await message.reply_text("❌ Tier must be either `silver` or `gold`.")
            return
        tier = tier_input

    # Apply premium status
    await database.set_user_premium(target_user, days, tier)
    await database.log_access(
        target_user,
        token="",
        action="subscription_activate",
        method="admin_grant",
        extra=f"{tier}_{days}d",
    )

    expiry_str = await database.get_premium_expiry_str(target_user)
    await message.reply_text(
        f"✅ **Premium granted successfully!**\n\n"
        f"👤 **User:** `{target_user}`\n"
        f"🏷 **Tier:** {tier.upper()}\n"
        f"📅 **Expiry:** {expiry_str}"
    )

    # Attempt to notify target user
    try:
        await client.send_message(
            chat_id=target_user,
            text=(
                f"🎉 **Premium Activated by Admin!** 🌟\n\n"
                f"Your premium membership has been manually granted by an administrator.\n"
                f"Status: **{expiry_str}**\n\n"
                "You now have access to premium download perks!"
            ),
        )
    except Exception as e:
        logger.warning(
            f"Could not notify user {target_user} of manual premium grant: {e}"
        )


@app.on_message(filters.command("revokepremium") & filters.private)
async def revokepremium_command_handler(client: Client, message: Message):
    """Manually revoke premium status from a user."""
    user_id = message.from_user.id
    if not await database.is_admin(user_id, client):
        await message.reply_text("⛔️ Admin only command.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("💡 **Usage:** `/revokepremium [user_id]`")
        return

    try:
        target_user = int(args[1])
    except ValueError:
        await message.reply_text("❌ User ID must be an integer.")
        return

    await database.revoke_user_premium(target_user)
    await database.log_access(
        target_user, token="", action="subscription_revoke", method="admin_revoke"
    )

    await message.reply_text(f"✅ Premium status revoked for user `{target_user}`.")

    # Attempt to notify target user
    try:
        await client.send_message(
            chat_id=target_user,
            text="⚠️ **Your premium membership has been cancelled/revoked by an administrator.**",
        )
    except Exception as e:
        logger.warning(
            f"Could not notify user {target_user} of premium revocation: {e}"
        )
