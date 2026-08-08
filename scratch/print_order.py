import asyncio
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

import os
import sys
sys.path.insert(0, os.getcwd())

os.environ["API_ID"] = "12345"
os.environ["API_HASH"] = "abcdef"
os.environ["BOT_TOKEN"] = "12345:abcdef"
os.environ["MONGO_URI"] = "mongodb://localhost:27017"

from bot import app

async def run_print():
    await asyncio.sleep(0.5)
    print("Callbacks in Group 0 in order:")
    for idx, h in enumerate(app.dispatcher.groups.get(0, [])):
        print(f" {idx+1}. {h.callback.__name__} (type: {type(h).__name__})")

if __name__ == "__main__":
    loop.run_until_complete(run_print())
