import sys
import os
sys.path.insert(0, os.getcwd())

import asyncio
import database

async def main():
    await database.init_db()
    user = await database.users_col.find_one({"_id": 846049642})
    print("User document in DB:")
    print(user)

asyncio.run(main())
