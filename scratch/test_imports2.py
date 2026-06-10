import asyncio

# Create and set event loop BEFORE importing anything
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# Now import bot (this is what app.py does)
import sys
for mod in list(sys.modules.keys()):
    if any(mod.startswith(p) for p in ['handlers', 'bot', 'database', 'utils', 'config']):
        del sys.modules[mod]

# Import the bot module - this is what app.py does
from bot import app

# Run the loop briefly to process pending call_soon callbacks (handler registration)
loop.call_soon(loop.stop)
loop.run_forever()

# Now check handlers
groups = app.dispatcher.groups
total = sum(len(h) for h in groups.values())
print(f"Total handlers registered: {total}")

# List all handlers in group 0
if 0 in groups:
    for i, h in enumerate(groups[0]):
        filt = getattr(h, 'filters', None)
        print(f"  Handler {i}: {type(h).__name__} filter={filt}")
else:
    for gid, handlers in groups.items():
        print(f"Group {gid}: {len(handlers)} handlers")
