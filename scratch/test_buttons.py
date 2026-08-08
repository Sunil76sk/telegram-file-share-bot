from pyrogram.types import InlineKeyboardButton
try:
    btn = InlineKeyboardButton("Test", url="")
    print("Created button successfully:", btn)
except Exception as e:
    print("Failed to create button:", e)
