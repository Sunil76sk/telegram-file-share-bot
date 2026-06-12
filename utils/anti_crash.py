from __future__ import annotations

import asyncio
import datetime
import logging
import sys
import traceback
from typing import Any, Callable, Coroutine

from database.mongo import db
from utils.audit_logger import log_error
from utils.state_machine import cleanup_stale_states

logger = logging.getLogger(__name__)

CRASH_RECOVERY_COL = db["crash_recovery"]
ERROR_RECOVERY_COL = db["error_recovery"]


async def record_crash(error: str, trace: str, handler_name: str | None = None):
    doc = {
        "error": error,
        "traceback": trace,
        "handler": handler_name,
        "crashed_at": datetime.datetime.now(datetime.timezone.utc),
        "recovered": False,
    }
    await CRASH_RECOVERY_COL.insert_one(doc)
    logger.critical(f"Crash recorded: {error}")


async def check_stale_locks(max_age_minutes: int = 30) -> int:
    from utils.locks import user_locks
    freed = 0
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=max_age_minutes)
    cursor = CRASH_RECOVERY_COL.find({"recovered": False, "crashed_at": {"$lt": cutoff}})
    async for doc in cursor:
        await CRASH_RECOVERY_COL.update_one(
            {"_id": doc["_id"]},
            {"$set": {"recovered": True, "recovered_at": datetime.datetime.now(datetime.timezone.utc)}}
        )
        freed += 1

    if freed:
        logger.info(f"Recovered {freed} stale crash records")
    return freed


async def recover_from_crash() -> dict[str, Any]:
    results = {
        "stale_locks_freed": 0,
        "stale_states_cleaned": 0,
        "error_recovery_cleaned": 0,
    }

    results["stale_locks_freed"] = await check_stale_locks()
    results["stale_states_cleaned"] = await cleanup_stale_states()

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
    result = await ERROR_RECOVERY_COL.delete_many({"recorded_at": {"$lt": cutoff}})
    results["error_recovery_cleaned"] = result.deleted_count

    logger.info(f"Crash recovery results: {results}")
    return results


async def safe_execute(
    handler: Callable[..., Coroutine[Any, Any, Any]],
    *args: Any,
    handler_name: str | None = None,
    **kwargs: Any,
) -> Any:
    try:
        return await handler(*args, **kwargs)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Error in handler {handler_name or handler.__name__}: {e}\n{tb}")
        await log_error(e, handler_name or handler.__name__)
        await record_crash(str(e), tb, handler_name or handler.__name__)
        return None


async def get_crash_stats() -> dict[str, int]:
    total = await CRASH_RECOVERY_COL.count_documents({})
    recovered = await CRASH_RECOVERY_COL.count_documents({"recovered": True})
    unrecovered = await CRASH_RECOVERY_COL.count_documents({"recovered": False})
    return {
        "total_crashes": total,
        "recovered": recovered,
        "unrecovered": unrecovered,
    }


async def worker_health_check(
    worker_name: str,
    last_heartbeat: datetime.datetime | None,
    max_gap_seconds: int = 120,
) -> bool:
    if not last_heartbeat:
        return False
    now = datetime.datetime.now(datetime.timezone.utc)
    gap = (now - last_heartbeat).total_seconds()
    if gap > max_gap_seconds:
        logger.warning(f"Worker '{worker_name}' heartbeat stale by {gap:.0f}s")
        return False
    return True
