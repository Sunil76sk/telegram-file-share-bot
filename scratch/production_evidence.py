import asyncio
import sys
import os

sys.path.insert(0, os.getcwd())

# Setup mock environmental variables
os.environ["API_ID"] = "12345"
os.environ["API_HASH"] = "abcdef"
os.environ["BOT_TOKEN"] = "12345:abcdef"

import database
import bot
from database.mongo import db

async def dump_evidence():
    await database.init_db()
    
    print("\n=== DATABASE EVIDENCE ===")
    collections = await db.list_collection_names()
    print(f"Total Collections: {len(collections)}")
    for col_name in sorted(collections):
        col = db[col_name]
        indexes = await col.index_information()
        idx_strs = []
        for name, info in indexes.items():
            keys = ", ".join([f"{k}:{v}" for k, v in info['key']])
            idx_strs.append(f"{name}({keys})")
        print(f"Collection: {col_name} -> Indexes: {', '.join(idx_strs)}")

    print("\n=== WORKER EVIDENCE ===")
    from utils.worker_framework import _registered_workers
    print(f"Registered Background Workers: {len(_registered_workers)}")
    for name, worker in _registered_workers.items():
        print(f"Worker: {name} -> Interval: {worker['interval']}s, Description: {worker['description']}")

    print("\n=== DISPATCHER REGISTRY ===")
    cmd_handlers = []
    cb_handlers = []
    
    for group, handlers in bot.app.dispatcher.groups.items():
        for h in handlers:
            h_type = h.__class__.__name__
            callback_name = h.callback.__name__ if hasattr(h, 'callback') else 'None'
            
            from pyrogram.filters import Filter
            flt = getattr(h, "filters", None)
            flt_str = str(flt) if flt else ""
            
            if "Filter.command" in flt_str or "command" in callback_name or "cmd" in callback_name:
                cmd_handlers.append(f"Group {group} -> {callback_name} (Filter: {flt_str})")
            elif "CallbackQueryHandler" in h_type or "callback" in callback_name:
                cb_handlers.append(f"Group {group} -> {callback_name} (Filter: {flt_str})")

    print("\nCommands Registered:")
    for cmd in cmd_handlers:
        print(f"  {cmd}")

    print("\nCallbacks Registered:")
    for cb in cb_handlers:
        print(f"  {cb}")

if __name__ == "__main__":
    asyncio.run(dump_evidence())
