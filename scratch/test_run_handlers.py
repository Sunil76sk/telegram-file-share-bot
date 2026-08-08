import sys
import os
sys.path.insert(0, os.getcwd())

import asyncio

# 1. Create and set the event loop BEFORE importing bot
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# 2. Import bot
import bot
client = bot.app

# Let's mock a user and chat
from pyrogram.types import Message, Chat, User
mock_user = User(id=123456, first_name="TestUser", username="testuser")
mock_chat = Chat(id=123456, type=type('ChatType', (), {'value': 'private'})()) # mock ChatType

# We need to initialize database
import database

async def test_run():
    await database.init_db()
    
    # Let's mock the reply_text method of message to print the response
    class MockMessage(Message):
        async def reply_text(self, text, *args, **kwargs):
            print(f"REPLY TEXT: {text}")
            return self
        async def reply_photo(self, photo, caption, *args, **kwargs):
            print(f"REPLY PHOTO with caption: {caption}")
            return self

    message = MockMessage(
        id=1,
        from_user=mock_user,
        chat=mock_chat,
        client=client
    )
    
    # Test each command handler
    print("\n--- Testing /premium handler ---")
    from handlers.premium import premium_command_handler
    try:
        await premium_command_handler(client, message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        
    print("\n--- Testing /store handler ---")
    from handlers.premium import store_command_handler
    try:
        await store_command_handler(client, message)
    except Exception as e:
        import traceback
        traceback.print_exc()

    print("\n--- Testing /referral handler ---")
    from handlers.referral import referral_command_handler
    try:
        await referral_command_handler(client, message)
    except Exception as e:
        import traceback
        traceback.print_exc()

    print("\n--- Testing /createbot handler ---")
    from handlers.saas import saas_command_handler
    try:
        await saas_command_handler(client, message)
    except Exception as e:
        import traceback
        traceback.print_exc()

    print("\n--- Testing /marketplace handler ---")
    from handlers.marketplace import marketplace_command_handler
    try:
        await marketplace_command_handler(client, message)
    except Exception as e:
        import traceback
        traceback.print_exc()

    print("\n--- Testing /sell handler ---")
    from handlers.marketplace import add_product_command_handler
    try:
        await add_product_command_handler(client, message)
    except Exception as e:
        import traceback
        traceback.print_exc()

    print("\n--- Testing /my_products handler ---")
    from handlers.marketplace import my_products_command_handler
    try:
        await my_products_command_handler(client, message)
    except Exception as e:
        import traceback
        traceback.print_exc()

    print("\n--- Testing /seller handler ---")
    from handlers.marketplace import seller_dashboard_command_handler
    try:
        await seller_dashboard_command_handler(client, message)
    except Exception as e:
        import traceback
        traceback.print_exc()

# Run the test
loop.run_until_complete(test_run())
