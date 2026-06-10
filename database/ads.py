from __future__ import annotations

import datetime
import logging
from bson import ObjectId
from database.mongo import ads_col, ad_impressions_col, ad_clicks_col

logger = logging.getLogger(__name__)


async def create_ad(
    ad_type: str,
    title: str,
    description: str,
    created_by: int,
    media: str | None = None,
    button_text: str | None = None,
    button_url: str | None = None,
    channel_id: int | str | None = None,
    channel_link: str | None = None,
    file_token: str | None = None,
    brand_name: str | None = None,
    brand_logo_url: str | None = None,
    brand_message: str | None = None,
    schedule_start: datetime.datetime | None = None,
    schedule_end: datetime.datetime | None = None,
    cpm: float = 5.0,
) -> dict:
    doc = {
        "type": ad_type,
        "title": title,
        "description": description,
        "media": media,
        "button_text": button_text,
        "button_url": button_url,
        "channel_id": channel_id,
        "channel_link": channel_link,
        "file_token": file_token,
        "brand_name": brand_name,
        "brand_logo_url": brand_logo_url,
        "brand_message": brand_message,
        "status": "active",
        "schedule_start": schedule_start,
        "schedule_end": schedule_end,
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "created_by": created_by,
        "impressions": 0,
        "clicks": 0,
        "revenue": 0.0,
        "cpm": cpm,
    }
    result = await ads_col.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def get_ad(ad_id: str) -> dict | None:
    try:
        obj_id = ObjectId(ad_id)
    except Exception:
        return None
    return await ads_col.find_one({"_id": obj_id})


async def get_all_ads(ad_type: str | None = None) -> list[dict]:
    query: dict = {}
    if ad_type:
        query["type"] = ad_type
    cursor = ads_col.find(query).sort("created_at", -1)
    return await cursor.to_list(length=200)


async def update_ad(ad_id: str, updates: dict) -> bool:
    try:
        obj_id = ObjectId(ad_id)
    except Exception:
        return False
    result = await ads_col.update_one({"_id": obj_id}, {"$set": updates})
    return result.modified_count > 0


async def delete_ad(ad_id: str) -> bool:
    try:
        obj_id = ObjectId(ad_id)
    except Exception:
        return False
    result = await ads_col.delete_one({"_id": obj_id})
    return result.deleted_count > 0


async def increment_ad_impressions(ad_id: str) -> None:
    try:
        obj_id = ObjectId(ad_id)
    except Exception:
        return
    await ads_col.update_one({"_id": obj_id}, {"$inc": {"impressions": 1}})
    revenue_inc = 0.0
    ad = await ads_col.find_one({"_id": obj_id}, {"cpm": 1})
    if ad:
        revenue_inc = ad.get("cpm", 5.0) / 1000.0
    await ads_col.update_one({"_id": obj_id}, {"$inc": {"revenue": revenue_inc}})


async def increment_ad_clicks(ad_id: str) -> None:
    try:
        obj_id = ObjectId(ad_id)
    except Exception:
        return
    await ads_col.update_one({"_id": obj_id}, {"$inc": {"clicks": 1}})


async def log_ad_impression(ad_id: str, user_id: int) -> None:
    try:
        obj_id = ObjectId(ad_id)
    except Exception:
        return
    doc = {
        "ad_id": obj_id,
        "user_id": user_id,
        "timestamp": datetime.datetime.now(datetime.timezone.utc),
    }
    await ad_impressions_col.insert_one(doc)
    await increment_ad_impressions(ad_id)


async def log_ad_click(ad_id: str, user_id: int) -> None:
    try:
        obj_id = ObjectId(ad_id)
    except Exception:
        return
    doc = {
        "ad_id": obj_id,
        "user_id": user_id,
        "timestamp": datetime.datetime.now(datetime.timezone.utc),
    }
    await ad_clicks_col.insert_one(doc)
    await increment_ad_clicks(ad_id)


async def get_ad_revenue_report(
    start_date: datetime.datetime | None = None,
    end_date: datetime.datetime | None = None,
) -> dict:
    match: dict = {}
    if start_date or end_date:
        time_match: dict = {}
        if start_date:
            time_match["$gte"] = start_date
        if end_date:
            time_match["$lte"] = end_date
        match["created_at"] = time_match

    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": "$type",
                "count": {"$sum": 1},
                "total_impressions": {"$sum": "$impressions"},
                "total_clicks": {"$sum": "$clicks"},
                "total_revenue": {"$sum": "$revenue"},
            }
        },
    ]
    cursor = ads_col.aggregate(pipeline)
    results = await cursor.to_list(length=20)

    summary = {
        "total_ads": 0,
        "total_impressions": 0,
        "total_clicks": 0,
        "total_revenue": 0.0,
        "by_type": {},
    }

    for r in results:
        ad_type = r["_id"] or "unknown"
        summary["total_ads"] += r["count"]
        summary["total_impressions"] += r["total_impressions"]
        summary["total_clicks"] += r["total_clicks"]
        summary["total_revenue"] += r["total_revenue"]
        summary["by_type"][ad_type] = {
            "count": r["count"],
            "impressions": r["total_impressions"],
            "clicks": r["total_clicks"],
            "revenue": r["total_revenue"],
        }

    return summary


async def get_ads_due_for_broadcast() -> list[dict]:
    now = datetime.datetime.now(datetime.timezone.utc)
    query = {
        "type": "broadcast",
        "status": "active",
        "$and": [
            {
                "$or": [
                    {"schedule_start": {"$exists": False}},
                    {"schedule_start": None},
                    {"schedule_start": {"$lte": now}},
                ]
            },
            {
                "$or": [
                    {"schedule_end": {"$exists": False}},
                    {"schedule_end": None},
                    {"schedule_end": {"$gte": now}},
                ]
            },
        ],
    }
    cursor = ads_col.find(query)
    return await cursor.to_list(length=50)


async def get_force_join_ads() -> list[dict]:
    query = {
        "type": "force_join",
        "status": "active",
        "channel_id": {"$exists": True, "$ne": None},
        "channel_link": {"$exists": True, "$ne": None},
    }
    cursor = ads_col.find(query)
    return await cursor.to_list(length=50)
