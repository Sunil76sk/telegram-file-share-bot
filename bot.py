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

import os  # noqa: E402
import socket  # noqa: E402
import datetime  # noqa: E402
import contextvars  # noqa: E402
from typing import Any  # noqa: E402

# Create a unique instance identifier
startup_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
INSTANCE_ID = f"{socket.gethostname()}-{os.getpid()}-{startup_time}"
# Per-update context. Retained for handlers that annotate the active update.
current_update_info: contextvars.ContextVar[dict[str, Any] | None] = (
    contextvars.ContextVar("current_update_info", default=None)
)

logger.info(f"[INSTANCE_START] instance={INSTANCE_ID}")

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
import handlers.shorteners  # noqa: E402
import handlers.ads  # noqa: E402
import handlers.analytics  # noqa: E402
import handlers.reactions_handler  # noqa: E402
import handlers.channel_analytics  # noqa: E402
import handlers.settings  # noqa: E402
import handlers.store  # noqa: E402
import handlers.movie_search  # noqa: E402
import handlers.marketplace  # noqa: E402
import handlers.post_builder  # noqa: E402
import handlers.help  # noqa: E402
import handlers.post_builder  # noqa: E402


from utils.worker_framework import (
    register_worker,
    start_workers,
    recover_workers,
    stop_workers,
)  # noqa: E402
from utils.queue_system import (
    register_handler,
    recover_interrupted_tasks,
    process_queue,
)  # noqa: E402
from utils.anti_crash import recover_from_crash  # noqa: E402


from utils.web_server import start_web_server, stop_web_server  # noqa: E402

# Override start to trigger background workers and sub-bots
original_start = app.start


async def custom_start():
    await original_start()

    # Single-instance protection: refuse to run if another instance is live,
    # then keep the lock fresh via a heartbeat. Prevents duplicate update
    # processing (double deliveries / double payment side-effects).
    await acquire_runtime_lock()
    asyncio.create_task(instance_heartbeat_worker())

    # Cache bot username for global fallback
    bot_me = app.me or await app.get_me()
    config.BOT_USERNAME = bot_me.username

    await database.init_db()
    from utils.multi_lang import load_translations

    await load_translations()
    await database.clear_active_deliveries()
    await database.delete_expired_drafts_and_states()
    await database.batches_col.delete_many({})
    await database.edit_sessions_col.delete_many({})
    logger.info(
        "Cleared stale batch, edit sessions, and expired drafts/temporary states from the database."
    )

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
    from utils.ads_engine import ads_scheduler_worker

    asyncio.create_task(ads_scheduler_worker(app))
    from utils.post_workers import scheduler_worker, repost_worker

    asyncio.create_task(scheduler_worker(app))
    asyncio.create_task(repost_worker(app))

    # Recover from any previous crashes or interruptions
    await recover_from_crash()
    await recover_interrupted_tasks()
    await recover_workers()

    # Register queue handlers
    async def _media_upload_handler(payload: dict):
        logger.info(f"Media upload task: {payload.get('file_id')}")

    register_handler("media_upload", _media_upload_handler)

    async def _broadcast_handler(payload: dict):
        logger.info(f"Broadcast task for {payload.get('user_id')}")

    register_handler("broadcast", _broadcast_handler)

    # Register and start background workers
    async def _queue_worker_fn():
        await process_queue(max_concurrent=5)

    register_worker(
        "queue_processor",
        _queue_worker_fn,
        interval=10,
        description="Process pending queue tasks",
    )

    async def _queue_cleanup_fn():
        from utils.queue_system import cleanup_completed_tasks

        await cleanup_completed_tasks(hours=24)

    register_worker(
        "queue_cleanup",
        _queue_cleanup_fn,
        interval=3600,
        description="Clean up completed queue tasks",
    )

    async def _post_history_cleanup_fn():
        from database.channel_post_history import cleanup_old_history

        await cleanup_old_history(days=90)

    register_worker(
        "post_history_cleanup",
        _post_history_cleanup_fn,
        interval=86400,
        description="Clean up old post history",
    )

    await start_workers()

    # Start the local redirect web server
    start_web_server()

    # Sync commands with BotFather (Module 30)
    from utils.botfather_menu import sync_bot_commands

    await sync_bot_commands(app)


app.start = custom_start  # type: ignore[assignment]


from pyrogram.types import Message, CallbackQuery  # noqa: E402
from pyrogram.enums import ChatType  # noqa: E402


@app.on_message(group=-100)
async def ignore_self_and_outgoing(client: Client, message: Message):
    """Drop the bot's own / outgoing messages before any handler runs."""
    is_self = message.from_user and client.me and message.from_user.id == client.me.id
    if message.outgoing or is_self:
        message.stop_propagation()


# Override stop to cleanly shutdown all running sub-bots
original_stop = app.stop


async def custom_stop():
    await stop_workers()
    stop_web_server()
    await original_stop()


app.stop = custom_stop  # type: ignore[assignment]


# --- RUNTIME GUARDS: single-instance lock + update de-duplication ---
import sys  # noqa: E402
from database.mongo import processed_updates_col, runtime_lock_col  # noqa: E402

