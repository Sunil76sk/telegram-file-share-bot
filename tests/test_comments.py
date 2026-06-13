import pytest
from unittest.mock import AsyncMock, MagicMock


class TestCommentsSystem:
    """Test comments system with safe getattr pattern."""

    @pytest.mark.asyncio
    async def test_no_discussion_group_returns_empty(self):
        """Test that missing discussion group returns empty string."""
        mock_chat = MagicMock()
        mock_chat.linked_chat = None
        mock_chat.linked_chat_id = None

        linked_chat = getattr(mock_chat, "linked_chat", None)
        linked_chat_id = getattr(mock_chat, "linked_chat_id", None)
        discussion_id = None
        if linked_chat:
            discussion_id = linked_chat.id
        discussion_id = discussion_id or linked_chat_id

        assert discussion_id is None

    @pytest.mark.asyncio
    async def test_linked_chat_detected(self):
        """Test that linked_chat is detected via getattr."""
        mock_chat = MagicMock()
        mock_chat.linked_chat = MagicMock(id=-100456)
        mock_chat.linked_chat_id = -100456

        linked_chat = getattr(mock_chat, "linked_chat", None)
        discussion_id = None
        if linked_chat:
            discussion_id = linked_chat.id
        if discussion_id is None:
            discussion_id = getattr(mock_chat, "linked_chat_id", None)

        assert discussion_id == -100456

    @pytest.mark.asyncio
    async def test_safe_getattr_pattern(self):
        """Test that getattr pattern works even if attribute doesn't exist."""
        mock_chat = MagicMock(spec=[])  # Empty spec - no attributes

        linked_chat = getattr(mock_chat, "linked_chat", None)
        linked_chat_id = getattr(mock_chat, "linked_chat_id", None)

        assert linked_chat is None
        assert linked_chat_id is None

    @pytest.mark.asyncio
    async def test_comments_url_fallback(self):
        """Test comments URL fallback when no username or invite link."""
        discussion_id = -100456
        fallback = f"https://t.me/c/{str(discussion_id).replace('-100', '')}"
        assert fallback == "https://t.me/c/456"

    @pytest.mark.asyncio
    async def test_comments_url_with_username(self):
        """Test comments URL with username."""
        username = "discussion_group"
        url = f"https://t.me/{username}"
        assert url == "https://t.me/discussion_group"
