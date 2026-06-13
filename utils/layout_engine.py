from __future__ import annotations

import logging
from typing import Any

from pyrogram.enums import ParseMode
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
    InputMediaVideo,
)

from utils.caption_builder import build_telegram_caption_html

logger = logging.getLogger(__name__)

LAYOUT_OPTIONS = {
    "standard": {
        "label": "Standard",
        "description": "Media first, caption below",
        "caption_above": False,
    },
    "caption_above": {
        "label": "Caption Above",
        "description": "Caption first, media below",
        "caption_above": True,
    },
    "text_only": {
        "label": "Text Only",
        "description": "Text message without media",
        "caption_above": False,
    },
    "album": {
        "label": "Album (Multi Media)",
        "description": "Multiple media items in a group",
        "caption_above": False,
    },
}


async def render_post(
    media_type: str,
    file_id: str | None,
    caption: str,
    buttons: list[list[dict[str, str]]],
    reactions: list[str] | None = None,
    reaction_counts: dict[str, int] | None = None,
    comments_url: str | None = None,
    caption_above: bool = False,
    media_files: list[dict[str, str]] | None = None,
    client: Any = None,
    chat_id: int | None = None,
) -> dict:
    reply_markup = _build_keyboard(buttons, reactions, reaction_counts, comments_url)
    parsed_caption = build_telegram_caption_html(caption)
    result = {
        "media_type": media_type,
        "caption": parsed_caption,
        "reply_markup": reply_markup,
        "parse_mode": ParseMode.HTML,
    }

    if media_type == "text":
        result["text"] = parsed_caption
    elif media_type == "album" and media_files:
        media_list = []
        for mf in media_files:
            if mf["media_type"] == "photo":
                media_list.append(InputMediaPhoto(mf["file_id"]))
            elif mf["media_type"] in ("video", "animation"):
                media_list.append(InputMediaVideo(mf["file_id"]))
        result["media"] = media_list
    else:
        if caption_above:
            result["caption_above"] = True
            result["file_id"] = file_id
        else:
            result["file_id"] = file_id

    return result


async def render_preview(
    media_type: str,
    file_id: str | None,
    caption: str,
    buttons: list[list[dict[str, str]]],
    reactions: list[str] | None = None,
    reaction_counts: dict[str, int] | None = None,
    comments_url: str | None = None,
    caption_above: bool = False,
    media_files: list[dict[str, str]] | None = None,
    client: Any = None,
    user_id: int | None = None,
):
    result = await render_post(
        media_type=media_type,
        file_id=file_id,
        caption=caption,
        buttons=buttons,
        reactions=reactions,
        reaction_counts=reaction_counts,
        comments_url=comments_url,
        caption_above=caption_above,
        media_files=media_files,
        client=client,
        chat_id=user_id,
    )

    if not client or not user_id:
        return result

    if media_type == "text":
        await client.send_message(
            chat_id=user_id,
            text=result["caption"],
            reply_markup=result["reply_markup"],
            parse_mode=ParseMode.HTML,
        )
    elif media_type == "album" and result.get("media"):
        if media_files:
            for mf in media_files:
                if mf["media_type"] == "photo":
                    result["media"].append(InputMediaPhoto(mf["file_id"]))
                elif mf["media_type"] in ("video", "animation"):
                    result["media"].append(InputMediaVideo(mf["file_id"]))
        await client.send_media_group(chat_id=user_id, media=result["media"])
        await client.send_message(
            chat_id=user_id,
            text=result["caption"],
            reply_markup=result["reply_markup"],
            parse_mode=ParseMode.HTML,
        )
    else:
        if caption_above:
            await client.send_message(
                chat_id=user_id,
                text=result["caption"],
                reply_markup=result["reply_markup"],
                parse_mode=ParseMode.HTML,
            )
            await client.send_cached_media(chat_id=user_id, file_id=file_id)
        else:
            await client.send_cached_media(
                chat_id=user_id,
                file_id=file_id,
                caption=result["caption"],
                reply_markup=result["reply_markup"],
                parse_mode=ParseMode.HTML,
            )

    return result


async def send_post(
    client: Any,
    chat_id: int,
    media_type: str,
    file_id: str | None,
    caption: str,
    buttons: list[list[dict[str, str]]],
    reactions: list[str] | None = None,
    reaction_counts: dict[str, int] | None = None,
    comments_url: str | None = None,
    caption_above: bool = False,
    media_files: list[dict[str, str]] | None = None,
) -> Any | None:
    reply_markup = _build_keyboard(buttons, reactions, reaction_counts, comments_url)
    parsed_caption = build_telegram_caption_html(caption)
    sent_msg = None

    try:
        if media_type == "text":
            sent_msg = await client.send_message(
                chat_id=chat_id,
                text=parsed_caption,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
            )
        elif media_type == "album":
            media_list = []
            if media_files:
                for mf in media_files:
                    if mf["media_type"] == "photo":
                        media_list.append(InputMediaPhoto(mf["file_id"]))
                    elif mf["media_type"] in ("video", "animation"):
                        media_list.append(InputMediaVideo(mf["file_id"]))
            if media_list:
                await client.send_media_group(chat_id=chat_id, media=media_list)
            sent_msg = await client.send_message(
                chat_id=chat_id,
                text=parsed_caption or "👇",
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
            )
        else:
            if caption_above:
                sent_msg = await client.send_message(
                    chat_id=chat_id,
                    text=parsed_caption,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML,
                )
                await client.send_cached_media(chat_id=chat_id, file_id=file_id)
            else:
                sent_msg = await client.send_cached_media(
                    chat_id=chat_id,
                    file_id=file_id,
                    caption=parsed_caption,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML,
                )
    except Exception as e:
        logger.error(f"Failed to send post to {chat_id}: {e}")
        return None

    return sent_msg


def _build_keyboard(
    buttons_spec: list[list[dict[str, str]]],
    reactions: list[str] | None = None,
    reaction_counts: dict[str, int] | None = None,
    comments_url: str | None = None,
) -> InlineKeyboardMarkup | None:
    keyboard = []

    if buttons_spec:
        for row in buttons_spec:
            keyboard_row = []
            for btn in row:
                keyboard_row.append(
                    InlineKeyboardButton(text=btn["text"], url=btn.get("url", ""))
                )
            keyboard.append(keyboard_row)

    if reactions:
        reaction_row = []
        counts = reaction_counts or {}
        for emoji in reactions:
            count = counts.get(emoji, 0)
            btn_text = f"{emoji} {count}" if count > 0 else emoji
            reaction_row.append(
                InlineKeyboardButton(text=btn_text, callback_data=f"react_click_{emoji}")
            )
        keyboard.append(reaction_row)

    if comments_url:
        keyboard.append([InlineKeyboardButton("💬 Comments", url=comments_url)])

    return InlineKeyboardMarkup(keyboard) if keyboard else None
