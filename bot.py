from __future__ import annotations

import asyncio
import logging

# Suppress Pyrogram's "TgCrypto is missing!" warning by setting log level to ERROR before importing
logging.getLogger("pyrogram.crypto.aes").setLevel(logging.ERROR)

from pyrogram import Client  # noqa: E402
import config  # noqa: E402
import database  # noqa: E402
from utils.expiry import deletion_worker, expiry_worker  # noqa: E402

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
import handlers.payment  # noqa: E402
import handlers.premium  # noqa: E402
import handlers.referral  # noqa: E402
import handlers.saas  # noqa: E402, F401
import handlers.shorteners  # noqa: E402
import handlers.funnel  # noqa: E402
import handlers.ads  # noqa: E402
import handlers.analytics  # noqa: E402
import handlers.premium_admin  # noqa: E402
import handlers.marketplace  # noqa: E402, F401


from utils.saas import saas_runner  # noqa: E402
from utils.web_server import start_web_server, stop_web_server  # noqa: E402

# Override start to trigger background workers and sub-bots
original_start = app.start


async def custom_start():
    await original_start()

    # Cache bot username for global fallback
    bot_me = app.me or await app.get_me()
    config.BOT_USERNAME = bot_me.username

    await database.init_db()
    await database.seed_plans()
    await database.seed_marketplace_categories()
    await database.clear_active_deliveries()
    await database.batches_col.delete_many({})
    await database.edit_sessions_col.delete_many({})
    logger.info("Cleared stale batch and edit sessions from the database.")

    # Auto-register shortener from .env config if not already in database
    if config.SHORTENER_API_URL and config.SHORTENER_API_KEY:
        existing = await database.shorteners_col.find_one(
            {"api_url": config.SHORTENER_API_URL.strip(), "bot_id": None}
        )
        if not existing:
            # Derive a friendly name from the URL domain
            from urllib.parse import urlparse

            domain = urlparse(config.SHORTENER_API_URL).netloc
            name = domain.split(".")[0].capitalize() if domain else "ConfigShortener"
            await database.add_shortener(
                name=name,
                api_url=config.SHORTENER_API_URL,
                api_key=config.SHORTENER_API_KEY,
                weight=1,
                geo_countries=["ALL"],
                cpm=3.0,
                bot_id=None,
            )
            logger.info(f"Auto-registered '{name}' shortener from .env config.")
        else:
            logger.info("Shortener from .env config already registered in database.")

    asyncio.create_task(deletion_worker(app))
    asyncio.create_task(expiry_worker())

    # Start all registered SaaS sub-bots in the background
    await saas_runner.start_all()

    # Start the local redirect web server
    start_web_server()


app.start = custom_start  # type: ignore[assignment]

# Override stop to cleanly shutdown all running sub-bots
original_stop = app.stop


async def custom_stop():
    await saas_runner.stop_all()
    stop_web_server()
    await original_stop()


app.stop = custom_stop  # type: ignore[assignment]
