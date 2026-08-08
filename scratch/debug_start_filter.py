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
from pyrogram.types import Message, Chat, User
mock_user = User(id=123456, first_name="TestUser", username="testuser")
mock_chat = Chat(id=123456, type="private")

import database
# Mock is_banned
async def mock_banned(uid):
    return False
database.is_banned = mock_banned
database.is_admin = lambda uid, c: asyncio.Future() # dummy async function
# Set future result to False
f_admin = asyncio.Future()
f_admin.set_result(False)
database.is_admin = lambda uid, c: f_admin

async def evaluate(filter_obj, client, message):
    res = filter_obj(client, message)
    if asyncio.iscoroutine(res):
        return await res
    return res

async def test_filters():
    await asyncio.sleep(0.5)
    
    # Find start_handler
    start_handler = None
    for group, handlers in client.dispatcher.groups.items():
        for handler in handlers:
            if handler.callback.__name__ == "start_handler":
                start_handler = handler
                break
    
    if start_handler:
        print("Found start_handler. Filters:", start_handler.filters)
        message = Message(
            id=1,
            text="/start",
            from_user=mock_user,
            chat=mock_chat,
            client=client
        )
        
        f_cmd = filters.command("start")
        f_priv = filters.private
        f_not_none = ~filters.create(lambda _, __, m: m.text is None)
        
        print("f_cmd(client, message):", await evaluate(f_cmd, client, message))
        print("f_priv(client, message):", await evaluate(f_priv, client, message))
        print("f_not_none(client, message):", await evaluate(f_not_none, client, message))
        
        # Let's check start_handler.filters directly
        res = await evaluate(start_handler.filters, client, message)
        print("Full filter result:", res)

loop.run_until_complete(test_filters())
