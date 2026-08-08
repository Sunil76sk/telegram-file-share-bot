import sys
import os
sys.path.insert(0, os.getcwd())

import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, Chat, User
from pyrogram.handlers import MessageHandler
from pyrogram.enums import ChatType

# Mock Client and Message
class MockUser:
    def __init__(self, id, username=None):
        self.id = id
        self.username = username
        self.first_name = "Test"
        self.last_name = "User"

class MockChat:
    def __init__(self, id):
        self.id = id
        self.type = ChatType.PRIVATE

class MockMessage:
    def __init__(self, text, from_user):
        self.text = text
        self.from_user = from_user
        self.chat = MockChat(from_user.id)
        self.caption = None
        self.document = None
        self.video = None
        self.audio = None
        self.photo = None
        self.voice = None
        self.animation = None

async def main():
    # Wait for pyrogram handler registration tasks to complete
    await asyncio.sleep(1.0)
    
    import bot
    import database
    await database.init_db()
    
    # Mock bot.app.me
    bot_user = MockUser(id=999999, username="my_bot")
    bot.app.me = bot_user
    
    user = MockUser(id=12345, username="testuser")
    
    commands = [
        "/start", "/seller", "/my_products", "/sell", 
        "/marketplace", "/createbot", "/referral", "/store", "/premium"
    ]
    
    print("--- TESTING COMMAND MATCHING ---")
    for cmd in commands:
        msg = MockMessage(text=cmd, from_user=user)
        print(f"\nMessage: {cmd}")
        matched_any = False
        for group, handlers in sorted(bot.app.dispatcher.groups.items()):
            for handler in handlers:
                if not isinstance(handler, MessageHandler):
                    continue
                try:
                    # Pyrogram MessageHandler filter is at handler.filters
                    flt = handler.filters
                    if flt:
                        res = flt(bot.app, msg)
                        if asyncio.iscoroutine(res):
                            res = await res
                        if res:
                            print(f"  [Group {group}] Matches: {handler.callback.__name__}")
                            matched_any = True
                except Exception as e:
                    # Don't print the expected regex filter error to keep output clean
                    if "Regex filter" not in str(e):
                        print(f"  [Group {group}] Error in {handler.callback.__name__}: {e}")
        if not matched_any:
            print("  NO MATCHING HANDLER FOUND!")

asyncio.run(main())
