from __future__ import annotations

import datetime
import logging
from database.mongo import saas_plans_col, saas_subscriptions_col

logger = logging.getLogger(__name__)

PLAN_DEFINITIONS = {
    "starter": {
        "name": "Starter",
        "description": "Best for creators getting started with file sharing.",
        "price_inr": 999,
        "features": {
            "max_bots": 1,
            "file_sharing": True,
            "analytics": True,
            "force_join": True,
            "premium_links": False,
            "branding": False,
            "shortener_integration": False,
            "multi_bot": False,
            "white_label": False,
            "advanced_analytics": False,
            "priority_support": False,
        },
    },
    "pro": {
        "name": "Pro",
        "description": "For educators, coaches, and influencers who need more.",
        "price_inr": 2499,
        "features": {
            "max_bots": 3,
            "file_sharing": True,
            "analytics": True,
            "force_join": True,
            "premium_links": True,
            "branding": True,
            "shortener_integration": True,
            "multi_bot": False,
            "white_label": False,
            "advanced_analytics": False,
            "priority_support": False,
        },
    },
    "agency": {
        "name": "Agency",
        "description": "For agencies and power users needing multi-bot management.",
        "price_inr": 4999,
        "features": {
            "max_bots": 10,
            "file_sharing": True,
            "analytics": True,
            "force_join": True,
            "premium_links": True,
            "branding": True,
            "shortener_integration": True,
            "multi_bot": True,
            "white_label": True,
            "advanced_analytics": True,
            "priority_support": True,
        },
    },
}


async def seed_plans():
    for plan_id, plan in PLAN_DEFINITIONS.items():
        existing = await saas_plans_col.find_one({"_id": plan_id})
        if not existing:
            await saas_plans_col.insert_one(
                {
                    "_id": plan_id,
                    "name": plan["name"],
                    "description": plan["description"],
                    "price_inr": plan["price_inr"],
                    "features": plan["features"],
                }
            )
    logger.info("SaaS plans seeded.")


def get_plan_features(plan_id: str) -> dict | None:
    plan = PLAN_DEFINITIONS.get(plan_id)
    if plan:
        return plan["features"]
    return None


def get_plan_max_bots(plan_id: str) -> int:
    features = get_plan_features(plan_id)
    if features:
        return features.get("max_bots", 1)
    return 1


async def get_active_subscription(user_id: int) -> dict | None:
    sub = await saas_subscriptions_col.find_one(
        {
            "user_id": user_id,
            "status": "active",
        }
    )
    if not sub:
        return None
    now = datetime.datetime.now(datetime.timezone.utc)
    expires_at = sub.get("expires_at")
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
        if expires_at < now:
            await saas_subscriptions_col.update_one(
                {"_id": sub["_id"]},
                {"$set": {"status": "expired"}},
            )
            return None
    return sub


async def create_subscription(
    user_id: int,
    plan_id: str,
    payment_method: str,
    payment_ref: str | None = None,
    months: int = 1,
) -> dict | None:
    existing = await get_active_subscription(user_id)
    if existing:
        return None
    now = datetime.datetime.now(datetime.timezone.utc)
    expires_at = now + datetime.timedelta(days=30 * months)
    doc = {
        "user_id": user_id,
        "plan_id": plan_id,
        "status": "active",
        "started_at": now,
        "expires_at": expires_at,
        "payment_method": payment_method,
        "payment_ref": payment_ref,
    }
    result = await saas_subscriptions_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def cancel_subscription(user_id: int) -> bool:
    result = await saas_subscriptions_col.update_one(
        {"user_id": user_id, "status": "active"},
        {"$set": {"status": "cancelled"}},
    )
    return result.modified_count > 0


async def get_user_plan(user_id: int) -> str:
    sub = await get_active_subscription(user_id)
    if sub:
        return sub["plan_id"]
    return "starter"


async def get_subscription_expiry(user_id: int) -> datetime.datetime | None:
    sub = await get_active_subscription(user_id)
    if sub:
        return sub.get("expires_at")
    return None


async def get_all_active_subscriptions() -> list[dict]:
    cursor = saas_subscriptions_col.find({"status": "active"})
    return await cursor.to_list(length=500)


async def get_subscription_by_user(user_id: int) -> dict | None:
    return await saas_subscriptions_col.find_one(
        {"user_id": user_id, "status": "active"}
    )
