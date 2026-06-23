"""One-time maintenance: de-duplicate purchases by payment_id and enforce the
unique index.

The audit added a unique+sparse index on ``purchases.payment_id``. On a database
that already contains duplicate payment_ids the index build fails (logged) until
the duplicates are removed. This script reports duplicates and, with --apply,
keeps the earliest purchase per payment_id and removes the rest, then (re)creates
the unique index.

Usage (from the project root, with the venv active):

    python -m maintenance.dedup_purchases            # dry run (report only)
    python -m maintenance.dedup_purchases --apply    # remove duplicates + index
"""

from __future__ import annotations

import asyncio
import sys

# Pyrogram (pulled in via config) needs an event loop set before import.
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from database.mongo import purchases_col  # noqa: E402


async def find_duplicate_payment_ids() -> list[dict]:
    pipeline = [
        {"$match": {"payment_id": {"$nin": [None, ""]}}},
        {
            "$group": {
                "_id": "$payment_id",
                "count": {"$sum": 1},
                "ids": {"$push": "$_id"},
            }
        },
        {"$match": {"count": {"$gt": 1}}},
    ]
    return [doc async for doc in purchases_col.aggregate(pipeline)]


async def run(apply: bool) -> None:
    duplicates = await find_duplicate_payment_ids()
    if not duplicates:
        print("No duplicate payment_ids found.")
    else:
        total_extra = sum(d["count"] - 1 for d in duplicates)
        print(
            f"Found {len(duplicates)} payment_id(s) with duplicates "
            f"({total_extra} redundant document(s)):"
        )
        for d in duplicates:
            print(f"  payment_id={d['_id']!r} count={d['count']}")

        if not apply:
            print(
                "\nDry run. Re-run with --apply to remove duplicates "
                "(keeps the earliest purchase per payment_id)."
            )
            return

        removed = 0
        for d in duplicates:
            # Keep the earliest purchase for this payment_id, remove the rest.
            keep = await purchases_col.find_one(
                {"payment_id": d["_id"]}, sort=[("created_at", 1)]
            )
            if not keep:
                continue
            result = await purchases_col.delete_many(
                {"payment_id": d["_id"], "_id": {"$ne": keep["_id"]}}
            )
            removed += result.deleted_count
        print(f"Removed {removed} redundant purchase document(s).")

    if apply:
        await purchases_col.create_index("payment_id", unique=True, sparse=True)
        print("Ensured unique+sparse index on purchases.payment_id.")


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    loop.run_until_complete(run(apply))
