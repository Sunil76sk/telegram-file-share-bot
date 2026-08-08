import asyncio
import os
import sys
sys.path.insert(0, os.getcwd())

os.environ["API_ID"] = "12345"
os.environ["API_HASH"] = "abcdef"
os.environ["BOT_TOKEN"] = "12345:abcdef"
os.environ["MONGO_URI"] = "mongodb://localhost:27017"

# Setup event loop
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

import database
import config
from utils.helpers import get_share_link
from pyrogram import Client
from pyrogram.types import User

# Mock database calls
async def mock_get_file_link(token):
    return {"token": token, "bot_id": None}

async def mock_get_shorteners(*args, **kwargs):
    return []  # No DB shorteners, force it to fall back to .env configuration

database.get_file_link = mock_get_file_link
database.get_shorteners = mock_get_shorteners

# Mock network call inside get_shortened_url
import urllib.request
from io import BytesIO

class MockHTTPResponse:
    def __init__(self, body, headers):
        self.body = body
        self.headers = headers
    def read(self, *args, **kwargs):
        return self.body
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

def mock_urlopen(req, *args, **kwargs):
    print(f"Mock urlopen called for URL: {req.full_url}")
    # Return mock JSON response containing a shortened url
    response_body = b'{"status":"success","shortenedUrl":"https://teraboxlinks.com/abc123"}'
    return MockHTTPResponse(response_body, {"Content-Type": "application/json"})

urllib.request.urlopen = mock_urlopen

async def test_main():
    client = Client("test_client")
    client.me = User(id=1234567, is_self=True, username="file_share_bot")
    
    # Configure shortener in config (simulating .env)
    config.SHORTENER_API_URL = "https://teraboxlinks.com/api"
    config.SHORTENER_API_KEY = "dummykey"
    
    token = "xyz789"
    print("Generating share link...")
    link = await get_share_link(client, token)
    print(f"Resulting Link: {link}")
    
    assert link == "https://teraboxlinks.com/abc123", f"Expected shortened link, got {link}"
    print("SUCCESS: Link was successfully shortened!")

if __name__ == "__main__":
    loop.run_until_complete(test_main())
