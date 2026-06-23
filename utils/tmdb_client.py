from __future__ import annotations

import logging
import urllib.parse
import urllib.request
import json
import asyncio
from database.creator_db import get_settings

logger = logging.getLogger(__name__)


class TMDBClient:
    BASE_URL = "https://api.themoviedb.org/3"
    IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

    async def _make_request(self, endpoint: str, params: dict) -> dict | None:
        """Helper to make async HTTP request to TMDB API."""
        settings = await get_settings()
        api_key = settings.get("tmdb_api_key")
        if not api_key:
            logger.warning("TMDB API Key not configured in settings.")
            return None

        params["api_key"] = api_key
        # Add default language if not specified
        if "language" not in params:
            params["language"] = settings.get("tmdb_default_language", "en")

        query_string = urllib.parse.urlencode(params)
        url = f"{self.BASE_URL}{endpoint}?{query_string}"

        def _fetch():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as response:
                    return json.loads(response.read().decode("utf-8"))
            except Exception as e:
                logger.error(f"TMDB API request failed for url {url}: {e}")
                return None

        return await asyncio.to_thread(_fetch)

    async def search_movies(self, query: str) -> list[dict]:
        """
        Search TMDB for movies.
        Returns list of:
        {
          "tmdb_id": int,
          "title": str,
          "year": str,
          "language": str,
          "poster_url": str
        }
        Max 5 results.
        Filter out results with no poster.
        """
        if not query:
            return []

        # Extract year if present in query, e.g. "Bhooth Bangla 2026"
        # We can pass the year parameter to TMDB for better results
        import re

        year_match = re.search(r"\b(19\d\d|20\d\d)\b", query)
        params = {"query": query}
        if year_match:
            params["year"] = year_match.group(1)
            # Remove year from query to search better
            params["query"] = query.replace(year_match.group(0), "").strip()

        data = await self._make_request("/search/movie", params)
        if not data or "results" not in data:
            return []

        results = []
        for item in data["results"]:
            poster_path = item.get("poster_path")
            if not poster_path:
                continue

            # Parse year from release_date
            release_date = item.get("release_date", "")
            year = release_date.split("-")[0] if release_date else "N/A"

            results.append(
                {
                    "tmdb_id": item["id"],
                    "title": item["title"],
                    "year": year,
                    "language": self.format_language(item.get("original_language", "")),
                    "poster_url": f"{self.IMAGE_BASE}{poster_path}",
                }
            )

            if len(results) >= 5:
                break

        return results

    async def get_movie_details(self, tmdb_id: int) -> dict | None:
        """
        Fetch full movie details.
        Returns details dict matching the required schema.
        """
        # We request append_to_response=release_dates,alternative_titles to get release info & also_known_as
        params = {"append_to_response": "release_dates,alternative_titles"}
        data = await self._make_request(f"/movie/{tmdb_id}", params)
        if not data:
            return None

        # Format year
        release_date_raw = data.get("release_date", "")
        year = release_date_raw.split("-")[0] if release_date_raw else "N/A"

        # Format runtime
        runtime_minutes = data.get("runtime") or 0
        runtime = self.format_runtime(runtime_minutes)

        # Get Release Info (Date + Country)
        release_date_str = "N/A"
        release_country = "N/A"
        if release_date_raw:
            # Reformat YYYY-MM-DD -> DD/MM/YYYY or keep as DD/MM/YYYY
            try:
                dt = asyncio.run_coroutine_threadsafe(
                    asyncio.to_thread(lambda: urllib.request.urlopen),  # dummy
                    asyncio.get_event_loop(),
                )  # no need, we can just split
                parts = release_date_raw.split("-")
                if len(parts) == 3:
                    release_date_str = f"{parts[2]}/{parts[1]}/{parts[0]}"
            except Exception:
                release_date_str = release_date_raw

        # Get country from release_dates or production_countries
        if data.get("production_countries"):
            release_country = data["production_countries"][0].get("name", "N/A")

        # Better: check release_dates for regional release info
        release_info = f"{release_date_str} ({release_country})"

        # Also Known As
        also_known_as = "N/A"
        alt_titles = data.get("alternative_titles", {}).get("titles", [])
        if alt_titles:
            # Pick first 2 alternative titles
            titles = [t["title"] for t in alt_titles[:2]]
            also_known_as = ", ".join(titles)

        # Genres
        genres_list = [g["name"] for g in data.get("genres", [])]

        # Poster URL
        poster_path = data.get("poster_path")
        poster_url = f"{self.IMAGE_BASE}{poster_path}" if poster_path else ""

        return {
            "tmdb_id": data["id"],
            "title": data["title"],
            "original_title": data.get("original_title", ""),
            "year": year,
            "rating": round(data.get("vote_average", 0.0), 1),
            "rating_count": data.get("vote_count", 0),
            "runtime_minutes": runtime_minutes,
            "runtime": runtime,
            "release_date": release_date_str,
            "release_country": release_country,
            "release_info": release_info,
            "genres": genres_list,
            "original_language": data.get("original_language", ""),
            "poster_url": poster_url,
            "also_known_as": also_known_as,
            "imdb_id": data.get("imdb_id"),
        }

    def format_runtime(self, minutes: int) -> str:
        """Convert 150 -> '2h 30min'"""
        if not minutes:
            return ""
        hours = minutes // 60
        mins = minutes % 60
        if hours > 0:
            return f"{hours}h {mins}min"
        return f"{mins}min"

    def format_genres(self, genres: list[str]) -> str:
        """
        Convert ["Action", "Comedy"] ->
        "⚔️ #Action, 🤣 #Comedy"
        With emoji mapping.
        """
        emoji_map = {
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
        formatted = []
        for g in genres:
            emoji = emoji_map.get(g, "")
            # Remove spaces from genre name for hashtag
            tag_name = g.replace(" ", "")
            if emoji:
                formatted.append(f"{emoji} #{tag_name}")
            else:
                formatted.append(f"#{tag_name}")
        return " ".join(formatted)

    def format_language(self, lang_code: str) -> str:
        """Convert language codes."""
        lang_map = {
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
        return lang_map.get(lang_code.lower(), f"#{lang_code.upper()}")
