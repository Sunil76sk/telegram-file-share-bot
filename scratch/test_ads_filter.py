import asyncio
import os
import sys
sys.path.insert(0, os.getcwd())

os.environ["API_ID"] = "12345"
os.environ["API_HASH"] = "abcdef"
os.environ["BOT_TOKEN"] = "12345:abcdef"
os.environ["MONGO_URI"] = "mongodb://localhost:27017"

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from pyrogram import filters
from pyrogram.types import Message, User, Chat
from pyrogram.enums import ChatType
from utils.helpers import admin_filter

# Mock database.is_admin
import database
async def mock_is_admin(*args, **kwargs):
    return True  # Mock user as admin
database.is_admin = mock_is_admin

async def test_filter():
    # Construct target filter (same as ads.py)
    target_filter = filters.text & filters.private & admin_filter & ~filters.regex(r"^/")
    
    # Mock message for /premium
    user = User(id=846049642, is_self=False, username="Sunilsk63")
    chat = Chat(id=846049642, type=ChatType.PRIVATE)
    
    msg_cmd = Message(id=1, from_user=user, chat=chat, text="/premium")
    msg_text = Message(id=2, from_user=user, chat=chat, text="Ad Title | Ad Desc | 5")
    
    client = None
    
    res_cmd = await target_filter(client, msg_cmd)
    res_text = await target_filter(client, msg_text)
    
    print(f"Filter matching for '/premium': {res_cmd}")
    print(f"Filter matching for plain text: {res_text}")
    
    assert res_cmd is False, "Expected /premium to NOT match"
    assert res_text is True, "Expected plain text to match"
    print("SUCCESS: Exclude commands filter logic works perfectly!")

if __name__ == "__main__":
    loop.run_until_complete(test_filter())
