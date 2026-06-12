from __future__ import annotations

import html
import re
from urllib.parse import urlparse


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def _is_safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme.lower() not in {"http", "https"}:
            return False
        if not parsed.netloc:
            return False
        return True
    except Exception:
        return False


def build_telegram_caption_html(caption: str) -> str:
    """Convert user caption to Telegram HTML.

    Supported syntax (user input):
      - Bold:    *bold*
      - Italic:  _italic_ (also supports /italic/)
      - Underline: __underline__ and ~underline~
      - Spoiler: ||spoiler||
      - Monospace: `code`
      - Preformatted: ```text``` (multiline)
      - Links:
          * [text](https://example.com)
          * raw https://example.com (auto-link)
      - Mentions/hashtags:
          * @username kept as plain text (Telegram will resolve)
          * #hashtag kept as plain text

    Anything not matching supported patterns is escaped.
    """

    if caption is None:
        caption = ""

    # 1) Escape everything first
    escaped = _escape(caption)

    # 2) Restore formatting by operating on the *escaped* text.
    #    This works because the markers (* _ __ ~ || ` ``` [ ] ( ) @ #) are not escaped.

    # Pre blocks: ```...```
    pre_re = re.compile(r"```([\s\S]*?)```")
    escaped = pre_re.sub(lambda m: f"<pre>{_escape(m.group(1))}</pre>", escaped)

    # Inline code: `...`
    code_re = re.compile(r"`([^`]+?)`")
    escaped = code_re.sub(lambda m: f"<code>{_escape(m.group(1))}</code>", escaped)

    # Spoiler: ||...||
    spoiler_re = re.compile(r"\|\|([\s\S]*?)\|\|")
    escaped = spoiler_re.sub(lambda m: f'<span class="tg-spoiler">{_escape(m.group(1))}</span>', escaped)

    # Bold: *...*
    bold_re = re.compile(r"\*([^*\n]+?)\*")
    escaped = bold_re.sub(lambda m: f"<b>{_escape(m.group(1))}</b>", escaped)

    # Italic: _..._ and /.../
    italic_re = re.compile(r"_([^_\n]+?)_")
    escaped = italic_re.sub(lambda m: f"<i>{_escape(m.group(1))}</i>", escaped)
    italic_slash_re = re.compile(r"/([^/\n]+?)/")
    escaped = italic_slash_re.sub(lambda m: f"<i>{_escape(m.group(1))}</i>", escaped)

    # Underline: __...__ and ~...~
    underline_re = re.compile(r"__([^_\n]+?)__")
    escaped = underline_re.sub(lambda m: f"<u>{_escape(m.group(1))}</u>", escaped)
    underline_tilde_re = re.compile(r"~([^~\n]+?)~")
    escaped = underline_tilde_re.sub(lambda m: f"<u>{_escape(m.group(1))}</u>", escaped)

    # Links: [text](url)
    link_re = re.compile(r"\[([^\]]+?)\]\(([^)\s]+)\)")

    def _link_sub(m: re.Match[str]) -> str:
        text_inner = m.group(1)
        url = m.group(2)
        if url.lower().startswith("tg://user"):
            return f'<a href="{_escape(url)}">{_escape(text_inner)}</a>'
        if not _is_safe_url(url):
            return _escape(m.group(0))
        return f'<a href="{_escape(url)}">{_escape(text_inner)}</a>'

    escaped = link_re.sub(_link_sub, escaped)

    # Auto-link raw https?://...
    autolink_re = re.compile(r"(https?://[^\s]+)")

    def _auto_sub(m: re.Match[str]) -> str:
        url = m.group(1)
        if not _is_safe_url(url):
            return _escape(url)
        safe_url = _escape(url)
        return f'<a href="{safe_url}">{safe_url}</a>'

    escaped = autolink_re.sub(_auto_sub, escaped)

    return escaped

