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

import os
import socket
import datetime
import contextvars

# Create a unique instance identifier
startup_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
INSTANCE_ID = f"{socket.gethostname()}-{os.getpid()}-{startup_time}"
current_update_info = contextvars.ContextVar("current_update_info", default=None)

# Log immediately on startup
logger.info(f"[INSTANCE_START]\ninstance={INSTANCE_ID}")
print(f"[INSTANCE_START]\ninstance={INSTANCE_ID}", flush=True)

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
import handlers.post_builder  # noqa: E402
import handlers.scheduler  # noqa: E402
import handlers.templates  # noqa: E402
import handlers.reactions_handler  # noqa: E402
import handlers.channel_analytics  # noqa: E402
import handlers.settings  # noqa: E402
import handlers.store  # noqa: E402
import handlers.movie_search  # noqa: E402
import handlers.marketplace  # noqa: E402

from utils.worker_framework import register_worker, start_workers, recover_workers, stop_workers  # noqa: E402
from utils.queue_system import register_handler, recover_interrupted_tasks, process_queue  # noqa: E402
from utils.draft_recovery import recover_interrupted_drafts  # noqa: E402
from utils.anti_crash import recover_from_crash  # noqa: E402


from utils.web_server import start_web_server, stop_web_server  # noqa: E402

# Override start to trigger background workers and sub-bots
original_start = app.start


async def custom_start():
    logger.info(f"[INSTANCE_START]\ninstance={INSTANCE_ID}")
    print(f"[INSTANCE_START]\ninstance={INSTANCE_ID}", flush=True)
    await original_start()

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
    logger.info("Cleared stale batch, edit sessions, and expired drafts/temporary states from the database.")

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
    from handlers.scheduler import start_scheduler_loop
    asyncio.create_task(start_scheduler_loop(app))

    # Recover from any previous crashes or interruptions
    await recover_from_crash()
    await recover_interrupted_drafts()
    await recover_interrupted_tasks()
    await recover_workers()

    # Register queue handlers
    async def _media_upload_handler(payload: dict):
        logger.info(f"Media upload task: {payload.get('file_id')}")
    register_handler("media_upload", _media_upload_handler)

    async def _broadcast_handler(payload: dict):
        logger.info(f"Broadcast task for {payload.get('user_id')}")
    register_handler("broadcast", _broadcast_handler)

    async def _post_schedule_handler(payload: dict):
        logger.info(f"Scheduled post task: {payload.get('post_id')}")
    register_handler("post_schedule", _post_schedule_handler)

    async def _metadata_extract_handler(payload: dict):
        logger.info(f"Metadata extraction for: {payload.get('file_id')}")
    register_handler("metadata_extract", _metadata_extract_handler)

    # Register and start background workers
    async def _queue_worker_fn():
        await process_queue(max_concurrent=5)
    register_worker("queue_processor", _queue_worker_fn, interval=10, description="Process pending queue tasks")

    async def _queue_cleanup_fn():
        from utils.queue_system import cleanup_completed_tasks
        await cleanup_completed_tasks(hours=24)
    register_worker("queue_cleanup", _queue_cleanup_fn, interval=3600, description="Clean up completed queue tasks")

    async def _draft_cleanup_fn():
        from utils.draft_recovery import cleanup_draft_recovery
        await cleanup_draft_recovery(hours=48)
    register_worker("draft_cleanup", _draft_cleanup_fn, interval=3600, description="Clean up old draft recovery records")

    async def _post_history_cleanup_fn():
        from database.channel_post_history import cleanup_old_history
        await cleanup_old_history(days=90)
    register_worker("post_history_cleanup", _post_history_cleanup_fn, interval=86400, description="Clean up old post history")

    await start_workers()

    # Start the local redirect web server
    start_web_server()

    # Sync commands with BotFather (Module 30)
    from utils.botfather_menu import sync_bot_commands
    await sync_bot_commands(app)

    # Debug print all registered handlers
    logger.info("--- REGISTERED HANDLERS ON STARTUP ---")
    for group, handlers in sorted(app.dispatcher.groups.items()):
        logger.info(f"Group {group}:")
        for h in handlers:
            logger.info(f"  - {h.__class__.__name__}: callback={h.callback.__name__ if hasattr(h, 'callback') else 'None'}")


