import sys
import os
sys.path.insert(0, os.getcwd())

import asyncio
from pyrogram import Client
import config

async def main():
    app = Client(
        name="test_get_me",
        api_id=config.API_ID,
        api_hash=str(config.API_HASH),
        bot_token=str(config.BOT_TOKEN),
        workdir="scratch",
    )
    await app.start()
    me = await app.get_me()
    print("Bot details:")
    print(f"ID: {me.id}")
    print(f"Name: {me.first_name}")
    print(f"Username: @{me.username}")
    await app.stop()

asyncio.run(main())
