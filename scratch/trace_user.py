import sys
import os
sys.path.insert(0, os.getcwd())

import asyncio
from unittest.mock import AsyncMock, MagicMock

async def run_trace():
    import bot
    import database
    await database.init_db()
    
    from handlers.start import start_handler
    from handlers.upload import file_uploader
    from handlers.premium import premium_command_handler
    
    # Let's ensure a file link exists in DB for testing start with payload
    await database.files_col.update_one(
        {"token": "test_token"},
        {
            "$set": {
                "token": "test_token",
                "files": [{"file_id": "file_123", "file_name": "test.txt", "file_size": 100, "media_type": "document"}],
                "owner_id": 846049642, # Admin owner
                "price": 0,
                "is_premium_only": False
            }
        },
        upsert=True
    )

    # Let's define the users to test
    users = [
        {"id": 846049642, "name": "Admin User"},
        {"id": 111111111, "name": "Normal User"}
    ]

    for user_info in users:
        uid = user_info["id"]
        uname = user_info["name"]
        print(f"\n==========================================")
        print(f"TRACING FLOW FOR: {uname} (ID: {uid})")
        print(f"==========================================")

        # 1. Test /start (no payload)
        print("\n--- 1. Testing /start (no payload) ---")
        client = MagicMock()
        client.me = type('User', (), {'id': 999, 'username': 'my_bot', 'is_bot': True})()
        
        msg = MagicMock()
        msg.from_user.id = uid
        msg.from_user.username = f"user_{uid}"
        msg.from_user.first_name = uname
        msg.from_user.last_name = ""
        msg.from_user.mention = f"@{uname}"
        msg.chat.id = uid
        msg.text = "/start"
        
        replies = []
        async def mock_reply_text(text, *args, **kwargs):
            replies.append(text)
            return MagicMock()
        msg.reply_text = mock_reply_text
        msg.stop_propagation = MagicMock()

        try:
            await start_handler(client, msg)
            print(f"Status: Executed successfully")
            print(f"Number of replies: {len(replies)}")
            print(f"Stop propagation called: {msg.stop_propagation.called}")
        except Exception as e:
            print(f"Status: FAILED with exception: {e}")
            import traceback
            traceback.print_exc()

        # 2. Test /start test_token (with payload)
        print("\n--- 2. Testing /start test_token (with payload) ---")
        msg = MagicMock()
        msg.from_user.id = uid
        msg.from_user.username = f"user_{uid}"
        msg.from_user.first_name = uname
        msg.from_user.last_name = ""
        msg.chat.id = uid
        msg.text = "/start test_token"
        
        replies = []
        msg.reply_text = mock_reply_text
        msg.stop_propagation = MagicMock()

        try:
            await start_handler(client, msg)
            print(f"Status: Executed successfully")
            print(f"Number of replies: {len(replies)}")
            if replies:
                print(f"Reply snippet: {repr(replies[0][:100])}")
            print(f"Stop propagation called: {msg.stop_propagation.called}")
        except Exception as e:
            print(f"Status: FAILED with exception: {e}")
            import traceback
            traceback.print_exc()

        # 3. Test File Upload
        print("\n--- 3. Testing File Upload ---")
        msg = MagicMock()
        msg.from_user.id = uid
        msg.from_user.username = f"user_{uid}"
        msg.from_user.first_name = uname
        msg.from_user.last_name = ""
        msg.chat.id = uid
        msg.text = None
        msg.caption = "my caption"
        msg.document = MagicMock()
        msg.document.file_id = "uploaded_file_id"
        msg.document.file_unique_id = f"uniq_{uid}"
        msg.document.file_name = "hello.txt"
        msg.document.file_size = 500
        msg.video = None
        msg.audio = None
        msg.photo = None
        msg.voice = None
        msg.animation = None
        
        replies = []
        msg.reply_text = mock_reply_text
        msg.stop_propagation = MagicMock()

        try:
            await file_uploader(client, msg)
            print(f"Status: Executed successfully")
            print(f"Number of replies: {len(replies)}")
            if replies:
                print(f"Reply snippet: {repr(replies[0][:100])}")
        except Exception as e:
            print(f"Status: FAILED with exception: {e}")
            import traceback
            traceback.print_exc()

        # 4. Test /premium
        print("\n--- 4. Testing /premium ---")
        msg = MagicMock()
        msg.from_user.id = uid
        msg.from_user.username = f"user_{uid}"
        msg.from_user.first_name = uname
        msg.from_user.last_name = ""
        msg.chat.id = uid
        msg.text = "/premium"
        
        replies = []
        msg.reply_text = mock_reply_text
        msg.stop_propagation = MagicMock()

        try:
            await premium_command_handler(client, msg)
            print(f"Status: Executed successfully")
            print(f"Number of replies: {len(replies)}")
            if replies:
                print(f"Reply snippet: {repr(replies[0][:100])}")
        except Exception as e:
            print(f"Status: FAILED with exception: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_trace())
