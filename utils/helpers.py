import re
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import UserNotParticipant
import config
import database

logger = logging.getLogger(__name__)


def format_size(bytes_size: int) -> str:
    """Format bytes into human-readable size."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"


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
    if await database.is_admin(user_id):
        return []

    not_joined = []

    # 1. Fetch static channels from config
    static_channels = config.FORCE_SUB_CHATS

    # 2. Fetch dynamic channels from database
    db_channels = await database.get_force_sub_channels()

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
            # Check if user is kicked or left
            if member.status in ["kicked", "left"]:
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
            if member.status in ["kicked", "left"]:
                invite_link = (
                    f"https://t.me/{chat_id_or_username.replace('@', '')}"
                    if isinstance(chat_id_or_username, str)
                    and not chat_id_or_username.startswith("-")
                    else None
                )
                chat_info = await client.get_chat(chat_id_or_username)
                not_joined.append(
                    {
                        "chat_id": chat_id_or_username,
                        "title": chat_info.title,
                        "invite_link": invite_link
                        or chat_info.invite_link
                        or f"https://t.me/{chat_info.username}",
                    }
                )
        except UserNotParticipant:
            try:
                chat_info = await client.get_chat(chat_id_or_username)
                invite_link = (
                    f"https://t.me/{chat_id_or_username.replace('@', '')}"
                    if isinstance(chat_id_or_username, str)
                    and not chat_id_or_username.startswith("-")
                    else chat_info.invite_link
                )
                not_joined.append(
                    {
                        "chat_id": chat_id_or_username,
                        "title": chat_info.title,
                        "invite_link": invite_link
                        or f"https://t.me/{chat_info.username}",
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
                    else ""
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


async def admin_check(_, __, message):
    """Custom filter to check if the sender is an administrator (static or dynamic)."""
    if not message or not message.from_user:
        return False
    return await database.is_admin(message.from_user.id)


async def banned_check(_, __, message):
    """Custom filter to check if the sender is banned from using the bot."""
    if not message or not message.from_user:
        return False
    return await database.is_banned(message.from_user.id)


admin_filter = filters.create(admin_check)
banned_filter = filters.create(banned_check)
