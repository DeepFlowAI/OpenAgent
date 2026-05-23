"""
Integration tests for Conversation API
"""
import csv
from io import StringIO
import time
import pytest
from httpx import AsyncClient

from tests.conftest import make_auth_header

TENANT_ID = "T_TEST_CONV"
HEADERS = make_auth_header(TENANT_ID)


def unique_name(prefix: str) -> str:
    return f"{prefix}-{int(time.time() * 1000) % 100000}"


async def _create_agent(client: AsyncClient) -> int:
    """Helper: create an agent and return its ID."""
    payload = {"name": unique_name("agent"), "description": "Agent for conversation tests"}
    resp = await client.post("/api/v1/agents", json=payload, headers=HEADERS)
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_conversation(
    client: AsyncClient, agent_id: int, **overrides
) -> dict:
    """Helper: create a conversation and return its data."""
    payload = {
        "agent_id": agent_id,
        "user_id": "test_user_001",
        "source": "api",
        **overrides,
    }
    resp = await client.post(
        f"/api/v1/agents/{agent_id}/conversations", json=payload, headers=HEADERS
    )
    assert resp.status_code == 201
    return resp.json()


async def _create_channel(client: AsyncClient, **overrides) -> dict:
    payload = {"name": unique_name("conv-ch"), **overrides}
    resp = await client.post("/api/v1/channels", json=payload, headers=HEADERS)
    assert resp.status_code == 201
    return resp.json()


async def _create_step(
    client: AsyncClient, agent_id: int, conv_id: int, **overrides
) -> dict:
    """Helper: create a conversation step and return its data."""
    payload = {
        "round_number": 1,
        "step_type": "user_message",
        "content": "Hello",
        **overrides,
    }
    resp = await client.post(
        f"/api/v1/agents/{agent_id}/conversations/{conv_id}/steps",
        json=payload,
        headers=HEADERS,
    )
    assert resp.status_code == 201
    return resp.json()


