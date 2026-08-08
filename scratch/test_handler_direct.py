import sys
import os
sys.path.insert(0, os.getcwd())

import asyncio
from unittest.mock import AsyncMock, MagicMock

async def main():
    import bot
    import database
    await database.init_db()
    
    # Import handlers
    from handlers.premium import premium_command_handler
    
    # Mock Client
    client = MagicMock()
    
    # Mock Message
    message = MagicMock()
    message.from_user.id = 846049642  # Use the admin ID from your .env
    message.from_user.mention = "@admin"
    
    # Track replies
    replies = []
    async def mock_reply_text(text, *args, **kwargs):
        replies.append(text)
        print(f"Reply received: {text}")
        return MagicMock()
        
    message.reply_text = mock_reply_text
    
    print("Calling premium_command_handler...")
    await premium_command_handler(client, message)
    print("Done. Replies:", replies)

asyncio.run(main())
