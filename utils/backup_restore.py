from __future__ import annotations

import datetime
import json
import logging
import os
from typing import Any

from database.mongo import db

logger = logging.getLogger(__name__)

BACKUP_COL = db["backup_jobs"]

EXPORT_COLLECTIONS = [
    "users",
    "files",
    "channels",
    "shorteners",
    "ads",
    "analytics_events",
    "payments",
    "upi_pending",
    "sub_bots",
    "scheduled_posts",
    "templates",
    "repost_jobs",
    "channel_stats",
    "transactions",
    "premium_users",
    "premium_plans",
    "referrals",
    "referral_rewards",
    "store_products",
    "store_orders",
    "coupons",
    "ad_impressions",
    "ad_clicks",
    "published_posts",
    "translations",
    "user_language",
]

IMPORT_COLLECTIONS = [
    "users",
    "files",
    "channels",
    "shorteners",
    "ads",
    "payments",
    "upi_pending",
    "sub_bots",
    "scheduled_posts",
    "templates",
    "repost_jobs",
    "channel_stats",
    "transactions",
    "premium_users",
    "premium_plans",
    "referrals",
    "referral_rewards",
    "store_products",
    "store_orders",
    "coupons",
    "published_posts",
    "translations",
    "user_language",
]

BACKUP_EXCLUDE_COLLECTIONS = {
    "processed_updates",
    "runtime_lock",
    "active_deliveries",
    "callback_tokens",
    "callback_execution_log",
    "state_transitions",
    "notification_queue",
    "queue_tasks",
    "diagnostics_logs",
    "error_audit_log",
    "event_audit_log",
    "admin_audit_log",
}


async def create_backup(
    created_by: int | None = None, include_all: bool = False
) -> dict[str, Any]:
    backup_id = f"backup_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    backup_data: dict[str, Any] = {
        "backup_id": backup_id,
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "created_by": created_by,
        "collections": {},
        "metadata": {
            "version": "1.0",
            "description": f"Backup created at {datetime.datetime.now(datetime.timezone.utc).isoformat()}",
        },
    }

    export_list = list(EXPORT_COLLECTIONS)
    if include_all:
        export_list = [
            c
            async for c in db.list_collection_names()
            if c not in BACKUP_EXCLUDE_COLLECTIONS
        ]

    for col_name in export_list:
        try:
            col = db[col_name]
            docs = []
            async for doc in col.find({}):
                doc["_id"] = str(doc["_id"])
                docs.append(doc)
            if docs:
                backup_data["collections"][col_name] = docs
                logger.info(f"Backed up {len(docs)} documents from {col_name}")
        except Exception as e:
            logger.error(f"Failed to backup collection {col_name}: {e}")

    await BACKUP_COL.insert_one(
        {
            "backup_id": backup_id,
            "status": "completed",
            "collections_count": len(backup_data["collections"]),
            "total_documents": sum(len(v) for v in backup_data["collections"].values()),
            "created_at": backup_data["created_at"],
            "created_by": created_by,
        }
    )

    filepath = os.path.join("backups", f"{backup_id}.json")
    os.makedirs("backups", exist_ok=True)

    def serialize(obj: Any) -> str:
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        return str(obj)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, default=serialize, indent=2)

    logger.info(f"Backup {backup_id} saved to {filepath}")
    return backup_data


async def restore_backup(
    backup_data: dict[str, Any], dry_run: bool = True
) -> dict[str, Any]:
    results: dict[str, Any] = {
        "collections_restored": 0,
        "documents_restored": 0,
        "errors": [],
    }

    for col_name, docs in backup_data.get("collections", {}).items():
        if col_name not in IMPORT_COLLECTIONS:
            logger.warning(
                f"Skipping restore of {col_name}: not in allowed import list"
            )
            continue

        try:
            col = db[col_name]
            restored = 0
            for doc in docs:
                if "_id" in doc:
                    doc["_id"] = str(doc["_id"])
                try:
                    if not dry_run:
                        await col.replace_one({"_id": doc["_id"]}, doc, upsert=True)
                    restored += 1
                except Exception as doc_err:
                    results["errors"].append(
                        f"Failed to restore doc in {col_name}: {doc_err}"
                    )

            results["collections_restored"] += 1
            results["documents_restored"] += restored
            logger.info(
                f"Restored {restored} documents to {col_name} (dry_run={dry_run})"
            )
        except Exception as e:
            results["errors"].append(f"Failed to restore collection {col_name}: {e}")

    return results


async def list_backups(limit: int = 10) -> list[dict]:
    cursor = BACKUP_COL.find().sort("created_at", -1).limit(limit)
    return [doc async for doc in cursor]


async def get_backup(backup_id: str) -> dict | None:
    return await BACKUP_COL.find_one({"backup_id": backup_id})


async def delete_backup(backup_id: str) -> bool:
    result = await BACKUP_COL.delete_one({"backup_id": backup_id})
    filepath = os.path.join("backups", f"{backup_id}.json")
    if os.path.exists(filepath):
        os.remove(filepath)
    return result.deleted_count > 0