class TestConversationAPI:

    @pytest.mark.asyncio
    async def test_list_conversations_returns_200(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversations",
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data

    @pytest.mark.asyncio
    async def test_create_conversation_returns_201(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        data = await _create_conversation(client, agent_id)
        assert data["agent_id"] == agent_id
        assert data["tenant_id"] == TENANT_ID
        assert data["status"] == "active"
        assert data["source"] == "api"
        assert data["channel_id"] is None
        assert data["channel_name"] is None
        assert data["external_id"].startswith("conv_")
        assert data["round_count"] == 0
        assert data["total_tokens"] == 0

    @pytest.mark.asyncio
    async def test_create_conversation_websdk_channel(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        channel = await _create_channel(client)
        data = await _create_conversation(
            client,
            agent_id,
            source="websdk",
            channel_id=channel["id"],
        )
        assert data["source"] == "websdk"
        assert data["channel_id"] == channel["id"]
        assert data["channel_name"] == channel["name"]

    @pytest.mark.asyncio
    async def test_get_conversation_returns_200(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        created = await _create_conversation(client, agent_id)
        conv_id = created["id"]

        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversations/{conv_id}", headers=HEADERS
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == conv_id
        assert "duration_seconds" in data

    @pytest.mark.asyncio
    async def test_get_nonexistent_conversation_returns_404(
        self, client: AsyncClient
    ):
        agent_id = await _create_agent(client)
        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversations/99999", headers=HEADERS
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_end_conversation(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        created = await _create_conversation(client, agent_id)
        conv_id = created["id"]

        resp = await client.post(
            f"/api/v1/agents/{agent_id}/conversations/{conv_id}/end", headers=HEADERS
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ended"
        assert data["ended_at"] is not None

    @pytest.mark.asyncio
    async def test_filter_by_status(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        created = await _create_conversation(client, agent_id)
        conv_id = created["id"]

        await client.post(
            f"/api/v1/agents/{agent_id}/conversations/{conv_id}/end", headers=HEADERS
        )

        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversations",
            params={"status_filter": "ended"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        for item in data["items"]:
            assert item["status"] == "ended"

    @pytest.mark.asyncio
    async def test_filter_by_source(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        await _create_conversation(client, agent_id, source="api")

        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversations",
            params={"source": "api"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        for item in data["items"]:
            assert item["source"] == "api"

    @pytest.mark.asyncio
    async def test_filter_by_multiple_sources(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        await _create_conversation(client, agent_id, source="websdk")
        await _create_conversation(client, agent_id, source="testchat")
        await _create_conversation(client, agent_id, source="api")

        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversations",
            params={"source": "websdk,testchat"},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        sources = {item["source"] for item in data["items"]}
        assert sources <= {"websdk", "testchat"}
        assert {"websdk", "testchat"} <= sources

    @pytest.mark.asyncio
    async def test_filter_by_channel_id_and_channel_source(
        self, client: AsyncClient
    ):
        agent_id = await _create_agent(client)
        channel = await _create_channel(client, agent_id=agent_id)
        other_channel = await _create_channel(client, agent_id=agent_id)
        matched = await _create_conversation(
            client,
            agent_id,
            source="websdk",
            channel_id=channel["id"],
            channel_source="official_site",
        )
        await _create_conversation(
            client,
            agent_id,
            source="websdk",
            channel_id=other_channel["id"],
            channel_source="official_site",
        )
        await _create_conversation(
            client,
            agent_id,
            source="websdk",
            channel_id=channel["id"],
            channel_source="docs_site",
        )

        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversations",
            params={
                "channel_id": str(channel["id"]),
                "channel_source": "official_site",
            },
            headers=HEADERS,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == matched["id"]

    @pytest.mark.asyncio
    async def test_filter_by_message_content_limits_to_user_and_assistant(
        self, client: AsyncClient
    ):
        agent_id = await _create_agent(client)
        user_match = await _create_conversation(client, agent_id)
        assistant_match = await _create_conversation(client, agent_id)
        excluded_tool = await _create_conversation(client, agent_id)

        await _create_step(
            client,
            agent_id,
            user_match["id"],
            step_type="user_message",
            content="Needle appears in user text",
        )
        await _create_step(
            client,
            agent_id,
            assistant_match["id"],
            step_type="assistant_message",
            content="Needle appears in assistant text",
        )
        await _create_step(
            client,
            agent_id,
            excluded_tool["id"],
            step_type="tool_call",
            content="Needle appears in tool content",
        )

        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversations",
            params={"message_content": "Needle"},
            headers=HEADERS,
        )

        assert resp.status_code == 200
        data = resp.json()
        ids = {item["id"] for item in data["items"]}
        assert user_match["id"] in ids
        assert assistant_match["id"] in ids
        assert excluded_tool["id"] not in ids

    @pytest.mark.asyncio
    async def test_channel_options_only_returns_agent_web_sdk_channels(
        self, client: AsyncClient
    ):
        agent_id = await _create_agent(client)
        other_agent_id = await _create_agent(client)
        bound = await _create_channel(client, agent_id=agent_id, channel_type="web-sdk")
        await _create_channel(client, agent_id=other_agent_id, channel_type="web-sdk")
        await _create_channel(client, agent_id=agent_id, channel_type="wechat")
        await _create_channel(client, channel_type="web-sdk")

        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversations/channel-options",
            headers=HEADERS,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == [{"id": bound["id"], "name": bound["name"]}]

    @pytest.mark.asyncio
    async def test_filter_by_conversation_id(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        created = await _create_conversation(client, agent_id)
        external_id = created["external_id"]

        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversations",
            params={"conversation_id": external_id},
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["external_id"] == external_id

    @pytest.mark.asyncio
    async def test_export_conversations_uses_filters_and_ignores_pagination(
        self, client: AsyncClient
    ):
        agent_id = await _create_agent(client)
        match_1 = await _create_conversation(client, agent_id, source="websdk")
        match_2 = await _create_conversation(client, agent_id, source="websdk")
        excluded = await _create_conversation(client, agent_id, source="api")

        await _create_step(
            client,
            agent_id,
            match_1["id"],
            content="first user",
            client_message_id="cmid-export-1",
        )
        llm_step = await _create_step(
            client,
            agent_id,
            match_1["id"],
            step_type="llm_call",
            thinking_content="think one",
            input_tokens=10,
            output_tokens=5,
        )
        await _create_step(
            client,
            agent_id,
            match_1["id"],
            step_type="tool_call",
            tool_name="search",
            brief="Search AI",
            parent_step_id=llm_step["id"],
        )
        await _create_step(
            client,
            agent_id,
            match_1["id"],
            step_type="assistant_message",
            content="first assistant",
        )
        await _create_step(
            client,
            agent_id,
            match_2["id"],
            content="second user",
        )
        await _create_step(
            client,
            agent_id,
            match_2["id"],
            step_type="assistant_message",
            content="second assistant",
        )
        await _create_step(
            client,
            agent_id,
            excluded["id"],
            content="excluded user",
        )

        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversations/export",
            params={"source": "websdk", "page": 1, "per_page": 1},
            headers=HEADERS,
        )

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        rows = list(csv.reader(StringIO(resp.content.decode("utf-8-sig"))))
        assert rows[0][:4] == ["会话 ID", "会话内部 ID", "会话开始时间", "轮次"]

        data_rows = rows[1:]
        exported_messages = [row[7] for row in data_rows]
        assert "first user" in exported_messages
        assert "second user" in exported_messages
        assert "excluded user" not in exported_messages

        first_row = next(row for row in data_rows if row[7] == "first user")
        assert first_row[5] == "cmid-export-1"
        assert first_row[8] == "think one\n\n---\n\ntool：Search AI"
        assert first_row[9] == "first assistant"
        assert first_row[10] == "10"
        assert first_row[11] == "5"
        assert first_row[12] == "false"

    @pytest.mark.asyncio
    async def test_create_missing_required_field_returns_422(
        self, client: AsyncClient
    ):
        agent_id = await _create_agent(client)
        resp = await client.post(
            f"/api/v1/agents/{agent_id}/conversations", json={}, headers=HEADERS
        )
        assert resp.status_code == 422
