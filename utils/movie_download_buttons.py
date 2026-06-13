from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.mongo import db

logger = logging.getLogger(__name__)

DOWNLOAD_BUTTONS_COL = db["movie_download_buttons"]

LINK_TYPES = {
    "direct": "direct",
    "shortener": "shortener",
    "premium": "premium_only",
    "password": "password_protected",
    "paid": "paid",
}

DEFAULT_BUTTON_LABELS = {
    "download": "📥 Download",
    "watch": "🎬 Watch Now",
    "hd": "📺 HD Quality",
    "subtitles": "📝 Subtitles",
    "torrent": "🧲 Torrent",
}


async def create_download_button_config(
    user_id: int,
    name: str,
    button_label: str,
    link_type: str,
    link_url: str,
    shortener_id: str | None = None,
    requires_premium: bool = False,
    requires_password: bool = False,
    password: str | None = None,
    price: float | None = None,
    file_id: str | None = None,
) -> str:
    doc = {
        "user_id": user_id,
        "name": name,
        "button_label": button_label,
        "link_type": link_type,
        "link_url": link_url,
        "shortener_id": shortener_id,
        "requires_premium": requires_premium,
        "requires_password": requires_password,
        "password": password,
        "price": price,
        "file_id": file_id,
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "updated_at": datetime.datetime.now(datetime.timezone.utc),
    }
    result = await DOWNLOAD_BUTTONS_COL.insert_one(doc)
    logger.info(f"Download button config created: {name} (type={link_type}) by user {user_id}")
    return str(result.inserted_id)


async def create_uuid_download_config(
    user_id: int,
    name: str,
    button_label: str,
    link_type: str,
    link_url: str = "",
    file_id: str | None = None,
    requires_premium: bool = False,
    requires_password: bool = False,
    password: str | None = None,
    price: float | None = None,
) -> tuple[str, str]:
    """Create download button config with UUID token (never predictable IDs).

    Returns (token, config_id).
    """
    token = f"dl_{uuid.uuid4().hex[:16]}"
    doc = {
        "token": token,
        "user_id": user_id,
        "name": name,
        "button_label": button_label,
        "link_type": link_type,
        "link_url": link_url,
        "file_id": file_id,
        "requires_premium": requires_premium,
        "requires_password": requires_password,
        "password": password,
        "price": price,
        "click_count": 0,
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "updated_at": datetime.datetime.now(datetime.timezone.utc),
    }
    result = await DOWNLOAD_BUTTONS_COL.insert_one(doc)
    logger.info(f"UUID download config created: {name} token={token} by user {user_id}")
    return token, str(result.inserted_id)


async def get_download_button_config(config_id: str) -> dict | None:
    from bson import ObjectId
    try:
        return await DOWNLOAD_BUTTONS_COL.find_one({"_id": ObjectId(config_id)})
    except Exception:
        return None


async def get_download_config_by_token(token: str) -> dict | None:
    """Fetch download config by UUID token (for dl_TOKEN deep links)."""
    return await DOWNLOAD_BUTTONS_COL.find_one({"token": token})


async def get_user_download_button_configs(user_id: int) -> list[dict]:
    cursor = DOWNLOAD_BUTTONS_COL.find({"user_id": user_id}).sort("created_at", -1)
    return [doc async for doc in cursor]


async def generate_download_buttons(
    configs: list[dict],
    user_id: int | None = None,
    additional_buttons: list[list[dict[str, str]]] | None = None,
) -> InlineKeyboardMarkup | None:
    keyboard: list[list[InlineKeyboardButton]] = []
    import config as bot_config
    bot_username = bot_config.BOT_USERNAME or "bot"

    for config in configs:
        config_id = str(config.get("_id"))
        token = config.get("token")
        if token:
            link_url = f"https://t.me/{bot_username}?start={token}"
        else:
            link_url = f"https://t.me/{bot_username}?start=dl_{config_id}"
        link_type = config.get("link_type", "direct")
        label = config.get("button_label", DEFAULT_BUTTON_LABELS.get("download", "📥 Download"))

        if link_type == "premium" and user_id:
            from database.users import is_user_premium
            if not await is_user_premium(user_id):
                label = "⭐ Premium Only"
        elif link_type == "password" and user_id:
            from database.state import get_password_entry_session
            session = await get_password_entry_session(user_id, f"btn_{config_id}")
            if not session:
                label = "🔒 Unlock"
        elif link_type == "paid" and user_id:
            label = f"💰 {label}"

        keyboard.append([
            InlineKeyboardButton(text=label, url=link_url)
        ])

    if additional_buttons:
        for row in additional_buttons:
            keyboard_row = []
            for btn in row:
                keyboard_row.append(
                    InlineKeyboardButton(text=btn["text"], url=btn.get("url", ""))
                )
            keyboard.append(keyboard_row)

    return InlineKeyboardMarkup(keyboard) if keyboard else None


async def update_download_button_config(config_id: str, user_id: int, updates: dict) -> bool:
    from bson import ObjectId
    updates["updated_at"] = datetime.datetime.now(datetime.timezone.utc)
    try:
        result = await DOWNLOAD_BUTTONS_COL.update_one(
            {"_id": ObjectId(config_id), "user_id": user_id},
            {"$set": updates},
        )
        return result.modified_count > 0
    except Exception:
        return False


async def delete_download_button_config(config_id: str, user_id: int) -> bool:
    from bson import ObjectId
    try:
        result = await DOWNLOAD_BUTTONS_COL.delete_one(
            {"_id": ObjectId(config_id), "user_id": user_id}
        )
        return result.deleted_count > 0
    except Exception:
        return False


async def increment_download_click(config_id: str) -> bool:
    from bson import ObjectId
    try:
        result = await DOWNLOAD_BUTTONS_COL.update_one(
            {"_id": ObjectId(config_id)},
            {"$inc": {"click_count": 1}},
        )
        return result.modified_count > 0
    except Exception:
        return False
