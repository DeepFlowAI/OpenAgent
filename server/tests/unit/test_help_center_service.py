"""
Unit tests for Help Center service — pure logic only (URL composition).
Repository / DB-dependent paths are covered by the integration suite.
"""
from app.configs.settings import settings
from app.services.help_center_service import build_public_root_url


class TestBuildPublicRootUrl:

    def test_returns_none_when_slug_missing(self):
        assert build_public_root_url(None) is None
        assert build_public_root_url("") is None

    def test_uses_configured_host(self, monkeypatch):
        monkeypatch.setattr(settings, "PUBLIC_DOCS_HOST", "docs.example.com")
        assert (
            build_public_root_url("my-help")
            == "https://docs.example.com/hc/my-help"
        )

    def test_strips_trailing_slash_from_host(self, monkeypatch):
        monkeypatch.setattr(settings, "PUBLIC_DOCS_HOST", "docs.example.com/")
        assert (
            build_public_root_url("my-help")
            == "https://docs.example.com/hc/my-help"
        )

    def test_strips_whitespace_from_host(self, monkeypatch):
        monkeypatch.setattr(
            settings, "PUBLIC_DOCS_HOST", "  docs.example.com  "
        )
        assert (
            build_public_root_url("my-help")
            == "https://docs.example.com/hc/my-help"
        )

    def test_returns_none_when_host_empty(self, monkeypatch):
        monkeypatch.setattr(settings, "PUBLIC_DOCS_HOST", "")
        assert build_public_root_url("my-help") is None
