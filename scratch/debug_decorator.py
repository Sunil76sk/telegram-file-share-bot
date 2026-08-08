import sys
import os
sys.path.insert(0, os.getcwd())

import pyrogram
from pyrogram import Client

print("Pyrogram version:", pyrogram.__version__)

# Let's override Client.add_handler to print when it's called
original_add_handler = Client.add_handler
def custom_add_handler(self, handler, group=0):
    print(f"add_handler called: handler={handler}, group={group}")
    return original_add_handler(self, handler, group)
Client.add_handler = custom_add_handler

import bot
print("Finished importing bot. Dispatcher groups keys:", list(bot.app.dispatcher.groups.keys()))
