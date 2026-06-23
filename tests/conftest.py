import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_db():
    """Mock all database collections and functions."""
    with patch("database.users_col") as users_col, patch(
        "database.post_drafts_col"
    ) as drafts_col, patch("database.scheduled_posts_col") as scheduled_col, patch(
        "database.repost_jobs_col"
    ) as repost_col, patch(
        "database.templates_col"
    ) as templates_col, patch(
        "database.channels_col"
    ) as channels_col, patch(
        "database.purchases_col"
    ) as purchases_col, patch(
        "database.products_col"
    ) as products_col, patch(
        "database.channel_stats_col"
    ) as stats_col:

        users_col.find_one = AsyncMock(return_value=None)
        users_col.update_one = AsyncMock()
        users_col.find = AsyncMock(return_value=[])
        drafts_col.find_one = AsyncMock(return_value=None)
        drafts_col.update_one = AsyncMock()
        drafts_col.delete_one = AsyncMock()
        scheduled_col.find = AsyncMock(return_value=[])
        scheduled_col.insert_one = AsyncMock(
            return_value=MagicMock(inserted_id="test_id")
        )
        scheduled_col.update_one = AsyncMock()
        scheduled_col.delete_one = AsyncMock()
        repost_col.find = AsyncMock(return_value=[])
        repost_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="test_id"))
        repost_col.update_one = AsyncMock()
        repost_col.delete_one = AsyncMock()
        templates_col.find = AsyncMock(return_value=[])
        templates_col.find_one = AsyncMock(return_value=None)
        templates_col.insert_one = AsyncMock()
        templates_col.delete_one = AsyncMock()
        channels_col.find = AsyncMock(return_value=[])
        channels_col.find_one = AsyncMock(return_value=None)
        channels_col.update_one = AsyncMock()
        purchases_col.count_documents = AsyncMock(return_value=0)
        purchases_col.insert_one = AsyncMock()
        purchases_col.find_one = AsyncMock(return_value=None)
        products_col.find_one = AsyncMock(return_value=None)
        stats_col.update_one = AsyncMock()

        yield {
            "users": users_col,
            "drafts": drafts_col,
            "scheduled": scheduled_col,
            "repost": repost_col,
            "templates": templates_col,
            "channels": channels_col,
            "purchases": purchases_col,
            "products": products_col,
            "stats": stats_col,
        }


@pytest.fixture
def mock_client():
    """Mock Pyrogram Client."""
    client = AsyncMock()
    client.me = MagicMock(username="test_bot", id=123456)
    client.send_message = AsyncMock()
    client.send_photo = AsyncMock(return_value=MagicMock(id=999))
    client.send_video = AsyncMock(return_value=MagicMock(id=999))
    client.send_cached_media = AsyncMock(return_value=MagicMock(id=999))
    client.send_media_group = AsyncMock()
    client.edit_message_text = AsyncMock()
    client.edit_message_reply_markup = AsyncMock()
    client.pin_chat_message = AsyncMock()
    client.delete_messages = AsyncMock()
    client.get_chat = AsyncMock(
        return_value=MagicMock(linked_chat=None, linked_chat_id=None)
    )
    client.get_chat_member = AsyncMock()
    return client
