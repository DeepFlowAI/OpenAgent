"""
Unit tests for Channel schema config normalization.
"""
import pytest
from pydantic import ValidationError

from app.schemas.channel import ChannelUpdate


class TestChannelSchemaConfig:

    def test_same_page_allowlist_normalizes_and_deduplicates_patterns(self):
        data = ChannelUpdate(
            config={
                "samePageNavigationUrlAllowlist": [
                    "  HTTPS://Login.EXAMPLE.com/*  ",
                    "",
                    "https://login.example.com/*",
                    "https://*.example.com/oauth/*",
                ]
            }
        )

        assert data.config == {
            "samePageNavigationUrlAllowlist": [
                "https://login.example.com/*",
                "https://*.example.com/oauth/*",
            ]
        }

    @pytest.mark.parametrize("pattern", ["https://*", "javascript:*"])
    def test_same_page_allowlist_rejects_invalid_patterns(self, pattern: str):
        with pytest.raises(ValidationError):
            ChannelUpdate(config={"samePageNavigationUrlAllowlist": [pattern]})

    def test_same_page_allowlist_rejects_too_many_patterns(self):
        with pytest.raises(ValidationError):
            ChannelUpdate(
                config={
                    "samePageNavigationUrlAllowlist": [
                        f"https://login{i}.example.com/*" for i in range(51)
                    ]
                }
            )
