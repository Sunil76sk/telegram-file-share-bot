from __future__ import annotations

import datetime
from bson import ObjectId
from database.mongo import upi_pending_col


# ─── UPI PENDING PAYMENTS ───────────────────────────────────────────


async def create_upi_payment(
    user_id: int,
    plan: str,
    amount_inr: float,
) -> str:
    """Create a pending UPI payment record. Returns inserted ID as string."""
    doc = {
        "user_id": user_id,
        "plan": plan,
        "amount_inr": amount_inr,
        "screenshot_msg_id": None,
        "status": "pending",
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "reviewed_by": None,
        "reviewed_at": None,
    }
    result = await upi_pending_col.insert_one(doc)
    return str(result.inserted_id)


async def set_upi_screenshot(payment_id: str, msg_id: int):
    """Attach screenshot message ID to a pending UPI payment."""
    try:
        await upi_pending_col.update_one(
            {"_id": ObjectId(payment_id)},
            {"$set": {"screenshot_msg_id": msg_id}},
        )
    except Exception:
        pass


async def get_pending_upi(user_id: int):
    """Get the most recent pending UPI payment for a user."""
    return await upi_pending_col.find_one(
        {"user_id": user_id, "status": "pending"},
        sort=[("created_at", -1)],
    )


async def get_upi_payment(payment_id: str):
    """Get a UPI payment by ID."""
    try:
        return await upi_pending_col.find_one({"_id": ObjectId(payment_id)})
    except Exception:
        return None


async def approve_upi(payment_id: str, admin_id: int) -> bool:
    """Approve a pending UPI payment."""
    try:
        result = await upi_pending_col.update_one(
            {"_id": ObjectId(payment_id), "status": "pending"},
            {
                "$set": {
                    "status": "approved",
                    "reviewed_by": admin_id,
                    "reviewed_at": datetime.datetime.now(datetime.timezone.utc),
                }
            },
        )
        return result.modified_count > 0
    except Exception:
        return False


async def reject_upi(payment_id: str, admin_id: int) -> bool:
    """Reject a pending UPI payment."""
    try:
        result = await upi_pending_col.update_one(
            {"_id": ObjectId(payment_id), "status": "pending"},
            {
                "$set": {
                    "status": "rejected",
                    "reviewed_by": admin_id,
                    "reviewed_at": datetime.datetime.now(datetime.timezone.utc),
                }
            },
        )
        return result.modified_count > 0
    except Exception:
        return False


async def get_all_pending_upi(limit: int = 50) -> list:
    """Get all pending UPI payments for admin review."""
    cursor = (
        upi_pending_col.find({"status": "pending"}).sort("created_at", 1).limit(limit)
    )
    return [doc async for doc in cursor]
