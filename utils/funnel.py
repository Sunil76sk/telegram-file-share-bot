from __future__ import annotations

import re

VALID_SOURCES = {"instagram", "youtube", "movie_review", "ott", "ai_content"}
ASSET_TYPES = {"wallpapers", "subtitles", "templates", "resource_packs", "educational"}


def parse_campaign_payload(payload: str) -> dict:
    result: dict = {"campaign_id": None, "source": None, "ref": None}
    if not payload:
        return result
    parts = payload.split("&")
    for part in parts:
        if part.startswith("cmp_"):
            result["campaign_id"] = part
        elif part.startswith("src_"):
            source = part.replace("src_", "", 1)
            if source in VALID_SOURCES:
                result["source"] = source
        elif part.startswith("ref_"):
            result["ref"] = part
    if not result["campaign_id"] and parts:
        first = parts[0]
        if not first.startswith(("src_", "ref_")):
            result["campaign_id"] = first
    return result


def is_valid_campaign_id(campaign_id: str) -> bool:
    return bool(re.match(r"^cmp_[a-zA-Z0-9_-]{3,64}$", campaign_id))


def is_valid_source(source: str) -> bool:
    return source in VALID_SOURCES


def is_valid_asset_type(asset_type: str) -> bool:
    return asset_type in ASSET_TYPES


def format_funnel_link(
    bot_username: str,
    campaign_id: str,
    source: str | None = None,
    ref: str | None = None,
) -> str:
    parts = [campaign_id]
    if source:
        parts.append(f"src_{source}")
    if ref:
        parts.append(ref)
    payload = "&".join(parts)
    return f"https://t.me/{bot_username}?start={payload}"


def source_display_name(source: str) -> str:
    names = {
        "instagram": "📸 Instagram Reel",
        "youtube": "🎬 YouTube Short",
        "movie_review": "🎥 Movie Review",
        "ott": "📺 OTT Content",
        "ai_content": "🤖 AI Content",
    }
    return names.get(source, source)


def asset_type_display_name(asset_type: str) -> str:
    names = {
        "wallpapers": "🖼 Wallpapers",
        "subtitles": "📝 Subtitles",
        "templates": "📋 Templates",
        "resource_packs": "📦 Resource Packs",
        "educational": "📚 Educational Materials",
    }
    return names.get(asset_type, asset_type)
