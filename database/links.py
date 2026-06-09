from __future__ import annotations

import datetime
from database.mongo import files_col, channels_col

# --- FILE HELPERS ---


async def save_file_link(
    token: str,
    files: list,
    owner_id: int,
    price: int = 0,
    is_premium_only: bool = False,
    bot_id: int | None = None,
):
    """Save a new shareable link with associated files metadata."""
    file_doc = {
        "token": token,
        "files": files,
        "owner_id": owner_id,
        "views": 0,
        "downloads": 0,
        "unique_users": [],
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "expires_at": None,
        "password_hash": None,
        "label": None,
        "price": price,
        "is_premium_only": is_premium_only,
        "bot_id": bot_id,
    }
    await files_col.insert_one(file_doc)


async def get_file_link(token: str):
    """Retrieve file share information by its token."""
    return await files_col.find_one({"token": token})


async def update_file_link(
    token: str,
    files: list,
):
    """Update file references in an existing shareable link (preserves the sharing token)."""
    await files_col.update_one(
        {"token": token},
        {
            "$set": {
                "files": files,
            }
        },
    )


async def increment_views(token: str):
    """Increment the download/view counter of a link."""
    await files_col.update_one({"token": token}, {"$inc": {"views": 1}})


async def delete_file_link(token: str) -> bool:
    """Delete a file sharing link."""
    result = await files_col.delete_one({"token": token})
    return result.deleted_count > 0


async def get_files_count() -> int:
    """Get the total number of shared links."""
    return await files_col.count_documents({})


async def get_files_by_owner(owner_id: int, limit: int = 50, skip: int = 0):
    """Get list of files shared by a specific admin."""
    cursor = (
        files_col.find({"owner_id": owner_id})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def increment_link_views(token: str, user_id: int):
    """Increment view counter and add user_id to unique users set."""
    await files_col.update_one(
        {"token": token}, {"$inc": {"views": 1}, "$addToSet": {"unique_users": user_id}}
    )


async def increment_link_downloads(token: str, user_id: int):
    """Increment download counter and add user_id to unique users set."""
    await files_col.update_one(
        {"token": token},
        {"$inc": {"downloads": 1}, "$addToSet": {"unique_users": user_id}},
    )


async def set_link_password(token: str, password_hash: str):
    """Store the password hash against the link token."""
    await files_col.update_one({"token": token}, {"$set": {"password_hash": password_hash}})


async def set_link_expiry(token: str, expires_at: datetime.datetime | None):
    """Set the expiry timestamp for a link."""
    await files_col.update_one({"token": token}, {"$set": {"expires_at": expires_at}})


# --- FORCE JOIN CHAT HELPERS ---


async def add_force_sub_channel(chat_id_or_username, title: str, invite_link: str, bot_id: int | None = None):
    """Add a channel to the force subscribe list in DB."""
    await channels_col.update_one(
        {"_id": chat_id_or_username},
        {
            "$set": {
                "title": title,
                "invite_link": invite_link,
                "bot_id": bot_id,
                "added_at": datetime.datetime.now(datetime.timezone.utc),
            }
        },
        upsert=True,
    )


async def get_force_sub_channels(bot_id: int | None = None) -> list:
    """Get all force subscription channels."""
    # Find channels where bot_id matches or is missing (if bot_id is None)
    if bot_id is None:
        query = {"bot_id": {"$in": [None, False]}}
    else:
        query = {"bot_id": bot_id}
    cursor = channels_col.find(query)
    return [doc async for doc in cursor]


async def delete_force_sub_channel(chat_id_or_username) -> bool:
    """Remove a channel from force subscribe list."""
    result = await channels_col.delete_one({"_id": chat_id_or_username})
    return result.deleted_count > 0


async def set_link_price(token: str, price: int):
    """Set custom price in Stars for a shared link."""
    await files_col.update_one({"token": token}, {"$set": {"price": price}})


async def set_link_premium_only(token: str, is_premium_only: bool):
    """Toggle premium-only access for a shared link."""
    await files_col.update_one({"token": token}, {"$set": {"is_premium_only": is_premium_only}})
