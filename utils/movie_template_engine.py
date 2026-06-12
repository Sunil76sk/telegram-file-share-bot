from __future__ import annotations

import datetime
import logging
from typing import Any

from database.mongo import db

logger = logging.getLogger(__name__)

TEMPLATE_COL = db["movie_templates"]

LAYOUT_TYPES = [
    "movie_review",
    "affiliate_promo",
    "store_promo",
    "premium_promo",
    "referral_promo",
    "custom",
]

MOVIE_REVIEW_LAYOUT = (
    "🎬 **{title}** ({year})\n\n"
    "⭐ **Rating:** {rating}/10\n"
    "🎭 **Genre:** {genre}\n"
    "🌍 **Language:** {language}\n"
    "⏱ **Duration:** {duration}\n\n"
    "{description}\n\n"
    "👇 **Download Below:**"
)

AFFILIATE_PROMO_LAYOUT = (
    "💸 **Special Offer!**\n\n"
    "{description}\n\n"
    "🔗 **Get it here:** {url}\n\n"
    "#Affiliate #Deals"
)

STORE_PROMO_LAYOUT = (
    "🛍️ **{product_name}**\n\n"
    "{description}\n\n"
    "💰 **Price:** {price}\n"
    "📦 **Stock:** {stock}\n\n"
    "👇 **Order Now:**"
)

PREMIUM_PROMO_LAYOUT = (
    "⭐ **Premium Plan**\n\n"
    "{description}\n\n"
    "✅ **Benefits:**\n"
    "{benefits}\n\n"
    "💳 **Price:** {price}\n\n"
    "👇 **Subscribe Now:**"
)

REFERRAL_PROMO_LAYOUT = (
    "👥 **Refer & Earn!**\n\n"
    "{description}\n\n"
    "🔗 **Your Referral Link:**\n"
    "{referral_link}\n\n"
    "💰 **Rewards:** {rewards}\n\n"
    "👇 **Share Now:**"
)

LAYOUT_TEMPLATES: dict[str, str] = {
    "movie_review": MOVIE_REVIEW_LAYOUT,
    "affiliate_promo": AFFILIATE_PROMO_LAYOUT,
    "store_promo": STORE_PROMO_LAYOUT,
    "premium_promo": PREMIUM_PROMO_LAYOUT,
    "referral_promo": REFERRAL_PROMO_LAYOUT,
}

DEFAULT_BUTTONS: dict[str, list[list[dict[str, str]]]] = {
    "movie_review": [
        [{"text": "🎬 Watch Now", "url": "https://t.me/"}],
        [{"text": "⭐ Rate This Movie", "url": "https://t.me/"}],
    ],
    "affiliate_promo": [
        [{"text": "🛒 Buy Now", "url": "https://t.me/"}],
    ],
    "store_promo": [
        [{"text": "🛍️ Order Now", "url": "https://t.me/"}],
        [{"text": "📦 View Catalog", "url": "https://t.me/"}],
    ],
    "premium_promo": [
        [{"text": "⭐ Subscribe", "url": "https://t.me/"}],
        [{"text": "❓ Learn More", "url": "https://t.me/"}],
    ],
    "referral_promo": [
        [{"text": "👥 Invite Friends", "url": "https://t.me/"}],
    ],
}


async def create_movie_template(
    user_id: int,
    name: str,
    layout_type: str,
    caption_template: str | None = None,
    buttons: list[list[dict[str, str]]] | None = None,
) -> str:
    if layout_type not in LAYOUT_TYPES:
        raise ValueError(f"Invalid layout type: {layout_type}. Valid: {LAYOUT_TYPES}")

    if not caption_template:
        caption_template = LAYOUT_TEMPLATES.get(layout_type, "")

    if buttons is None:
        buttons = DEFAULT_BUTTONS.get(layout_type, [])

    doc = {
        "user_id": user_id,
        "name": name,
        "layout_type": layout_type,
        "caption_template": caption_template,
        "buttons": buttons,
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "updated_at": datetime.datetime.now(datetime.timezone.utc),
    }
    result = await TEMPLATE_COL.insert_one(doc)
    logger.info(f"Movie template created: {name} (type={layout_type}) by user {user_id}")
    return str(result.inserted_id)


async def get_movie_template(template_id: str) -> dict | None:
    from bson import ObjectId
    try:
        return await TEMPLATE_COL.find_one({"_id": ObjectId(template_id)})
    except Exception:
        return None


async def get_user_movie_templates(user_id: int) -> list[dict]:
    cursor = TEMPLATE_COL.find({"user_id": user_id}).sort("created_at", -1)
    return [doc async for doc in cursor]


async def update_movie_template(template_id: str, user_id: int, updates: dict) -> bool:
    from bson import ObjectId
    updates["updated_at"] = datetime.datetime.now(datetime.timezone.utc)
    try:
        result = await TEMPLATE_COL.update_one(
            {"_id": ObjectId(template_id), "user_id": user_id},
            {"$set": updates},
        )
        return result.modified_count > 0
    except Exception:
        return False


async def delete_movie_template(template_id: str, user_id: int) -> bool:
    from bson import ObjectId
    try:
        result = await TEMPLATE_COL.delete_one(
            {"_id": ObjectId(template_id), "user_id": user_id}
        )
        return result.deleted_count > 0
    except Exception:
        return False


async def apply_movie_template(
    template: dict,
    variables: dict[str, Any] | None = None,
) -> tuple[str, list[list[dict[str, str]]]]:
    caption = template.get("caption_template", "")
    buttons = template.get("buttons", [])

    if variables:
        try:
            caption = caption.format(**variables)
        except KeyError as e:
            logger.warning(f"Missing template variable: {e}")

    buttons_copy: list[list[dict[str, str]]] = []
    for row in buttons:
        new_row: list[dict[str, str]] = []
        for btn in row:
            btn_text = btn.get("text", "")
            btn_url = btn.get("url", "")
            if variables:
                try:
                    btn_text = btn_text.format(**variables)
                    btn_url = btn_url.format(**variables)
                except KeyError:
                    pass
            new_row.append({"text": btn_text, "url": btn_url})
        buttons_copy.append(new_row)

    return caption, buttons_copy


async def get_available_layouts() -> list[dict[str, str]]:
    return [
        {"type": lt, "label": lt.replace("_", " ").title()}
        for lt in LAYOUT_TYPES
    ]
