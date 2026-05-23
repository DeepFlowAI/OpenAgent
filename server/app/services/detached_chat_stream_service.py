"""
Detached chat stream runner for public Web SDK chat.

The public Web SDK needs a different lifecycle from the admin test drawer:
closing the browser tab, hiding/destroying the iframe, or losing the SSE
transport should not cancel the backend round. Only the explicit "stop
response" action should cancel it.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from typing import AsyncIterator

from app.db import session as db_session
from app.services.agent_engine_service import AgentEngineService
from app.services.round_event_buffer import RoundKey, parse_event_id, round_event_buffer

logger = logging.getLogger(__name__)

_QUEUE_CLOSED = object()
_SUBSCRIBER_QUEUE_SIZE = 1024
_HEARTBEAT_INTERVAL_SEC = 5.0
_CANCEL_DRAIN_TIMEOUT_SEC = 2.0


@dataclass(frozen=True)
class DetachedChatKey:
    scope: str
    owner: str
    client_message_id: str


@dataclass
class _DetachedRun:
    key: DetachedChatKey
    task: asyncio.Task[None] | None = None
    subscribers: set[asyncio.Queue[str | object]] = field(default_factory=set)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def subscribe(self) -> asyncio.Queue[str | object]:
        queue: asyncio.Queue[str | object] = asyncio.Queue(
            maxsize=_SUBSCRIBER_QUEUE_SIZE,
        )
        async with self.lock:
            if self.task is not None and self.task.done():
                queue.put_nowait(_QUEUE_CLOSED)
            else:
                self.subscribers.add(queue)
        return queue

    def start(self, task: asyncio.Task[None]) -> None:
        self.task = task

    async def unsubscribe(self, queue: asyncio.Queue[str | object]) -> None:
        async with self.lock:
            self.subscribers.discard(queue)

    async def broadcast(self, event: str) -> None:
        async with self.lock:
            subscribers = list(self.subscribers)

        for queue in subscribers:
            _put_drop_oldest(queue, event)

    async def close(self) -> None:
        async with self.lock:
            subscribers = list(self.subscribers)
            self.subscribers.clear()

        for queue in subscribers:
            _put_drop_oldest(queue, _QUEUE_CLOSED)


class DetachedChatStreamService:
    _runs: dict[DetachedChatKey, _DetachedRun] = {}
    _lock = asyncio.Lock()

    @classmethod
    async def stream_public_chat(
        cls,
        *,
        channel_token: str,
        agent_id: int,
        user_message: str,
        conversation_id: int | None,
        customer_context: dict | None,
        resume: bool,
        client_message_id: str | None,
        last_event_id: str | None,
    ) -> AsyncIterator[str]:
        cls._ensure_single_process_runtime()
        if not client_message_id:
            async for event in cls._stream_direct(
                agent_id=agent_id,
                user_message=user_message,
                conversation_id=conversation_id,
                customer_context=customer_context,
                resume=resume,
                client_message_id=client_message_id,
                last_event_id=last_event_id,
            ):
                yield event
            return

        key = DetachedChatKey(
            scope="public_channel",
            owner=channel_token,
            client_message_id=client_message_id,
        )
        run, queue = await cls._get_or_start_public_run(
            key=key,
            agent_id=agent_id,
            user_message=user_message,
            conversation_id=conversation_id,
            customer_context=customer_context,
            resume=resume,
            client_message_id=client_message_id,
            last_event_id=last_event_id,
        )
        cached_tail, last_replayed_seq = cls._cached_tail(
            conversation_id=conversation_id,
            last_event_id=last_event_id,
        )
        try:
            for event in cached_tail:
                yield event

            while True:
                try:
                    item = await asyncio.wait_for(
                        queue.get(),
                        timeout=_HEARTBEAT_INTERVAL_SEC,
                    )
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue

                if item is _QUEUE_CLOSED:
                    break

                event = str(item)
                event_cursor = _extract_round_cursor(event)
                if event_cursor and last_replayed_seq is not None:
                    event_round, event_seq = event_cursor
                    replay_round, replay_seq = last_replayed_seq
                    if event_round == replay_round and event_seq <= replay_seq:
                        continue
                yield event
        finally:
            await run.unsubscribe(queue)

    @classmethod
    async def cancel_public_chat(
        cls,
        *,
        channel_token: str,
        client_message_id: str,
    ) -> bool:
        cls._ensure_single_process_runtime()
        key = DetachedChatKey(
            scope="public_channel",
            owner=channel_token,
            client_message_id=client_message_id,
        )
        async with cls._lock:
            run = cls._runs.get(key)
        if run is None or run.task is None or run.task.done():
            return False
        run.task.cancel()
        try:
            await asyncio.wait_for(run.task, timeout=_CANCEL_DRAIN_TIMEOUT_SEC)
        except asyncio.CancelledError:
            pass
        except asyncio.TimeoutError:
            logger.warning(
                "Detached public chat cancel still draining after %.1fs — "
                "channel=%s client_message_id=%s",
                _CANCEL_DRAIN_TIMEOUT_SEC,
                channel_token,
                client_message_id,
            )
        return True

    @classmethod
    def _ensure_single_process_runtime(cls) -> None:
        worker_count = _configured_worker_count()
        if worker_count <= 1:
            return
        message = (
            "Detached public Web SDK chat uses in-process task state and "
            f"requires a single API worker; detected worker_count={worker_count}. "
            "Use one uvicorn worker or replace this service with Redis/task-queue "
            "backed state before enabling multiple workers."
        )
        logger.error(message)
        raise RuntimeError(message)

    @classmethod
    async def _get_or_start_public_run(
        cls,
        *,
        key: DetachedChatKey,
        agent_id: int,
        user_message: str,
        conversation_id: int | None,
        customer_context: dict | None,
        resume: bool,
        client_message_id: str,
        last_event_id: str | None,
    ) -> tuple[_DetachedRun, asyncio.Queue[str | object]]:
        async with cls._lock:
            existing = cls._runs.get(key)
            if (
                existing is not None
                and existing.task is not None
                and not existing.task.done()
            ):
                return existing, await existing.subscribe()
            if existing is not None:
                cls._runs.pop(key, None)

            run = _DetachedRun(key=key)
            queue = await run.subscribe()
            cls._runs[key] = run

            async def producer() -> None:
                await cls._produce_public_chat(
                    key=key,
                    agent_id=agent_id,
                    user_message=user_message,
                    conversation_id=conversation_id,
                    customer_context=customer_context,
                    resume=resume,
                    client_message_id=client_message_id,
                    last_event_id=last_event_id,
                )

            task = asyncio.create_task(producer())
            run.start(task)
            task.add_done_callback(lambda _task: cls._forget_run(key, run))
            return run, queue

    @classmethod
    async def _produce_public_chat(
        cls,
        *,
        key: DetachedChatKey,
        agent_id: int,
        user_message: str,
        conversation_id: int | None,
        customer_context: dict | None,
        resume: bool,
        client_message_id: str,
        last_event_id: str | None,
    ) -> None:
        try:
            async with db_session.AsyncSessionLocal() as db:
                stream = AgentEngineService.run_chat_round(
                    db,
                    agent_id=agent_id,
                    user_message=user_message,
                    conversation_id=conversation_id,
                    customer_context=customer_context,
                    resume=resume,
                    # Deliberately do not bind this to any one HTTP request:
                    # a dropped SSE consumer must not stop the backend round.
                    is_disconnected_cb=None,
                    client_message_id=client_message_id,
                    last_event_id=last_event_id,
                )
                async for event in stream:
                    run = cls._runs.get(key)
                    if run is not None:
                        await run.broadcast(event)
        except asyncio.CancelledError:
            logger.info(
                "Detached public chat cancelled — channel=%s client_message_id=%s",
                key.owner,
                key.client_message_id,
            )
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Detached public chat stream error")
            run = cls._runs.get(key)
            if run is not None:
                await run.broadcast(
                    "event: error\ndata: "
                    f"{json.dumps({'message': str(exc)}, ensure_ascii=False)}\n\n",
                )
        finally:
            run = cls._runs.get(key)
            if run is not None:
                await run.close()

    @classmethod
    async def _stream_direct(
        cls,
        *,
        agent_id: int,
        user_message: str,
        conversation_id: int | None,
        customer_context: dict | None,
        resume: bool,
        client_message_id: str | None,
        last_event_id: str | None,
    ) -> AsyncIterator[str]:
        async with db_session.AsyncSessionLocal() as db:
            stream = AgentEngineService.run_chat_round(
                db,
                agent_id=agent_id,
                user_message=user_message,
                conversation_id=conversation_id,
                customer_context=customer_context,
                resume=resume,
                is_disconnected_cb=None,
                client_message_id=client_message_id,
                last_event_id=last_event_id,
            )
            async for event in stream:
                yield event

    @classmethod
    def _cached_tail(
        cls,
        *,
        conversation_id: int | None,
        last_event_id: str | None,
    ) -> tuple[list[str], tuple[int, int] | None]:
        if conversation_id is None or not last_event_id:
            return [], None
        parsed = parse_event_id(last_event_id)
        if parsed is None:
            return [], None
        round_number, last_seq = parsed
        cached = round_event_buffer.slice_after(
            RoundKey(conversation_id=conversation_id, round_number=round_number),
            last_seq,
        )
        if not cached:
            return [], (round_number, last_seq)
        replayed_seq = last_seq
        for raw in cached:
            cursor = _extract_round_cursor(raw)
            if cursor and cursor[0] == round_number:
                replayed_seq = max(replayed_seq, cursor[1])
        return cached, (round_number, replayed_seq)

    @classmethod
    def _forget_run(cls, key: DetachedChatKey, run: _DetachedRun) -> None:
        if cls._runs.get(key) is run:
            cls._runs.pop(key, None)


def _put_drop_oldest(
    queue: asyncio.Queue[str | object],
    item: str | object,
) -> None:
    try:
        queue.put_nowait(item)
        return
    except asyncio.QueueFull:
        pass

    try:
        queue.get_nowait()
    except asyncio.QueueEmpty:
        pass
    queue.put_nowait(item)


def _extract_round_cursor(raw_event: str) -> tuple[int, int] | None:
    first_line = raw_event.split("\n", 1)[0]
    if not first_line.startswith("id:"):
        return None
    return parse_event_id(first_line[3:].strip())


def _configured_worker_count() -> int:
    """Best-effort guard for unsupported multi-worker deployments.

    The detached runner keeps live task handles in process memory. That is
    deliberate for the current single-uvicorn-worker deployment, but unsafe
    with multiple API workers because a cancel/reattach request can land on a
    different process from the one holding the running task.
    """
    counts: list[int] = []
    for key in ("WEB_CONCURRENCY", "UVICORN_WORKERS", "GUNICORN_WORKERS"):
        value = os.getenv(key)
        if value and value.isdigit():
            counts.append(int(value))

    arg_text = " ".join(sys.argv)
    gunicorn_args = os.getenv("GUNICORN_CMD_ARGS")
    if gunicorn_args:
        arg_text = f"{arg_text} {gunicorn_args}"
    for match in re.finditer(r"(?:--workers|-w)(?:=|\s+)(\d+)", arg_text):
        counts.append(int(match.group(1)))

    return max(counts) if counts else 1
