from __future__ import annotations

import datetime
import json
import logging
import traceback
from typing import Any

from database.mongo import db

logger = logging.getLogger(__name__)

ADMIN_LOG_COL = db["admin_audit_log"]
ERROR_LOG_COL = db["error_audit_log"]
EVENT_LOG_COL = db["event_audit_log"]


async def log_admin_action(
    admin_id: int,
    action: str,
    target_type: str | None = None,
    target_id: str | int | None = None,
    details: dict[str, Any] | None = None,
    success: bool = True,
    ip_address: str | None = None,
):
    doc = {
        "admin_id": admin_id,
        "action": action,
        "target_type": target_type,
        "target_id": str(target_id) if target_id else None,
        "details": details or {},
        "success": success,
        "ip_address": ip_address,
        "timestamp": datetime.datetime.now(datetime.timezone.utc),
    }
    await ADMIN_LOG_COL.insert_one(doc)
    logger.info(f"ADMIN_ACTION: admin={admin_id} action={action} target={target_type}:{target_id} success={success}")


async def log_error(
    module: str,
    function: str,
    error: str,
    user_id: int | None = None,
    update_id: str | None = None,
    trace: str | None = None,
    metadata: dict[str, Any] | None = None,
):
    doc = {
        "module": module,
        "function": function,
        "error": error,
        "traceback": trace or traceback.format_exc(),
        "user_id": user_id,
        "update_id": update_id,
        "metadata": metadata or {},
        "timestamp": datetime.datetime.now(datetime.timezone.utc),
    }
    await ERROR_LOG_COL.insert_one(doc)
    logger.error(f"ERROR: module={module} func={function} error={error} user={user_id}")


async def log_event(
    event_type: str,
    user_id: int | None = None,
    data: dict[str, Any] | None = None,
    channel_id: int | str | None = None,
):
    doc = {
        "event_type": event_type,
        "user_id": user_id,
        "channel_id": str(channel_id) if channel_id else None,
        "data": data or {},
        "timestamp": datetime.datetime.now(datetime.timezone.utc),
    }
    await EVENT_LOG_COL.insert_one(doc)
    logger.debug(f"EVENT: type={event_type} user={user_id}")


async def get_admin_logs(
    admin_id: int | None = None,
    action: str | None = None,
    limit: int = 50,
    skip: int = 0,
) -> list[dict]:
    query: dict[str, Any] = {}
    if admin_id:
        query["admin_id"] = admin_id
    if action:
        query["action"] = action
    cursor = ADMIN_LOG_COL.find(query).sort("timestamp", -1).skip(skip).limit(limit)
    return [doc async for doc in cursor]


async def get_error_logs(
    module: str | None = None,
    limit: int = 50,
    skip: int = 0,
) -> list[dict]:
    query: dict[str, Any] = {}
    if module:
        query["module"] = module
    cursor = ERROR_LOG_COL.find(query).sort("timestamp", -1).skip(skip).limit(limit)
    return [doc async for doc in cursor]


async def cleanup_old_logs(days: int = 90):
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    for col in [ADMIN_LOG_COL, ERROR_LOG_COL, EVENT_LOG_COL]:
        result = await col.delete_many({"timestamp": {"$lt": cutoff}})
        if result.deleted_count:
            logger.info(f"Cleaned {result.deleted_count} old logs from {col.name}")
