import re
import logging
import urllib.request
import json
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import UserNotParticipant
import config
import database

logger = logging.getLogger(__name__)


def format_size(bytes_size: int | float) -> str:
    """Format bytes into human-readable size."""
    size = float(bytes_size)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def is_valid_token(token: str) -> bool:
    """Validate token format: alphanumeric, underscores, hyphens, length 3-64."""
    return bool(re.match(r"^[a-zA-Z0-9_-]{3,64}$", token))


def extract_file_details(message: Message):
    """Utility to extract file ID, unique ID, name, type, size, and caption from Pyrogram message."""
    file_id = None
    file_unique_id = None
    file_name = "Unknown File"
    file_type = "unknown"
    file_size = 0
    caption = message.caption or ""

    if message.document:
        file_id = message.document.file_id
        file_unique_id = message.document.file_unique_id
        file_name = message.document.file_name or "document"
        file_type = "document"
        file_size = message.document.file_size
    elif message.video:
        file_id = message.video.file_id
        file_unique_id = message.video.file_unique_id
        file_name = message.video.file_name or f"video_{message.id}.mp4"
        file_type = "video"
        file_size = message.video.file_size
    elif message.audio:
        file_id = message.audio.file_id
        file_unique_id = message.audio.file_unique_id
        file_name = message.audio.file_name or f"audio_{message.id}.mp3"
        file_type = "audio"
        file_size = message.audio.file_size
    elif message.photo:
        file_id = message.photo.file_id
        file_unique_id = message.photo.file_unique_id
        file_name = f"photo_{message.id}.jpg"
        file_type = "photo"
        file_size = message.photo.file_size
    elif message.voice:
        file_id = message.voice.file_id
        file_unique_id = message.voice.file_unique_id
        file_name = f"voice_{message.id}.ogg"
        file_type = "voice"
        file_size = message.voice.file_size
    elif message.animation:
        file_id = message.animation.file_id
        file_unique_id = message.animation.file_unique_id
        file_name = message.animation.file_name or f"animation_{message.id}.gif"
        file_type = "animation"
        file_size = message.animation.file_size

    return file_id, file_unique_id, file_name, file_type, file_size, caption


async def get_not_subscribed_channels(client: Client, user_id: int) -> list:
    """
    Check membership of user in all required channels.
    Returns a list of dicts: [{"chat_id": ..., "title": ..., "invite_link": ...}] for channels they haven't joined.
    """
    # Exclude admins from force join checks
    if await database.is_admin(user_id, client):
        return []

    not_joined = []

    # Get bot details to determine if we are running the main bot or a sub-bot
    bot_me = client.me or await client.get_me()
    is_main_bot = True
    bot_id = bot_me.id

    sub_bot_doc = await database.sub_bots_col.find_one({"username": bot_me.username})
    if sub_bot_doc:
        is_main_bot = False

    # 1. Fetch static channels from config (only for main bot)
    static_channels = config.FORCE_SUB_CHATS if is_main_bot else []

    # 2. Fetch dynamic channels from database (specific to this bot)
    db_channels = await database.get_force_sub_channels(None if is_main_bot else bot_id)

    # Combine lists. Ensure no duplicate checking by using a set of IDs/usernames
    checked_chats = set()

    # Process DB channels first (because we have invite link and title)
    for channel in db_channels:
        chat_id = channel["_id"]
        title = channel["title"]
        invite_link = channel["invite_link"]
        checked_chats.add(chat_id)

        try:
            member = await client.get_chat_member(chat_id, user_id)
            # Check if user is kicked or left (using string conversion for compatibility with Pyrogram v1/v2 enums)
            member_status = str(member.status).split(".")[-1].lower()
            if member_status in ["kicked", "left", "banned"]:
                not_joined.append(
                    {"chat_id": chat_id, "title": title, "invite_link": invite_link}
                )
        except UserNotParticipant:
            not_joined.append(
                {"chat_id": chat_id, "title": title, "invite_link": invite_link}
            )
        except Exception as e:
            logger.error(f"Error checking dynamic channel subscription {chat_id}: {e}")
            # Do not block the user if there is a bot administration error
            continue

    # Process static channels
    for chat_id_or_username in static_channels:
        if chat_id_or_username in checked_chats:
            continue
        checked_chats.add(chat_id_or_username)

        try:
            member = await client.get_chat_member(chat_id_or_username, user_id)
            member_status = str(member.status).split(".")[-1].lower()
            if member_status in ["kicked", "left", "banned"]:
                invite_link = (
                    f"https://t.me/{chat_id_or_username.replace('@', '')}"
                    if isinstance(chat_id_or_username, str)
                    and not chat_id_or_username.startswith("-")
                    else None
                )
                try:
                    chat_info = await client.get_chat(chat_id_or_username)
                except Exception:
                    chat_info = None

                fallback_link = (
                    f"https://t.me/c/{str(chat_id_or_username).replace('-100', '')}/1"
                    if not isinstance(chat_id_or_username, str)
                    or chat_id_or_username.startswith("-")
                    else f"https://t.me/{str(chat_id_or_username).replace('@', '')}"
                )

                not_joined.append(
                    {
                        "chat_id": chat_id_or_username,
                        "title": (
                            getattr(chat_info, "title", str(chat_id_or_username))
                            if chat_info
                            else str(chat_id_or_username)
                        ),
                        "invite_link": invite_link
                        or (
                            getattr(chat_info, "invite_link", None)
                            if chat_info
                            else None
                        )
                        or (
                            f"https://t.me/{getattr(chat_info, 'username')}"
                            if chat_info and getattr(chat_info, "username", None)
                            else fallback_link
                        ),
                    }
                )
        except UserNotParticipant:
            try:
                chat_info = await client.get_chat(chat_id_or_username)
                invite_link = (
                    f"https://t.me/{chat_id_or_username.replace('@', '')}"
                    if isinstance(chat_id_or_username, str)
                    and not chat_id_or_username.startswith("-")
                    else getattr(chat_info, "invite_link", None)
                )
                fallback_link = (
                    f"https://t.me/c/{str(chat_id_or_username).replace('-100', '')}/1"
                    if not isinstance(chat_id_or_username, str)
                    or chat_id_or_username.startswith("-")
                    else f"https://t.me/{str(chat_id_or_username).replace('@', '')}"
                )
                not_joined.append(
                    {
                        "chat_id": chat_id_or_username,
                        "title": getattr(chat_info, "title", str(chat_id_or_username)),
                        "invite_link": invite_link
                        or (
                            f"https://t.me/{getattr(chat_info, 'username')}"
                            if getattr(chat_info, "username", None)
                            else fallback_link
                        ),
                    }
                )
            except Exception as get_chat_err:
                logger.error(
                    f"Error getting static chat info for {chat_id_or_username}: {get_chat_err}"
                )
                # Fallback info
                title = str(chat_id_or_username)
                invite_link = (
                    f"https://t.me/{chat_id_or_username.replace('@', '')}"
                    if isinstance(chat_id_or_username, str)
                    and not chat_id_or_username.startswith("-")
                    else f"https://t.me/c/{str(chat_id_or_username).replace('-100', '')}/1"
                )
                not_joined.append(
                    {
                        "chat_id": chat_id_or_username,
                        "title": title,
                        "invite_link": invite_link,
                    }
                )
        except Exception as e:
            logger.error(
                f"Error checking static channel subscription {chat_id_or_username}: {e}"
            )
            # Skip checking if there's an error (e.g. ChatAdminRequired or PeerIdInvalid) to prevent blocking access
            continue

    return not_joined


