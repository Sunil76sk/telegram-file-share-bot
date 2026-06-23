from __future__ import annotations

import datetime
import json
import logging
import re
from typing import Any

from database.mongo import db

logger = logging.getLogger(__name__)

MOVIE_META_COL = db["movie_metadata"]
MEDIA_LIBRARY_COL = db["media_library"]


GENRE_KEYWORDS: dict[str, list[str]] = {
    "action": [
        "action",
        "thriller",
        "war",
        "mission",
        "combat",
        "fight",
        "explosive",
        "fast",
    ],
    "comedy": ["comedy", "funny", "humor", "laugh", "comic", "sitcom"],
    "drama": ["drama", "emotional", "heartfelt", "intense", "powerful"],
    "horror": ["horror", "scary", "thriller", "creepy", "haunted", "paranormal"],
    "romance": ["romance", "love", "romantic", "rom-com", "romantic comedy"],
    "sci-fi": [
        "sci-fi",
        "science fiction",
        "space",
        "future",
        "futuristic",
        "alien",
        "cyberpunk",
    ],
    "fantasy": ["fantasy", "magic", "mythical", "supernatural", "wizard"],
    "thriller": ["thriller", "suspense", "psychological", "mystery", "crime"],
    "animation": ["animation", "animated", "cartoon", "anime", "pixar", "disney"],
    "documentary": ["documentary", "docu", "real story", "true story", "biography"],
    "adventure": ["adventure", "journey", "exploration", "quest", "epic"],
    "musical": ["musical", "music", "concert", "band", "dance"],
}


async def extract_movie_metadata(
    title: str,
    description: str | None = None,
    year: int | None = None,
    genre: str | None = None,
    language: str | None = None,
    imdb_id: str | None = None,
    poster_url: str | None = None,
    rating: float | None = None,
    duration_minutes: int | None = None,
    director: str | None = None,
    cast_list: list[str] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "title": title,
        "description": description or "",
        "year": year,
        "genre": genre or _infer_genre(title, description),
        "language": language or "en",
        "imdb_id": imdb_id,
        "poster_url": poster_url,
        "rating": rating,
        "duration_minutes": duration_minutes,
        "director": director,
        "cast": cast_list or [],
        "search_terms": _generate_search_terms(title, year),
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "updated_at": datetime.datetime.now(datetime.timezone.utc),
    }
    return metadata


async def save_movie_metadata(metadata: dict[str, Any]) -> str:
    result = await MOVIE_META_COL.insert_one(metadata)
    logger.info(f"Movie metadata saved: {metadata.get('title')}")
    return str(result.inserted_id)


async def get_movie_metadata(movie_id: str) -> dict | None:
    from bson import ObjectId

    try:
        return await MOVIE_META_COL.find_one({"_id": ObjectId(movie_id)})
    except Exception:
        return None


