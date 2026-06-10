import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())

import sys

# Clean up our modules
for mod in list(sys.modules.keys()):
    if any(mod.startswith(p) for p in ['handlers', 'bot', 'database', 'utils', 'config']):
        del sys.modules[mod]

# Import bot to trigger all handler imports
import bot

# Now try to send a test message through the dispatcher
# Check if all handlers have filters that match
from bot import app

# Get all registered handlers
groups = app.dispatcher.groups
print(f"Total groups: {len(groups)}")
for gid, handlers in groups.items():
    for i, h in enumerate(handlers):
        filt = h.filters
        print(f"Group {gid}, Handler {i}: type={type(h).__name__}, filter={filt}")

# Now let's try some specific command tests
print("\n--- Testing command matching ---")

# Simulate a /premium command
from pyrogram import filters
cmd_premium = filters.command(["premium", "subscribe"])
print(f"/premium filter: {cmd_premium}")

cmd_start = filters.command("start")
print(f"/start filter: {cmd_start}")

print("\nBot is fully initialized and handlers are registered.")
print(f"Total handler count: {sum(len(h) for h in groups.values())}")
