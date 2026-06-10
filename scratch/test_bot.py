import urllib.request
import json
from dotenv import load_dotenv
import os

load_dotenv()
bot_token = os.getenv("BOT_TOKEN")

# Get updates to see if the bot is processing messages
url = f"https://api.telegram.org/bot{bot_token}/getUpdates?timeout=5"
try:
    response = urllib.request.urlopen(url, timeout=10)
    data = json.loads(response.read().decode("utf-8"))
    if data.get("ok"):
        updates = data.get("result", [])
        print(f"Total updates: {len(updates)}")
        for update in updates[-3:]:  # Last 3
            msg = update.get("message", {})
            text = msg.get("text", "")
            chat_id = msg.get("chat", {}).get("id", "")
            print(f"Update {update['update_id']}: chat={chat_id}, text='{text}'")
        if not updates:
            print("No updates - send a /start message to the bot first")
    else:
        print(f"API error: {data}")
except Exception as e:
    print(f"Error: {e}")