async def search_movies(
    query: str,
    genre: str | None = None,
    year: int | None = None,
    language: str | None = None,
    limit: int = 20,
    skip: int = 0,
) -> list[dict]:
    search_filter: dict = {}

    if query:
        search_filter["$or"] = [
            {"title": {"$regex": query, "$options": "i"}},
            {"search_terms": {"$regex": query, "$options": "i"}},
            {"description": {"$regex": query, "$options": "i"}},
        ]
    if genre:
        search_filter["genre"] = genre
    if year:
        search_filter["year"] = year
    if language:
        search_filter["language"] = language

    cursor = (
        MOVIE_META_COL.find(search_filter)
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def update_movie_metadata(movie_id: str, updates: dict) -> bool:
    from bson import ObjectId

    updates["updated_at"] = datetime.datetime.now(datetime.timezone.utc)
    try:
        result = await MOVIE_META_COL.update_one(
            {"_id": ObjectId(movie_id)}, {"$set": updates}
        )
        return result.modified_count > 0
    except Exception:
        return False


async def delete_movie_metadata(movie_id: str) -> bool:
    from bson import ObjectId

    try:
        result = await MOVIE_META_COL.delete_one({"_id": ObjectId(movie_id)})
        return result.deleted_count > 0
    except Exception:
        return False


async def add_to_media_library(
    user_id: int,
    file_id: str,
    file_name: str,
    file_size: int,
    media_type: str,
    metadata_id: str | None = None,
    tags: list[str] | None = None,
) -> str:
    doc = {
        "user_id": user_id,
        "file_id": file_id,
        "file_name": file_name,
        "file_size": file_size,
        "media_type": media_type,
        "metadata_id": metadata_id,
        "tags": tags or [],
        "download_count": 0,
        "created_at": datetime.datetime.now(datetime.timezone.utc),
    }
    result = await MEDIA_LIBRARY_COL.insert_one(doc)
    return str(result.inserted_id)


async def get_media_library(
    user_id: int,
    media_type: str | None = None,
    limit: int = 50,
    skip: int = 0,
) -> list[dict]:
    query: dict = {"user_id": user_id}
    if media_type:
        query["media_type"] = media_type
    cursor = (
        MEDIA_LIBRARY_COL.find(query).sort("created_at", -1).skip(skip).limit(limit)
    )
    return [doc async for doc in cursor]


async def remove_from_media_library(library_id: str, user_id: int) -> bool:
    from bson import ObjectId

    try:
        result = await MEDIA_LIBRARY_COL.delete_one(
            {"_id": ObjectId(library_id), "user_id": user_id}
        )
        return result.deleted_count > 0
    except Exception:
        return False


async def increment_media_download(library_id: str) -> bool:
    from bson import ObjectId

    try:
        result = await MEDIA_LIBRARY_COL.update_one(
            {"_id": ObjectId(library_id)}, {"$inc": {"download_count": 1}}
        )
        return result.modified_count > 0
    except Exception:
        return False


def _infer_genre(title: str, description: str | None = None) -> str:
    combined = f"{title} {description or ''}".lower()
    scores: dict[str, int] = {}
    for genre, keywords in GENRE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score > 0:
            scores[genre] = score
    if scores:
        return max(scores, key=scores.get)
    return "general"


def _generate_search_terms(title: str, year: int | None = None) -> list[str]:
    terms = set()
    words = re.sub(r"[^\w\s]", " ", title).split()
    for w in words:
        if len(w) > 2:
            terms.add(w.lower())
    if year:
        terms.add(str(year))
    return list(terms)


async def import_existing_post(
    user_id: int,
    channel_id: int | str,
    message_id: int,
    client: Any,
) -> dict | None:
    try:
        from pyrogram import Client

        if not isinstance(client, Client):
            logger.error("Invalid client for import_existing_post")
            return None

        msg = await client.get_messages(channel_id, message_id)
        if not msg:
            return None

        draft = {
            "user_id": user_id,
            "channel_id": channel_id,
            "media_type": "text",
            "file_id": None,
            "media_files": [],
            "caption": msg.text or msg.caption or "",
            "buttons": [],
            "reactions": [],
            "reactions_enabled": False,
            "comments": False,
            "comments_enabled": False,
            "caption_above": False,
            "pin": False,
            "pin_message": False,
            "state": "active",
            "imported_from": message_id,
            "created_at": datetime.datetime.now(datetime.timezone.utc),
        }

        if msg.photo:
            draft["media_type"] = "photo"
            draft["file_id"] = msg.photo.file_id
        elif msg.video:
            draft["media_type"] = "video"
            draft["file_id"] = msg.video.file_id
        elif msg.document:
            draft["media_type"] = "document"
            draft["file_id"] = msg.document.file_id
        elif msg.audio:
            draft["media_type"] = "audio"
            draft["file_id"] = msg.audio.file_id
        elif msg.animation:
            draft["media_type"] = "animation"
            draft["file_id"] = msg.animation.file_id

        from database.creator_db import save_post_draft

        await save_post_draft(user_id, draft)
        logger.info(
            f"Imported post {message_id} from channel {channel_id} for user {user_id}"
        )
        return draft
    except Exception as e:
        logger.error(f"Failed to import post: {e}")
        return None


async def fetch_movie_from_api(title: str, year: int | None = None) -> dict | None:
    """Fetch movie details dynamically from TMDB or OMDB API using env credentials."""
    import urllib.request
    import urllib.parse
    import json
    import os
    import asyncio

    tmdb_key = os.getenv("TMDB_API_KEY")
    omdb_key = os.getenv("OMDB_API_KEY")

    if tmdb_key:
        try:
            query = urllib.parse.quote(title)
            url = f"https://api.themoviedb.org/3/search/movie?api_key={tmdb_key}&query={query}"
            if year:
                url += f"&year={year}"

            def _get():
                req = urllib.request.Request(
                    url, headers={"Accept": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=5) as r:
                    return json.loads(r.read().decode("utf-8"))

            res = await asyncio.to_thread(_get)
            if res.get("results"):
                movie = res["results"][0]
                movie_id = movie["id"]
                detail_url = (
                    f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={tmdb_key}"
                )

                def _get_details():
                    with urllib.request.urlopen(detail_url, timeout=5) as r:
                        return json.loads(r.read().decode("utf-8"))

                details = await asyncio.to_thread(_get_details)

                poster_path = details.get("poster_path")
                poster_url = (
                    f"https://image.tmdb.org/t/p/w500{poster_path}"
                    if poster_path
                    else None
                )

                return {
                    "title": details.get("title", title),
                    "description": details.get("overview", ""),
                    "year": (
                        int(details.get("release_date", "0000").split("-")[0])
                        if details.get("release_date")
                        else year
                    ),
                    "genre": (
                        ", ".join([g["name"] for g in details.get("genres", [])])
                        if details.get("genres")
                        else "general"
                    ),
                    "language": details.get("original_language", "en"),
                    "imdb_id": details.get("imdb_id"),
                    "poster_url": poster_url,
                    "rating": details.get("vote_average", 0.0),
                    "duration_minutes": details.get("runtime", 0),
                    "director": "",
                    "cast": [],
                }
        except Exception as e:
            logger.error(f"Error fetching from TMDB: {e}")

    if omdb_key:
        try:
            query = urllib.parse.quote(title)
            url = f"http://www.omdbapi.com/?apikey={omdb_key}&t={query}"
            if year:
                url += f"&y={year}"

            def _get():
                with urllib.request.urlopen(url, timeout=5) as r:
                    return json.loads(r.read().decode("utf-8"))

            res = await asyncio.to_thread(_get)
            if res.get("Response") == "True":
                runtime_str = res.get("Runtime", "0").split()[0]
                try:
                    duration = int(runtime_str)
                except ValueError:
                    duration = 0
                return {
                    "title": res.get("Title", title),
                    "description": res.get("Plot", ""),
                    "year": (
                        int(res.get("Year", "0"))
                        if res.get("Year", "").isdigit()
                        else year
                    ),
                    "genre": res.get("Genre", "general"),
                    "language": res.get("Language", "en"),
                    "imdb_id": res.get("imdbID"),
                    "poster_url": (
                        res.get("Poster") if res.get("Poster") != "N/A" else None
                    ),
                    "rating": (
                        float(res.get("imdbRating", 0.0))
                        if res.get("imdbRating") != "N/A"
                        else 0.0
                    ),
                    "duration_minutes": duration,
                    "director": res.get("Director", ""),
                    "cast": [
                        c.strip() for c in res.get("Actors", "").split(",") if c.strip()
                    ],
                }
        except Exception as e:
            logger.error(f"Error fetching from OMDB: {e}")

    return None
