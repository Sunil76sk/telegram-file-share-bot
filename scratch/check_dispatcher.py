import sys
import os
sys.path.insert(0, os.getcwd())

import bot

# Print dispatcher attributes
print("Dispatcher attributes:")
for attr in dir(bot.app.dispatcher):
    val = getattr(bot.app.dispatcher, attr)
    print(f"dispatcher.{attr}: {type(val)}")

print("\nDispatcher groups:")
print(bot.app.dispatcher.groups)
