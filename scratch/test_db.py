import sys
import os
sys.path.insert(0, os.getcwd())

import asyncio
import database

async def main():
    print("Testing DB connection...")
    try:
        await database.init_db()
        print("Database initialized successfully!")
        
        # Test getting all categories
        cats = await database.get_all_categories()
        print(f"Categories found: {cats}")
        
    except Exception as e:
        print(f"DB Error: {e}")

asyncio.run(main())
