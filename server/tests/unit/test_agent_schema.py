"""
Unit tests for ModelConfig backward compatibility (thinking_mode → split fields).
"""
import pytest

from app.schemas.agent import ModelConfig, EngineConfig


class TestModelConfigThinkingMigration:

    def test_new_fields_default_false(self):
        cfg = ModelConfig()
        assert cfg.first_round_thinking is False
        assert cfg.subsequent_rounds_thinking is False

    def test_new_fields_explicit(self):
        cfg = ModelConfig(first_round_thinking=True, subsequent_rounds_thinking=False)
        assert cfg.first_round_thinking is True
        assert cfg.subsequent_rounds_thinking is False

    def test_legacy_thinking_mode_true_maps_to_both_true(self):
        cfg = ModelConfig(**{"thinking_mode": True})
        assert cfg.first_round_thinking is True
        assert cfg.subsequent_rounds_thinking is True

    def test_legacy_thinking_mode_false_maps_to_both_false(self):
        cfg = ModelConfig(**{"thinking_mode": False})
        assert cfg.first_round_thinking is False
        assert cfg.subsequent_rounds_thinking is False

    def test_legacy_thinking_mode_does_not_override_explicit_new_fields(self):
        cfg = ModelConfig(**{
            "thinking_mode": True,
            "first_round_thinking": False,
            "subsequent_rounds_thinking": True,
        })
        assert cfg.first_round_thinking is False
        assert cfg.subsequent_rounds_thinking is True

    def test_engine_config_merge_with_legacy_data(self):
        raw = {
            "model": {
                "model_name": "gpt-4o",
                "thinking_mode": True,
                "temperature": 0.5,
            }
        }
        config = EngineConfig(**{**EngineConfig().model_dump(), **raw})
        assert config.model.first_round_thinking is True
        assert config.model.subsequent_rounds_thinking is True
        assert config.model.temperature == 0.5

    def test_engine_config_merge_with_new_data(self):
        raw = {
            "model": {
                "model_name": "gpt-4o",
                "first_round_thinking": False,
                "subsequent_rounds_thinking": True,
            }
        }
        config = EngineConfig(**{**EngineConfig().model_dump(), **raw})
        assert config.model.first_round_thinking is False
        assert config.model.subsequent_rounds_thinking is True

    def test_no_thinking_fields_at_all_defaults(self):
        raw = {"model": {"model_name": "kimi-k2.5"}}
        config = EngineConfig(**{**EngineConfig().model_dump(), **raw})
        assert config.model.first_round_thinking is False
        assert config.model.subsequent_rounds_thinking is False
