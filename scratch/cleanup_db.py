import asyncio
import database
from database.mongo import ad_drafts_col, post_drafts_col

async def main():
    await database.init_db()
    user_id = 846049642
    
    # Clear ad draft
    res_ad = await ad_drafts_col.delete_one({"_id": user_id})
    print(f"Cleared ad draft for {user_id}: {res_ad.deleted_count}")
    
    # Clear post draft if any
    res_post = await post_drafts_col.delete_one({"_id": user_id})
    print(f"Cleared post draft for {user_id}: {res_post.deleted_count}")

if __name__ == "__main__":
    asyncio.run(main())
