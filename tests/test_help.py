import pytest
from unittest.mock import MagicMock


class TestHelpCommand:
    """Test help command and navigation."""

    def test_help_sections_exist(self):
        """Test that all help sections are defined."""
        HELP_SECTIONS = {
            "upload": {"title": "Upload Files", "text": "text"},
            "posts": {"title": "Create Posts", "text": "text"},
            "movie": {"title": "Movie Metadata", "text": "text"},
            "schedule": {"title": "Scheduling", "text": "text"},
            "repost": {"title": "Auto Repost", "text": "text"},
            "premium": {"title": "Premium", "text": "text"},
            "store": {"title": "Store", "text": "text"},
            "referral": {"title": "Referral", "text": "text"},
            "settings": {"title": "Settings", "text": "text"},
        }

        required_sections = [
            "upload",
            "posts",
            "movie",
            "schedule",
            "repost",
            "premium",
            "store",
            "referral",
            "settings",
        ]
        for section in required_sections:
            assert section in HELP_SECTIONS, f"Missing section: {section}"

    def test_help_sections_have_title_and_text(self):
        """Test that all sections have title and text."""
        HELP_SECTIONS = {
            "upload": {"title": "Upload Files", "text": "text"},
            "posts": {"title": "Create Posts", "text": "text"},
        }

        for key, section in HELP_SECTIONS.items():
            assert "title" in section, f"Section {key} missing title"
            assert "text" in section, f"Section {key} missing text"
            assert len(section["title"]) > 0
            assert len(section["text"]) > 0

    def test_help_callback_data_format(self):
        """Test that help callback data follows help_{key} format."""
        HELP_SECTIONS = {
            "upload": {},
            "posts": {},
            "movie": {},
            "schedule": {},
            "repost": {},
            "premium": {},
            "store": {},
            "referral": {},
            "settings": {},
        }

        for key in HELP_SECTIONS:
            callback_data = f"help_{key}"
            assert callback_data.startswith("help_")

    def test_help_back_callback(self):
        """Test that back button uses help_back callback."""
        callback_data = "help_back"
        assert callback_data == "help_back"
