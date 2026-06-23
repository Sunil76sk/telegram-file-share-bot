from __future__ import annotations

import logging
import datetime
from pyrogram import Client
from pymongo.errors import DuplicateKeyError
from pyrogram.raw.types import (
    UpdateNewMessage,
    MessageService,
    MessageActionPaymentSentMe,
    UpdateBotPrecheckoutQuery,
)
from bot import app
import database
from utils.delivery import deliver_files
from utils.helpers import answer_pre_checkout

logger = logging.getLogger(__name__)


async def _validate_payment_payload(payload: str) -> tuple[bool, str | None]:
    """Validate that a Stars payment payload still resolves to a live, purchasable
    item before approving checkout.

    Returns (ok, error_message). Fails closed: on any unknown payload or lookup
    error we reject, so the user is not charged for something undeliverable
    (they can simply retry).
    """
    try:
        if payload.startswith("premium_"):
            parts = payload.split("_")
            duration = (
                parts[2] if len(parts) == 3 else (parts[1] if len(parts) == 2 else "")
            )
            if duration not in ("weekly", "monthly", "lifetime"):
                return False, "This subscription plan is no longer available."
            return True, None

        if payload.startswith("prod_buy_"):
            prod_id = payload.split("prod_buy_")[1]
            from bson import ObjectId

            try:
                product = await database.get_product_by_id(ObjectId(prod_id))
            except Exception:
                product = None
            if not product:
                return False, "This product is no longer available."
            if not product.get("is_active", True):
                return False, "This product is currently unavailable."
            return True, None

        if payload.startswith("unlock_"):
            token = payload.split("_", 1)[1]
            if not await database.get_file_link(token):
                return False, "This file link no longer exists."
            return True, None

        if payload.startswith("catalog_"):
            item_id = payload.split("_")[1]
            if not await database.get_catalog_item(item_id):
                return False, "This item is no longer available."
            return True, None

        return False, "Invalid payment session. Please restart your purchase."
    except Exception as e:
        logger.error(f"Error validating payment payload '{payload}': {e}")
        return False, "Could not verify this purchase. Please try again."


