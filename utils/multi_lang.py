from __future__ import annotations

import logging
from typing import Any

from database.mongo import db

logger = logging.getLogger(__name__)

LANG_COL = db["translations"]
USER_LANG_COL = db["user_language"]

SUPPORTED_LANGUAGES = {
    "en": "English",
    "hi": "हिन्दी",
    "bn": "বাংলা",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "pt": "Português",
    "ru": "Русский",
    "ar": "العربية",
    "id": "Bahasa Indonesia",
    "ms": "Bahasa Melayu",
    "th": "ไทย",
    "vi": "Tiếng Việt",
    "ko": "한국어",
    "zh": "中文",
    "ja": "日本語",
}

DEFAULT_LANG = "en"

_strings: dict[str, dict[str, str]] = {}
_loaded = False


async def load_translations():
    global _strings, _loaded
    _strings = {}
    cursor = LANG_COL.find({})
    async for doc in cursor:
        lang = doc.get("language", DEFAULT_LANG)
        key = doc.get("key")
        value = doc.get("value", key or "")
        if lang not in _strings:
            _strings[lang] = {}
        if key:
            _strings[lang][key] = value
    _loaded = True
    logger.info(f"Loaded {len(_strings)} languages from database")


def get_string(key: str, lang: str = DEFAULT_LANG, **kwargs: Any) -> str:
    if not _loaded:
        return key.replace("_", " ").title()

    lang_code = lang if lang in _strings else DEFAULT_LANG
    text = _strings.get(lang_code, {}).get(key)

    if text is None and lang_code != DEFAULT_LANG:
        text = _strings.get(DEFAULT_LANG, {}).get(key)

    if text is None:
        text = key.replace("_", " ").title()

    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError:
            pass
    return text


async def set_translation(lang: str, key: str, value: str):
    await LANG_COL.update_one(
        {"language": lang, "key": key},
        {"$set": {"value": value}},
        upsert=True,
    )
    if lang in _strings:
        _strings[lang][key] = value
    logger.info(f"Translation set: lang={lang} key={key}")


async def bulk_set_translations(lang: str, translations: dict[str, str]):
    for key, value in translations.items():
        await set_translation(lang, key, value)
    logger.info(f"Bulk loaded {len(translations)} translations for {lang}")


async def get_user_lang(user_id: int) -> str:
    doc = await USER_LANG_COL.find_one({"_id": user_id})
    return doc.get("language", DEFAULT_LANG) if doc else DEFAULT_LANG


async def set_user_lang(user_id: int, lang: str):
    if lang not in SUPPORTED_LANGUAGES:
        logger.warning(f"Unsupported language '{lang}' for user {user_id}")
        return
    await USER_LANG_COL.update_one(
        {"_id": user_id},
        {"$set": {"language": lang}},
        upsert=True,
    )
    logger.info(f"User {user_id} language set to {lang}")


async def export_translations() -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    cursor = LANG_COL.find({})
    async for doc in cursor:
        lang = doc.get("language", DEFAULT_LANG)
        key = doc.get("key")
        value = doc.get("value", "")
        if lang not in result:
            result[lang] = {}
        if key:
            result[lang][key] = value
    return result


async def import_translations(data: dict[str, dict[str, str]]):
    for lang, strings in data.items():
        await bulk_set_translations(lang, strings)
    global _strings, _loaded
    await load_translations()
    logger.info(f"Imported translations for {len(data)} languages")
