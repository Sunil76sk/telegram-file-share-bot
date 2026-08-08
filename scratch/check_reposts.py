import asyncio
try:
    asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from database.mongo import db

async def check():
    print("Checking active repost jobs in DB...")
    cursor = db.repost_jobs.find({})
    jobs = [doc async for doc in cursor]
    if not jobs:
        print("No repost jobs found.")
        return
    for job in jobs:
        print("---")
        print(f"ID: {job.get('_id')}")
        print(f"User: {job.get('user_id')}")
        print(f"Channel: {job.get('channel_id')}")
        print(f"Status: {job.get('status')}")
        print(f"Delete Old: {job.get('delete_old')}")
        print(f"Last Post ID: {job.get('last_post_id')}")
        print(f"Last Posted At: {job.get('last_posted_at')}")
        print(f"Next Post At: {job.get('next_post_at')}")

if __name__ == "__main__":
    asyncio.run(check())
