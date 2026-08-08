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

# Mock the database calls before importing handlers/bot to prevent any live DB connection attempts
import database
async def mock_async_false(*args, **kwargs):
    return False

database.is_banned = mock_async_false
database.is_admin = mock_async_false

from bot import app
from pyrogram.types import Message, User, Chat
from pyrogram.enums import ChatType

async def test_matching():
    await asyncio.sleep(0.5)
    
    # Mock client.me
    app.me = User(id=1234567, is_self=True, username="file_share_bot")
    
    commands = [
        "/start",
        "/premium",
        "/referral",
        "/marketplace",
        "/seller",
        "/store",
        "/createbot"
    ]
    
    user = User(id=846049642, is_self=False, username="Sunilsk63")
    chat = Chat(id=846049642, type=ChatType.PRIVATE)
    
    print("Evaluating command matching in Group 0:\n")
    
    for cmd in commands:
        msg = Message(id=1, from_user=user, chat=chat, text=cmd)
        print(f"Command: {cmd}")
        matched_any = False
        group_handlers = app.dispatcher.groups.get(0, [])
        for h in group_handlers:
            try:
                matched = await h.check(app, msg)
            except Exception as e:
                matched = f"ERROR: {e}"
            
            if matched and not isinstance(matched, str):
                callback_name = h.callback.__name__ if hasattr(h, 'callback') else 'None'
                print(f"  -> Matches: {callback_name}")
                matched_any = True
                break
            elif isinstance(matched, str):
                callback_name = h.callback.__name__ if hasattr(h, 'callback') else 'None'
                print(f"  -> Error evaluating {callback_name}: {matched}")
        if not matched_any:
            print("  -> Matches: NONE")
        print()

if __name__ == "__main__":
    loop.run_until_complete(test_matching())
