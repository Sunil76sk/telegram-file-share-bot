import asyncio
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from pyrogram import filters
from pyrogram.types import Message, User

# Test filters.command matching
cmd_premium = filters.command(["premium", "subscribe"])
cmd_start = filters.command("start")

# Create a mock message object (we can't fully instantiate Message without a client)
# But we can check the filter's internal logic

print("Premium command filter type:", type(cmd_premium))
print("Start command filter type:", type(cmd_start))

# Check if the filters have the right structure
print("Premium filter named filters:", [f for f in getattr(cmd_premium, 'filters', [])] if hasattr(cmd_premium, 'filters') else "N/A")

# Let's check the actual pyrogram source for filters.command
import inspect
try:
    src = inspect.getsource(filters.command)
    print("\n--- filters.command source (first 30 lines) ---")
    for line in src.split('\n')[:30]:
        print(line)
except:
    print("Could not get source")
