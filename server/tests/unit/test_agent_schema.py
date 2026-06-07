"""
Unit tests for ModelConfig backward compatibility (thinking_mode → split fields).
"""
import pytest
from pydantic import ValidationError

from app.schemas.agent import (
    ContextConfig,
    ModelConfig,
    EngineConfig,
    EngineConfigUpdate,
)


DEFAULT_TOOL_CALL_LIMIT_REPLY = (
    "抱歉，本轮回复已达到工具调用上限，暂时无法继续处理。请简化问题、缩小查询范围或稍后重试。"
)


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


class TestContextConfig:

    def test_max_tool_loop_rounds_defaults_to_20(self):
        config = ContextConfig()

        assert config.max_tool_loop_rounds == 20

    def test_max_tool_loop_rounds_accepts_custom_value(self):
        config = ContextConfig(max_tool_loop_rounds=3)

        assert config.max_tool_loop_rounds == 3

    def test_max_tool_loop_rounds_must_be_positive(self):
        with pytest.raises(ValidationError):
            ContextConfig(max_tool_loop_rounds=0)

    def test_max_tool_loop_rounds_caps_at_100(self):
        with pytest.raises(ValidationError):
            ContextConfig(max_tool_loop_rounds=101)


class TestConversationSettingsConfig:

    def test_conversation_settings_defaults_to_disabled(self):
        config = EngineConfig()

        welcome = config.conversation_settings.welcome_message
        assert welcome.enabled is False
        assert welcome.blocks == []
        disclaimer = config.conversation_settings.ai_disclaimer
        assert disclaimer.enabled is False
        assert disclaimer.content == "本内容由AI生成，仅供参考"
        tool_limit_reply = config.conversation_settings.tool_call_limit_reply
        assert tool_limit_reply.enabled is True
        assert tool_limit_reply.content == DEFAULT_TOOL_CALL_LIMIT_REPLY

    def test_welcome_message_accepts_markdown_and_embed_blocks(self):
        config = EngineConfig(
            conversation_settings={
                "welcome_message": {
                    "enabled": True,
                    "blocks": [
                        {"type": "markdown", "content": "您好，我是智能助手。"},
                        {
                            "type": "embed",
                            "embed_code": "<iframe src=\"https://example.com\"></iframe>",
                            "height": 360,
                        },
                    ],
                }
            }
        )

        welcome = config.conversation_settings.welcome_message
        assert welcome.enabled is True
        assert welcome.blocks[0].type == "markdown"
        assert welcome.blocks[1].type == "embed"

    def test_embed_height_must_be_positive(self):
        with pytest.raises(ValidationError):
            EngineConfig(
                conversation_settings={
                    "welcome_message": {
                        "enabled": True,
                        "blocks": [
                            {
                                "type": "embed",
                                "embed_code": "<iframe></iframe>",
                                "height": 0,
                            }
                        ],
                    }
                }
            )

    def test_ai_disclaimer_accepts_enabled_plain_text(self):
        config = EngineConfig(
            conversation_settings={
                "ai_disclaimer": {
                    "enabled": True,
                    "content": "AI 内容仅供参考，请自行判断。",
                }
            }
        )

        disclaimer = config.conversation_settings.ai_disclaimer
        assert disclaimer.enabled is True
        assert disclaimer.content == "AI 内容仅供参考，请自行判断。"

    def test_ai_disclaimer_requires_content_when_enabled(self):
        with pytest.raises(ValidationError):
            EngineConfig(
                conversation_settings={
                    "ai_disclaimer": {
                        "enabled": True,
                        "content": "   ",
                    }
                }
            )

    def test_ai_disclaimer_content_has_max_length(self):
        with pytest.raises(ValidationError):
            EngineConfig(
                conversation_settings={
                    "ai_disclaimer": {
                        "enabled": True,
                        "content": "a" * 201,
                    }
                }
            )

    def test_tool_call_limit_reply_accepts_enabled_markdown(self):
        config = EngineConfig(
            conversation_settings={
                "tool_call_limit_reply": {
                    "enabled": True,
                    "content": "**工具调用已达上限**\n\n- 请缩小范围后重试\n- 或查看 [帮助文档](https://example.com/help)",
                }
            }
        )

        reply = config.conversation_settings.tool_call_limit_reply
        assert reply.enabled is True
        assert reply.content == (
            "**工具调用已达上限**\n\n"
            "- 请缩小范围后重试\n"
            "- 或查看 [帮助文档](https://example.com/help)"
        )

    def test_tool_call_limit_reply_requires_content_when_enabled(self):
        with pytest.raises(ValidationError):
            EngineConfig(
                conversation_settings={
                    "tool_call_limit_reply": {
                        "enabled": True,
                        "content": "   ",
                    }
                }
            )

    def test_tool_call_limit_reply_content_has_max_length(self):
        with pytest.raises(ValidationError):
            EngineConfig(
                conversation_settings={
                    "tool_call_limit_reply": {
                        "enabled": True,
                        "content": "a" * 301,
                    }
                }
            )


class TestEngineConfigSystemPrompt:

    def test_system_prompt_accepts_30000_chars(self):
        config = EngineConfig(system_prompt="a" * 30000)

        assert len(config.system_prompt) == 30000

    def test_system_prompt_rejects_more_than_30000_chars(self):
        with pytest.raises(ValidationError):
            EngineConfigUpdate(system_prompt="a" * 30001)

    def test_engine_config_update_json_schema_exposes_30000_char_limit(self):
        schema = EngineConfigUpdate.model_json_schema()
        system_prompt_schema = schema["properties"]["system_prompt"]

        assert system_prompt_schema["anyOf"][0]["maxLength"] == 30000


class TestEngineConfigUpdate:

    def test_conversation_settings_update_requires_complete_section_object(self):
        with pytest.raises(ValidationError):
            EngineConfigUpdate(
                conversation_settings={
                    "ai_disclaimer": {
                        "content": "新免责声明",
                    }
                }
            )

    def test_conversation_settings_update_accepts_single_complete_section(self):
        update = EngineConfigUpdate(
            conversation_settings={
                "ai_disclaimer": {
                    "enabled": True,
                    "content": "AI 内容仅供参考。",
                },
            }
        )

        assert update.conversation_settings is not None
        assert update.conversation_settings.ai_disclaimer.enabled is True

    def test_conversation_settings_update_accepts_multiple_complete_sections(self):
        update = EngineConfigUpdate(
            conversation_settings={
                "welcome_message": {
                    "enabled": False,
                    "blocks": [],
                },
                "ai_disclaimer": {
                    "enabled": True,
                    "content": "AI 内容仅供参考。",
                },
                "tool_call_limit_reply": {
                    "enabled": True,
                    "content": "**工具调用已达上限**",
                },
            }
        )

        assert update.conversation_settings is not None
        assert update.conversation_settings.welcome_message.blocks == []
        assert (
            update.conversation_settings.tool_call_limit_reply.content
            == "**工具调用已达上限**"
        )
