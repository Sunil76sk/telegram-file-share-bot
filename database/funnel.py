from __future__ import annotations

import datetime
import logging
from database.mongo import funnel_campaigns_col, funnel_analytics_col

logger = logging.getLogger(__name__)


async def create_campaign(
    campaign_id: str,
    source: str,
    title: str,
    description: str,
    asset_type: str,
    chat_id: int | str,
    invite_link: str,
    file_token: str | None = None,
    thumbnail_url: str | None = None,
) -> dict | None:
    existing = await funnel_campaigns_col.find_one({"_id": campaign_id})
    if existing:
        return None
    doc = {
        "_id": campaign_id,
        "source": source,
        "title": title,
        "description": description,
        "asset_type": asset_type,
        "chat_id": chat_id,
        "invite_link": invite_link,
        "file_token": file_token,
        "thumbnail_url": thumbnail_url,
        "active": True,
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "views": 0,
        "conversions": 0,
    }
    await funnel_campaigns_col.insert_one(doc)
    return doc


async def get_campaign(campaign_id: str) -> dict | None:
    return await funnel_campaigns_col.find_one({"_id": campaign_id})


async def get_campaigns_by_source(source: str, active_only: bool = True) -> list[dict]:
    query: dict = {"source": source}
    if active_only:
        query["active"] = True
    cursor = funnel_campaigns_col.find(query).sort("created_at", -1)
    return await cursor.to_list(length=100)


async def get_all_campaigns(active_only: bool = True) -> list[dict]:
    query: dict = {"active": True} if active_only else {}
    cursor = funnel_campaigns_col.find(query).sort("created_at", -1)
    return await cursor.to_list(length=100)


async def get_campaigns_by_asset_type(asset_type: str, active_only: bool = True) -> list[dict]:
    query: dict = {"asset_type": asset_type}
    if active_only:
        query["active"] = True
    cursor = funnel_campaigns_col.find(query).sort("created_at", -1)
    return await cursor.to_list(length=100)


async def update_campaign(campaign_id: str, updates: dict) -> bool:
    result = await funnel_campaigns_col.update_one({"_id": campaign_id}, {"$set": updates})
    return result.modified_count > 0


async def delete_campaign(campaign_id: str) -> bool:
    result = await funnel_campaigns_col.delete_one({"_id": campaign_id})
    return result.deleted_count > 0


async def increment_campaign_views(campaign_id: str) -> None:
    await funnel_campaigns_col.update_one(
        {"_id": campaign_id},
        {"$inc": {"views": 1}},
    )


async def increment_campaign_conversions(campaign_id: str) -> None:
    await funnel_campaigns_col.update_one(
        {"_id": campaign_id},
        {"$inc": {"conversions": 1}},
    )


async def log_source_visit(
    user_id: int,
    source: str,
    campaign_id: str | None = None,
    ref: str | None = None,
) -> None:
    doc = {
        "user_id": user_id,
        "source": source,
        "campaign_id": campaign_id,
        "ref": ref,
        "visited_at": datetime.datetime.now(datetime.timezone.utc),
    }
    await funnel_analytics_col.insert_one(doc)


async def get_source_analytics(source: str | None = None) -> list[dict]:
    match: dict = {}
    if source:
        match["source"] = source
    cursor = funnel_analytics_col.aggregate([
        {"$match": match},
        {"$group": {
            "_id": "$source",
            "total_visits": {"$sum": 1},
            "unique_users": {"$addToSet": "$user_id"},
        }},
        {"$project": {
            "source": "$_id",
            "total_visits": 1,
            "unique_users_count": {"$size": "$unique_users"},
        }},
    ])
    return await cursor.to_list(length=50)


async def get_campaign_stats(campaign_id: str) -> dict | None:
    campaign = await funnel_campaigns_col.find_one({"_id": campaign_id})
    if not campaign:
        return None
    total_visits = await funnel_analytics_col.count_documents({"campaign_id": campaign_id})
    pipeline = [
        {"$match": {"campaign_id": campaign_id}},
        {"$group": {"_id": None, "unique_users": {"$addToSet": "$user_id"}}},
    ]
    cursor = funnel_analytics_col.aggregate(pipeline)
    result = await cursor.to_list(length=1)
    unique_users = len(result[0]["unique_users"]) if result else 0
    return {
        "campaign_id": campaign_id,
        "views": campaign.get("views", 0),
        "conversions": campaign.get("conversions", 0),
        "total_analytics_visits": total_visits,
        "unique_users": unique_users,
    }
