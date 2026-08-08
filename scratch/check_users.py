import sys
import os
sys.path.insert(0, os.getcwd())

import asyncio

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

import database

async def check_users():
    await database.init_db()
    
    users = await database.users_col.find({}).to_list(length=100)
    print(f"Total users: {len(users)}")
    for user in users:
        print(f"User ID: {user.get('_id')}")
        print(f"  Username: {user.get('username')}")
        print(f"  First Name: {user.get('first_name')}")
        print(f"  Is Banned: {user.get('is_banned')}")
        print(f"  Is Admin: {user.get('is_admin')}")
        print(f"  Premium: {user.get('is_premium')} (expires: {user.get('premium_expiry')})")
        print("-" * 20)

loop.run_until_complete(check_users())