app.start = custom_start  # type: ignore[assignment]


from pyrogram.types import Message

@app.on_message(group=-100)
async def debug_message_logger(client: Client, message: Message):
    logger.info(f"DEBUG RECEIVE: text='{message.text}', user='{message.from_user.id if message.from_user else None}', chat='{message.chat.id}', outgoing={message.outgoing}")
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


# --- TEMPORARY RUNTIME LOGGING & GUARDS FOR INVESTIGATION ---
import time
import sys
from pyrogram.types import Message, CallbackQuery
from database.mongo import processed_updates_col, runtime_lock_col

# Reconfigure stdout for UTF-8 to ensure emojis don't crash the prints
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
                logger.error(f"Active bot instance detected! Hostname: {lock.get('hostname')}, PID: {lock.get('pid')}, Last Heartbeat: {last_heartbeat}")
                print(f"FATAL: Active instance already running on {lock.get('hostname')} (PID {lock.get('pid')}). Exiting.", flush=True)
                sys.exit(1)
        
        await runtime_lock_col.update_one(
            {"lock_name": lock_name},
            {"$set": {
                "instance_id": INSTANCE_ID,
                "hostname": hostname,
                "pid": pid,
                "started_at": now,
                "heartbeat": now
            }}
        )
    else:
        await runtime_lock_col.insert_one({
            "lock_name": lock_name,
            "instance_id": INSTANCE_ID,
            "hostname": hostname,
            "pid": pid,
            "started_at": now,
            "heartbeat": now
        })
    logger.info("Successfully acquired runtime lock.")

async def instance_heartbeat_worker():
    lock_name = "bot_runtime_lock"
    while True:
        try:
            await asyncio.sleep(30)
            now = datetime.datetime.now(datetime.timezone.utc)
            res = await runtime_lock_col.update_one(
                {"lock_name": lock_name, "instance_id": INSTANCE_ID},
                {"$set": {"heartbeat": now}}
            )
            if res.modified_count == 0:
                logger.warning("Lost runtime lock ownership. Exiting process to prevent duplication.")
                print("FATAL: Lost runtime lock ownership. Exiting process.", flush=True)
                os._exit(1)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in instance heartbeat worker: {e}")

# 1. Incoming Update Loggers (Group -200 to run first)
@app.on_message(group=-200)
async def log_incoming_message(client: Client, message: Message):
    # Update Processing Guard (Module 19)
    update_key = f"msg_{message.chat.id}_{message.id}"
    user_id = message.from_user.id if message.from_user else None
    try:
        await processed_updates_col.insert_one({
            "update_id": update_key,
            "user_id": user_id,
            "processed_at": datetime.datetime.now(datetime.timezone.utc)
        })
    except Exception:
        # Already processed or write conflict, drop update
        logger.warning(f"Duplicate update key {update_key} detected. Dropping message.")
        message.stop_propagation()
        return

    current_update_info.set({
        "handler": "unknown",
        "update_id": message.id,
        "message_id": message.id
    })
    log_msg = (
        f"[INCOMING_UPDATE]\n"
        f"instance={INSTANCE_ID}\n"
        f"update_id={message.id}\n"
        f"message_id={message.id}\n"
        f"user_id={message.from_user.id if message.from_user else None}\n"
        f"chat_id={message.chat.id}\n"
        f"text={message.text}\n"
        f"callback_data=None"
    )
    logger.info(log_msg)
    print(log_msg, flush=True)

