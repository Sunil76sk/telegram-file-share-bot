import asyncio
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

import os
import sys
sys.path.insert(0, os.getcwd())

os.environ["API_ID"] = "12345"
os.environ["API_HASH"] = "abcdef"
os.environ["BOT_TOKEN"] = "12345:abcdef"
os.environ["MONGO_URI"] = "mongodb://localhost:27017"

from bot import app
import inspect

print("Dispatcher.handler_worker source:")
print(inspect.getsource(app.dispatcher.__class__.handler_worker))
