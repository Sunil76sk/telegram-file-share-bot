import sys
import os
import asyncio
import datetime
import time

sys.path.insert(0, os.getcwd())

# Setup mock env
os.environ["API_ID"] = "12345"
os.environ["API_HASH"] = "abcdef"
os.environ["BOT_TOKEN"] = "12345:abcdef"

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import bot
import database
from pyrogram.types import Message, Chat, User
from pyrogram import Client

# Mock replies list with timestamps
replies_timeline = []

class MockMessage(Message):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._propagation_stopped = False

    async def reply_text(self, text, *args, **kwargs):
        t = time.time()
        replies_timeline.append({
            "timestamp_ms": int(t * 1000),
            "text": text[:40],
            "handler": sys._getframe(1).f_code.co_name
        })
        print(f"   [Reply T={int(t*1000)}ms] {sys._getframe(1).f_code.co_name} sent: {text[:40]}...")
        return self

    def stop_propagation(self):
        self._propagation_stopped = True
        print(f"   [Stop Propagation T={int(time.time()*1000)}ms] Called by {sys._getframe(1).f_code.co_name}")
        super().stop_propagation()

async def run_simulation():
    await database.init_db()
    user_id = 7777777
    mock_user = User(id=user_id, first_name="SimUser", username="simuser")
    mock_chat = Chat(id=user_id, type=type('ChatType', (), {'value': 'private'})())

    # Ensure a clean database state
    await database.post_drafts_col.delete_one({"_id": user_id})

    # Step 1: Simulate the "Edit Caption" button click
    print("\n[T0] Clicking 'Edit Caption' button...")
    draft = {
        "draft_id": str(user_id),
        "user_id": user_id,
        "channel_id": -100123,
        "media_type": "photo",
        "file_id": "file_123",
        "caption": "Old Caption",
        "state": "awaiting_caption",
        "created_at": datetime.datetime.now(datetime.timezone.utc),
    }
    await database.save_post_draft(user_id, draft)
    print("Draft state set to 'awaiting_caption'")

    # Step 2: User sends caption text (Single Message)
    msg_id = 9991
    user_msg = MockMessage(
        id=msg_id,
        from_user=mock_user,
        chat=mock_chat,
        text="New Caption Text!",
        client=bot.app
    )

    print(f"\n[T1] Dispatcher received incoming message ID {msg_id}...")
    
    # We call dispatcher's handler_worker directly to simulate Pyrogram dispatcher
    try:
        await bot.app.dispatcher.handler_worker(user_msg)
    except Exception as e:
        print(f"Dispatcher error: {e}")

    print("\n--- TIMELINE SUMMARY ---")
    for r in replies_timeline:
        print(f"Time: {r['timestamp_ms']}ms | Outgoing from: {r['handler']} | Content: {r['text']}")

    # Cleanup
    await database.post_drafts_col.delete_one({"_id": user_id})

if __name__ == "__main__":
    loop.run_until_complete(run_simulation())
