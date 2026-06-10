import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())

import sys
# Clean up our modules
for mod in list(sys.modules.keys()):
    if mod.startswith('handlers') or mod == 'bot' or mod.startswith('database') or mod.startswith('utils') or mod.startswith('config'):
        del sys.modules[mod]

print('Importing bot...')
import bot

# Check which handler modules are loaded
handler_modules = [m for m in sys.modules.keys() if m.startswith('handlers.')]
print('Handler modules loaded:', sorted(handler_modules))

# Check if bot module has the app
app = bot.app
groups = app.dispatcher.groups
total = 0
for gid, handler_list in groups.items():
    total += len(handler_list)
    print('Group ' + str(gid) + ': ' + str(len(handler_list)) + ' handlers')
print('Total: ' + str(total) + ' handlers registered')
