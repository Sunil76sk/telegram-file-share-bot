import sys
import os
sys.path.insert(0, os.getcwd())

import asyncio
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from bot import app

print("Groups keys:", list(app.dispatcher.groups.keys()))
for group, handlers in app.dispatcher.groups.items():
    print(f"Group {group}: {len(handlers)} handlers")
