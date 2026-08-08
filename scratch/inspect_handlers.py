import sys
import os
sys.path.insert(0, os.getcwd())

import bot
from pyrogram.handlers import MessageHandler, CallbackQueryHandler

print("--- REGISTERED HANDLERS ---")
for group, handlers in bot.app.dispatcher.groups.items():
    print(f"\nGroup {group}:")
    for handler in handlers:
        if isinstance(handler, MessageHandler):
            print(f"  MessageHandler: callback={handler.callback.__name__}, filters={handler.filters}")
        elif isinstance(handler, CallbackQueryHandler):
            print(f"  CallbackQueryHandler: callback={handler.callback.__name__}, filters={handler.filters}")
        else:
            print(f"  Handler: {handler}")
