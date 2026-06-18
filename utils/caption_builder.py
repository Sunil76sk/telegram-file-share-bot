from __future__ import annotations

import html
import re
from urllib.parse import urlparse


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def _esc(value) -> str:
    """Escape any value (coerced to str) for HTML parse mode."""
    return html.escape(str(value), quote=True)


# ─── Genre / language / runtime formatting ───────────────────────────
# Relocated from TMDBClient so the movie-post flow no longer depends on TMDB.
# Visual output is intentionally identical to the previous implementation.

_GENRE_EMOJI = {
    "Action": "⚔️",
    "Comedy": "😂",
    "Drama": "🎭",
    "Horror": "🧟",
    "Romance": "💕",
    "Thriller": "😱",
    "Fantasy": "🫧",
    "Animation": "🎨",
    "Crime": "🔫",
    "Adventure": "🧗",
    "Sci-Fi": "👽",
    "Science Fiction": "👽",
    "Family": "👨‍👩‍👧‍👦",
    "Mystery": "🔍",
    "History": "📜",
    "War": "🪖",
    "Documentary": "📹",
}

_LANGUAGE_MAP = {
    "hi": "#Hindi",
    "kn": "#Kannada",
    "ta": "#Tamil",
    "te": "#Telugu",
    "ml": "#Malayalam",
    "en": "#English",
    "es": "#Spanish",
    "fr": "#French",
    "ko": "#Korean",
    "ja": "#Japanese",
}


def format_runtime(minutes: int) -> str:
    """Convert 150 -> '2h 30min'."""
    if not minutes:
        return ""
    hours = minutes // 60
    mins = minutes % 60
    if hours > 0:
        return f"{hours}h {mins}min"
    return f"{mins}min"


def format_genres(genres: list[str]) -> str:
    """Convert ['Comedy', 'Horror'] -> '😂 #Comedy 🧟 #Horror'.

    Genre names come from the bot's fixed selection list, so the output is
    trusted and does not require HTML escaping.
    """
    formatted = []
    for g in genres:
        emoji = _GENRE_EMOJI.get(g, "")
        tag_name = g.replace(" ", "")
        formatted.append(f"{emoji} #{tag_name}" if emoji else f"#{tag_name}")
    return " ".join(formatted)


def format_language(lang_code: str) -> str:
    """Convert a language code to its hashtag form (e.g. 'hi' -> '#Hindi')."""
    return _LANGUAGE_MAP.get(lang_code.lower(), f"#{lang_code.upper()}")


def _rating_display(rating) -> str | None:
    """Return a clean rating string ('6', '7.5') or None if not a positive number."""
    try:
        value = float(rating)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return str(int(value)) if value.is_integer() else str(value)


def build_movie_caption(fields: dict) -> str:
    """Assemble the fixed movie-post caption in Telegram HTML.

    Every free-text field typed by the admin (title, year, aka, runtime,
    release info) is HTML-escaped to prevent injection and broken entities.
    Genre and language are generated from fixed maps and are already safe.

    Expected ``fields`` keys: title, year, aka, rating, rating_count, runtime,
    release_info, genres (list of names), language (pre-formatted hashtag).
    Empty / "N/A" fields are omitted (Movie title is required to render).
    """
    lines: list[str] = []

    title = (fields.get("title") or "").strip()
    year = str(fields.get("year") or "").strip()
    if title:
        year_str = f" [{_esc(year)}]" if year and year != "N/A" else ""
        lines.append(f"<b>Movie:</b> {_esc(title)}{year_str}")

    aka = (fields.get("aka") or "").strip()
    if aka and aka != "N/A":
        lines.append(f"<i>Also Known As:</i> {_esc(aka)}")

    rating_disp = _rating_display(fields.get("rating"))
    if rating_disp is not None:
        rating_count = fields.get("rating_count") or 0
        runtime = (fields.get("runtime") or "").strip()
        lines.append(f"<b>Rating ⭐:</b> {rating_disp} / 10")
        runtime_part = f" {_esc(runtime)} |" if runtime and runtime != "N/A" else ""
        lines.append(f"({rating_disp} based on {_esc(rating_count)} user ratings) | |{runtime_part}")

    release = (fields.get("release_info") or "").strip()
    if release and release != "N/A":
        lines.append(f"<b>Release Info:</b> {_esc(release)}")

    genres = fields.get("genres") or []
    if genres:
        genre_str = format_genres(genres)
        if genre_str:
            lines.append(f"<b>Genre:</b> {genre_str}")

    language = (fields.get("language") or "").strip()
    if language and language != "N/A":
        lines.append(f"<b>Language:</b> {language}")

    return "\n".join(lines)


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

