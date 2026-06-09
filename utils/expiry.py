import asyncio
import datetime
import logging
from pyrogram import Client
import database

logger = logging.getLogger(__name__)


async def deletion_worker(client: Client):
    """Background worker that runs periodically to delete expired delivered messages."""
    logger.info("Background deletion worker started.")
    while True:
        try:
            tasks = await database.get_expired_deletions()
            for task in tasks:
                chat_id = task["chat_id"]
                message_ids = task["message_ids"]
                logger.info(
                    f"Attempting to delete {len(message_ids)} expired messages in chat {chat_id}..."
                )
                try:
                    await client.delete_messages(
                        chat_id=chat_id, message_ids=message_ids
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to delete expired messages in chat {chat_id}: {e}"
                    )
                await database.remove_deletion_task(task["_id"])
        except Exception as e:
            logger.error(f"Error in deletion worker: {e}")
        await asyncio.sleep(10)


async def expiry_worker():
    """Background worker that periodically deletes expired links from MongoDB."""
    logger.info("Background expiry cleaner worker started.")
    while True:
        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            result = await database.files_col.delete_many(
                {"expires_at": {"$ne": None, "$lte": now}}
            )
            if result.deleted_count > 0:
                logger.info(
                    f"Cleaned up {result.deleted_count} expired link(s) from database."
                )
        except Exception as e:
            logger.error(f"Error in expiry worker: {e}")
        await asyncio.sleep(60)
