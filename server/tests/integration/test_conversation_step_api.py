"""
Integration tests for ConversationStep API
"""
import asyncio
import time
import pytest
from httpx import AsyncClient

from tests.conftest import make_auth_header

TENANT_ID = "T_TEST_STEP"
HEADERS = make_auth_header(TENANT_ID)


def unique_name(prefix: str) -> str:
    return f"{prefix}-{int(time.time() * 1000) % 100000}"


async def _create_agent(client: AsyncClient) -> int:
    payload = {"name": unique_name("agent"), "description": "Agent for step tests"}
    resp = await client.post("/api/v1/agents", json=payload, headers=HEADERS)
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_api_key(client: AsyncClient, scopes: list[str]) -> str:
    payload = {"name": unique_name("key"), "scopes": scopes}
    resp = await client.post("/api/v1/system/api-keys", json=payload, headers=HEADERS)
    assert resp.status_code == 201
    return resp.json()["key_value"]


async def _create_conversation(client: AsyncClient, agent_id: int) -> dict:
    payload = {"agent_id": agent_id, "user_id": "step_test_user", "source": "chat"}
    resp = await client.post(
        f"/api/v1/agents/{agent_id}/conversations", json=payload, headers=HEADERS
    )
    assert resp.status_code == 201
    return resp.json()


async def _create_step(
    client: AsyncClient, agent_id: int, conv_id: int, **overrides
) -> dict:
    payload = {
        "round_number": 1,
        "step_type": "user_message",
        "content": "Hello, agent!",
        **overrides,
    }
    resp = await client.post(
        f"/api/v1/agents/{agent_id}/conversations/{conv_id}/steps",
        json=payload,
        headers=HEADERS,
    )
    assert resp.status_code == 201
    return resp.json()


