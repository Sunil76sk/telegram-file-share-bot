import asyncio
import database
from database.mongo import post_drafts_col, ad_drafts_col, users_col

async def main():
    await database.init_db()
    
    # Inspect user 846049642 (from .env ADMIN_IDS)
    user_id = 846049642
    
    user = await users_col.find_one({"_id": user_id})
    post_draft = await post_drafts_col.find_one({"_id": user_id})
    ad_draft = await ad_drafts_col.find_one({"_id": user_id})
    
    print(f"--- DATABASE STATE FOR USER {user_id} ---")
    print(f"User State: {user.get('state') if user else None}")
    print(f"Post Draft: {post_draft}")
    print(f"Ad Draft: {ad_draft}")

if __name__ == "__main__":
    asyncio.run(main())
