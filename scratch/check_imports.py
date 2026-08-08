import sys
import os
sys.path.insert(0, os.getcwd())

print("Python version:", sys.version)
print("Current directory:", os.getcwd())

try:
    import bot
    print("Imported bot successfully")
    print("Bot app name:", bot.app.name)
    print("Dispatcher groups:", list(bot.app.dispatcher.groups.keys()))
except Exception as e:
    import traceback
    traceback.print_exc()
2