from __future__ import annotations

import asyncio
import datetime
import logging
import signal
import sys
from typing import Any, Callable, Coroutine

from database.mongo import db

logger = logging.getLogger(__name__)

WORKER_COL = db["worker_status"]
WORKER_HEARTBEAT_COL = db["worker_heartbeats"]

_registered_workers: dict[str, dict[str, Any]] = {}
_running_workers: dict[str, asyncio.Task] = {}
_shutdown_event = asyncio.Event()


def register_worker(
    name: str,
    handler: Callable[..., Coroutine[Any, Any, None]],
    interval: int = 30,
    description: str = "",
):
    _registered_workers[name] = {
        "name": name,
        "handler": handler,
        "interval": interval,
        "description": description,
    }
    logger.info(f"Worker registered: {name} (interval={interval}s)")


async def _worker_loop(name: str, handler: Callable, interval: int):
    while not _shutdown_event.is_set():
        try:
            await WORKER_COL.update_one(
                {"worker_name": name},
                {
                    "$set": {
                        "status": "running",
                        "last_heartbeat": datetime.datetime.now(datetime.timezone.utc),
                        "last_run": datetime.datetime.now(datetime.timezone.utc),
                    }
                },
                upsert=True,
            )

            await WORKER_HEARTBEAT_COL.insert_one(
                {
                    "worker_name": name,
                    "timestamp": datetime.datetime.now(datetime.timezone.utc),
                }
            )

            await handler()

            await WORKER_COL.update_one(
                {"worker_name": name},
                {"$inc": {"tasks_processed": 1}},
            )
        except asyncio.CancelledError:
            logger.info(f"Worker '{name}' cancelled")
            break
        except Exception as e:
            logger.error(f"Worker '{name}' error: {e}")
            await WORKER_COL.update_one(
                {"worker_name": name},
                {"$inc": {"errors": 1}},
            )

        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            break


async def start_workers():
    for name, config in _registered_workers.items():
        if name not in _running_workers or _running_workers[name].done():
            task = asyncio.create_task(
                _worker_loop(name, config["handler"], config["interval"]),
                name=f"worker_{name}",
            )
            _running_workers[name] = task
            logger.info(f"Worker '{name}' started")


async def stop_workers():
    _shutdown_event.set()
    for name, task in _running_workers.items():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    for name in _registered_workers:
        await WORKER_COL.update_one(
            {"worker_name": name},
            {"$set": {"status": "stopped"}},
        )
    logger.info("All workers stopped")


async def get_worker_status(name: str | None = None) -> list[dict]:
    query = {}
    if name:
        query["worker_name"] = name
    cursor = WORKER_COL.find(query).sort("worker_name", 1)
    return [doc async for doc in cursor]


async def recover_workers():
    """Recover workers that were running before a restart."""
    cursor = WORKER_COL.find({"status": "running"})
    async for doc in cursor:
        name = doc.get("worker_name")
        if name in _registered_workers:
            logger.info(f"Recovering worker '{name}' after restart")
            await WORKER_COL.update_one(
                {"worker_name": name},
                {"$set": {"status": "recovered", "errors": 0}},
            )


def setup_signal_handlers():
    def _signal_handler():
        logger.info("Shutdown signal received")
        asyncio.create_task(stop_workers())

    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _signal_handler)
            except NotImplementedError:
                pass
    except RuntimeError:
        pass
