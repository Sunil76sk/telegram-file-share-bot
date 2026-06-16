import asyncio
import logging

# Create and set event loop before importing pyrogram (required for Python 3.12+ / 3.14)
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from bot import app  # noqa: E402

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Starting Telegram File Share Bot...")
    app.run()
