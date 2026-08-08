import sys
import os
sys.path.insert(0, os.getcwd())

import bot

# Print all attributes of bot.app related to handlers
for attr in dir(bot.app):
    if "handler" in attr.lower():
        val = getattr(bot.app, attr)
        print(f"bot.app.{attr}: {val} (type: {type(val)})")

# Let's inspect bot.app.dispatcher
print("\nDispatcher handlers:")
print(bot.app.dispatcher.handlers)
print("\nDispatcher groups:")
print(bot.app.dispatcher.groups)
