from __future__ import annotations

import asyncio
import datetime
import logging
import uuid
from typing import Any, Callable, Coroutine

from database.mongo import db

logger = logging.getLogger(__name__)

QUEUE_COL = db["queue_tasks"]
QUEUE_LOG_COL = db["queue_execution_log"]

_task_handlers: dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {}


def register_handler(task_type: str, handler: Callable[..., Coroutine[Any, Any, Any]]):
    _task_handlers[task_type] = handler
    logger.info(f"Queue handler registered: {task_type}")


async def enqueue(
    task_type: str,
    payload: dict[str, Any] | None = None,
    priority: int = 0,
    scheduled_at: datetime.datetime | None = None,
    max_retries: int = 3,
    user_id: int | None = None,
) -> str:
    task_id = str(uuid.uuid4())
    doc = {
        "_id": task_id,
        "task_type": task_type,
        "payload": payload or {},
        "priority": priority,
        "status": "pending",
        "scheduled_at": scheduled_at or datetime.datetime.now(datetime.timezone.utc),
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "started_at": None,
        "completed_at": None,
        "error": None,
        "retries": 0,
        "max_retries": max_retries,
        "user_id": user_id,
    }
    await QUEUE_COL.insert_one(doc)
    logger.info(f"Task enqueued: type={task_type} id={task_id} priority={priority}")
    return task_id


async def dequeue(batch_size: int = 10) -> list[dict]:
    now = datetime.datetime.now(datetime.timezone.utc)
    cursor = QUEUE_COL.find({
        "status": "pending",
        "scheduled_at": {"$lte": now},
    }).sort([("priority", -1), ("created_at", 1)]).limit(batch_size)

    tasks = []
    async for doc in cursor:
        tasks.append(doc)

    return tasks


async def start_task(task_id: str) -> bool:
    result = await QUEUE_COL.update_one(
        {"_id": task_id, "status": "pending"},
        {"$set": {
            "status": "running",
            "started_at": datetime.datetime.now(datetime.timezone.utc),
        }}
    )
    return result.modified_count > 0


async def complete_task(task_id: str, result: Any = None):
    await QUEUE_COL.update_one(
        {"_id": task_id},
        {"$set": {
            "status": "completed",
            "completed_at": datetime.datetime.now(datetime.timezone.utc),
            "result": result,
        }}
    )


async def fail_task(task_id: str, error: str, retry: bool = True):
    doc = await QUEUE_COL.find_one({"_id": task_id})
    if not doc:
        return

    retries = doc.get("retries", 0) + 1
    max_retries = doc.get("max_retries", 3)

    if retry and retries < max_retries:
        next_schedule = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=10 * retries)
        await QUEUE_COL.update_one(
            {"_id": task_id},
            {"$set": {
                "status": "pending",
                "retries": retries,
                "error": error,
                "scheduled_at": next_schedule,
            }}
        )
        logger.info(f"Task {task_id} scheduled for retry {retries}/{max_retries}")
    else:
        await QUEUE_COL.update_one(
            {"_id": task_id},
            {"$set": {
                "status": "failed",
                "completed_at": datetime.datetime.now(datetime.timezone.utc),
                "error": error,
                "retries": retries,
            }}
        )
        logger.error(f"Task {task_id} failed permanently: {error}")


async def process_queue(max_concurrent: int = 5):
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _process(task: dict):
        async with semaphore:
            task_id = task["_id"]
            task_type = task["task_type"]

            if not await start_task(task_id):
                return

            handler = _task_handlers.get(task_type)
            if not handler:
                await fail_task(task_id, f"No handler for task type {task_type}", retry=False)
                return

            try:
                result = await handler(task.get("payload", {}))
                await complete_task(task_id, result)
                logger.info(f"Task {task_id} completed successfully")
            except Exception as e:
                logger.error(f"Task {task_id} failed: {e}")
                await fail_task(task_id, str(e))

    tasks = await dequeue(batch_size=max_concurrent)
    if tasks:
        await asyncio.gather(*[_process(t) for t in tasks])


async def get_queue_stats() -> dict[str, int]:
    pending = await QUEUE_COL.count_documents({"status": "pending"})
    running = await QUEUE_COL.count_documents({"status": "running"})
    completed = await QUEUE_COL.count_documents({"status": "completed"})
    failed = await QUEUE_COL.count_documents({"status": "failed"})
    return {
        "pending": pending,
        "running": running,
        "completed": completed,
        "failed": failed,
        "total": pending + running + completed + failed,
    }


async def cleanup_completed_tasks(hours: int = 24):
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    result = await QUEUE_COL.delete_many({
        "status": {"$in": ["completed", "failed"]},
        "completed_at": {"$lt": cutoff},
    })
    if result.deleted_count:
        logger.info(f"Cleaned {result.deleted_count} completed/failed tasks older than {hours}h")


async def recover_interrupted_tasks():
    result = await QUEUE_COL.update_many(
        {"status": "running"},
        {"$set": {
            "status": "pending",
            "error": "Interrupted - recovered on restart",
            "retries": 0,
        }}
    )
    if result.modified_count:
        logger.info(f"Recovered {result.modified_count} interrupted tasks")
