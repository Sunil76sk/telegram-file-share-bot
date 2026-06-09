from __future__ import annotations

import datetime
from bson import ObjectId
from database.mongo import premium_catalog_col, access_logs_col, upi_pending_col


# ─── PREMIUM CATALOG ────────────────────────────────────────────────

VALID_CATEGORIES = [
    "ai_resources",
    "editing_assets",
    "courses",
    "templates",
    "educational",
]


async def add_catalog_item(
    title: str,
    description: str,
    category: str,
    token: str,
    price_stars: int,
    price_upi: float,
    tier_required: str | None,
    created_by: int,
) -> str:
    """Add a new premium content item to the catalog. Returns the inserted ID as string."""
    doc = {
        "title": title,
        "description": description,
        "category": category,
        "token": token,
        "price_stars": price_stars,
        "price_upi": price_upi,
        "tier_required": tier_required,
        "is_active": True,
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "created_by": created_by,
        "total_purchases": 0,
        "total_revenue_stars": 0,
    }
    result = await premium_catalog_col.insert_one(doc)
    return str(result.inserted_id)


async def get_catalog_item(item_id: str):
    """Get a single catalog item by its ObjectId string."""
    try:
        return await premium_catalog_col.find_one({"_id": ObjectId(item_id)})
    except Exception:
        return None


async def get_catalog_by_category(category: str, active_only: bool = True) -> list:
    """Get all catalog items in a specific category."""
    query: dict = {"category": category}
    if active_only:
        query["is_active"] = True
    cursor = premium_catalog_col.find(query).sort("created_at", -1)
    return [doc async for doc in cursor]


async def get_all_catalog_items(active_only: bool = False) -> list:
    """Get all catalog items, optionally filtered to active only."""
    query: dict = {}
    if active_only:
        query["is_active"] = True
    cursor = premium_catalog_col.find(query).sort("created_at", -1)
    return [doc async for doc in cursor]


async def update_catalog_item(item_id: str, **fields) -> bool:
    """Update fields of a catalog item."""
    try:
        result = await premium_catalog_col.update_one(
            {"_id": ObjectId(item_id)},
            {"$set": fields},
        )
        return result.modified_count > 0
    except Exception:
        return False


async def delete_catalog_item(item_id: str) -> bool:
    """Delete a catalog item permanently."""
    try:
        result = await premium_catalog_col.delete_one({"_id": ObjectId(item_id)})
        return result.deleted_count > 0
    except Exception:
        return False


async def toggle_catalog_item(item_id: str) -> bool | None:
    """Toggle active status of a catalog item. Returns new status or None on error."""
    try:
        item = await premium_catalog_col.find_one({"_id": ObjectId(item_id)})
        if not item:
            return None
        new_status = not item.get("is_active", True)
        await premium_catalog_col.update_one(
            {"_id": ObjectId(item_id)},
            {"$set": {"is_active": new_status}},
        )
        return new_status
    except Exception:
        return None


async def increment_catalog_purchases(item_id: str, stars_amount: int = 0):
    """Increment purchase count and revenue for a catalog item."""
    try:
        await premium_catalog_col.update_one(
            {"_id": ObjectId(item_id)},
            {"$inc": {"total_purchases": 1, "total_revenue_stars": stars_amount}},
        )
    except Exception:
        pass


async def get_catalog_item_by_token(token: str):
    """Find a catalog item by its linked file token."""
    return await premium_catalog_col.find_one({"token": token})


# ─── ACCESS LOGS ─────────────────────────────────────────────────────


async def log_access(
    user_id: int,
    token: str,
    action: str,
    method: str = "direct",
    catalog_item_id: str | None = None,
    amount: int | float | None = None,
    extra: str | None = None,
):
    """Log a premium content access event."""
    doc = {
        "user_id": user_id,
        "token": token,
        "catalog_item_id": catalog_item_id,
        "action": action,
        "method": method,
        "amount": amount,
        "extra": extra,
        "timestamp": datetime.datetime.now(datetime.timezone.utc),
    }
    await access_logs_col.insert_one(doc)


async def get_access_logs(user_id: int, limit: int = 50) -> list:
    """Get access logs for a specific user, most recent first."""
    cursor = (
        access_logs_col.find({"user_id": user_id})
        .sort("timestamp", -1)
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def get_access_logs_by_token(token: str, limit: int = 50) -> list:
    """Get access logs for a specific content token, most recent first."""
    cursor = (
        access_logs_col.find({"token": token})
        .sort("timestamp", -1)
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def get_access_log_stats() -> dict:
    """Get aggregate access log statistics."""
    total = await access_logs_col.count_documents({})
    pipeline = [
        {"$group": {"_id": "$action", "count": {"$sum": 1}}},
    ]
    action_counts = {}
    async for doc in access_logs_col.aggregate(pipeline):
        action_counts[doc["_id"]] = doc["count"]
    return {"total": total, "by_action": action_counts}


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
        upi_pending_col.find({"status": "pending"})
        .sort("created_at", 1)
        .limit(limit)
    )
    return [doc async for doc in cursor]
