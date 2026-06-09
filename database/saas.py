from __future__ import annotations

import datetime
from database.mongo import sub_bots_col

async def add_sub_bot(owner_id: int, bot_token: str, username: str):
    """Add a new sub-bot token and link it to the owner."""
    bot_data = {
        "owner_id": owner_id,
        "bot_token": bot_token,
        "username": username,
        "is_active": True,
        "created_at": datetime.datetime.now(datetime.timezone.utc),
    }
    await sub_bots_col.update_one(
        {"bot_token": bot_token},
        {"$set": bot_data},
        upsert=True
    )

async def get_sub_bots_by_owner(owner_id: int) -> list:
    """Retrieve all sub-bots owned by a specific user."""
    cursor = sub_bots_col.find({"owner_id": owner_id})
    return [doc async for doc in cursor]

async def get_all_active_sub_bots() -> list:
    """Retrieve all active sub-bots to spin them up on startup."""
    cursor = sub_bots_col.find({"is_active": True})
    return [doc async for doc in cursor]

async def remove_sub_bot(owner_id: int, bot_token: str) -> bool:
    """Delete a sub-bot configuration permanently."""
    result = await sub_bots_col.delete_one({"owner_id": owner_id, "bot_token": bot_token})
    return result.deleted_count > 0

async def set_sub_bot_active(bot_token: str, active: bool):
    """Enable or disable a sub-bot dynamically."""
    await sub_bots_col.update_one(
        {"bot_token": bot_token},
        {"$set": {"is_active": active}}
    )
