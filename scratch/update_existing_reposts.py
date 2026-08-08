import asyncio
try:
    asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from database.mongo import db

async def run():
    print("Updating existing active repost jobs in DB to delete_old=True...")
    res = await db.repost_jobs.update_many(
        {"status": "active"},
        {"$set": {"delete_old": True}}
    )
    print(f"Updated {res.modified_count} jobs.")

if __name__ == "__main__":
    asyncio.run(run())
