import sys
import os
import asyncio
import datetime

sys.path.insert(0, os.getcwd())

# Setup mock env
os.environ["API_ID"] = "12345"
os.environ["API_HASH"] = "abcdef"
os.environ["BOT_TOKEN"] = "12345:abcdef"

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

import bot
import database
from pyrogram.types import Message, Chat, User
from pyrogram import Client, ContinuePropagation

class MockMessage(Message):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._replies = []
        self._propagation_stopped = False

    async def reply_text(self, text, *args, **kwargs):
        self._replies.append(text)
        print(f"   [Reply] {text}")
        return self

    def stop_propagation(self):
        self._propagation_stopped = True
        print("   [Stop Propagation] Called")

async def run_trace():
    await database.init_db()
    
    user_id = 999888777
    mock_user = User(id=user_id, first_name="TraceUser", username="traceuser")
    mock_chat = Chat(id=user_id, type=type('ChatType', (), {'value': 'private'})())
    
    # 1. Setup Creator Studio Post Draft in 'awaiting_caption' state
    draft = {
        "draft_id": str(user_id),
        "user_id": user_id,
        "channel_id": -100123456789,
        "media_type": "photo",
        "file_id": "file_123",
        "caption": "Old Caption",
        "state": "awaiting_caption",
        "created_at": datetime.datetime.now(datetime.timezone.utc),
    }
    await database.save_post_draft(user_id, draft)
    print(f"Post draft saved with state: {draft['state']}")

    # 2. Simulate User Sending New Caption Text
    message = MockMessage(id=100, from_user=mock_user, chat=mock_chat, text="This is my brand new caption!", client=bot.app)
    
    print("\nExecuting Group 1 text_message_handler:")
    from handlers.start import text_message_handler
    try:
        await text_message_handler(bot.app, message)
    except Exception as e:
        print(f"Group 1 Error: {e}")
        
    print(f"Group 1 replies sent: {message._replies}")
    print(f"Group 1 propagation stopped? {message._propagation_stopped}")

    # 3. Simulate Group 5 builder_input_handler if group 1 bypassed
    if not message._propagation_stopped:
        print("\nExecuting Group 5 builder_input_handler:")
        from handlers.post_builder import builder_input_handler
        try:
            await builder_input_handler(bot.app, message)
        except ContinuePropagation:
            print("Group 5 ContinuePropagation raised")
        except Exception as e:
            print(f"Group 5 Error: {e}")
            
        print(f"Total replies sent after Group 5: {message._replies}")
        print(f"Propagation stopped now? {message._propagation_stopped}")
    
    # Cleanup
    await database.post_drafts_col.delete_one({"_id": user_id})

if __name__ == "__main__":
    loop.run_until_complete(run_trace())
