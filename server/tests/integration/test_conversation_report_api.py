"""
Integration tests for Conversation Report API

Covers the two endpoints under
  /api/v1/agents/{agent_id}/conversation-report/{overview,trend}
"""
import time
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from tests.conftest import make_auth_header

TENANT_ID = "T_TEST_REPORT"
HEADERS = make_auth_header(TENANT_ID)
UTC = timezone.utc


def _unique(prefix: str) -> str:
    return f"{prefix}-{int(time.time() * 1000) % 100000}"


async def _create_agent(client: AsyncClient) -> int:
    resp = await client.post(
        "/api/v1/agents",
        json={"name": _unique("agent-rpt"), "description": "report test"},
        headers=HEADERS,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_conversation(
    client: AsyncClient,
    agent_id: int,
    *,
    source: str = "websdk",
    is_test: bool = False,
    started_at: datetime | None = None,
) -> int:
    payload = {
        "agent_id": agent_id,
        "user_id": "u1",
        "source": source,
        "is_test": is_test,
    }
    resp = await client.post(
        f"/api/v1/agents/{agent_id}/conversations", json=payload, headers=HEADERS
    )
    assert resp.status_code == 201, resp.text
    conv_id = resp.json()["id"]

    if started_at is not None:
        from app.db.session import AsyncSessionLocal
        from app.models.conversation import Conversation
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(Conversation)
                .where(Conversation.id == conv_id)
                .values(started_at=started_at)
            )
            await session.commit()

    return conv_id


