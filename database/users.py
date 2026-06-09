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
    await users_col.update_one(
        {"_id": user_id},
        {"$set": {"active": active}}
    )


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


async def is_admin(user_id: int) -> bool:
    """Check if user ID is in static config admin list or dynamic admin database."""
    if user_id in config.ADMIN_IDS:
        return True
    doc = await admins_col.find_one({"_id": user_id})
    return doc is not None
