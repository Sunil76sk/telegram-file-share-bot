import sys
import os
sys.path.insert(0, os.getcwd())

import asyncio
import bot
from pyrogram.handlers import MessageHandler, CallbackQueryHandler

async def main():
    # Wait for pyrogram to run its registration tasks in the event loop
    await asyncio.sleep(1.0)
    
    print("--- REGISTERED HANDLERS ---")
    for group, handlers in sorted(bot.app.dispatcher.groups.items()):
        print(f"\nGroup {group}:")
        for handler in handlers:
            if isinstance(handler, MessageHandler):
                print(f"  MessageHandler: callback={handler.callback.__name__}, filters={handler.filters}")
            elif isinstance(handler, CallbackQueryHandler):
                print(f"  CallbackQueryHandler: callback={handler.callback.__name__}, filters={handler.filters}")
            else:
                print(f"  Handler: {handler}")

asyncio.run(main())
