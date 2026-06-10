import urllib.request
import json
from dotenv import load_dotenv
import os

load_dotenv()
bot_token = os.getenv("BOT_TOKEN")

# Get recent updates
url = f"https://api.telegram.org/bot{bot_token}/getUpdates?offset=-10"
response = urllib.request.urlopen(url, timeout=10)
data = json.loads(response.read().decode("utf-8"))

if data.get("ok"):
    updates = data.get("result", [])
    print(f"Recent updates ({len(updates)}):")
    for u in updates:
        if "message" in u:
            msg = u["message"]
            text = msg.get("text", "")[:100]
            chat_id = msg.get("chat", {}).get("id", "")
            print(f'  MSG: chat={chat_id} text="{text}"')
        if "callback_query" in u:
            cb = u["callback_query"]
            print(f'  CB:  user={cb.get("from",{}).get("id","")} data="{cb.get("data","")}"')
else:
    print("Error:", data)
