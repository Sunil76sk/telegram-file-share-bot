from __future__ import annotations

import asyncio
import logging

# Suppress Pyrogram's "TgCrypto is missing!" warning by setting log level to ERROR before importing
logging.getLogger("pyrogram.crypto.aes").setLevel(logging.ERROR)

from pyrogram import Client
import config
import database
from utils.expiry import deletion_worker, expiry_worker

# Setup Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Reduce Pyrogram log verbosity
logging.getLogger("pyrogram").setLevel(logging.WARNING)

# Initialize Pyrogram Bot Client
app = Client(
    name="file_share_bot",
    api_id=config.API_ID,
    api_hash=str(config.API_HASH),
    bot_token=str(config.BOT_TOKEN),
    workdir=".",  # Keep session files in project root
)

# Manually import all handler modules to register their @app.on_... decorators
import handlers.start  # noqa: E402
import handlers.upload  # noqa: E402
import handlers.callbacks  # noqa: E402
import handlers.edit  # noqa: E402
import handlers.stats  # noqa: E402
import handlers.broadcast  # noqa: E402

# Override start to trigger background workers
original_start = app.start


async def custom_start():
    await original_start()
    await database.init_db()
    await database.clear_active_deliveries()
    await database.batches_col.delete_many({})
    await database.edit_sessions_col.delete_many({})
    logger.info("Cleared stale batch and edit sessions from the database.")
    asyncio.create_task(deletion_worker(app))
    asyncio.create_task(expiry_worker())


app.start = custom_start  # type: ignore[assignment]