async def _create_step(
    client: AsyncClient,
    agent_id: int,
    conv_id: int,
    *,
    step_type: str,
    round_number: int = 1,
    created_at: datetime | None = None,
    feedback_rating: str | None = None,
) -> int:
    resp = await client.post(
        f"/api/v1/agents/{agent_id}/conversations/{conv_id}/steps",
        json={
            "round_number": round_number,
            "step_type": step_type,
            "content": "x",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    step_id = resp.json()["id"]

    if created_at is not None or feedback_rating is not None:
        from app.db.session import AsyncSessionLocal
        from app.models.conversation_step import ConversationStep
        async with AsyncSessionLocal() as session:
            values: dict = {}
            if created_at is not None:
                values["created_at"] = created_at
            if feedback_rating is not None:
                values["feedback_rating"] = feedback_rating
                values["feedback_updated_at"] = created_at or datetime.now(UTC)
            await session.execute(
                update(ConversationStep)
                .where(ConversationStep.id == step_id)
                .values(**values)
            )
            await session.commit()

    return step_id


class TestConversationReportOverview:

    @pytest.mark.asyncio
    async def test_happy_path_counts_and_rates(self, client: AsyncClient):
        agent_id = await _create_agent(client)

        # In-range conversation #1 with messages and feedback
        t0 = datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
        conv1 = await _create_conversation(
            client, agent_id, source="websdk", started_at=t0
        )
        await _create_step(
            client, agent_id, conv1,
            step_type="user_message", created_at=t0,
        )
        await _create_step(
            client, agent_id, conv1,
            step_type="user_message", round_number=2, created_at=t0 + timedelta(minutes=1),
        )
        await _create_step(
            client, agent_id, conv1,
            step_type="assistant_message", round_number=3, created_at=t0 + timedelta(minutes=2),
            feedback_rating="like",
        )
        await _create_step(
            client, agent_id, conv1,
            step_type="assistant_message", round_number=4, created_at=t0 + timedelta(minutes=3),
            feedback_rating="dislike",
        )

        # In-range conversation #2: no user_message → not effective
        conv2 = await _create_conversation(
            client, agent_id, source="api", started_at=t0 + timedelta(hours=1)
        )
        await _create_step(
            client, agent_id, conv2,
            step_type="assistant_message", created_at=t0 + timedelta(hours=1),
        )

        # Out-of-range conversation: should be excluded by started_at window
        await _create_conversation(
            client, agent_id, source="websdk",
            started_at=datetime(2026, 4, 1, tzinfo=UTC),
        )

        # Excluded: is_test=true
        conv_test = await _create_conversation(
            client, agent_id, source="websdk", is_test=True, started_at=t0,
        )
        await _create_step(client, agent_id, conv_test, step_type="user_message", created_at=t0)

        # Excluded: source=testchat (we cannot create directly via API since
        # `testchat` is accepted; verify it does not leak into stats)
        conv_tc = await _create_conversation(
            client, agent_id, source="testchat", started_at=t0,
        )
        await _create_step(client, agent_id, conv_tc, step_type="user_message", created_at=t0)

        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversation-report/overview",
            params={
                "started_at_from": "2026-05-12T00:00:00+00:00",
                "started_at_to": "2026-05-19T00:00:00+00:00",
            },
            headers=HEADERS,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["session_count"] == 2  # conv1 + conv2 (both source in {websdk, api})
        assert data["effective_session_count"] == 1  # only conv1
        assert data["user_message_count"] == 2
        assert data["agent_message_count"] == 3  # 2 from conv1 + 1 from conv2
        assert data["reply_rate"] == 150.0  # 3 / 2 = 1.5 — kept as is for visibility
        assert data["like_count"] == 1
        assert data["dislike_count"] == 1
        assert data["like_rate"] == 50.0
        assert data["dislike_rate"] == 50.0

    @pytest.mark.asyncio
    async def test_empty_range_returns_zeros_and_null_rates(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversation-report/overview",
            params={
                "started_at_from": "2026-05-12T00:00:00+00:00",
                "started_at_to": "2026-05-19T00:00:00+00:00",
            },
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_count"] == 0
        assert data["user_message_count"] == 0
        assert data["reply_rate"] is None
        assert data["like_rate"] is None
        assert data["dislike_rate"] is None

    @pytest.mark.asyncio
    async def test_missing_query_returns_422(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversation-report/overview",
            headers=HEADERS,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_start_after_end_returns_400(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversation-report/overview",
            params={
                "started_at_from": "2026-05-20T00:00:00+00:00",
                "started_at_to": "2026-05-19T00:00:00+00:00",
            },
            headers=HEADERS,
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_range_exceeds_366_days_returns_400(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversation-report/overview",
            params={
                "started_at_from": "2024-01-01T00:00:00+00:00",
                "started_at_to": "2026-05-19T00:00:00+00:00",
            },
            headers=HEADERS,
        )
        assert resp.status_code == 400


class TestConversationReportTrend:

    @pytest.mark.asyncio
    async def test_hour_granularity_fills_gaps(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        # Two activity buckets: 14:00 and 16:00 (15:00 should be 0-filled)
        t14 = datetime(2026, 5, 19, 14, 5, tzinfo=UTC)
        t16 = datetime(2026, 5, 19, 16, 5, tzinfo=UTC)
        c1 = await _create_conversation(client, agent_id, source="websdk", started_at=t14)
        await _create_step(client, agent_id, c1, step_type="user_message", created_at=t14)
        await _create_step(
            client, agent_id, c1, step_type="assistant_message",
            round_number=2, created_at=t14 + timedelta(minutes=1), feedback_rating="like",
        )
        c2 = await _create_conversation(client, agent_id, source="api", started_at=t16)
        await _create_step(client, agent_id, c2, step_type="user_message", created_at=t16)

        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversation-report/trend",
            params={
                "started_at_from": "2026-05-19T14:00:00+00:00",
                "started_at_to": "2026-05-19T17:00:00+00:00",
                "granularity": "hour",
            },
            headers=HEADERS,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["granularity"] == "hour"
        assert len(data["buckets"]) == 3

        b0, b1, b2 = data["buckets"]
        assert b0["session_count"] == 1
        assert b0["user_message_count"] == 1
        assert b0["agent_message_count"] == 1
        assert b0["like_count"] == 1
        assert b0["reply_rate"] == 100.0
        assert b0["like_rate"] == 100.0

        assert b1["session_count"] == 0
        assert b1["reply_rate"] is None
        assert b1["like_rate"] is None

        assert b2["session_count"] == 1
        assert b2["user_message_count"] == 1
        assert b2["agent_message_count"] == 0
        assert b2["reply_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_hour_granularity_keeps_same_clock_time_on_different_days(
        self, client: AsyncClient
    ):
        agent_id = await _create_agent(client)
        t_day1 = datetime(2026, 5, 19, 14, 5, tzinfo=UTC)
        t_day2 = datetime(2026, 5, 20, 14, 5, tzinfo=UTC)
        c1 = await _create_conversation(
            client, agent_id, source="websdk", started_at=t_day1
        )
        await _create_step(
            client, agent_id, c1, step_type="user_message", created_at=t_day1
        )
        c2 = await _create_conversation(
            client, agent_id, source="api", started_at=t_day2
        )
        await _create_step(
            client, agent_id, c2, step_type="user_message", created_at=t_day2
        )

        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversation-report/trend",
            params={
                "started_at_from": "2026-05-19T00:00:00+00:00",
                "started_at_to": "2026-05-21T00:00:00+00:00",
                "granularity": "hour",
            },
            headers=HEADERS,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data["buckets"]) == 48

        active = [b for b in data["buckets"] if b["session_count"] > 0]
        assert len(active) == 2
        assert {b["session_count"] for b in active} == {1, 1}
        assert sum(b["session_count"] for b in data["buckets"]) == 2

    @pytest.mark.asyncio
    async def test_trend_excludes_messages_from_sessions_started_outside_range(
        self, client: AsyncClient
    ):
        agent_id = await _create_agent(client)
        conv_id = await _create_conversation(
            client,
            agent_id,
            source="websdk",
            started_at=datetime(2026, 5, 18, 23, 50, tzinfo=UTC),
        )
        await _create_step(
            client,
            agent_id,
            conv_id,
            step_type="user_message",
            created_at=datetime(2026, 5, 19, 0, 10, tzinfo=UTC),
        )

        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversation-report/trend",
            params={
                "started_at_from": "2026-05-19T00:00:00+00:00",
                "started_at_to": "2026-05-19T01:00:00+00:00",
                "granularity": "hour",
            },
            headers=HEADERS,
        )
        assert resp.status_code == 200, resp.text
        bucket = resp.json()["buckets"][0]
        assert bucket["session_count"] == 0
        assert bucket["effective_session_count"] == 0
        assert bucket["user_message_count"] == 0

    @pytest.mark.asyncio
    async def test_reconciliation_overview_equals_sum_of_trend(
        self, client: AsyncClient
    ):
        agent_id = await _create_agent(client)
        t0 = datetime(2026, 5, 19, 14, 30, tzinfo=UTC)
        c1 = await _create_conversation(client, agent_id, source="websdk", started_at=t0)
        await _create_step(client, agent_id, c1, step_type="user_message", created_at=t0)
        await _create_step(
            client, agent_id, c1, step_type="assistant_message",
            round_number=2, created_at=t0 + timedelta(seconds=10), feedback_rating="like",
        )
        c2 = await _create_conversation(client, agent_id, source="api",
                                        started_at=t0 + timedelta(hours=1))
        await _create_step(client, agent_id, c2, step_type="user_message",
                           created_at=t0 + timedelta(hours=1))

        params = {
            "started_at_from": "2026-05-19T14:00:00+00:00",
            "started_at_to": "2026-05-19T17:00:00+00:00",
        }

        ov = (await client.get(
            f"/api/v1/agents/{agent_id}/conversation-report/overview",
            params=params, headers=HEADERS,
        )).json()
        tr = (await client.get(
            f"/api/v1/agents/{agent_id}/conversation-report/trend",
            params={**params, "granularity": "hour"}, headers=HEADERS,
        )).json()

        # Reconcilable counters: session_count, user_message_count, agent_message_count,
        # like_count, dislike_count (per §3.4.2 可对账关系).
        for field in ("session_count", "user_message_count", "agent_message_count",
                      "like_count", "dislike_count"):
            assert ov[field] == sum(b[field] for b in tr["buckets"]), field

    @pytest.mark.asyncio
    async def test_invalid_granularity_returns_422(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversation-report/trend",
            params={
                "started_at_from": "2026-05-12T00:00:00+00:00",
                "started_at_to": "2026-05-19T00:00:00+00:00",
                "granularity": "week",
            },
            headers=HEADERS,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_granularity_returns_422(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversation-report/trend",
            params={
                "started_at_from": "2026-05-12T00:00:00+00:00",
                "started_at_to": "2026-05-19T00:00:00+00:00",
            },
            headers=HEADERS,
        )
        assert resp.status_code == 422