async def admin_check(_, client: Client, message: Message):
    """Custom filter to check if the sender is an administrator (static or dynamic)."""
    if not message or not message.from_user:
        return False
    return await database.is_admin(message.from_user.id, client)


async def banned_check(_, __, message):
    """Custom filter to check if the sender is banned from using the bot."""
    if not message or not message.from_user:
        return False
    return await database.is_banned(message.from_user.id)


admin_filter = filters.create(admin_check)
banned_filter = filters.create(banned_check)


async def call_telegram_api(client: Client, method: str, params: dict) -> dict:
    """Make an asynchronous HTTP POST request to the Telegram Bot API."""
    bot_token = getattr(client, "bot_token", None) or config.BOT_TOKEN
    url = f"https://api.telegram.org/bot{bot_token}/{method}"

    def _call():
        req = urllib.request.Request(
            url,
            data=json.dumps(params).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    try:
        return await asyncio.to_thread(_call)
    except Exception as e:
        logger.error(f"Error calling Telegram API method {method}: {e}")
        return {"ok": False, "description": str(e)}


async def send_stars_invoice(
    client: Client,
    chat_id: int,
    title: str,
    description: str,
    payload: str,
    amount: int,
) -> bool:
    """Send a Telegram Stars invoice to the user."""
    params = {
        "chat_id": chat_id,
        "title": title,
        "description": description,
        "payload": payload,
        "provider_token": "",  # Empty for Telegram Stars
        "currency": "XTR",
        "prices": [{"label": title, "amount": amount}],
    }
    res = await call_telegram_api(client, "sendInvoice", params)
    return res.get("ok", False)


async def answer_pre_checkout(
    client: Client,
    pre_checkout_query_id: str,
    ok: bool,
    error_message: str | None = None,
) -> bool:
    """Answer pre checkout query."""
    params = {"pre_checkout_query_id": pre_checkout_query_id, "ok": ok}
    if error_message:
        params["error_message"] = error_message
    res = await call_telegram_api(client, "answerPreCheckoutQuery", params)
    return res.get("ok", False)


async def get_share_link(client: Client, token: str) -> str:
    """Generate the final share link (shortened if shorteners are active, otherwise raw deep link)."""
    bot_me = client.me or await client.get_me()
    username = bot_me.username or "bot"
    raw_link = f"https://t.me/{username}?start={token}"

    file_doc = await database.get_file_link(token)
    bot_id = file_doc.get("bot_id") if file_doc else None

    active_shorteners = await database.get_shorteners(bot_id=bot_id, active_only=True)
    if not active_shorteners and bot_id is not None:
        active_shorteners = await database.get_shorteners(bot_id=None, active_only=True)

    has_shorteners = len(active_shorteners) > 0
    use_config_fallback = not has_shorteners and bool(
        config.SHORTENER_API_URL and config.SHORTENER_API_KEY
    )

    if has_shorteners or use_config_fallback:
        long_url = f"https://t.me/{username}?start=unl_{token}"
        short_url = None

        if has_shorteners:
            shortener = await database.get_best_shortener(bot_id=bot_id)
            if shortener:
                from utils.web_server import generate_short_link

                short_url = await generate_short_link(shortener, long_url)

        if not short_url and use_config_fallback:
            from utils.delivery import get_shortened_url

            short_url = await get_shortened_url(long_url)

        if short_url:
            return short_url

    return raw_link
