import inspect
import pyrogram
from pyrogram import Client
from pyrogram.dispatcher import Dispatcher

print("--- Client.add_handler ---")
print(inspect.getsource(Client.add_handler))

print("--- Dispatcher.add_handler ---")
print(inspect.getsource(Dispatcher.add_handler))
