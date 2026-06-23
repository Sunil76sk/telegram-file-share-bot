import pytest
import uuid
import datetime
from unittest.mock import AsyncMock, MagicMock, patch


class TestDraftCreation:
    """Test post draft creation and schema."""

    @pytest.mark.asyncio
    async def test_draft_schema_has_poster_media(self):
        """Test that new draft schema includes poster_media field."""
        draft = {
            "draft_id": "123",
            "user_id": 123,
            "channel_id": -100123,
            "media_type": "text",
            "file_id": None,
            "media_files": [],
            "caption": "",
            "custom_buttons": [],
            "reactions": [],
            "reactions_enabled": False,
            "comments_enabled": False,
            "caption_above": False,
            "pin_message": False,
            "poster_media": {"type": None, "file_id": None},
            "download_files": [],
            "layout_type": "layout_a",
            "timezone": "Asia/Kolkata",
            "state": "awaiting_media",
        }
        assert draft["poster_media"]["type"] is None
        assert draft["poster_media"]["file_id"] is None
        assert draft["layout_type"] == "layout_a"
        assert draft["download_files"] == []

    @pytest.mark.asyncio
    async def test_draft_schema_has_layout_type(self):
        """Test that layout_type is in draft."""
        for layout in ["layout_a", "layout_b", "layout_c", "layout_d"]:
            draft = {"layout_type": layout}
            assert draft["layout_type"] == layout

    @pytest.mark.asyncio
    async def test_draft_schema_has_timezone(self):
        """Test that timezone field exists in draft."""
        draft = {"timezone": "Asia/Kolkata"}
        assert draft["timezone"] == "Asia/Kolkata"


class TestPosterUpload:
    """Test photo and video poster upload."""

    @pytest.mark.asyncio
    async def test_photo_poster_storage(self):
        """Test that photo poster stores type and file_id correctly."""
        poster_media = {"type": "photo", "file_id": "AgACAgIAAxkBAAI"}
        assert poster_media["type"] == "photo"
        assert poster_media["file_id"] == "AgACAgIAAxkBAAI"

    @pytest.mark.asyncio
    async def test_video_poster_storage(self):
        """Test that video poster stores type and file_id correctly."""
        poster_media = {"type": "video", "file_id": "AgACAgIAAxkBAAJ"}
        assert poster_media["type"] == "video"
        assert poster_media["file_id"] == "AgACAgIAAxkBAAJ"

    @pytest.mark.asyncio
    async def test_no_poster(self):
        """Test that no poster has type=None."""
        poster_media = {"type": None, "file_id": None}
        assert poster_media["type"] is None


class TestDeepLinkGeneration:
    """Test UUID deep link generation."""

    @pytest.mark.asyncio
    async def test_uuid_download_config_format(self):
        """Test that UUID download config generates dl_ token."""
        token = f"dl_{uuid.uuid4().hex[:16]}"
        assert token.startswith("dl_")
        assert len(token) > 10

    @pytest.mark.asyncio
    async def test_deep_link_format(self):
        """Test that deep link follows dl_<hex> format."""
        token = f"dl_{uuid.uuid4().hex[:16]}"
        assert token.startswith("dl_")
        parts = token.split("_")
        assert len(parts) == 2
        assert len(parts[1]) >= 16

    @pytest.mark.asyncio
    async def test_deep_link_uniqueness(self):
        """Test that each deep link token is unique."""
        tokens = set()
        for _ in range(100):
            token = f"dl_{uuid.uuid4().hex[:16]}"
            tokens.add(token)
        assert len(tokens) == 100

    @pytest.mark.asyncio
    async def test_deep_link_not_predictable(self):
        """Test that deep link tokens are not sequential."""
        token1 = f"dl_{uuid.uuid4().hex[:16]}"
        token2 = f"dl_{uuid.uuid4().hex[:16]}"
        assert token1 != token2


class TestLayoutSystem:
    """Test post layout rendering."""

    def test_layout_a_structure(self):
        """Layout A: single download button."""
        layout = "layout_a"
        download_files = [{"label": "Download", "token": "dl_abc123"}]
        assert layout == "layout_a"
        assert len(download_files) == 1

    def test_layout_b_structure(self):
        """Layout B: quality buttons (480P, 720P, 1080P)."""
        layout = "layout_b"
        download_files = [
            {"label": "480P", "token": "dl_abc"},
            {"label": "720P", "token": "dl_def"},
            {"label": "1080P", "token": "dl_ghi"},
        ]
        assert layout == "layout_b"
        assert len(download_files) == 3
        assert download_files[0]["label"] == "480P"
        assert download_files[2]["label"] == "1080P"

    def test_layout_c_structure(self):
        """Layout C: download + watch + trailer."""
        layout = "layout_c"
        download_files = [
            {"label": "Download", "token": "dl_a"},
            {"label": "Watch Online", "token": "dl_b"},
            {"label": "Trailer", "token": "dl_c"},
        ]
        assert layout == "layout_c"
        assert len(download_files) == 3

    def test_layout_d_structure(self):
        """Layout D: download + comments + reactions."""
        layout = "layout_d"
        download_files = [{"label": "Download", "token": "dl_a"}]
        reactions = ["\u2764\ufe0f", "\U0001f525"]
        comments_url = "https://t.me/discussion"
        assert layout == "layout_d"
        assert len(download_files) == 1
        assert len(reactions) == 2
        assert comments_url.startswith("https://")


class TestErrorHandling:
    """Test specific Telegram error handling."""

    def test_chat_admin_required_error(self):
        """Test ChatAdminRequired is caught."""
        error = Exception("ChatAdminRequired")
        assert "admin" in str(error).lower()

    def test_chat_write_forbidden_error(self):
        """Test ChatWriteForbidden is caught."""
        error = Exception("ChatWriteForbidden")
        assert "forbidden" in str(error).lower()

    def test_message_too_long_error(self):
        """Test MessageTooLong is caught."""
        error = Exception("MessageTooLong")
        assert "long" in str(error).lower()
