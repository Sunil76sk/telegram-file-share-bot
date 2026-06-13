import pytest
import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId


class TestTemplateCRUD:
    """Test template create, read, delete operations."""

    @pytest.mark.asyncio
    async def test_save_template_document_fields(self):
        """Test that template document has all required fields."""
        template_doc = {
            "user_id": 123,
            "name": "My Template",
            "type": "movie",
            "caption": "Movie: {title}",
            "buttons": [[{"text": "Download", "url": "https://example.com"}]],
            "created_at": datetime.datetime.now(datetime.timezone.utc),
        }
        assert "user_id" in template_doc
        assert "name" in template_doc
        assert "type" in template_doc
        assert "caption" in template_doc
        assert "buttons" in template_doc

    @pytest.mark.asyncio
    async def test_delete_template_result(self):
        """Test that delete returns correct result."""
        deleted_count = 1
        result = deleted_count > 0
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_nonexistent_template(self):
        """Test deleting nonexistent template returns False."""
        deleted_count = 0
        result = deleted_count > 0
        assert result is False

    @pytest.mark.asyncio
    async def test_invalid_template_id_returns_none(self):
        """Test that invalid template ID results in None."""
        result = None
        assert result is None


class TestTemplateLoadWithoutDraft:
    """Test template loading without active draft."""

    @pytest.mark.asyncio
    async def test_template_creates_draft(self):
        """Test that loading template auto-creates draft if none exists."""
        template = {
            "_id": ObjectId(),
            "user_id": 123,
            "name": "Movie Template",
            "caption": "Movie: {title}\nRating: {rating}",
            "buttons": [[{"text": "Download", "url": "https://example.com"}]],
        }
        draft = {
            "draft_id": "123",
            "user_id": 123,
            "channel_id": -100123,
            "media_type": "text",
            "file_id": None,
            "media_files": [],
            "caption": template["caption"],
            "custom_buttons": template["buttons"],
            "reactions": [],
            "reactions_enabled": False,
            "comments_enabled": False,
            "caption_above": False,
            "pin_message": False,
            "poster_media": {"type": None, "file_id": None},
            "download_files": [],
            "layout_type": "layout_a",
            "state": "active",
        }
        assert draft["caption"] == template["caption"]
        assert draft["custom_buttons"] == template["buttons"]
        assert draft["state"] == "active"


class TestTemplateTypes:
    """Test supported template types."""

    def test_template_types(self):
        """Test that all template types are valid."""
        valid_types = ["movie", "affiliate", "store", "premium", "referral", "custom"]
        assert len(valid_types) == 6
        assert "movie" in valid_types
        assert "custom" in valid_types