# Reconfigure stdout for UTF-8 so emoji in logs don't crash Windows consoles.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# Single Instance Protection
async def acquire_runtime_lock():
    lock_name = "bot_runtime_lock"
    now = datetime.datetime.now(datetime.timezone.utc)
    hostname = socket.gethostname()
    pid = os.getpid()

    lock = await runtime_lock_col.find_one({"lock_name": lock_name})
    if lock:
        last_heartbeat = lock.get("heartbeat")
        if last_heartbeat:
            if last_heartbeat.tzinfo is None:
                last_heartbeat = last_heartbeat.replace(tzinfo=datetime.timezone.utc)
            if (now - last_heartbeat).total_seconds() < 60:
                logger.error(
                    f"Active bot instance detected! Hostname: {lock.get('hostname')}, "
                    f"PID: {lock.get('pid')}, Last Heartbeat: {last_heartbeat}"
                )
                print(
                    f"FATAL: Active instance already running on {lock.get('hostname')} "
                    f"(PID {lock.get('pid')}). Exiting.",
                    flush=True,
                )
                sys.exit(1)

        await runtime_lock_col.update_one(
            {"lock_name": lock_name},
            {
                "$set": {
                    "instance_id": INSTANCE_ID,
                    "hostname": hostname,
                    "pid": pid,
                    "started_at": now,
                    "heartbeat": now,
                }
            },
        )
    else:
        await runtime_lock_col.insert_one(
            {
                "lock_name": lock_name,
                "instance_id": INSTANCE_ID,
                "hostname": hostname,
                "pid": pid,
                "started_at": now,
                "heartbeat": now,
            }
        )
    logger.info("Successfully acquired runtime lock.")


async def instance_heartbeat_worker():
    lock_name = "bot_runtime_lock"
    while True:
        try:
            await asyncio.sleep(30)
            now = datetime.datetime.now(datetime.timezone.utc)
            res = await runtime_lock_col.update_one(
                {"lock_name": lock_name, "instance_id": INSTANCE_ID},
                {"$set": {"heartbeat": now}},
            )
            if res.modified_count == 0:
                logger.warning(
                    "Lost runtime lock ownership. Exiting process to prevent duplication."
                )
                print(
                    "FATAL: Lost runtime lock ownership. Exiting process.", flush=True
                )
                os._exit(1)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in instance heartbeat worker: {e}")


# Update de-duplication guard (group -200, runs before all handlers).
# A unique index on processed_updates.update_id makes the insert fail on a
# duplicate delivery, so we drop the update instead of processing it twice.
@app.on_message(group=-200)
async def dedup_message_guard(client: Client, message: Message):
    # Fresh update: clear the per-update builder-context cache so the input
    # routers below share a single draft read instead of querying repeatedly.
    database.reset_builder_context_cache()
    update_key = f"msg_{message.chat.id}_{message.id}"
    user_id = message.from_user.id if message.from_user else None
    try:
        await processed_updates_col.insert_one(
            {
                "update_id": update_key,
                "user_id": user_id,
                "processed_at": datetime.datetime.now(datetime.timezone.utc),
            }
        )
    except Exception:
        logger.warning(f"Duplicate update key {update_key} detected. Dropping message.")
        message.stop_propagation()
        return

    # Message rate limiting: 20 text messages / minute per user (private chats).
    # Curbs command/input spam (caption, password, store, search). Media uploads
    # are not text so batch uploads are unaffected.
    if (
        user_id
        and message.text
        and message.chat
        and message.chat.type == ChatType.PRIVATE
    ):
        from utils.rate_limiter import check_rate_limit

        allowed = await check_rate_limit(
            user_id, "message", limit=20, window_seconds=60
        )
        if not allowed:
            # Send the "slow down" notice at most once per window to avoid spam.
            notice_ok = await check_rate_limit(
                user_id, "message_limit_notice", limit=1, window_seconds=60
            )
            if notice_ok:
                try:
                    await message.reply_text(
                        "⏳ You're sending messages too quickly. Please slow down and try again in a minute."
                    )
                except Exception:
                    pass
            message.stop_propagation()


@app.on_callback_query(group=-200)
async def dedup_and_ratelimit_callback_guard(
    client: Client, callback_query: CallbackQuery
):
    update_key = f"cb_{callback_query.id}"
    try:
        await processed_updates_col.insert_one(
            {
                "update_id": update_key,
                "user_id": callback_query.from_user.id,
                "processed_at": datetime.datetime.now(datetime.timezone.utc),
            }
        )
    except Exception:
        logger.warning(
            f"Duplicate update key {update_key} detected. Dropping callback."
        )
        callback_query.stop_propagation()
        return

    # Rate limit: callback queries (50/min)
    user_id = callback_query.from_user.id
    from utils.rate_limiter import check_rate_limit

    allowed = await check_rate_limit(
        user_id, "callback_query", limit=50, window_seconds=60
    )
    if not allowed:
        logger.warning(f"Callback query rate limit exceeded for user {user_id}")
        await callback_query.answer(
            "❌ Rate limit exceeded (50/min). Please slow down.", show_alert=True
        )
        callback_query.stop_propagation()