@app.on_callback_query(group=-200)
async def log_incoming_callback(client: Client, callback_query: CallbackQuery):
    # Update Processing Guard (Module 19)
    update_key = f"cb_{callback_query.id}"
    try:
        await processed_updates_col.insert_one({
            "update_id": update_key,
            "user_id": callback_query.from_user.id,
            "processed_at": datetime.datetime.now(datetime.timezone.utc)
        })
    except Exception:
        # Already processed or write conflict, drop callback
        logger.warning(f"Duplicate update key {update_key} detected. Dropping callback.")
        callback_query.stop_propagation()
        return

    # Rate Limit: Callback queries (50/min) (Module 26)
    user_id = callback_query.from_user.id
    from utils.rate_limiter import check_rate_limit
    allowed = await check_rate_limit(user_id, "callback_query", limit=50, window_seconds=60)
    if not allowed:
        logger.warning(f"Callback query rate limit exceeded for user {user_id}")
        await callback_query.answer("❌ Rate limit exceeded (50/min). Please slow down.", show_alert=True)
        callback_query.stop_propagation()
        return

    msg_id = callback_query.message.id if callback_query.message else None
    chat_id = callback_query.message.chat.id if callback_query.message else None
    current_update_info.set({
        "handler": "unknown",
        "update_id": callback_query.id,
        "message_id": msg_id
    })
    log_msg = (
        f"[INCOMING_UPDATE]\n"
        f"instance={INSTANCE_ID}\n"
        f"update_id={callback_query.id}\n"
        f"message_id={msg_id}\n"
        f"user_id={callback_query.from_user.id}\n"
        f"chat_id={chat_id}\n"
        f"text=None\n"
        f"callback_data={callback_query.data}"
    )
    logger.info(log_msg)
    print(log_msg, flush=True)

# 2. Outgoing Reply/Send Method Wrappers
original_send_message = Client.send_message
async def patched_send_message(self, chat_id, text, *args, **kwargs):
    info = current_update_info.get()
    h_name = info["handler"] if info else "unknown"
    u_id = info["update_id"] if info else "unknown"
    m_id = info["message_id"] if info else "unknown"
    log_msg = (
        f"[OUTGOING_REPLY]\n"
        f"instance={INSTANCE_ID}\n"
        f"handler={h_name}\n"
        f"update_id={u_id}\n"
        f"message_id={m_id}\n"
        f"reply_type=send_message"
    )
    logger.info(log_msg)
    print(log_msg, flush=True)
    return await original_send_message(self, chat_id, text, *args, **kwargs)
Client.send_message = patched_send_message

original_reply_text = Message.reply_text
async def patched_reply_text(self, text, *args, **kwargs):
    info = current_update_info.get()
    h_name = info["handler"] if info else "unknown"
    u_id = info["update_id"] if info else "unknown"
    m_id = info["message_id"] if info else "unknown"
    log_msg = (
        f"[OUTGOING_REPLY]\n"
        f"instance={INSTANCE_ID}\n"
        f"handler={h_name}\n"
        f"update_id={u_id}\n"
        f"message_id={m_id}\n"
        f"reply_type=reply_text"
    )
    logger.info(log_msg)
    print(log_msg, flush=True)
    return await original_reply_text(self, text, *args, **kwargs)
Message.reply_text = patched_reply_text

original_edit_message_text = Client.edit_message_text
async def patched_edit_message_text(self, chat_id, message_id, text, *args, **kwargs):
    info = current_update_info.get()
    h_name = info["handler"] if info else "unknown"
    u_id = info["update_id"] if info else "unknown"
    m_id = info["message_id"] if info else "unknown"
    log_msg = (
        f"[OUTGOING_REPLY]\n"
        f"instance={INSTANCE_ID}\n"
        f"handler={h_name}\n"
        f"update_id={u_id}\n"
        f"message_id={m_id}\n"
        f"reply_type=edit_message_text"
    )
    logger.info(log_msg)
    print(log_msg, flush=True)
    return await original_edit_message_text(self, chat_id, message_id, text, *args, **kwargs)
