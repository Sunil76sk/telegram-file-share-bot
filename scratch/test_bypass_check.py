import asyncio
import database
import datetime

async def test_bypass():
    await database.init_db()
    user_id = 12345
    
    # Simulate saving post draft
    draft = {
        "draft_id": str(user_id),
        "user_id": user_id,
        "state": "awaiting_caption",
        "created_at": datetime.datetime.now(datetime.timezone.utc),
    }
    await database.save_post_draft(user_id, draft)
    
    # Read post draft
    retrieved = await database.get_post_draft(user_id)
    print("Retrieved draft:", retrieved)
    print("Retrieved type:", type(retrieved))
    if retrieved:
        print("Retrieved state:", retrieved.get("state"))
        print("State type:", type(retrieved.get("state")))
        print("Is state in list?", retrieved.get("state") in [
            "awaiting_media", "awaiting_caption", "awaiting_buttons", "awaiting_reactions",
            "awaiting_schedule_time", "awaiting_repost_interval", "awaiting_delete_gap"
        ])

if __name__ == "__main__":
    asyncio.run(test_bypass())
