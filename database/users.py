from __future__ import annotations

import datetime
import config
from database.mongo import users_col, admins_col

# --- USER HELPERS ---


async def add_user(
    user_id: int, username: str | None = None, first_name: str = "", last_name: str = ""
):
    """Add a new user or update their details if they exist."""
    user_data = {
        "user_id": user_id,
        "username": username,
        "first_name": first_name,
        "last_name": last_name,
        "last_seen": datetime.datetime.now(datetime.timezone.utc),
        "active": True,
    }

    # Use upsert to create or update
    await users_col.update_one(
        {"_id": user_id},
        {
            "$set": user_data,
            "$setOnInsert": {
                "is_banned": False,
                "joined_at": datetime.datetime.now(datetime.timezone.utc),
            },
        },
        upsert=True,
    )


async def get_user(user_id: int):
    """Retrieve user details by user ID."""
    return await users_col.find_one({"_id": user_id})


async def set_user_active_status(user_id: int, active: bool):
    """Update active status of a user (e.g. if they blocked the bot)."""
    await users_col.update_one({"_id": user_id}, {"$set": {"active": active}})


async def ban_user(user_id: int):
    """Ban a user from accessing the bot."""
    await users_col.update_one(
        {"_id": user_id}, {"$set": {"is_banned": True}}, upsert=True
    )


async def unban_user(user_id: int):
    """Unban a user."""
    await users_col.update_one(
        {"_id": user_id}, {"$set": {"is_banned": False}}, upsert=True
    )


async def is_banned(user_id: int) -> bool:
    """Check if a user is banned."""
    user = await users_col.find_one({"_id": user_id})
    if user:
        return user.get("is_banned", False)
    return False


async def get_users_count() -> int:
    """Get the total number of users."""
    return await users_col.count_documents({})


async def get_all_users():
    """Get a list of all active user IDs."""
    cursor = users_col.find({"active": {"$ne": False}}, {"_id": 1, "user_id": 1})
    return [doc.get("user_id", doc["_id"]) async for doc in cursor]


async def delete_user(user_id: int) -> bool:
    """Permanently delete a user from the database."""
    result = await users_col.delete_one({"_id": user_id})
    return result.deleted_count > 0


# --- DYNAMIC ADMIN HELPERS ---


async def add_admin(user_id: int):
    """Dynamically promote a user to admin."""
    await admins_col.update_one(
        {"_id": user_id},
        {"$set": {"added_at": datetime.datetime.now(datetime.timezone.utc)}},
        upsert=True,
    )


async def remove_admin(user_id: int) -> bool:
    """Demote a dynamic admin."""
    result = await admins_col.delete_one({"_id": user_id})
    return result.deleted_count > 0


async def get_dynamic_admins() -> list:
    """Get the list of all dynamically added admin user IDs."""
    cursor = admins_col.find({})
    return [doc["_id"] async for doc in cursor]


async def is_admin(user_id: int, client=None) -> bool:
    """Check if user ID is in static config admin list, dynamic admin database, or is the owner of the client sub-bot."""
    if user_id in config.ADMIN_IDS:
        return True
    doc = await admins_col.find_one({"_id": user_id})
    if doc is not None:
        return True

    # If client is provided, check if client is a sub-bot and user_id is the owner
    if client:
        from database.mongo import sub_bots_col

        bot_me = getattr(client, "me", None)
        if bot_me:
            sub_bot = await sub_bots_col.find_one({"username": bot_me.username})
            if sub_bot and sub_bot.get("owner_id") == user_id:
                return True

    return False


# --- MONETIZATION & REFERRAL HELPERS ---


async def set_user_referred_by(user_id: int, referrer_id: int):
    """Set the referrer for a user."""
    await users_col.update_one({"_id": user_id}, {"$set": {"referred_by": referrer_id}})


async def add_user_points(user_id: int, points: int):
    """Add or subtract points from a user."""
    await users_col.update_one(
        {"_id": user_id}, {"$inc": {"points": points}}, upsert=True
    )


async def get_user_points(user_id: int) -> int:
    """Get the current points of a user."""
    user = await users_col.find_one({"_id": user_id})
    if user:
        return user.get("points", 0)
    return 0


async def is_user_premium(user_id: int) -> bool:
    """Check if the user has an active premium subscription."""
    # Admins are automatically premium
    if await is_admin(user_id):
        return True

    user = await users_col.find_one({"_id": user_id})
    if not user:
        return False

    expiry = user.get("premium_expiry")
    if expiry:
        # Check if expiry date is naive or aware, keep it timezone aware for comparison
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=datetime.timezone.utc)
        return expiry > datetime.datetime.now(datetime.timezone.utc)

    return user.get("is_premium_lifetime", False)


