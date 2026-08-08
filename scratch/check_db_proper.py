import sys
import os
import asyncio

sys.path.insert(0, os.getcwd())

import database

async def main():
    await database.init_db()
    channels = await database.channels_col.find().to_list(None)
    print("CHANNELS IN DB:", channels)
    
    post_drafts = await database.post_drafts_col.find().to_list(None)
    print("POST DRAFTS IN DB:", post_drafts)

    users = await database.users_col.find().to_list(None)
    print("USERS IN DB:", users)

    ad_drafts = await database.ad_drafts_col.find().to_list(None)
    print("AD DRAFTS IN DB:", ad_drafts)

if __name__ == "__main__":
    asyncio.run(main())
