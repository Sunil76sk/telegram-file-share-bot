from __future__ import annotations

import datetime
import random
import logging
from bson import ObjectId
from database.mongo import shorteners_col, files_col

logger = logging.getLogger(__name__)


async def add_shortener(
    name: str,
    api_url: str,
    api_key: str,
    weight: int = 1,
    geo_countries: list[str] | None = None,
    cpm: float = 3.0,
    bot_id: int | None = None,
) -> str:
    """
    Add a new URL shortener configuration.

    geo_countries: List of country codes (e.g. ['US', 'IN', 'GB']) or ['ALL'].
    bot_id: None for global bot shorteners, or sub-bot user ID/bot ID for SaaS.
    """
    if geo_countries is None:
        geo_countries = ["ALL"]
    # Normalize to uppercase
    geo_countries = [c.strip().upper() for c in geo_countries if c.strip()]
    if not geo_countries:
        geo_countries = ["ALL"]

    doc = {
        "name": name,
        "api_url": api_url.strip(),
        "api_key": api_key.strip(),
        "weight": max(1, weight),
        "geo_countries": geo_countries,
        "cpm": max(0.0, cpm),
        "bot_id": bot_id,
        "status": "active",
        "views": 0,
        "clicks": 0,
        "revenue": 0.0,
        "created_at": datetime.datetime.now(datetime.timezone.utc),
    }
    res = await shorteners_col.insert_one(doc)
    return str(res.inserted_id)


async def get_shorteners(
    bot_id: int | None = None, active_only: bool = False
) -> list[dict]:
    """Retrieve all shortener configurations for a bot."""
    query: dict = {"bot_id": bot_id}
    if active_only:
        query["status"] = "active"
    cursor = shorteners_col.find(query).sort("created_at", -1)
    return [doc async for doc in cursor]


async def get_shortener_by_id(shortener_id: str) -> dict | None:
    """Retrieve a shortener configuration by its hex ID string."""
    try:
        return await shorteners_col.find_one({"_id": ObjectId(shortener_id)})
    except Exception:
        return None


async def delete_shortener(shortener_id: str) -> bool:
    """Delete a shortener configuration."""
    try:
        res = await shorteners_col.delete_one({"_id": ObjectId(shortener_id)})
        return res.deleted_count > 0
    except Exception:
        return False


async def update_shortener(shortener_id: str, fields: dict) -> bool:
    """Update fields of an existing shortener configuration."""
    try:
        # Normalize geo countries if provided
        if "geo_countries" in fields and fields["geo_countries"] is not None:
            fields["geo_countries"] = [
                c.strip().upper() for c in fields["geo_countries"] if c.strip()
            ]
            if not fields["geo_countries"]:
                fields["geo_countries"] = ["ALL"]

        res = await shorteners_col.update_one(
            {"_id": ObjectId(shortener_id)}, {"$set": fields}
        )
        return res.modified_count > 0
    except Exception as e:
        logger.error(f"Error updating shortener: {e}")
        return False


async def increment_shortener_stats(
    shortener_id: str | ObjectId, views: int = 0, clicks: int = 0, revenue: float = 0.0
):
    """Increment views, clicks, and revenue metrics for a shortener."""
    try:
        obj_id = (
            ObjectId(shortener_id) if isinstance(shortener_id, str) else shortener_id
        )
        await shorteners_col.update_one(
            {"_id": obj_id},
            {
                "$inc": {
                    "views": views,
                    "clicks": clicks,
                    "revenue": round(revenue, 5),
                }
            },
        )
    except Exception as e:
        logger.error(f"Error incrementing shortener stats: {e}")


async def get_best_shortener(
    bot_id: int | None = None,
    user_country: str | None = None,
    user_lang: str | None = None,
) -> dict | None:
    """
    Select the best shortener using geo-targeting and weighted rotation.
    """
    shorteners = await get_shorteners(bot_id=bot_id, active_only=True)
    if not shorteners:
        # If this is a sub-bot and has no custom shorteners, fall back to global ones
        if bot_id is not None:
            shorteners = await get_shorteners(bot_id=None, active_only=True)
        if not shorteners:
            return None

    # Filter by geo-targeting
    matched = []
    user_country_upper = user_country.upper() if user_country else None
    user_lang_upper = user_lang.upper() if user_lang else None

    for s in shorteners:
        geo = s.get("geo_countries", ["ALL"])
        if "ALL" in geo:
            matched.append(s)
            continue

        # Check if country matches
        if user_country_upper and user_country_upper in geo:
            matched.append(s)
            continue

        # Check if language matches (e.g. user_lang is 'en' or 'ru')
        if user_lang_upper:
            # Match languages like RU or EN
            lang_match = False
            for country_code in geo:
                if country_code == user_lang_upper or user_lang_upper.startswith(
                    country_code
                ):
                    lang_match = True
                    break
            if lang_match:
                matched.append(s)
                continue

    if not matched:
        # Fallback to shorteners configured with "ALL" or just any active shortener if none matches
        matched = [s for s in shorteners if "ALL" in s.get("geo_countries", ["ALL"])]
        if not matched:
            matched = shorteners

    # Weighted rotation
    total_weight = sum(s.get("weight", 1) for s in matched)
    if total_weight <= 0:
        return random.choice(matched)

    pick = random.uniform(0, total_weight)
    current = 0.0
    for s in matched:
        current += s.get("weight", 1)
        if current >= pick:
            return s

    return matched[0]


# --- LINK LEVEL MONETIZATION STATS ---


async def increment_link_monetization_stats(
    token: str, views: int = 0, clicks: int = 0, revenue: float = 0.0
):
    """Increment monetization specific metrics on a shared file link."""
    await files_col.update_one(
        {"token": token},
        {
            "$inc": {
                "monetization_views": views,
                "monetization_clicks": clicks,
                "monetization_revenue": round(revenue, 5),
            }
        },
    )
