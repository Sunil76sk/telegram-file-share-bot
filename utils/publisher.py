from __future__ import annotations

import logging
from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.channel_post_history import record_post
from database.creator_db import delete_post_draft, get_settings, increment_channel_stat

logger = logging.getLogger(__name__)

async def publish_post(draft: dict, client: Client, delete_draft: bool = True) -> int:
    """
    Single publish function used by:
    - Send Now
    - Scheduled publish
    - Auto Repost
    
    Returns: message_id
    """
    channel_id = draft["channel_id"]
    caption = draft.get("caption_html") or draft.get("caption") or ""
    
    # 1. Build inline keyboard from url_buttons
    buttons = []
    # Support both 'url_buttons' (from draft) and 'buttons' (from repost job schema)
    url_buttons_list = draft.get("url_buttons") or draft.get("buttons") or []
    for btn in url_buttons_list:
        buttons.append(
            InlineKeyboardButton(
                text=btn["text"],
                url=btn.get("shortened_url") or btn["url"]
            )
        )
        
    # 2. Check and append Tutorial Video button if enabled
    settings = await get_settings()
    if settings.get("tutorial_show_on_post") and settings.get("tutorial_shortened_url"):
        buttons.append(
            InlineKeyboardButton(
                text="🎥 Tutorial Video",
                url=settings["tutorial_shortened_url"]
            )
        )
        
    keyboard = InlineKeyboardMarkup([buttons[i:i+1] for i in range(len(buttons))])
    
    # 3. Send photo with caption
    # Support both 'poster_file_id' and 'file_id'
    photo_file_id = draft.get("poster_file_id") or draft.get("file_id")
    if not photo_file_id:
        raise ValueError("No poster file_id found to publish.")

    kwargs = {}
    if buttons:
        kwargs["reply_markup"] = keyboard

    msg = await client.send_photo(
        chat_id=channel_id,
        photo=photo_file_id,
        caption=caption,
        parse_mode=ParseMode.HTML,
        **kwargs
    )
    if not msg:
        raise ValueError("Failed to publish post: send_photo returned None.")
    
    # 4. Pin if enabled
    # Support both 'pin_message' and 'pin'
    should_pin = draft.get("pin_message") or draft.get("pin", False)
    if should_pin:
        try:
            await client.pin_chat_message(
                chat_id=channel_id, 
                message_id=msg.id,
                disable_notification=True
            )
        except Exception as e:
            logger.warning(f"Pin failed for channel {channel_id}: {e}")
            
    # 5. Save to post_history
    try:
        await record_post(
            channel_id=channel_id,
            user_id=draft["user_id"],
            message_id=msg.id,
            media_type="photo",
            caption=caption,
            buttons=url_buttons_list,
            reactions=draft.get("reactions"),
            comments=draft.get("comments_enabled") or draft.get("comments", False),
            pin=should_pin,
            scheduled=draft.get("schedule_enabled") or draft.get("scheduled", False),
            repost=draft.get("repost_enabled") or draft.get("repost", False)
        )
    except Exception as e:
        logger.error(f"Failed to record post history: {e}")
        
    # 6. Increment channel stat
    try:
        await increment_channel_stat(channel_id, "publishes", 1)
    except Exception as e:
        logger.error(f"Failed to increment channel stat: {e}")
        
    # 7. Delete draft after successful publish
    if delete_draft:
        try:
            await delete_post_draft(draft["user_id"])
        except Exception as e:
            logger.error(f"Failed to delete post draft: {e}")
        
    return msg.id
