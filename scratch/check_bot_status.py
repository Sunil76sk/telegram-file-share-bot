import asyncio
import os
import urllib.request
import json
from dotenv import load_dotenv

load_dotenv()

async def main():
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        print("Error: BOT_TOKEN not found in .env")
        return

    url = f"https://api.telegram.org/bot{bot_token}/getMe"
    try:
        response = urllib.request.urlopen(url, timeout=10)
        data = json.loads(response.read().decode("utf-8"))
        if data.get("ok"):
            result = data["result"]
            print(f"Bot Username: @{result.get('username')}")
            print(f"Bot Name: {result.get('first_name')}")
            print(f"Bot ID: {result.get('id')}")
        else:
            print(f"Failed to get bot info: {data}")
    except Exception as e:
        print(f"Error calling Telegram API: {e}")

if __name__ == "__main__":
    asyncio.run(main())