class TestConversationStepAPI:

    @pytest.mark.asyncio
    async def test_get_empty_timeline(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        conv = await _create_conversation(client, agent_id)

        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversations/{conv['id']}/steps",
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["conversation_id"] == conv["id"]
        assert data["steps"] == []
        assert data["total_steps"] == 0

    @pytest.mark.asyncio
    async def test_submit_feedback_with_api_key_updates_assistant_step(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        conv = await _create_conversation(client, agent_id)
        step = await _create_step(
            client,
            agent_id,
            conv["id"],
            step_type="assistant_message",
            content="Helpful answer",
        )
        api_key = await _create_api_key(client, ["chat"])

        resp = await client.post(
            f"/api/v1/agents/{agent_id}/conversations/{conv['id']}/steps/{step['id']}/feedback",
            json={"rating": "like", "comment": "  clear answer  "},
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["step_id"] == step["id"]
        assert data["feedback_rating"] == "like"
        assert data["feedback_comment"] == "clear answer"
        assert data["feedback_updated_at"]

    @pytest.mark.asyncio
    async def test_submit_feedback_with_api_key_requires_chat_scope(self, client: AsyncClient):
        api_key = await _create_api_key(client, ["config"])

        resp = await client.post(
            "/api/v1/agents/1/conversations/1/steps/1/feedback",
            json={"rating": "like"},
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_user_message_step(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        conv = await _create_conversation(client, agent_id)

        step = await _create_step(
            client, agent_id, conv["id"],
            step_type="user_message",
            content="What is AI?",
        )
        assert step["step_type"] == "user_message"
        assert step["content"] == "What is AI?"
        assert step["step_order"] == 1
        assert step["round_number"] == 1

    @pytest.mark.asyncio
    async def test_create_llm_call_step(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        conv = await _create_conversation(client, agent_id)

        await _create_step(
            client, agent_id, conv["id"],
            step_type="user_message",
            content="Hello",
        )

        llm_step = await _create_step(
            client, agent_id, conv["id"],
            step_type="llm_call",
            model_name="gpt-4",
            provider="openai",
            thinking_enabled=True,
            thinking_content="Let me think about this...",
            request_messages=[
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hello"},
            ],
            request_tools=[],
            request_params={"temperature": 0.7, "max_tokens": 4096},
            content="Hi there!",
            finish_reason="stop",
            input_tokens=50,
            output_tokens=10,
            total_tokens=60,
            duration_ms=1200,
        )
        assert llm_step["step_type"] == "llm_call"
        assert llm_step["model_name"] == "gpt-4"
        assert llm_step["thinking_content"] == "Let me think about this..."
        assert llm_step["step_order"] == 2
        assert llm_step["total_tokens"] == 60

    @pytest.mark.asyncio
    async def test_create_tool_call_step(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        conv = await _create_conversation(client, agent_id)

        await _create_step(client, agent_id, conv["id"])

        llm = await _create_step(
            client, agent_id, conv["id"],
            step_type="llm_call",
            model_name="gpt-4",
            provider="openai",
            response_tool_calls=[{
                "id": "call_abc123",
                "type": "function",
                "function": {"name": "search", "arguments": '{"query":"AI"}'},
            }],
            finish_reason="tool_calls",
        )

        tool_step = await _create_step(
            client, agent_id, conv["id"],
            step_type="tool_call",
            tool_name="search",
            tool_type="search",
            tool_call_id="call_abc123",
            tool_arguments={"query": "AI"},
            tool_response='{"results": []}',
            brief="Search for AI",
            parent_step_id=llm["id"],
        )
        assert tool_step["step_type"] == "tool_call"
        assert tool_step["tool_name"] == "search"
        assert tool_step["brief"] == "Search for AI"
        assert tool_step["parent_step_id"] == llm["id"]

    @pytest.mark.asyncio
    async def test_full_round_timeline(self, client: AsyncClient):
        """Test a complete round: user -> llm -> tool -> llm -> assistant"""
        agent_id = await _create_agent(client)
        conv = await _create_conversation(client, agent_id)
        conv_id = conv["id"]

        await _create_step(client, agent_id, conv_id, step_type="user_message", content="Search for AI trends")

        llm1 = await _create_step(
            client, agent_id, conv_id,
            step_type="llm_call", model_name="gpt-4", provider="openai",
            thinking_content="I should search for this.", finish_reason="tool_calls",
            input_tokens=100, output_tokens=20, total_tokens=120, duration_ms=800,
        )

        await _create_step(
            client, agent_id, conv_id,
            step_type="tool_call", tool_name="web_search", tool_type="search",
            tool_call_id="call_search_1", brief="Search AI trends 2026", parent_step_id=llm1["id"],
        )

        await _create_step(
            client, agent_id, conv_id,
            step_type="llm_call", model_name="gpt-4", provider="openai",
            thinking_content="Now I can summarize.", content="Here are the AI trends...",
            finish_reason="stop", input_tokens=200, output_tokens=100, total_tokens=300, duration_ms=1500,
        )

        await _create_step(client, agent_id, conv_id, step_type="assistant_message", content="Here are the AI trends for 2026...")

        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversations/{conv_id}/steps", headers=HEADERS
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_steps"] == 5
        assert [s["step_type"] for s in data["steps"]] == [
            "user_message", "llm_call", "tool_call", "llm_call", "assistant_message"
        ]
        orders = [s["step_order"] for s in data["steps"]]
        assert orders == sorted(orders)

    @pytest.mark.asyncio
    async def test_get_step_detail(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        conv = await _create_conversation(client, agent_id)

        step = await _create_step(
            client, agent_id, conv["id"],
            step_type="llm_call", model_name="claude-3", provider="anthropic",
            request_messages=[{"role": "user", "content": "Hi"}],
            request_tools=[{"type": "function", "function": {"name": "search"}}],
            request_params={"temperature": 0.5},
            content="Hello!", finish_reason="stop",
            input_tokens=10, output_tokens=5, total_tokens=15,
        )

        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversations/{conv['id']}/steps/{step['id']}",
            headers=HEADERS,
        )
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["request_messages"] == [{"role": "user", "content": "Hi"}]
        assert detail["request_tools"] is not None
        assert detail["request_params"] == {"temperature": 0.5}

    @pytest.mark.asyncio
    async def test_get_nonexistent_step_returns_404(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        conv = await _create_conversation(client, agent_id)

        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversations/{conv['id']}/steps/99999",
            headers=HEADERS,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_step(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        conv = await _create_conversation(client, agent_id)

        step = await _create_step(
            client, agent_id, conv["id"],
            step_type="llm_call", model_name="gpt-4", provider="openai", status="running",
        )

        resp = await client.put(
            f"/api/v1/agents/{agent_id}/conversations/{conv['id']}/steps/{step['id']}",
            json={
                "content": "Updated response", "finish_reason": "stop", "status": "success",
                "input_tokens": 50, "output_tokens": 30, "total_tokens": 80, "duration_ms": 900,
            },
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "Updated response"
        assert data["finish_reason"] == "stop"
        assert data["status"] == "success"
        assert data["total_tokens"] == 80

    @pytest.mark.asyncio
    async def test_conversation_counters_updated(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        conv = await _create_conversation(client, agent_id)
        conv_id = conv["id"]

        await _create_step(client, agent_id, conv_id, step_type="user_message", content="Hello")
        await _create_step(
            client, agent_id, conv_id, step_type="llm_call", model_name="gpt-4", provider="openai",
            input_tokens=50, output_tokens=20, total_tokens=70,
        )
        await _create_step(client, agent_id, conv_id, step_type="tool_call", tool_name="search", brief="search query")
        await _create_step(client, agent_id, conv_id, step_type="assistant_message", content="Here is your answer.")

        resp = await client.get(f"/api/v1/agents/{agent_id}/conversations/{conv_id}", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["llm_call_count"] == 1
        assert data["tool_call_count"] == 1
        assert data["round_count"] == 1
        assert data["total_tokens"] >= 70

    @pytest.mark.asyncio
    async def test_auto_title_from_first_user_message(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        conv = await _create_conversation(client, agent_id)
        conv_id = conv["id"]
        assert conv["title"] is None

        await _create_step(client, agent_id, conv_id, step_type="user_message", content="What is machine learning?")

        resp = await client.get(f"/api/v1/agents/{agent_id}/conversations/{conv_id}", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["title"] == "What is machine learning?"

    @pytest.mark.asyncio
    async def test_create_step_invalid_type_returns_422(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        conv = await _create_conversation(client, agent_id)

        resp = await client.post(
            f"/api/v1/agents/{agent_id}/conversations/{conv['id']}/steps",
            json={"round_number": 1, "step_type": "invalid_type"},
            headers=HEADERS,
        )
        assert resp.status_code == 422

    # ── sub-req 2: incomplete status ──────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_incomplete_llm_step_persists(self, client: AsyncClient):
        """Sub-req 2: the schema regex must accept status='incomplete' so the
        engine's _persist_incomplete_llm_step path can write partial llm_calls.
        """
        agent_id = await _create_agent(client)
        conv = await _create_conversation(client, agent_id)

        await _create_step(
            client, agent_id, conv["id"],
            step_type="user_message", content="hi",
        )
        step = await _create_step(
            client, agent_id, conv["id"],
            step_type="llm_call",
            model_name="gpt-4",
            provider="openai",
            content="partial reply...",
            thinking_content="...",
            status="incomplete",
            metadata={"incomplete_reason": "give_up:idle_timeout", "partial_content_chars": 16},
        )
        assert step["status"] == "incomplete"

        resp = await client.get(
            f"/api/v1/agents/{agent_id}/conversations/{conv['id']}/steps",
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Admin path KEEPS incomplete steps for ops debugging.
        statuses = [s["status"] for s in data["steps"]]
        assert "incomplete" in statuses

    @pytest.mark.asyncio
    async def test_invalid_status_value_returns_422(self, client: AsyncClient):
        agent_id = await _create_agent(client)
        conv = await _create_conversation(client, agent_id)

        resp = await client.post(
            f"/api/v1/agents/{agent_id}/conversations/{conv['id']}/steps",
            json={"round_number": 1, "step_type": "llm_call", "status": "bogus"},
            headers=HEADERS,
        )
        assert resp.status_code == 422

    # ── sub-req 3: client_message_id idempotency ──────────────────────

    @pytest.mark.asyncio
    async def test_user_message_unique_by_client_message_id(self, client: AsyncClient):
        """Sub-req 3: the partial unique index must reject a second
        user_message step with the same (conversation_id, client_message_id).

        Behavioral contract: the DB constraint fires. ASGITransport in tests
        propagates the IntegrityError, while in production FastAPI returns 500.
        Either way: the duplicate is NOT silently created.
        """
        from sqlalchemy.exc import IntegrityError

        agent_id = await _create_agent(client)
        conv = await _create_conversation(client, agent_id)
        cmid = "cmid-test-" + str(int(time.time() * 1000))

        first = await _create_step(
            client, agent_id, conv["id"],
            step_type="user_message", content="first", client_message_id=cmid,
        )
        assert first["client_message_id"] == cmid

        with pytest.raises((IntegrityError, Exception)):
            await client.post(
                f"/api/v1/agents/{agent_id}/conversations/{conv['id']}/steps",
                json={
                    "round_number": 1,
                    "step_type": "user_message",
                    "content": "second-attempt",
                    "client_message_id": cmid,
                },
                headers=HEADERS,
            )

    @pytest.mark.asyncio
    async def test_repository_get_user_message_by_client_id(self, client: AsyncClient):
        """Sub-req 3: the repository lookup used by auto-resume must round-trip."""
        from app.db.session import AsyncSessionLocal
        from app.repositories.conversation_step_repository import ConversationStepRepository

        agent_id = await _create_agent(client)
        conv = await _create_conversation(client, agent_id)
        cmid = "cmid-lookup-" + str(int(time.time() * 1000))

        seeded = await _create_step(
            client, agent_id, conv["id"],
            step_type="user_message", content="findme", client_message_id=cmid,
        )

        async with AsyncSessionLocal() as session:
            found = await ConversationStepRepository.get_user_message_by_client_id(
                session, conv["id"], cmid,
            )
            assert found is not None
            assert found.id == seeded["id"]
            assert found.step_type == "user_message"

            missing = await ConversationStepRepository.get_user_message_by_client_id(
                session, conv["id"], "no-such-id",
            )
            assert missing is None

    @pytest.mark.asyncio
    async def test_service_filters_incomplete_when_requested(self, client: AsyncClient):
        """Sub-req 2: ConversationStepService.get_timeline(include_incomplete=False)
        must drop incomplete steps. We use the HTTP API to seed data (avoiding
        FK violations on agent_id), then exercise the service layer through a
        fresh session that shares the same test database.
        """
        from sqlalchemy.ext.asyncio import async_sessionmaker
        from app.db.session import engine as live_engine, AsyncSessionLocal
        from app.services.conversation_step_service import ConversationStepService

        # Seed via HTTP so FK constraints (agent_id, tenant) line up.
        agent_id = await _create_agent(client)
        conv = await _create_conversation(client, agent_id)
        conv_id = conv["id"]
        await _create_step(
            client, agent_id, conv_id,
            step_type="user_message", content="hi",
        )
        await _create_step(
            client, agent_id, conv_id,
            step_type="llm_call", model_name="gpt-4", provider="openai",
            content="partial...", status="incomplete",
            metadata={"incomplete_reason": "give_up:idle_timeout"},
        )
        await _create_step(
            client, agent_id, conv_id,
            step_type="assistant_message", content="final reply",
        )

        # Reach into the test DB via the same factory the FastAPI deps used.
        async with AsyncSessionLocal() as session:
            full = await ConversationStepService.get_timeline(session, conv_id)
            assert full["total_steps"] == 3
            assert any(s["status"] == "incomplete" for s in full["steps"])

            filtered = await ConversationStepService.get_timeline(
                session, conv_id, include_incomplete=False,
            )
            assert filtered["total_steps"] == 2
            assert all(s["status"] != "incomplete" for s in filtered["steps"])
        # `live_engine` is a module-level reference kept alive elsewhere; we
        # don't dispose it here.
        _ = live_engine

    # ── sub-req 3 (concurrency): round-level advisory lock ────────────

    @pytest.mark.asyncio
    async def test_round_advisory_lock_blocks_concurrent_acquire(
        self, client: AsyncClient,
    ):
        """The low-level PG advisory lock primitive the engine builds on
        must:

        1. Let the first acquirer through (locked=True).
        2. Refuse a second concurrent acquirer on a *different* connection
           (locked=False) — that's what lets the engine's higher-level
           wait loop block on a busy round.
        3. Release on context exit so the next attempt succeeds.

        We exercise the helper directly with two AsyncSession instances
        because it's stateful (session-level lock keyed on the underlying
        backend connection); pure unit testing wouldn't catch a regression
        where someone accidentally switches to ``pg_try_advisory_xact_lock``
        (which would auto-release at every commit and silently break us).
        """
        from app.db.session import AsyncSessionLocal
        from app.services.agent_engine_service import _round_advisory_lock

        # Use values that won't collide with anything else in the test DB —
        # advisory locks are cluster-wide so test isolation matters.
        conv_id, round_n = 987_654_321, 7

        s1 = AsyncSessionLocal()
        s2 = AsyncSessionLocal()
        try:
            async with _round_advisory_lock(s1, conv_id, round_n) as locked1:
                assert locked1 is True
                async with _round_advisory_lock(s2, conv_id, round_n) as locked2:
                    assert locked2 is False, (
                        "second session should NOT acquire while first holds it"
                    )
            # After the outer release, a fresh session must be able to
            # acquire — otherwise we have a leak.
            async with AsyncSessionLocal() as s3:
                async with _round_advisory_lock(s3, conv_id, round_n) as locked3:
                    assert locked3 is True
        finally:
            await s1.close()
            await s2.close()

    @pytest.mark.asyncio
    async def test_hold_round_lock_waits_until_release(
        self, client: AsyncClient, monkeypatch,
    ):
        """Sub-req 3: ``_hold_round_lock`` is the engine-level entry point
        that BLOCKS (with a bounded timeout) instead of failing fast. The
        flow we care about for weak-network reconnects:

        1. Request A acquires the per-round lock and starts streaming.
        2. Request B (same client_message_id retry, OR a real concurrent
           fresh message) calls ``_hold_round_lock`` → it cannot acquire
           and starts polling.
        3. A finishes (lock released).
        4. B's wait loop wakes up, re-derives round state, and acquires.

        Without the wait B would have surfaced a 409 to the user mid-retry
        — the whole point of sub-req 3 is to make that recoverable
        transparently.

        Pinned to the PostgreSQL advisory backend: the holder uses the real
        ``pg_advisory_lock`` primitive, which only the advisory backend of
        ``_hold_round_lock`` contends with.
        """
        from app.configs.settings import settings
        from app.db.session import AsyncSessionLocal
        from app.repositories.conversation_repository import ConversationRepository
        from app.services.agent_engine_service import (
            _hold_round_lock,
            _round_advisory_lock,
        )

        monkeypatch.setattr(settings, "ROUND_LOCK_BACKEND", "advisory")

        agent_id = await _create_agent(client)
        conv_dict = await _create_conversation(client, agent_id)
        conv_id = conv_dict["id"]

        # Hold the lock from session A keyed on round 1 — the value
        # ``_hold_round_lock`` will re-derive from ``conv.round_count + 1``.
        async with AsyncSessionLocal() as session_a, AsyncSessionLocal() as session_b:
            conv_b = await ConversationRepository.get_by_id(session_b, conv_id)
            assert conv_b is not None
            initial_round = (conv_b.round_count or 0) + 1

            holder_lock_ctx = _round_advisory_lock(
                session_a, conv_id, initial_round,
            )
            holder_locked = await holder_lock_ctx.__aenter__()
            assert holder_locked is True

            try:
                # Kick off B's wait in the background.
                acquire_event = asyncio.Event()

                async def waiter_acquire():
                    async with _hold_round_lock(
                        session_b, conv_b, conv_id, client_message_id=None,
                        timeout_sec=10.0,
                    ) as (rn, resume):
                        acquire_event.set()
                        return rn, resume

                waiter_task = asyncio.create_task(waiter_acquire())

                # B should NOT have acquired yet (timer-quanta tolerant).
                await asyncio.sleep(0.5)
                assert not acquire_event.is_set(), (
                    "_hold_round_lock should still be waiting while A holds the lock"
                )
            finally:
                # Release A's lock; B should wake up and acquire promptly.
                await holder_lock_ctx.__aexit__(None, None, None)

            rn, resume = await asyncio.wait_for(waiter_task, timeout=5.0)
            assert acquire_event.is_set()
            assert rn == initial_round, (
                "no concurrent commit happened, so the recomputed round number "
                "must equal the original"
            )
            assert resume is False

    @pytest.mark.asyncio
    async def test_hold_round_lock_timeout_raises_conflict(
        self, client: AsyncClient, monkeypatch,
    ):
        """If a wedged round never releases the lock within the timeout
        budget, ``_hold_round_lock`` MUST surface a ``ConflictError`` so
        SSE callers see ``event: error`` instead of an indefinite hang.

        Pinned to the advisory backend (see the waits-until-release test).
        """
        from app.configs.settings import settings
        from app.core.exceptions import ConflictError
        from app.db.session import AsyncSessionLocal
        from app.repositories.conversation_repository import ConversationRepository
        from app.services.agent_engine_service import (
            _hold_round_lock,
            _round_advisory_lock,
        )

        monkeypatch.setattr(settings, "ROUND_LOCK_BACKEND", "advisory")

        agent_id = await _create_agent(client)
        conv_dict = await _create_conversation(client, agent_id)
        conv_id = conv_dict["id"]

        async with AsyncSessionLocal() as session_a, AsyncSessionLocal() as session_b:
            conv_b = await ConversationRepository.get_by_id(session_b, conv_id)
            initial_round = (conv_b.round_count or 0) + 1

            holder_ctx = _round_advisory_lock(session_a, conv_id, initial_round)
            try:
                assert await holder_ctx.__aenter__() is True

                with pytest.raises(ConflictError):
                    async with _hold_round_lock(
                        session_b, conv_b, conv_id, client_message_id=None,
                        timeout_sec=0.5,  # exit fast for the test
                    ):
                        pass  # pragma: no cover — should never enter
            finally:
                await holder_ctx.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_hold_round_lock_memory_backend_serializes(
        self, client: AsyncClient, monkeypatch,
    ):
        """Default ``memory`` backend serializes rounds per conversation with
        ZERO DB lock connections: while holder A is inside ``_hold_round_lock``,
        a concurrent B for the same conversation must wait, then acquire once A
        releases — re-deriving the same round number.
        """
        from app.configs.settings import settings
        from app.db.session import AsyncSessionLocal
        from app.repositories.conversation_repository import ConversationRepository
        from app.services.agent_engine_service import _hold_round_lock

        monkeypatch.setattr(settings, "ROUND_LOCK_BACKEND", "memory")

        agent_id = await _create_agent(client)
        conv_dict = await _create_conversation(client, agent_id)
        conv_id = conv_dict["id"]

        async with AsyncSessionLocal() as session_a, AsyncSessionLocal() as session_b:
            conv_a = await ConversationRepository.get_by_id(session_a, conv_id)
            conv_b = await ConversationRepository.get_by_id(session_b, conv_id)
            initial_round = (conv_a.round_count or 0) + 1

            release_a = asyncio.Event()
            b_acquired = asyncio.Event()

            async def holder_a():
                async with _hold_round_lock(
                    session_a, conv_a, conv_id, client_message_id=None,
                    timeout_sec=10.0,
                ):
                    await release_a.wait()

            async def waiter_b():
                async with _hold_round_lock(
                    session_b, conv_b, conv_id, client_message_id=None,
                    timeout_sec=10.0,
                ) as (rn, resume):
                    b_acquired.set()
                    return rn, resume

            a_task = asyncio.create_task(holder_a())
            await asyncio.sleep(0.1)  # let A take the lock first
            b_task = asyncio.create_task(waiter_b())

            await asyncio.sleep(0.3)
            assert not b_acquired.is_set(), (
                "B must wait while A holds the in-process conversation lock"
            )

            release_a.set()
            await asyncio.wait_for(a_task, timeout=5.0)
            rn, resume = await asyncio.wait_for(b_task, timeout=5.0)
            assert b_acquired.is_set()
            assert rn == initial_round
            assert resume is False

    @pytest.mark.asyncio
    async def test_hold_round_lock_memory_backend_timeout_raises_conflict(
        self, client: AsyncClient, monkeypatch,
    ):
        """Memory backend honors the wait budget: a second waiter that can't
        acquire within ``timeout_sec`` surfaces ``ConflictError``."""
        from app.configs.settings import settings
        from app.core.exceptions import ConflictError
        from app.db.session import AsyncSessionLocal
        from app.repositories.conversation_repository import ConversationRepository
        from app.services.agent_engine_service import _hold_round_lock

        monkeypatch.setattr(settings, "ROUND_LOCK_BACKEND", "memory")

        agent_id = await _create_agent(client)
        conv_dict = await _create_conversation(client, agent_id)
        conv_id = conv_dict["id"]

        async with AsyncSessionLocal() as session_a, AsyncSessionLocal() as session_b:
            conv_a = await ConversationRepository.get_by_id(session_a, conv_id)
            conv_b = await ConversationRepository.get_by_id(session_b, conv_id)

            release_a = asyncio.Event()

            async def holder_a():
                async with _hold_round_lock(
                    session_a, conv_a, conv_id, client_message_id=None,
                    timeout_sec=10.0,
                ):
                    await release_a.wait()

            a_task = asyncio.create_task(holder_a())
            await asyncio.sleep(0.1)
            try:
                with pytest.raises(ConflictError):
                    async with _hold_round_lock(
                        session_b, conv_b, conv_id, client_message_id=None,
                        timeout_sec=0.5,
                    ):
                        pass  # pragma: no cover — should never enter
            finally:
                release_a.set()
                await asyncio.wait_for(a_task, timeout=5.0)

    # ── sub-req 2 (cancel path): partial persistence under shield ─────

    @pytest.mark.asyncio
    async def test_cancel_during_stream_persists_incomplete_step(
        self, client: AsyncClient, monkeypatch,
    ):
        """Sub-req 2 regression: when the SSE consumer closes the generator
        mid-stream (TCP RST / browser navigation / mobile WebView
        background-kill), the engine's ``except (CancelledError,
        GeneratorExit)`` branch MUST run and persist whatever partial
        bytes the user already saw, *under* ``asyncio.shield`` so the DB
        write isn't itself cancelled.

        Without this guarantee, a stale `incomplete_reason='client_cancelled'`
        regression would silently drop user-visible content from the
        timeline and break the resume-from-incomplete UX (sub-req 4
        timeline reconciliation depends on it).

        We mock the LLM client so the engine yields two ``content_delta``
        events, then close the generator (raises ``GeneratorExit`` at the
        current yield) and assert the row landed.
        """
        from app.db.session import AsyncSessionLocal
        from app.libs.llm.base import LLMStreamDelta, LLMStreamResult
        from app.repositories.conversation_step_repository import (
            ConversationStepRepository,
        )
        from app.services.agent_engine_service import AgentEngineService

        agent_id = await _create_agent(client)
        conv_dict = await _create_conversation(client, agent_id)
        conv_id = conv_dict["id"]

        # Real LLM providers (OpenAI/Anthropic clients) BOTH yield each
        # delta AND mutate the shared ``stream_result`` accumulator —
        # ``stream_result.content`` reflects everything the user has seen
        # so far. The engine reads from it on cancel/error to persist the
        # ``incomplete`` row, so a test mock that only yields deltas would
        # quietly persist an empty body and miss the regression we care
        # about (timeline reconciliation needs the content). Mirror that
        # contract here.
        class _FakeStreamIter:
            def __init__(self, result: LLMStreamResult):
                self._step = 0
                self._result = result

            def __aiter__(self):
                return self

            async def __anext__(self):
                self._step += 1
                if self._step == 1:
                    chunk = "Hello "
                elif self._step == 2:
                    chunk = "world"
                else:
                    # Should not be reached in the cancel-before-finish path.
                    await asyncio.sleep(60)  # pragma: no cover
                    raise StopAsyncIteration  # pragma: no cover
                self._result.content = (self._result.content or "") + chunk
                return LLMStreamDelta(content=chunk, thinking_content=None)

        class _FakeLLMClient:
            async def stream_chat(self, messages, **kwargs):
                result = LLMStreamResult(
                    content="",
                    thinking_content="",
                    tool_calls=[],
                    finish_reason=None,
                    request_id=None,
                    model=kwargs.get("model"),
                    incomplete_reason=None,
                )
                return _FakeStreamIter(result), result

        monkeypatch.setattr(
            "app.services.agent_engine_service.create_llm_client",
            lambda: _FakeLLMClient(),
        )

        async with AsyncSessionLocal() as session:
            gen = AgentEngineService.run_chat_round(
                session,
                agent_id=agent_id,
                user_message="Hi there",
                conversation_id=conv_id,
            )

            content_deltas_seen = 0
            async for event in gen:
                # Sub-req 4: every frame now leads with `id: r{n}-e{seq}\n`
                # so `startswith` against the event line stops working;
                # match anywhere in the (small) frame instead.
                if "\nevent: content_delta\n" in event:
                    content_deltas_seen += 1
                if content_deltas_seen >= 2:
                    break

            assert content_deltas_seen == 2

            # Close the generator → injects GeneratorExit at the current
            # yield. The engine's except branch must run, shield the DB
            # write, and re-raise so aclose() returns cleanly.
            await gen.aclose()

        # Verify the persisted incomplete row. We use a fresh session to
        # ensure the read isn't satisfied from the engine session's cache.
        async with AsyncSessionLocal() as session:
            steps = await ConversationStepRepository.get_steps_by_round(
                session, conv_id, 1,
            )
        statuses = [(s.step_type, s.status) for s in steps]
        incomplete_steps = [
            s for s in steps if s.step_type == "llm_call" and s.status == "incomplete"
        ]
        assert len(incomplete_steps) == 1, (
            f"expected one incomplete llm_call, got steps: {statuses}"
        )

        meta = incomplete_steps[0].metadata_ or {}
        assert meta.get("incomplete_reason") == "client_cancelled", (
            f"incomplete_reason should mark the cancel path; got metadata: {meta}"
        )
        # The two deltas we let through were 'Hello ' (6) + 'world' (5) = 11.
        assert meta.get("partial_content_chars") == 11
        # And the user-facing content we already streamed must be persisted
        # so the timeline reconstruction (sub-req 4) can show it back.
        assert (incomplete_steps[0].content or "") == "Hello world"

    # ── sub-req 4 (resume protocol): event id, buffer, round_start ────

    @pytest.mark.asyncio
    async def test_event_ids_are_monotonic_per_round_with_round_start(
        self, client: AsyncClient, monkeypatch,
    ):
        """Sub-req 4: every engine-emitted SSE frame must carry an
        ``id: r{round}-e{seq}`` line, the seq must be monotonic, and the
        first frame in the round must be ``round_start`` carrying server-
        driven watchdog config + the client_message_id echo.

        This is the wire-format contract the SDK depends on for
        Last-Event-ID resume; if any one of these breaks the buffer
        fast-path silently degrades to step-replay across the whole app.
        """
        from app.libs.llm.base import LLMStreamDelta, LLMStreamResult
        from app.services.agent_engine_service import AgentEngineService

        agent_id = await _create_agent(client)
        conv_dict = await _create_conversation(client, agent_id)

        class _Iter:
            def __init__(self, result):
                self._n = 0
                self._result = result

            def __aiter__(self):
                return self

            async def __anext__(self):
                self._n += 1
                if self._n == 1:
                    self._result.content = "Hi"
                    return LLMStreamDelta(content="Hi", thinking_content=None)
                if self._n == 2:
                    self._result.content = "Hi there"
                    self._result.finish_reason = "stop"
                    return LLMStreamDelta(content=" there", finish_reason="stop")
                raise StopAsyncIteration

        class _Client:
            async def stream_chat(self, messages, **kwargs):
                result = LLMStreamResult(
                    content="", thinking_content="", tool_calls=[],
                    finish_reason=None, model=kwargs.get("model"),
                    incomplete_reason=None,
                )
                return _Iter(result), result

        monkeypatch.setattr(
            "app.services.agent_engine_service.create_llm_client",
            lambda: _Client(),
        )

        from app.db.session import AsyncSessionLocal
        cmid = "evt-id-test-cmid-12345"
        async with AsyncSessionLocal() as session:
            frames = []
            async for raw in AgentEngineService.run_chat_round(
                session, agent_id=agent_id, user_message="ping",
                conversation_id=conv_dict["id"], client_message_id=cmid,
            ):
                frames.append(raw)

        # Every round-scoped frame must lead with `id: r{round}-e{seq}`.
        round_frames = [f for f in frames if f.startswith("id: r")]
        assert round_frames, f"expected at least one r-prefixed frame, got: {frames}"

        # Parse seq numbers and assert monotonic, no gaps.
        seqs = []
        for f in round_frames:
            first_line = f.split("\n", 1)[0]
            assert first_line.startswith("id: r1-e"), first_line
            seqs.append(int(first_line.split("-e", 1)[1]))
        assert seqs == sorted(seqs), f"seqs not monotonic: {seqs}"
        assert seqs == list(range(seqs[0], seqs[0] + len(seqs))), (
            f"seqs have gaps: {seqs}"
        )

        # First round-scoped frame is round_start with the expected payload.
        first_frame = round_frames[0]
        assert "\nevent: round_start\n" in first_frame
        # Extract data line
        data_line = next(
            line for line in first_frame.split("\n") if line.startswith("data:")
        )
        import json as _json
        payload = _json.loads(data_line[5:].strip())
        assert payload["round_number"] == 1
        assert payload["resume"] is False
        assert payload["client_message_id"] == cmid
        watchdog = payload["watchdog"]
        for key in ("first_chunk_ms", "chunk_idle_ms", "overall_ms"):
            assert isinstance(watchdog[key], int) and watchdog[key] > 0, watchdog

        # Last frame is `done`.
        assert "\nevent: done\n" in round_frames[-1]

    @pytest.mark.asyncio
    async def test_conversation_created_uses_pre_e_id_not_round_scoped(
        self, client: AsyncClient, monkeypatch,
    ):
        """``conversation_created`` is emitted BEFORE the round lock is
        acquired (we don't yet know `round_number`), so it must carry a
        ``pre-e{n}`` id — never an ``r{round}-e{seq}`` one.

        This is what justifies the SDK's `_ROUND_EVENT_ID_RE` filter on
        ``last_event_id``: ``ChatRequest.last_event_id`` is regex-pinned to
        ``r\\d+-e\\d+`` and would 422 the next retry if the SDK echoed back
        a ``pre-e*`` cursor — silently breaking reconnect for every brand-
        new conversation. If anyone changes the wire format here, this
        test fails first instead of the user.
        """
        from app.libs.llm.base import LLMStreamDelta, LLMStreamResult
        from app.services.agent_engine_service import AgentEngineService

        agent_id = await _create_agent(client)

        class _Iter:
            def __init__(self, result):
                self._n = 0
                self._result = result

            def __aiter__(self):
                return self

            async def __anext__(self):
                self._n += 1
                if self._n == 1:
                    self._result.content = "ok"
                    self._result.finish_reason = "stop"
                    return LLMStreamDelta(content="ok", finish_reason="stop")
                raise StopAsyncIteration

        class _Client:
            async def stream_chat(self, messages, **kwargs):
                result = LLMStreamResult(
                    content="", thinking_content="", tool_calls=[],
                    finish_reason=None, model=kwargs.get("model"),
                    incomplete_reason=None,
                )
                return _Iter(result), result

        monkeypatch.setattr(
            "app.services.agent_engine_service.create_llm_client",
            lambda: _Client(),
        )

        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            frames = []
            # NOTE: no `conversation_id` — engine creates one on the fly
            # and emits `conversation_created` as the very first frame.
            async for raw in AgentEngineService.run_chat_round(
                session, agent_id=agent_id, user_message="hello",
            ):
                frames.append(raw)

        # Find the conversation_created frame.
        cc_frame = next(
            (f for f in frames if "\nevent: conversation_created\n" in f),
            None,
        )
        assert cc_frame is not None, f"missing conversation_created in: {frames}"

        first_line = cc_frame.split("\n", 1)[0]
        assert first_line.startswith("id: pre-e"), (
            f"conversation_created must use pre-e* id (it precedes the "
            f"round lock), got: {first_line!r}"
        )
        # And explicitly NOT round-scoped — the round number isn't known yet.
        assert not first_line.startswith("id: r"), first_line

        # Sanity: round-scoped frames still come after with r1-e* ids.
        round_frames = [f for f in frames if f.startswith("id: r")]
        assert round_frames, "expected round-scoped frames after conversation_created"
        assert all(f.split("\n", 1)[0].startswith("id: r1-e") for f in round_frames)

    @pytest.mark.asyncio
    async def test_resume_buffer_fast_path_replays_done_without_regenerating(
        self, client: AsyncClient, monkeypatch,
    ):
        """Sub-req 4 hot path: a same-round retry whose `last_event_id`
        falls inside the still-warm ring buffer AND whose tail contains
        `done` MUST replay the cached frames byte-for-byte and exit
        WITHOUT calling the LLM again.

        This is the high-value reconnect case: client successfully
        completed the round but lost the network on the final ~200ms
        and missed the `done` frame.
        """
        from app.libs.llm.base import LLMStreamDelta, LLMStreamResult
        from app.services.agent_engine_service import AgentEngineService

        agent_id = await _create_agent(client)
        conv_dict = await _create_conversation(client, agent_id)
        conv_id = conv_dict["id"]

        llm_calls = 0

        class _Iter:
            def __init__(self, result):
                self._n = 0
                self._result = result

            def __aiter__(self):
                return self

            async def __anext__(self):
                self._n += 1
                if self._n == 1:
                    self._result.content = "Done!"
                    self._result.finish_reason = "stop"
                    return LLMStreamDelta(content="Done!", finish_reason="stop")
                raise StopAsyncIteration

        class _Client:
            async def stream_chat(self, messages, **kwargs):
                nonlocal llm_calls
                llm_calls += 1
                result = LLMStreamResult(
                    content="", thinking_content="", tool_calls=[],
                    finish_reason=None, model=kwargs.get("model"),
                    incomplete_reason=None,
                )
                return _Iter(result), result

        monkeypatch.setattr(
            "app.services.agent_engine_service.create_llm_client",
            lambda: _Client(),
        )

        from app.db.session import AsyncSessionLocal
        cmid = "buf-fast-test-cmid"

        # First request: completes normally, fills the buffer.
        async with AsyncSessionLocal() as session:
            frames_first = []
            async for raw in AgentEngineService.run_chat_round(
                session, agent_id=agent_id, user_message="hi",
                conversation_id=conv_id, client_message_id=cmid,
            ):
                frames_first.append(raw)

        assert llm_calls == 1
        assert any("\nevent: done\n" in f for f in frames_first)

        # Pretend the client received only the round_start frame and
        # then disconnected. Reconnect with that frame's id as cursor.
        round_start_id = frames_first[0].split("\n", 1)[0].replace("id: ", "")
        assert round_start_id.startswith("r1-e")

        # Second request: same cmid, last_event_id pointing at the very
        # first frame. The buffer holds everything past that — and the
        # last frame is `done`. Engine MUST replay without calling LLM.
        async with AsyncSessionLocal() as session:
            frames_second = []
            async for raw in AgentEngineService.run_chat_round(
                session, agent_id=agent_id, user_message="hi",
                conversation_id=conv_id, client_message_id=cmid,
                resume=True, last_event_id=round_start_id,
            ):
                frames_second.append(raw)

        assert llm_calls == 1, "fast path must NOT call the LLM again"
        # Replayed frames are exactly the suffix of the original stream.
        assert frames_second == frames_first[1:], (
            "fast-path replay must be byte-equal to the original suffix"
        )

    @pytest.mark.asyncio
    async def test_resume_buffer_fast_path_replays_terminal_when_cursor_past_done(
        self, client: AsyncClient, monkeypatch,
    ):
        """Sub-req 4 corner: when the client's ``last_event_id`` advanced
        PAST the round's terminal ``done`` frame and then a retry came in
        anyway (SDK persisted the cursor to disk + restarted, a custom
        SDK without our ``receivedDoneOrError`` guard, or the chat-page's
        ``onDone`` handler threw and the retry path fired) — the buffer
        fast-path must recognize "cursor past terminal" and replay
        just that one terminal frame instead of falling through to
        step-replay (which would re-run the LLM and double-bill the
        user for a turn that finished).

        Sending zero frames is also wrong: the SDK interprets an empty
        response body as an unexpected disconnect and loops on retry.
        Replaying just the ``done`` frame is the only correct behavior;
        the chat page's ``onDone`` is idempotent (clears stream flags +
        refs) so re-firing it is safe.
        """
        from app.libs.llm.base import LLMStreamDelta, LLMStreamResult
        from app.services.agent_engine_service import AgentEngineService

        agent_id = await _create_agent(client)
        conv_dict = await _create_conversation(client, agent_id)
        conv_id = conv_dict["id"]

        llm_calls = 0

        class _Iter:
            def __init__(self, result):
                self._n = 0
                self._result = result

            def __aiter__(self):
                return self

            async def __anext__(self):
                self._n += 1
                if self._n == 1:
                    self._result.content = "Done!"
                    self._result.finish_reason = "stop"
                    return LLMStreamDelta(content="Done!", finish_reason="stop")
                raise StopAsyncIteration

        class _Client:
            async def stream_chat(self, messages, **kwargs):
                nonlocal llm_calls
                llm_calls += 1
                result = LLMStreamResult(
                    content="", thinking_content="", tool_calls=[],
                    finish_reason=None, model=kwargs.get("model"),
                    incomplete_reason=None,
                )
                return _Iter(result), result

        monkeypatch.setattr(
            "app.services.agent_engine_service.create_llm_client",
            lambda: _Client(),
        )

        from app.db.session import AsyncSessionLocal
        cmid = "buf-fast-terminal-cmid"

        # First request runs end-to-end and fills the buffer with `done`.
        async with AsyncSessionLocal() as session:
            frames_first = []
            async for raw in AgentEngineService.run_chat_round(
                session, agent_id=agent_id, user_message="hi",
                conversation_id=conv_id, client_message_id=cmid,
            ):
                frames_first.append(raw)

        assert llm_calls == 1
        done_frame = next(
            (f for f in frames_first if "\nevent: done\n" in f), None,
        )
        assert done_frame is not None, "first request must have produced a done frame"
        done_id = done_frame.split("\n", 1)[0].replace("id: ", "")
        assert done_id.startswith("r1-e")

        # Second request: cursor sits AT the done frame's id (so the
        # buffer's slice_after returns []) yet the round really is done.
        async with AsyncSessionLocal() as session:
            frames_second = []
            async for raw in AgentEngineService.run_chat_round(
                session, agent_id=agent_id, user_message="hi",
                conversation_id=conv_id, client_message_id=cmid,
                resume=True, last_event_id=done_id,
            ):
                frames_second.append(raw)

        assert llm_calls == 1, (
            "cursor past terminal must NOT trigger LLM regeneration; "
            "the round was already done in cache"
        )
        # Exactly one frame replayed: the done frame itself. No
        # round_start, no assistant_reset, no step-replay frames.
        assert len(frames_second) == 1, (
            f"expected single done frame; got {len(frames_second)}: "
            f"{frames_second}"
        )
        assert "\nevent: done\n" in frames_second[0]
        # Byte-equal to the original done frame so the SDK's id-based
        # cursor remains consistent.
        assert frames_second[0] == done_frame

    @pytest.mark.asyncio
    async def test_cold_resume_emits_assistant_reset_before_clean_replay(
        self, client: AsyncClient, monkeypatch,
    ):
        """Pre-existing bug: when a round had successful tool rounds AND
        an incomplete trailing llm_call, the engine emitted
        ``assistant_reset`` AFTER replaying the clean steps. Combined
        with the new ``onRoundStart(resume=true)`` UI wipe, this caused
        the just-replayed clean tool rounds to be cleared, leaving only
        the regenerated tail visible to the user.

        After the fix, the order is:
            round_start → assistant_reset → ...clean replay... → fresh stream → done

        so the wipe lands on the dropped-connection partial bubble (the
        thing it was meant to wipe) and the clean replay is preserved.
        """
        from app.libs.llm.base import LLMStreamDelta, LLMStreamResult
        from app.services.agent_engine_service import AgentEngineService

        agent_id = await _create_agent(client)
        conv_dict = await _create_conversation(client, agent_id)
        conv_id = conv_dict["id"]
        cmid = "cold-resume-order-cmid"

        # Seed a round with: user_message → clean llm_call (with tool
        # request) → tool_call (success) → incomplete llm_call. NO
        # assistant_message — so the round is mid-flight, eligible for
        # resume regeneration.
        await _create_step(
            client, agent_id, conv_id,
            step_type="user_message", content="ask",
            client_message_id=cmid,
        )
        clean_llm = await _create_step(
            client, agent_id, conv_id,
            step_type="llm_call",
            model_name="gpt-4", provider="openai_compatible",
            content="let me look that up", status="success",
            response_tool_calls=[{
                "id": "tc_1",
                "type": "function",
                "function": {"name": "search", "arguments": "{}"},
            }],
        )
        await _create_step(
            client, agent_id, conv_id,
            step_type="tool_call",
            tool_name="search", tool_call_id="tc_1",
            tool_response="result", brief="search()",
            parent_step_id=clean_llm["id"],
        )
        await _create_step(
            client, agent_id, conv_id,
            step_type="llm_call",
            model_name="gpt-4", provider="openai_compatible",
            content="partial...", status="incomplete",
            metadata={"incomplete_reason": "give_up:idle_timeout"},
        )

        # Stub the LLM so the regenerate-tail loop terminates quickly.
        class _Iter:
            def __init__(self, result):
                self._n = 0
                self._result = result

            def __aiter__(self):
                return self

            async def __anext__(self):
                self._n += 1
                if self._n == 1:
                    self._result.content = "regenerated"
                    self._result.finish_reason = "stop"
                    return LLMStreamDelta(content="regenerated", finish_reason="stop")
                raise StopAsyncIteration

        class _Client:
            async def stream_chat(self, messages, **kwargs):
                result = LLMStreamResult(
                    content="", thinking_content="", tool_calls=[],
                    finish_reason=None, model=kwargs.get("model"),
                    incomplete_reason=None,
                )
                return _Iter(result), result

        monkeypatch.setattr(
            "app.services.agent_engine_service.create_llm_client",
            lambda: _Client(),
        )

        # Drive the resume directly. Auto-resume kicks in via cmid match
        # so we don't need to pass resume=True explicitly.
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            frames = []
            async for raw in AgentEngineService.run_chat_round(
                session, agent_id=agent_id, user_message="ask",
                conversation_id=conv_id, client_message_id=cmid,
            ):
                frames.append(raw)

        # Locate event indices in the raw frame stream.
        def _index(event_name: str) -> int:
            for i, f in enumerate(frames):
                if f"\nevent: {event_name}\n" in f:
                    return i
            return -1

        reset_idx = _index("assistant_reset")
        first_replay_idx = next(
            (
                i for i, f in enumerate(frames)
                if any(
                    f"\nevent: {ev}\n" in f
                    for ev in ("content_delta", "tool_call", "tool_result", "llm_step_created")
                )
            ),
            -1,
        )
        round_start_idx = _index("round_start")

        assert reset_idx >= 0, f"missing assistant_reset in: {frames}"
        assert round_start_idx >= 0, "missing round_start"
        assert first_replay_idx >= 0, "missing replay frames"

        # The whole point of the fix: reset MUST come before any clean
        # replay frame; otherwise the UI wipe nukes the just-replayed
        # successful tool round.
        assert round_start_idx < reset_idx < first_replay_idx, (
            f"expected round_start < assistant_reset < first replay frame; "
            f"got indices round_start={round_start_idx}, "
            f"reset={reset_idx}, first_replay={first_replay_idx}"
        )

        # Reset payload pins the reason + tool_round attribution.
        import json as _json
        reset_data_line = next(
            line for line in frames[reset_idx].split("\n") if line.startswith("data:")
        )
        reset_payload = _json.loads(reset_data_line[5:].strip())
        assert reset_payload["reason"] == "resume_discard_incomplete"
        assert reset_payload["tool_round"] == 1, (
            f"tool_round should equal the count of clean (non-incomplete) "
            f"llm_call steps replayed; got {reset_payload['tool_round']}"
        )

        # Sanity: stream still ends with `done` (regen-tail succeeded).
        assert "\nevent: done\n" in frames[-1]

    @pytest.mark.asyncio
    async def test_watchdog_widens_for_thinking_models(
        self, client: AsyncClient,
    ):
        """Sub-req 4 watchdog tuning: thinking-model rounds need a
        wider first-chunk window (chain-of-thought can take 60–120s
        before the first visible token). The default config tuned for
        fast models would false-positive every reasoning request.

        Verifies the math directly via ``_watchdog_for`` rather than
        going through the full engine, since the values are pure config.
        """
        from app.schemas.agent import EngineConfig, ModelConfig
        from app.services.agent_engine_service import _watchdog_for

        fast = _watchdog_for(EngineConfig(model=ModelConfig(
            first_round_thinking=False, subsequent_rounds_thinking=False,
        )))
        thinking = _watchdog_for(EngineConfig(model=ModelConfig(
            first_round_thinking=True, subsequent_rounds_thinking=False,
        )))
        assert thinking["first_chunk_ms"] >= fast["first_chunk_ms"]
        assert thinking["chunk_idle_ms"] >= fast["chunk_idle_ms"]
        assert thinking["overall_ms"] >= fast["overall_ms"]

    @pytest.mark.asyncio
    async def test_round_event_buffer_slice_after(self):
        """Unit-style coverage of the buffer's resume primitives."""
        from app.services.round_event_buffer import (
            RoundEventBuffer,
            RoundKey,
            format_event_id,
            parse_event_id,
        )

        buf = RoundEventBuffer()
        key = RoundKey(conversation_id=10001, round_number=3)

        # Empty: slice returns None (caller falls back to step replay).
        assert buf.slice_after(key, -1) is None

        # Append a few frames.
        for seq in range(5):
            event_id = format_event_id(3, seq)
            buf.append(key, seq, f"id: {event_id}\nevent: x\ndata: {{}}\n\n")

        # last_seq=-1 returns all events from the start.
        all_events = buf.slice_after(key, -1)
        assert all_events is not None and len(all_events) == 5

        # last_seq=2 returns events with seq>2 (i.e. 3, 4).
        tail = buf.slice_after(key, 2)
        assert tail is not None and len(tail) == 2
        assert "r3-e3" in tail[0] and "r3-e4" in tail[1]

        # Cursor at the latest buffered seq (4) returns empty list — the
        # client is already up to date; this is distinct from "lost" and
        # the caller MUST NOT step-replay.
        caught_up = buf.slice_after(key, 4)
        assert caught_up == []

        # Cursor far in the future also returns empty list (defensive —
        # client claims to have seen frames beyond what we ever sent).
        ahead = buf.slice_after(key, 99)
        assert ahead == []

        # latest_raw peeks at the tail without consuming. Lets the engine
        # decide "cursor past terminal — replay just the tail" when
        # slice_after returned [].
        latest = buf.latest_raw(key)
        assert latest is not None and "r3-e4" in latest

        # parse_event_id round-trips and rejects garbage.
        assert parse_event_id("r3-e7") == (3, 7)
        assert parse_event_id("garbage") is None
        assert parse_event_id(None) is None
        assert parse_event_id("") is None

        # Eviction wipes state for both helpers.
        buf.evict(key)
        assert buf.slice_after(key, -1) is None
        assert buf.latest_raw(key) is None

        # latest_raw on an unknown key is also None (not an exception).
        unknown_key = RoundKey(conversation_id=99999, round_number=1)
        assert buf.latest_raw(unknown_key) is None

    @pytest.mark.asyncio
    async def test_round_buffer_gap_returns_none_not_empty(self):
        """Ring eviction must surface as ``None`` (gap → fall back to
        step-replay), never as ``[]`` (which means "client up to date").

        If a future change conflated the two, the engine's buffer
        fast-path predicate would still skip on ``[]``, but downstream
        code that treats the buffer as a source of truth (e.g. an
        observability checker or an alternate fast-path with looser
        ``done`` requirements) would silently lose the frames the ring
        evicted. Pin the distinction at the helper level so it can't
        regress quietly.
        """
        from collections import deque
        from app.services.round_event_buffer import _Entry, _RoundBuffer

        inner = _RoundBuffer()
        # Simulate a ring that has already evicted seqs 0..4, leaving
        # seqs 5..7 in a small bounded deque (mirrors what happens
        # in production once the round has streamed >MAX_EVENTS_PER_ROUND
        # deltas).
        inner._events = deque(
            [
                _Entry(seq=5, raw="r1-e5\n"),
                _Entry(seq=6, raw="r1-e6\n"),
                _Entry(seq=7, raw="r1-e7\n"),
            ],
            maxlen=3,
        )

        # Cursor at seq=2 → events 3, 4 are GONE. Must signal None.
        assert inner.slice_after(2) is None
        # Cursor at seq=4 → directly precedes first_seq=5; buffer
        # suffices, replay 5..7.
        replay = inner.slice_after(4)
        assert replay is not None and [e.split("\n")[0] for e in replay] == [
            "r1-e5", "r1-e6", "r1-e7",
        ]
        # Cursor at last buffered seq (7) → up-to-date, empty list.
        assert inner.slice_after(7) == []
        # Empty buffer → None (no info — caller falls back).
        inner._events = deque(maxlen=3)
        assert inner.slice_after(-1) is None
