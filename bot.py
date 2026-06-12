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
import handlers.shorteners  # noqa: E402
import handlers.ads  # noqa: E402
import handlers.analytics  # noqa: E402
import handlers.post_builder  # noqa: E402
import handlers.scheduler  # noqa: E402
import handlers.templates  # noqa: E402
import handlers.channel_analytics  # noqa: E402
import handlers.reactions_handler  # noqa: E402


from utils.web_server import start_web_server, stop_web_server  # noqa: E402

# Override start to trigger background workers and sub-bots
original_start = app.start


async def custom_start():
    import os
    import socket
    import datetime
    pid = os.getpid()
    hostname = socket.gethostname()
    timestamp = datetime.datetime.now().isoformat()
    logger.info(f"STARTUP LOG - PID: {pid}, Hostname: {hostname}, Timestamp: {timestamp}")
    logger.info("BOT INSTANCE STARTED")
    await original_start()

    # Cache bot username for global fallback
    bot_me = app.me or await app.get_me()
    config.BOT_USERNAME = bot_me.username

    await database.init_db()
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

    # Start the local redirect web server
    start_web_server()

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
    stop_web_server()
    await original_stop()


app.stop = custom_stop  # type: ignore[assignment]


# --- TEMPORARY RUNTIME LOGGING FOR INVESTIGATION ---
import inspect
import time
from pyrogram.types import Message, CallbackQuery

# Reconfigure stdout for UTF-8 to ensure emojis don't crash the prints
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 1. Incoming Update Loggers (Group -200 to run first)
@app.on_message(group=-200)
async def log_incoming_message(client: Client, message: Message):
    import os
    pid = os.getpid()
    logger.info(f"Incoming Update - PID: {pid} | Update ID: {message.id} | Message ID: {message.id}")
    t_ms = int(time.time() * 1000)
    logger.info(f"[LIVE LOG][INCOMING_MSG] timestamp={t_ms} update_id={message.id} message_id={message.id} user_id={message.from_user.id if message.from_user else None} chat_id={message.chat.id} text={repr(message.text)} outgoing={message.outgoing}")

@app.on_callback_query(group=-200)
async def log_incoming_callback(client: Client, callback_query: CallbackQuery):
    import os
    pid = os.getpid()
    logger.info(f"Incoming Update - PID: {pid} | Update ID: {callback_query.id} | Message ID: {callback_query.message.id if callback_query.message else None}")
    t_ms = int(time.time() * 1000)
    logger.info(f"[LIVE LOG][INCOMING_CB] timestamp={t_ms} update_id={callback_query.id} user_id={callback_query.from_user.id} chat_id={callback_query.message.chat.id if callback_query.message else None} data={repr(callback_query.data)}")

# Helper to log caller information
def get_caller_info():
    frame = inspect.currentframe()
    # Go up the stack to find the first caller outside of our wrappers
    while frame:
        co_filename = frame.f_code.co_filename
        co_name = frame.f_code.co_name
        if "bot.py" not in co_filename and "pyrogram" not in co_filename and "inspect" not in co_filename:
            # Found the handler file/function
            basename = co_filename.split("/")[-1].split("\\")[-1]
            return f"{basename}:{co_name}:{frame.f_lineno}"
        frame = frame.f_back
    return "unknown:unknown:0"

# 2. Outgoing Reply/Send Method Wrappers
original_send_message = Client.send_message
async def patched_send_message(self, chat_id, text, *args, **kwargs):
    t_ms = int(time.time() * 1000)
    caller = get_caller_info()
    print(f"[LIVE LOG][OUTGOING][send_message] timestamp={t_ms} chat_id={chat_id} text={repr(text)} caller={caller}")
    return await original_send_message(self, chat_id, text, *args, **kwargs)
Client.send_message = patched_send_message

original_reply_text = Message.reply_text
async def patched_reply_text(self, text, *args, **kwargs):
    t_ms = int(time.time() * 1000)
    caller = get_caller_info()
    print(f"[LIVE LOG][OUTGOING][reply_text] timestamp={t_ms} chat_id={self.chat.id} reply_to_msg_id={self.id} text={repr(text)} caller={caller}")
    return await original_reply_text(self, text, *args, **kwargs)
Message.reply_text = patched_reply_text

original_send_photo = Client.send_photo
async def patched_send_photo(self, chat_id, photo, caption="", *args, **kwargs):
    t_ms = int(time.time() * 1000)
    caller = get_caller_info()
    print(f"[LIVE LOG][OUTGOING][send_photo] timestamp={t_ms} chat_id={chat_id} caption={repr(caption)} caller={caller}")
    return await original_send_photo(self, chat_id, photo, caption=caption, *args, **kwargs)
Client.send_photo = patched_send_photo

original_send_document = Client.send_document
async def patched_send_document(self, chat_id, document, caption="", *args, **kwargs):
    t_ms = int(time.time() * 1000)
    caller = get_caller_info()
    print(f"[LIVE LOG][OUTGOING][send_document] timestamp={t_ms} chat_id={chat_id} caption={repr(caption)} caller={caller}")
    return await original_send_document(self, chat_id, document, caption=caption, *args, **kwargs)
Client.send_document = patched_send_document

original_edit_message_text = Client.edit_message_text
async def patched_edit_message_text(self, chat_id, message_id, text, *args, **kwargs):
    t_ms = int(time.time() * 1000)
    caller = get_caller_info()
    print(f"[LIVE LOG][OUTGOING][edit_message_text] timestamp={t_ms} chat_id={chat_id} message_id={message_id} text={repr(text)} caller={caller}")
    return await original_edit_message_text(self, chat_id, message_id, text, *args, **kwargs)
Client.edit_message_text = patched_edit_message_text

original_msg_edit_text = Message.edit_text
async def patched_msg_edit_text(self, text, *args, **kwargs):
    t_ms = int(time.time() * 1000)
    caller = get_caller_info()
    print(f"[LIVE LOG][OUTGOING][msg_edit_text] timestamp={t_ms} chat_id={self.chat.id} message_id={self.id} text={repr(text)} caller={caller}")
    return await original_msg_edit_text(self, text, *args, **kwargs)
Message.edit_text = patched_msg_edit_text
# ----------------------------------------------------