@app.on_raw_update(group=10)
async def payment_raw_update_handler(client: Client, update, users, chats):
    """Handle raw pre-checkout and successful payment updates directly from Telegram."""

    # 1. Handle Pre-Checkout Query
    if isinstance(update, UpdateBotPrecheckoutQuery):
        query_id = str(update.query_id)
        payload = getattr(update, "payload", b"") or b""
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8", errors="replace")
        logger.info(
            f"Received raw pre-checkout query {query_id} from user {update.user_id} (payload={payload})"
        )
        ok, error_message = await _validate_payment_payload(payload)
        if not ok:
            logger.warning(
                f"Rejecting pre-checkout {query_id} for user {update.user_id}: {error_message}"
            )
        try:
            await answer_pre_checkout(
                client=client,
                pre_checkout_query_id=query_id,
                ok=ok,
                error_message=error_message,
            )
        except Exception as e:
            logger.error(f"Error answering pre-checkout query {query_id}: {e}")
        return

    # 2. Handle Successful Payment Service Message
    if isinstance(update, UpdateNewMessage):
        message = update.message
        if isinstance(message, MessageService):
            action = message.action
            if isinstance(action, MessageActionPaymentSentMe):
                # Extract user ID
                user_id = getattr(message.peer_id, "user_id", None)
                if not user_id:
                    user_id = getattr(message.from_id, "user_id", None)

                if not user_id:
                    logger.error("Could not determine user_id for successful payment")
                    return

                # Decode payload
                payload = action.payload
                if isinstance(payload, bytes):
                    payload = payload.decode("utf-8")

                amount = action.total_amount
                charge_id = (
                    (
                        getattr(action.charge, "id", None)
                        if hasattr(action, "charge") and action.charge
                        else None
                    )
                    or f"charge_{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}"
                )

                logger.info(
                    f"Successful payment from user {user_id}: payload={payload}, amount={amount} Stars, charge={charge_id}"
                )

                # Idempotency guard: atomically claim this charge_id. If the same
                # payment update is delivered more than once (Telegram redelivery
                # or two bot instances polling the same token), only the first
                # insert succeeds; every duplicate raises and is dropped BEFORE
                # any entitlement/delivery side-effect runs. This prevents premium
                # duration stacking and duplicate file delivery.
                try:
                    await database.payments_col.insert_one(
                        {
                            "_id": charge_id,
                            "user_id": user_id,
                            "amount": amount,
                            "payload": payload,
                            "status": "completed",
                            "processed": True,
                            "created_at": datetime.datetime.now(datetime.timezone.utc),
                        }
                    )
                except DuplicateKeyError:
                    logger.warning(
                        f"Duplicate successful-payment update for charge {charge_id} "
                        f"(user {user_id}, payload={payload}). Skipping side-effects."
                    )
                    return

                if payload.startswith("premium_"):
                    # Handle subscription purchase
                    parts = payload.split("_")
                    if len(parts) == 3:
                        tier = parts[1]
                        duration = parts[2]
                    else:
                        tier = "gold"  # Backward compatibility
                        duration = parts[1]

                    days = 0
                    if duration == "weekly":
                        days = 7
                    elif duration == "monthly":
                        days = 30
                    elif duration == "lifetime":
                        days = 0  # 0 signals lifetime premium

                    await database.set_user_premium(user_id, days, tier)
                    await database.log_access(
                        user_id,
                        token="",
                        action="subscription_activate",
                        method="stars",
                        amount=amount,
                        extra=payload,
                    )
                    expiry_str = await database.get_premium_expiry_str(user_id)

                    try:
                        await client.send_message(
                            chat_id=user_id,
                            text=(
                                f"🌟 **Premium Membership Activated!** 🌟\n\n"
                                f"Thank you for supporting us! Your account has been upgraded.\n"
                                f"Status: **{expiry_str}**\n\n"
                                f"You can now enjoy instant downloads without timers, ads, or URL shortener checks!"
                            ),
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to send premium confirmation to {user_id}: {e}"
                        )

                elif payload.startswith("prod_buy_"):
                    # Handle digital marketplace product purchase
                    prod_id = payload.split("prod_buy_")[1]
                    from bson import ObjectId

                    product = await database.get_product_by_id(ObjectId(prod_id))
                    if product:
                        # Prevent duplicate purchases
                        if await database.verify_purchase(user_id, product["_id"]):
                            purchase = await database.purchases_col.find_one(
                                {
                                    "user_id": user_id,
                                    "product_id": product["_id"],
                                    "status": "completed",
                                }
                            )
                            try:
                                await client.send_message(
                                    chat_id=user_id,
                                    text=f"✅ **Already Purchased!**\n\nYou already own **{product['name']}**. Delivering your files...",
                                )
                            except Exception:
                                pass
                            if purchase:
                                from handlers.marketplace import deliver_product_files

                                await deliver_product_files(
                                    client, user_id, purchase, product
                                )
                        else:
                            # Record the purchase and bump the sales counter
                            # atomically so we never mark a user as paid without
                            # also counting the sale (or vice versa).
                            _purchase_holder: dict = {}

                            async def _record_product_purchase(session):
                                _purchase_holder["purchase"] = (
                                    await database.record_purchase(
                                        user_id=user_id,
                                        product_id=product["_id"],
                                        product_token=product["token"],
                                        amount_paid=amount,
                                        payment_id=charge_id,
                                        status="completed",
                                        files_delivered=product["files"],
                                        session=session,
                                    )
                                )
                                await database.increment_product_sales(
                                    product["_id"], session=session
                                )

                            await database.with_transaction(_record_product_purchase)
                            purchase = _purchase_holder["purchase"]
                            try:
                                await client.send_message(
                                    chat_id=user_id,
                                    text=f"🎉 **Purchase Successful!**\n\nYou successfully bought **{product['name']}**! Delivering your files now...",
                                )
                            except Exception:
                                pass

                            from handlers.marketplace import deliver_product_files

                            await deliver_product_files(
                                client, user_id, purchase, product
                            )
                    else:
                        try:
                            await client.send_message(
                                chat_id=user_id,
                                text="❌ **Product Not Found!**\n\nWe could not find the product associated with your payment.",
                            )
                        except Exception:
                            pass

                elif payload.startswith("catalog_"):
                    # Handle catalog item purchase
                    item_id = payload.split("_")[1]
                    item = await database.get_catalog_item(item_id)
                    if item:
                        token = item["token"]
                        await database.unlock_link_for_user(user_id, token)
                        await database.increment_catalog_purchases(item_id, amount)
                        await database.log_access(
                            user_id,
                            token,
                            action="purchase",
                            method="stars",
                            catalog_item_id=item_id,
                            amount=amount,
                        )

                        file_doc = await database.get_file_link(token)
                        if file_doc:
                            try:
                                await client.send_message(
                                    chat_id=user_id,
                                    text=(
                                        f"🔓 **{item['title']} Unlocked!**\n\n"
                                        "Your payment was received successfully. We are delivering your files now..."
                                    ),
                                )
                            except Exception:
                                pass
                            await deliver_files(
                                client, user_id, file_doc, bypass_monetization=True
                            )
                        else:
                            try:
                                await client.send_message(
                                    chat_id=user_id,
                                    text=(
                                        "❌ **Files Not Found!**\n\n"
                                        "The item was unlocked successfully, but the files have been deleted by the admin."
                                    ),
                                )
                            except Exception:
                                pass
                    else:
                        try:
                            await client.send_message(
                                chat_id=user_id,
                                text="❌ **Item Not Found!**\n\nWe could not find the catalog item associated with your payment.",
                            )
                        except Exception:
                            pass

                elif payload.startswith("unlock_"):
                    # Handle pay-to-unlock link purchase
                    token = payload.split("_", 1)[1]
                    await database.unlock_link_for_user(user_id, token)
                    await database.log_access(
                        user_id, token, action="purchase", method="stars", amount=amount
                    )

                    file_doc = await database.get_file_link(token)
                    if file_doc:
                        try:
                            await client.send_message(
                                chat_id=user_id,
                                text=(
                                    "🔓 **File Link Unlocked!**\n\n"
                                    "Your payment was received successfully. We are delivering your files now..."
                                ),
                            )
                        except Exception:
                            pass
                        await deliver_files(
                            client, user_id, file_doc, bypass_monetization=True
                        )
                    else:
                        try:
                            await client.send_message(
                                chat_id=user_id,
                                text=(
                                    "❌ **Files Not Found!**\n\n"
                                    "The link was unlocked successfully, but the files have been deleted by the admin."
                                ),
                            )
                        except Exception:
                            pass
