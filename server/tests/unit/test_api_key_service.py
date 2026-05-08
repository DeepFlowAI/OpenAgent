"""
Unit tests for API Key service
"""
import pytest

from app.services.api_key_service import (
    _generate_key, _mask_key, _validate_scopes, _scopes_to_list,
    KEY_PREFIX, VALID_SCOPES,
)


class TestApiKeyGeneration:

    def test_generate_key_starts_with_prefix(self):
        key = _generate_key()
        assert key.startswith(KEY_PREFIX)

    def test_generate_key_has_correct_length(self):
        key = _generate_key()
        assert len(key) == 3 + 48  # "sk-" + 48 hex chars

    def test_generate_key_is_unique(self):
        keys = {_generate_key() for _ in range(50)}
        assert len(keys) == 50

    def test_mask_key_hides_middle(self):
        # Synthetic value (not a real key, no `sk-` prefix) so secret scanners
        # don't flag this fixture. The mask logic only cares about length /
        # prefix slicing, not the prefix string itself.
        key = "fake-test-aaaabbbbccccddddeeeeffff11112222333344445555"
        masked = _mask_key(key)
        assert masked.startswith(key[:7])
        assert masked.endswith(key[-4:])
        assert "••••••••••••" in masked

    def test_mask_key_does_not_expose_full_key(self):
        key = _generate_key()
        masked = _mask_key(key)
        assert key != masked
        assert len(masked) < len(key)


class TestScopeValidation:

    def test_validate_scopes_single_chat(self):
        result = _validate_scopes(["chat"])
        assert result == "chat"

    def test_validate_scopes_single_config(self):
        result = _validate_scopes(["config"])
        assert result == "config"

    def test_validate_scopes_both_sorted(self):
        result = _validate_scopes(["config", "chat"])
        assert result == "chat,config"

    def test_validate_scopes_deduplicates(self):
        result = _validate_scopes(["chat", "chat"])
        assert result == "chat"

    def test_validate_scopes_empty_raises(self):
        from app.core.exceptions import ValidationError
        with pytest.raises(ValidationError):
            _validate_scopes([])

    def test_validate_scopes_invalid_raises(self):
        from app.core.exceptions import ValidationError
        with pytest.raises(ValidationError):
            _validate_scopes(["chat", "admin"])


class TestScopeConversion:

    def test_scopes_to_list_single(self):
        assert _scopes_to_list("chat") == ["chat"]

    def test_scopes_to_list_multiple(self):
        assert _scopes_to_list("chat,config") == ["chat", "config"]

    def test_scopes_to_list_with_spaces(self):
        assert _scopes_to_list("chat , config") == ["chat", "config"]

    def test_scopes_to_list_empty(self):
        assert _scopes_to_list("") == []
