"""
Unit tests for public channel welcome-message projection.
"""
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.routers.v1.public import get_public_channel


def _channel(agent_id: int | None = 7):
    channel_token = "test-channel-id"
    return SimpleNamespace(
        id=1,
        **{"token": channel_token},
        name="Website",
        description=None,
        channel_type="web-sdk",
        agent_id=agent_id,
        access_mode="embed",
        config={},
        tenant_id="T_SECRET",
        secret_key="csk_secret",
        created_at=datetime(2026, 5, 16, tzinfo=UTC),
        updated_at=datetime(2026, 5, 16, tzinfo=UTC),
    )


class TestPublicChannelWelcomeMessage:

    @pytest.mark.asyncio
    async def test_get_public_channel_projects_welcome_message_without_secrets(
        self, monkeypatch: pytest.MonkeyPatch,
    ):
        async def fake_get_channel_by_token(db, token: str):
            return _channel(agent_id=7)

        async def fake_get_agent_by_id(db, agent_id: int):
            return SimpleNamespace(
                id=agent_id,
                engine_config={
                    "conversation_settings": {
                        "welcome_message": {
                            "enabled": True,
                            "blocks": [
                                {
                                    "type": "markdown",
                                    "content": "欢迎使用公开渠道。",
                                }
                            ],
                        },
                        "ai_disclaimer": {
                            "enabled": True,
                            "content": "AI 内容仅供参考。",
                        },
                        "faq": {
                            "enabled": True,
                            "title": "热点问题",
                            "categories": [
                                {
                                    "name": "明星爆款",
                                    "questions": [
                                        {"text": "哪款奶瓶更适合我家宝宝呢？"}
                                    ],
                                }
                            ],
                        },
                        "tool_call_limit_reply": {
                            "enabled": True,
                            "content": "**工具调用已达上限**\n\n请缩小范围后重试。",
                        },
                    }
                },
            )

        monkeypatch.setattr(
            "app.routers.v1.public.ChannelService.get_by_token",
            fake_get_channel_by_token,
        )
        monkeypatch.setattr(
            "app.routers.v1.public.AgentService.get_by_id",
            fake_get_agent_by_id,
        )

        response = await get_public_channel("public-token", db=None)
        data = response.model_dump()

        assert "tenant_id" not in data
        assert "secret_key" not in data
        welcome = data["conversation_settings"]["welcome_message"]
        assert welcome["enabled"] is True
        assert welcome["blocks"] == [
            {"type": "markdown", "content": "欢迎使用公开渠道。"}
        ]
        disclaimer = data["conversation_settings"]["ai_disclaimer"]
        assert disclaimer == {
            "enabled": True,
            "content": "AI 内容仅供参考。",
        }
        faq = data["conversation_settings"]["faq"]
        assert faq == {
            "enabled": True,
            "title": "热点问题",
            "categories": [
                {
                    "name": "明星爆款",
                    "questions": [
                        {"text": "哪款奶瓶更适合我家宝宝呢？"}
                    ],
                }
            ],
        }
        tool_limit_reply = data["conversation_settings"]["tool_call_limit_reply"]
        assert tool_limit_reply == {
            "enabled": True,
            "content": "**工具调用已达上限**\n\n请缩小范围后重试。",
        }

    @pytest.mark.asyncio
    async def test_get_public_channel_defaults_welcome_message_when_unbound(
        self, monkeypatch: pytest.MonkeyPatch,
    ):
        async def fake_get_channel_by_token(db, token: str):
            return _channel(agent_id=None)

        monkeypatch.setattr(
            "app.routers.v1.public.ChannelService.get_by_token",
            fake_get_channel_by_token,
        )

        response = await get_public_channel("public-token", db=None)

        assert response.conversation_settings.welcome_message.enabled is False
        assert response.conversation_settings.welcome_message.blocks == []
        assert response.conversation_settings.ai_disclaimer.enabled is False
        assert (
            response.conversation_settings.ai_disclaimer.content
            == "本内容由AI生成，仅供参考"
        )
        assert response.conversation_settings.faq.enabled is False
        assert response.conversation_settings.faq.title == "常见问题"
        assert response.conversation_settings.faq.categories == []
        assert response.conversation_settings.tool_call_limit_reply.enabled is True
        assert (
            response.conversation_settings.tool_call_limit_reply.content
            == "抱歉，本轮回复已达到工具调用上限，暂时无法继续处理。请简化问题、缩小查询范围或稍后重试。"
        )
