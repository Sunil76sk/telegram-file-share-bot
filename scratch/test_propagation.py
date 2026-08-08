import asyncio
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from pyrogram import Client, filters
from pyrogram.types import Message, User
from pyrogram.handlers import MessageHandler
import os

os.environ["API_ID"] = "12345"
os.environ["API_HASH"] = "abcdef"
os.environ["BOT_TOKEN"] = "12345:abcdef"

app = Client("test_client", workdir=".")

@app.on_message(group=-100)
async def g_neg_100(client, message):
    print("Group -100 executed")

@app.on_message(group=0)
async def g_0(client, message):
    print("Group 0 executed")

async def run_test():
    # Wait for async registration
    await asyncio.sleep(0.1)
    
    # Simulate an incoming message update
    user = User(id=123, is_self=False)
    message = Message(id=1, from_user=user, text="/start")
    
    print("Triggering message...")
    # Directly call dispatcher's update handling
    # We can inspect dispatcher updates
    await app.dispatcher.handler_worker(message)

if __name__ == "__main__":
    loop.run_until_complete(run_test())
