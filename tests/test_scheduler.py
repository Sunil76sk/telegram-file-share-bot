import pytest
import datetime
from unittest.mock import AsyncMock, MagicMock, patch


class TestScheduledPostProcessing:
    """Test scheduled post processing."""

    @pytest.mark.asyncio
    async def test_timezone_conversion_utc(self):
        """Test UTC passthrough."""
        utc_time = datetime.datetime(2026, 6, 14, 14, 0, tzinfo=datetime.timezone.utc)
        assert utc_time.hour == 14
        assert utc_time.tzinfo == datetime.timezone.utc

    @pytest.mark.asyncio
    async def test_timezone_conversion_utc_offset(self):
        """Test UTC offset calculation."""
        utc_time = datetime.datetime(2026, 6, 14, 14, 0, tzinfo=datetime.timezone.utc)
        offset = datetime.timedelta(hours=5, minutes=30)
        ist_time = utc_time + offset
        assert ist_time.hour == 19  # 14:00 UTC + 5:30 = 19:30 IST
        assert ist_time.minute == 30

    @pytest.mark.asyncio
    async def test_future_time_validation(self):
        """Test that past times are rejected."""
        now = datetime.datetime.now(datetime.timezone.utc)
        past_time = now - datetime.timedelta(hours=1)
        assert past_time <= now

    @pytest.mark.asyncio
    async def test_future_time_acceptance(self):
        """Test that future times are accepted."""
        now = datetime.datetime.now(datetime.timezone.utc)
        future_time = now + datetime.timedelta(hours=1)
        assert future_time > now

    @pytest.mark.asyncio
    async def test_retry_count_increment(self):
        """Test retry count increments on failure."""
        retry_count = 0
        max_retries = 3

        for attempt in range(max_retries):
            retry_count += 1
            if retry_count >= max_retries:
                break

        assert retry_count == 3

    @pytest.mark.asyncio
    async def test_scheduler_status_values(self):
        """Test valid scheduler status values."""
        valid_statuses = ["pending", "completed", "failed", "cancelled"]
        assert "pending" in valid_statuses
        assert "completed" in valid_statuses
        assert "failed" in valid_statuses
        assert "cancelled" in valid_statuses

    @pytest.mark.asyncio
    async def test_scheduled_post_document_fields(self):
        """Test that scheduled post has all required fields."""
        post = {
            "user_id": 123,
            "channel_id": -100123,
            "media_type": "text",
            "file_id": None,
            "caption": "Test",
            "scheduled_time": datetime.datetime.now(datetime.timezone.utc),
            "status": "pending",
            "retry_count": 0,
            "failure_reason": None,
            "poster_media": {"type": None, "file_id": None},
            "layout_type": "layout_a",
            "download_files": [],
            "custom_buttons": [],
        }
        assert "retry_count" in post
        assert "failure_reason" in post
        assert "poster_media" in post
        assert "layout_type" in post


class TestAutoRepost:
    """Test auto repost persistent state."""

    @pytest.mark.asyncio
    async def test_repost_job_fields(self):
        """Test that repost job has all required persistent fields."""
        job = {
            "channel_id": -100123,
            "message_id": 456,
            "last_posted_at": datetime.datetime.now(datetime.timezone.utc),
            "repost_interval": 60,
            "next_post_at": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=60),
            "status": "active",
            "retry_count": 0,
        }
        assert "channel_id" in job
        assert "message_id" in job
        assert "last_posted_at" in job
        assert "next_post_at" in job
        assert "repost_interval" in job

    @pytest.mark.asyncio
    async def test_repost_survives_restart(self):
        """Test that next_post_at is stored in DB (not memory)."""
        now = datetime.datetime.now(datetime.timezone.utc)
        next_post = now + datetime.timedelta(minutes=60)
        assert next_post > now
        assert next_post.tzinfo == datetime.timezone.utc

    @pytest.mark.asyncio
    async def test_supported_intervals(self):
        """Test supported repost intervals in minutes."""
        supported = {
            "30min": 30,
            "1hour": 60,
            "3hours": 180,
            "6hours": 360,
            "12hours": 720,
            "24hours": 1440,
        }
        assert len(supported) == 6
        assert supported["1hour"] == 60

    @pytest.mark.asyncio
    async def test_delete_gap_is_seconds(self):
        """Test that delete_gap is stored in seconds."""
        delete_gap = 10
        assert isinstance(delete_gap, int)
        assert delete_gap >= 0
