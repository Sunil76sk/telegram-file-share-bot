from __future__ import annotations

import datetime
import gc
import logging
import os
import platform
import sys
import time
from typing import Any

from database.mongo import db

logger = logging.getLogger(__name__)

DIAG_COL = db["diagnostics_logs"]


async def run_diagnostics() -> dict[str, Any]:
    results: dict[str, Any] = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "system": _get_system_info(),
        "python": _get_python_info(),
        "database": await _get_db_info(),
        "workers": await _get_worker_info(),
        "performance": _get_performance_metrics(),
        "collections": await _get_collection_stats(),
    }
    await DIAG_COL.insert_one({
        "type": "diagnostic",
        "results": results,
        "timestamp": datetime.datetime.now(datetime.timezone.utc),
    })
    return results


def _get_system_info() -> dict[str, Any]:
    return {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "pid": os.getpid(),
        "memory_usage_mb": _get_memory_usage(),
    }


def _get_python_info() -> dict[str, Any]:
    return {
        "version": sys.version,
        "executable": sys.executable,
        "path": sys.path[:5],
    }


def _get_memory_usage() -> float:
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return round(process.memory_info().rss / (1024 * 1024), 2)
    except ImportError:
        return 0.0


def _get_performance_metrics() -> dict[str, Any]:
    gc.collect()
    return {
        "gc_objects": len(gc.get_objects()),
        "gc_generations": [len(gc.get_objects(i)) for i in range(3)],
    }


async def _get_db_info() -> dict[str, Any]:
    try:
        info = await db.command("dbStats")
        return {
            "collections": info.get("collections", 0),
            "documents": info.get("objects", 0),
            "data_size_mb": round(info.get("dataSize", 0) / (1024 * 1024), 2),
            "index_size_mb": round(info.get("indexSize", 0) / (1024 * 1024), 2),
        }
    except Exception as e:
        return {"error": str(e)}


async def _get_worker_info() -> list[dict]:
    workers = []
    cursor = db["worker_status"].find()
    async for doc in cursor:
        workers.append({
            "name": doc.get("worker_name"),
            "status": doc.get("status", "unknown"),
            "last_heartbeat": doc.get("last_heartbeat"),
            "tasks_processed": doc.get("tasks_processed", 0),
            "errors": doc.get("errors", 0),
        })
    return workers


async def _get_collection_stats() -> list[dict]:
    stats = []
    for col_name in await db.list_collection_names():
        try:
            count = await db[col_name].estimated_document_count()
            stats.append({"name": col_name, "documents": count})
        except Exception:
            stats.append({"name": col_name, "documents": -1})
    return stats


async def get_diagnostics_history(limit: int = 10) -> list[dict]:
    cursor = DIAG_COL.find({"type": "diagnostic"}).sort("timestamp", -1).limit(limit)
    return [doc async for doc in cursor]


async def check_system_health() -> dict[str, Any]:
    issues = []
    warnings = []

    db_info = await _get_db_info()
    if "error" in db_info:
        issues.append(f"Database connection: {db_info['error']}")

    workers = await _get_worker_info()
    for w in workers:
        if w["status"] == "stopped":
            warnings.append(f"Worker '{w['name']}' is stopped")
        last_hb = w.get("last_heartbeat")
        if last_hb:
            if hasattr(last_hb, "tzinfo") and last_hb.tzinfo is None:
                last_hb = last_hb.replace(tzinfo=datetime.timezone.utc)
            if (datetime.datetime.now(datetime.timezone.utc) - last_hb).total_seconds() > 120:
                issues.append(f"Worker '{w['name']}' heartbeat expired")

    memory = _get_memory_usage()
    if memory > 500:
        warnings.append(f"High memory usage: {memory}MB")

    return {
        "healthy": len(issues) == 0,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "issues": issues,
        "warnings": warnings,
        "db_info": db_info,
        "workers": workers,
        "memory_mb": memory,
    }
