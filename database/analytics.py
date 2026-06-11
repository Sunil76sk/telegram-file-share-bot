from __future__ import annotations

import datetime
import logging
from database.mongo import analytics_events_col, users_col, files_col

logger = logging.getLogger(__name__)


async def track_event(
    user_id: int,
    event_type: str,
    token: str | None = None,
    country: str | None = None,
    source: str | None = None,
    metadata: dict | None = None,
):
    date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    doc = {
        "date": date_str,
        "user_id": user_id,
        "event": event_type,
        "token": token,
        "country": country,
        "source": source,
        "metadata": metadata or {},
        "timestamp": datetime.datetime.now(datetime.timezone.utc),
    }
    await analytics_events_col.insert_one(doc)


async def log_access(
    user_id: int,
    token: str = "",
    action: str = "",
    method: str = "",
    catalog_item_id: str | None = None,
    amount: float | int | None = None,
    extra: str | None = None,
):
    """Log access and subscription payment events into the analytics logs."""
    metadata = {
        "method": method,
        "catalog_item_id": catalog_item_id,
        "amount": amount,
        "extra": extra,
    }
    await track_event(
        user_id=user_id,
        event_type=action,
        token=token or None,
        metadata=metadata,
    )


async def get_dau(days: int = 1) -> int:
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    pipeline = [
        {"$match": {"timestamp": {"$gte": since}}},
        {"$group": {"_id": "$user_id"}},
        {"$count": "count"},
    ]
    cursor = analytics_events_col.aggregate(pipeline)
    result = await cursor.to_list(length=1)
    return result[0]["count"] if result else 0


async def get_mau(days: int = 30) -> int:
    return await get_dau(days=days)


async def get_user_growth(days: int = 30) -> dict:
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    pipeline = [
        {"$match": {"joined_at": {"$gte": since}}},
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$joined_at"}},
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    cursor = users_col.aggregate(pipeline)
    results = await cursor.to_list(length=365)
    total_new = sum(r["count"] for r in results)
    return {"daily": results, "total_new": total_new}


async def get_top_files(metric: str = "views", limit: int = 10) -> list[dict]:
    sort_field = metric
    cursor = files_col.find().sort(sort_field, -1).limit(limit)
    return await cursor.to_list(length=limit)


async def get_geo_distribution(days: int = 30) -> list[dict]:
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    pipeline = [
        {
            "$match": {
                "timestamp": {"$gte": since},
                "country": {"$exists": True, "$ne": None},
            }
        },
        {"$group": {"_id": "$country", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 20},
    ]
    cursor = analytics_events_col.aggregate(pipeline)
    return await cursor.to_list(length=20)


async def get_traffic_sources(days: int = 30) -> list[dict]:
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    pipeline = [
        {
            "$match": {
                "timestamp": {"$gte": since},
                "source": {"$exists": True, "$ne": None},
            }
        },
        {"$group": {"_id": "$source", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    cursor = analytics_events_col.aggregate(pipeline)
    return await cursor.to_list(length=20)


async def get_conversion_funnel(days: int = 30) -> dict:
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    match = {"$match": {"timestamp": {"$gte": since}}}

    pipeline = [
        match,
        {"$group": {"_id": "$event", "count": {"$sum": 1}}},
    ]
    cursor = analytics_events_col.aggregate(pipeline)
    results = await cursor.to_list(length=20)

    funnel = {
        "shortener_view": 0,
        "shortener_click": 0,
        "file_view": 0,
        "file_download": 0,
    }
    for r in results:
        event = r["_id"]
        if event in funnel:
            funnel[event] = r["count"]

    # Compute conversion rates
    funnel["view_to_click_ctr"] = (
        (funnel["shortener_click"] / funnel["shortener_view"] * 100)
        if funnel["shortener_view"] > 0
        else 0.0
    )
    funnel["click_to_download_rate"] = (
        (funnel["file_download"] / funnel["shortener_click"] * 100)
        if funnel["shortener_click"] > 0
        else 0.0
    )
    return funnel


async def get_daily_events(days: int = 7) -> list[dict]:
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    pipeline = [
        {"$match": {"timestamp": {"$gte": since}}},
        {
            "$group": {
                "_id": {
                    "date": "$date",
                    "event": "$event",
                },
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id.date": 1}},
    ]
    cursor = analytics_events_col.aggregate(pipeline)
    return await cursor.to_list(length=500)


async def get_advertiser_analytics(user_id: int) -> dict:
    total_views = await analytics_events_col.count_documents({"event": "file_view"})
    total_downloads = await analytics_events_col.count_documents(
        {"event": "file_download"}
    )
    dau = await get_dau(1)
    mau = await get_mau(30)
    total_users = await users_col.count_documents({})
    total_files = await files_col.count_documents({})

    top_files = await get_top_files("views", 5)
    geo = await get_geo_distribution(30)

    return {
        "total_views": total_views,
        "total_downloads": total_downloads,
        "dau": dau,
        "mau": mau,
        "total_users": total_users,
        "total_files": total_files,
        "top_files": top_files,
        "geo_distribution": geo,
    }
