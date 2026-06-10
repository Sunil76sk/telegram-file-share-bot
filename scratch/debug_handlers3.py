import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())

import sys

# Clean up
for mod in list(sys.modules.keys()):
    if mod.startswith('handlers') or mod == 'bot' or mod.startswith('database') or mod.startswith('utils') or mod.startswith('config'):
        del sys.modules[mod]

# Monkey-patch before importing bot
import pyrogram.dispatcher
original_add_handler = pyrogram.dispatcher.Dispatcher.add_handler

def debug_add_handler(self, handler, group=0):
    print('add_handler called: handler=' + str(type(handler).__name__) + ', group=' + str(group))
    return original_add_handler(self, handler, group)

pyrogram.dispatcher.Dispatcher.add_handler = debug_add_handler

print('Importing bot...')
import bot

app = bot.app
groups = app.dispatcher.groups
total = 0
for gid, handler_list in groups.items():
    total += len(handler_list)
    print('Group ' + str(gid) + ': ' + str(len(handler_list)) + ' handlers')
print('Total: ' + str(total) + ' handlers registered')
