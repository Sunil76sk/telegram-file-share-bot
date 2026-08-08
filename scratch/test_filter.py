import asyncio
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from pyrogram import Client, filters
from pyrogram.types import Message, User
import sys

# Mock configuration and database to avoid real DB connections during import
import os
os.environ["API_ID"] = "12345"
os.environ["API_HASH"] = "abcdef"
os.environ["BOT_TOKEN"] = "12345:abcdef"
os.environ["MONGO_URI"] = "mongodb://localhost:27017"

async def mock_banned_check(_, __, message):
    print("banned_check called!")
    return False

# Create custom filter
banned_filter = filters.create(mock_banned_check)

# Negate it
negated_filter = ~banned_filter

async def run_test():
    # Create a dummy message
    user = User(id=123, is_self=False)
    message = Message(id=1, from_user=user, text="/marketplace")
    client = None

    print("Testing positive filter...")
    try:
        res = await banned_filter(client, message)
        print("Positive filter returned:", res)
    except Exception as e:
        print("Positive filter failed:", e)

    print("\nTesting negated filter...")
    try:
        res = await negated_filter(client, message)
        print("Negated filter returned:", res)
    except Exception as e:
        print("Negated filter failed:", e)

if __name__ == "__main__":
    loop.run_until_complete(run_test())