async def set_user_premium(user_id: int, days: int, tier: str | None = None):
    """Grant premium status to a user for a certain number of days (or lifetime if days <= 0).

    Args:
        user_id: The user's Telegram ID.
        days: Number of days for the subscription. 0 or negative = lifetime.
        tier: Optional premium tier ('silver' or 'gold'). If None, defaults to 'gold'.
    """
    effective_tier = tier or "gold"

    if days <= 0:
        # Lifetime Premium
        await users_col.update_one(
            {"_id": user_id},
            {
                "$set": {
                    "is_premium_lifetime": True,
                    "premium_expiry": None,
                    "premium_tier": effective_tier,
                }
            },
            upsert=True,
        )
    else:
        # Temporary Premium
        user = await users_col.find_one({"_id": user_id})
        current_expiry = user.get("premium_expiry") if user else None

        now = datetime.datetime.now(datetime.timezone.utc)
        if current_expiry:
            if current_expiry.tzinfo is None:
                current_expiry = current_expiry.replace(tzinfo=datetime.timezone.utc)
            start_date = max(now, current_expiry)
        else:
            start_date = now

        new_expiry = start_date + datetime.timedelta(days=days)
        await users_col.update_one(
            {"_id": user_id},
            {
                "$set": {
                    "premium_expiry": new_expiry,
                    "is_premium_lifetime": False,
                    "premium_tier": effective_tier,
                }
            },
            upsert=True,
        )


async def set_user_premium_tier(user_id: int, tier: str):
    """Set the premium tier for a user ('silver' or 'gold')."""
    await users_col.update_one(
        {"_id": user_id}, {"$set": {"premium_tier": tier}}, upsert=True
    )


async def get_user_premium_tier(user_id: int) -> str | None:
    """Get the current premium tier of a user. Returns 'silver', 'gold', or None."""
    # Admins are automatically gold-tier
    if await is_admin(user_id):
        return "gold"

    user = await users_col.find_one({"_id": user_id})
    if not user:
        return None

    # Only return tier if premium is actually active
    is_premium = False
    if user.get("is_premium_lifetime", False):
        is_premium = True
    else:
        expiry = user.get("premium_expiry")
        if expiry:
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=datetime.timezone.utc)
            is_premium = expiry > datetime.datetime.now(datetime.timezone.utc)

    if is_premium:
        return user.get("premium_tier", "gold")
    return None


async def revoke_user_premium(user_id: int):
    """Revoke premium status from a user entirely."""
    await users_col.update_one(
        {"_id": user_id},
        {
            "$set": {
                "is_premium_lifetime": False,
                "premium_expiry": None,
                "premium_tier": None,
            }
        },
    )


async def get_premium_expiry_str(user_id: int) -> str:
    """Get a human-readable representation of premium expiry including tier."""
    user = await users_col.find_one({"_id": user_id})
    if not user:
        return "Regular User"

    tier = user.get("premium_tier")
    tier_label = ""
    if tier == "gold":
        tier_label = " 👑 Gold"
    elif tier == "silver":
        tier_label = " 🥈 Silver"

    if user.get("is_premium_lifetime", False):
        return f"Lifetime Premium{tier_label} 🌟"

    expiry = user.get("premium_expiry")
    if expiry:
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=datetime.timezone.utc)
        if expiry > datetime.datetime.now(datetime.timezone.utc):
            return f"Premium{tier_label} until {expiry.strftime('%Y-%m-%d %H:%M:%S UTC')} 🌟"

    return "Regular User"


async def has_user_unlocked_link(user_id: int, token: str) -> bool:
    """Check if a user has unlocked/paid for a specific shared link."""
    # Admins automatically have access
    if await is_admin(user_id):
        return True

    user = await users_col.find_one({"_id": user_id})
    if user:
        unlocked_links = user.get("unlocked_links", [])
        return token in unlocked_links
    return False


async def unlock_link_for_user(user_id: int, token: str):
    """Add a link token to the user's list of unlocked links."""
    await users_col.update_one(
        {"_id": user_id}, {"$addToSet": {"unlocked_links": token}}, upsert=True
    )


async def get_user_referrals(user_id: int) -> list:
    """Get all users referred by this user."""
    cursor = users_col.find({"referred_by": user_id})
    return [doc async for doc in cursor]


async def get_referral_leaderboard(limit: int = 10) -> list:
    """Get the top referrers."""
    # Aggregate referrals count
    pipeline = [
        {"$match": {"referred_by": {"$exists": True, "$ne": None}}},
        {"$group": {"_id": "$referred_by", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": limit},
    ]
    cursor = users_col.aggregate(pipeline)
    leaderboard = []
    async for doc in cursor:
        user_info = await users_col.find_one({"_id": doc["_id"]})
        username = user_info.get("username") if user_info else None
        first_name = user_info.get("first_name", "User") if user_info else "User"
        display_name = f"@{username}" if username else first_name
        leaderboard.append(
            {"user_id": doc["_id"], "name": display_name, "count": doc["count"]}
        )
    return leaderboard
