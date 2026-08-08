import asyncio
import database

async def main():
    await database.init_db()
    channels = await database.channels_col.find().to_list(None)
    print("CHANNELS IN DB:", channels)
    
    post_drafts = await database.post_drafts_col.find().to_list(None)
    print("POST DRAFTS IN DB:", post_drafts)

if __name__ == "__main__":
    asyncio.run(main())
