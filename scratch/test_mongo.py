import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os
load_dotenv()
async def check():
    client = AsyncIOMotorClient(os.getenv('MONGO_URI'), serverSelectionTimeoutMS=5000)
    try:
        info = await client.server_info()
        print('MongoDB connected: ' + str(info.get('version', 'unknown')))
    except Exception as e:
        print('MongoDB connection failed: ' + str(e))
    finally:
        client.close()
asyncio.run(check())