Client.edit_message_text = patched_edit_message_text

original_msg_edit_text = Message.edit_text
async def patched_msg_edit_text(self, text, *args, **kwargs):
    info = current_update_info.get()
    h_name = info["handler"] if info else "unknown"
    u_id = info["update_id"] if info else "unknown"
    m_id = info["message_id"] if info else "unknown"
    log_msg = (
        f"[OUTGOING_REPLY]\n"
        f"instance={INSTANCE_ID}\n"
        f"handler={h_name}\n"
        f"update_id={u_id}\n"
        f"message_id={m_id}\n"
        f"reply_type=edit_message_text"
    )
    logger.info(log_msg)
    print(log_msg, flush=True)
    return await original_msg_edit_text(self, text, *args, **kwargs)
Message.edit_text = patched_msg_edit_text

original_reply_photo = Message.reply_photo
async def patched_reply_photo(self, photo, *args, **kwargs):
    info = current_update_info.get()
    h_name = info["handler"] if info else "unknown"
    u_id = info["update_id"] if info else "unknown"
    m_id = info["message_id"] if info else "unknown"
    log_msg = (
        f"[OUTGOING_REPLY]\n"
        f"instance={INSTANCE_ID}\n"
        f"handler={h_name}\n"
        f"update_id={u_id}\n"
        f"message_id={m_id}\n"
        f"reply_type=reply_photo"
    )
    logger.info(log_msg)
    print(log_msg, flush=True)
    return await original_reply_photo(self, photo, *args, **kwargs)
Message.reply_photo = patched_reply_photo

original_send_photo = Client.send_photo
async def patched_send_photo(self, chat_id, photo, *args, **kwargs):
    info = current_update_info.get()
    h_name = info["handler"] if info else "unknown"
    u_id = info["update_id"] if info else "unknown"
    m_id = info["message_id"] if info else "unknown"
    log_msg = (
        f"[OUTGOING_REPLY]\n"
        f"instance={INSTANCE_ID}\n"
        f"handler={h_name}\n"
        f"update_id={u_id}\n"
        f"message_id={m_id}\n"
        f"reply_type=reply_photo"
    )
    logger.info(log_msg)
    print(log_msg, flush=True)
    return await original_send_photo(self, chat_id, photo, *args, **kwargs)
Client.send_photo = patched_send_photo

original_reply_document = Message.reply_document
async def patched_reply_document(self, document, *args, **kwargs):
    info = current_update_info.get()
    h_name = info["handler"] if info else "unknown"
    u_id = info["update_id"] if info else "unknown"
    m_id = info["message_id"] if info else "unknown"
    log_msg = (
        f"[OUTGOING_REPLY]\n"
        f"instance={INSTANCE_ID}\n"
        f"handler={h_name}\n"
        f"update_id={u_id}\n"
        f"message_id={m_id}\n"
        f"reply_type=reply_document"
    )
    logger.info(log_msg)
    print(log_msg, flush=True)
    return await original_reply_document(self, document, *args, **kwargs)
Message.reply_document = patched_reply_document

original_send_document = Client.send_document
async def patched_send_document(self, chat_id, document, *args, **kwargs):
    info = current_update_info.get()
    h_name = info["handler"] if info else "unknown"
    u_id = info["update_id"] if info else "unknown"
    m_id = info["message_id"] if info else "unknown"
    log_msg = (
        f"[OUTGOING_REPLY]\n"
        f"instance={INSTANCE_ID}\n"
        f"handler={h_name}\n"
        f"update_id={u_id}\n"
        f"message_id={m_id}\n"
        f"reply_type=reply_document"
    )
    logger.info(log_msg)
    print(log_msg, flush=True)
    return await original_send_document(self, chat_id, document, *args, **kwargs)
Client.send_document = patched_send_document
# ----------------------------------------------------
