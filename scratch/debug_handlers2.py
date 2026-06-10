import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())

import sys

# Clean up modules
for mod in list(sys.modules.keys()):
    if mod.startswith('handlers') or mod == 'bot' or mod.startswith('database') or mod.startswith('utils') or mod.startswith('config'):
        del sys.modules[mod]

# Import bot module, but monkey-patch first
import types

# We need to intercept the import of handlers to debug
# But first let's just import and check the dispatcher
import bot

app = bot.app

# Check dispatcher structure
print('Dispatcher type:', type(app.dispatcher))
print('Dispatcher groups:', app.dispatcher.groups)
print('Groups type:', type(app.dispatcher.groups))

# Check if groups have any handlers
for gid, handlers in app.dispatcher.groups.items():
    print('Group ' + str(gid) + ' type:', type(handlers))
    print('Group ' + str(gid) + ' contents:', handlers)

# Check on_message method
print('on_message type:', type(app.on_message))

# Check if there's any registered handlers in the client
print('Handler methods on app:')
for attr in dir(app):
    if 'handler' in attr.lower() or 'handler' in attr.lower():
        print(' - ' + attr)
