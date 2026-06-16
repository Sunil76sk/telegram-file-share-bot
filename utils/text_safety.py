"""Helpers for safely embedding untrusted user input into Telegram messages.

Most messages in this bot are sent with Pyrogram's default (combined Markdown)
parse mode. Interpolating raw user input (passwords, product names, captions)
into those strings lets a stray ``*``, ``_`` or backtick corrupt the message or
make Telegram reject the send. Use ``escape_markdown`` for those interpolations.
"""

from __future__ import annotations

import html as _html

# Characters that are significant in Pyrogram's combined Markdown parser.
_MD_SPECIALS = ("\\", "`", "*", "_", "[", "]", "~", "|")


def escape_markdown(text: str | None) -> str:
    """Escape characters that would break Pyrogram's default Markdown parsing."""
    if not text:
        return ""
    for ch in _MD_SPECIALS:
        text = text.replace(ch, "\\" + ch)
    return text


def escape_html(text: str | None) -> str:
    """Escape user input for messages sent with HTML parse mode."""
    return _html.escape(text or "", quote=True)


def truncate(text: str | None, limit: int) -> str:
    """Truncate visible text to ``limit`` characters with an ellipsis."""
    if not text:
        return ""
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text
