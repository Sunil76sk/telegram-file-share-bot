import sys
import os
sys.path.insert(0, os.getcwd())

import asyncio
import database

async def main():
    try:
        await database.init_db()
        print("Database connected.")
        
        # Check categories
        cats = await database.get_all_categories()
        print(f"Number of categories: {len(cats)}")
        for c in cats:
            name_clean = c['name'].encode('ascii', 'ignore').decode('ascii')
            print(f" - Category: {name_clean} (slug: {c['slug']})")
            
        # Check active sub-bots
        sub_bots = await database.get_all_active_sub_bots()
        print(f"Number of active sub-bots: {len(sub_bots)}")
        for sb in sub_bots:
            print(f" - Sub-bot: @{sb['username']}")
            
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(main())
