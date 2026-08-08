import sys
import os
import asyncio
sys.path.insert(0, os.getcwd())
import database

async def main():
    await database.init_db()
    drafts = await database.post_drafts_col.find().to_list(length=10)
    print("DRAFTS:")
    for d in drafts:
        print(d)

if __name__ == "__main__":
    asyncio.run(main())
