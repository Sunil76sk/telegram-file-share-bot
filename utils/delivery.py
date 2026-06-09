from __future__ import annotations

import logging
from pyrogram import Client
import database
import config

logger = logging.getLogger(__name__)


async def deliver_files(client: Client, chat_id: int, file_doc: dict):
    files = file_doc.get("files", [])
    token = file_doc.get("token")

    if not files:
        await client.send_message(chat_id, "No files found in this sharing link.")
        return

    if not token or not await database.start_delivery(chat_id, token):
        logger.warning(
            f"Delivery already in progress for user {chat_id} on token {token}. Skipping duplicate delivery."
        )
        return

    try:
        delay = getattr(config, "AUTO_DELETE_SECONDS", 300)
        if delay >= 60:
            minutes = delay // 60
            time_str = f"{minutes} minute{'s' if minutes > 1 else ''}"
        else:
            time_str = f"{delay} second{'s' if delay != 1 else ''}"

        info_msg = await client.send_message(
            chat_id,
            f"Delivering {len(files)} file(s)...\n\n"
            f"Note: All delivered files and this info message will be automatically deleted after {time_str} for security purposes.",
        )

        sent_message_ids = [info_msg.id]
        failures = 0
        for index, file_obj in enumerate(files):
            file_id = file_obj.get("file_id")
            caption = file_obj.get("caption", "")
            try:
                msg = await client.send_cached_media(
                    chat_id=chat_id, file_id=file_id, caption=caption
                )
                sent_message_ids.append(msg.id)
            except Exception as e:
                logger.error(
                    f"Failed to deliver file index {index} with ID {file_id}: {e}"
                )
                failures += 1

        if failures == len(files):
            await client.send_message(
                chat_id,
                "All file deliveries failed. The files may have been deleted or the bot lacks permissions.",
            )
        else:
            await database.increment_link_downloads(token, chat_id)
            await database.schedule_deletion(
                chat_id, sent_message_ids, delay_seconds=delay
            )
    finally:
        await database.finish_delivery(chat_id, token)
