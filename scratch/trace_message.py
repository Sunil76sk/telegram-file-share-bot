import sys
import os
sys.path.insert(0, os.getcwd())

import asyncio

# 1. Create and set the event loop BEFORE importing bot
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# 2. Import bot now so that bot and pyrogram use our event loop
import bot
client = bot.app
client.me = type('User', (), {'id': 999, 'username': 'my_bot', 'is_bot': True})()

from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.types import Message, Chat, User
mock_user = User(id=123456, first_name="TestUser", username="testuser")
mock_chat = Chat(id=123456, type=ChatType.PRIVATE)

import database
# Mock database checks to return False / normal values
async def mock_banned(uid): return False
database.is_banned = mock_banned
async def mock_admin(uid, c): return False
database.is_admin = mock_admin

async def evaluate(filter_obj, client, message):
    res = filter_obj(client, message)
    if asyncio.iscoroutine(res):
        return await res
    return res

async def test_filters():
    # Let the loop run so dispatcher.groups gets populated on this same loop!
    await asyncio.sleep(0.5)
    
    print("Populated dispatcher groups keys:", list(client.dispatcher.groups.keys()))
    
    commands_to_test = [
        "/start",
        "/seller",
        "/my_products",
        "/sell",
        "/marketplace",
        "/createbot",
        "/referral",
        "/store",
        "/premium",
    ]
    
    for cmd in commands_to_test:
        print(f"\n--- Testing command: {cmd} ---")
        message = Message(
            id=1,
            text=cmd,
            from_user=mock_user,
            chat=mock_chat,
            client=client
        )
        
        matched_any = False
        for group, handlers in client.dispatcher.groups.items():
            for handler in handlers:
                from pyrogram.handlers import MessageHandler
                if isinstance(handler, MessageHandler):
                    func = handler.filters
                    if func:
                        try:
                            res = await evaluate(func, client, message)
                            if res:
                                matched_any = True
                                callback_name = handler.callback.__name__
                                module_name = handler.callback.__module__
                                print(f"Matched: {module_name}.{callback_name} (Group: {group})")
                        except Exception as e:
                            print(f"Error checking filter for {handler.callback.__name__}: {e}")
                    else:
                        print(f"No-filter handler: {handler.callback.__name__} (Group: {group})")
        if not matched_any:
            print("No handlers matched this command!")

# Run the test on our loop
loop.run_until_complete(test_filters())
