"""
Conversation title summary service.

Generates a short, one-line summary title for a conversation's first round and
writes it back to ``conversations.title`` for the Web SDK history list.

Runs asynchronously off the chat hot path: it owns its own DB session, swallows
all failures, and only overwrites a title that is empty or still equal to the
first-user-message fallback truncation — never a preset (Embed) or human title.
"""
import asyncio
import logging

from app.configs.settings import settings
from app.db.session import AsyncSessionLocal
from app.libs.llm.factory import create_llm_client
from app.repositories.conversation_repository import ConversationRepository

logger = logging.getLogger(__name__)

# Keep strong references to in-flight tasks so they are not garbage collected
# before completion (asyncio only holds weak references to tasks).
_background_tasks: set[asyncio.Task] = set()

# The fallback title written by the engine is ``user_message[:200]``; keep this
# in sync with ``agent_engine_service`` / ``conversation_step_service``.
_FALLBACK_TITLE_MAX = 200

_TITLE_SYSTEM_PROMPT = (
    "You write a concise title for a chat conversation. "
    "Summarize the user's intent in a single short phrase of at most "
    "{max_chars} characters. Reply in the same language as the conversation. "
    "Output only the title text — no quotes, no punctuation, no prefix, no explanation."
)

_QUOTE_CHARS = "\"'“”‘’「」『』《》"
_TRAILING_PUNCT = "。.!！?？,，、;；:：…~～"


def _clean_title(raw: str, max_chars: int) -> str:
    """Normalize raw model output into a single-line short title."""
    title = (raw or "").strip()
    if not title:
        return ""
    # Keep only the first non-empty line.
    title = title.splitlines()[0].strip()
    # Strip wrapping quotes and trailing punctuation.
    title = title.strip(_QUOTE_CHARS).strip()
    title = title.rstrip(_TRAILING_PUNCT).strip()
    if len(title) > max_chars:
        title = title[:max_chars].strip()
    return title


def _should_overwrite(current_title: str | None, fallback_title: str) -> bool:
    """Only overwrite an empty title or the first-user-message fallback."""
    current = current_title or ""
    return current == "" or current == fallback_title


async def _generate_and_store(
    conversation_id: int, user_message: str, assistant_message: str
) -> None:
    fallback_title = user_message[:_FALLBACK_TITLE_MAX]
    try:
        # 1. Read the current title and decide whether to proceed, then release
        #    the DB connection BEFORE the (potentially slow) LLM call — holding a
        #    pooled connection idle across the LLM round can starve the chat
        #    engine's connection pool.
        async with AsyncSessionLocal() as db:
            conv = await ConversationRepository.get_by_id(db, conversation_id)
            if conv is None or not _should_overwrite(conv.title, fallback_title):
                return

        # 2. Call the LLM while holding no DB connection.
        max_chars = settings.CONVERSATION_TITLE_MAX_CHARS
        messages = [
            {
                "role": "system",
                "content": _TITLE_SYSTEM_PROMPT.format(max_chars=max_chars),
            },
            {
                "role": "user",
                "content": (
                    f"User question:\n{user_message}\n\n"
                    f"Assistant answer:\n{assistant_message}"
                ),
            },
        ]
        resp = await create_llm_client().chat(
            messages,
            model=settings.CONVERSATION_TITLE_MODEL,
            temperature=settings.CONVERSATION_TITLE_TEMPERATURE,
            max_tokens=settings.CONVERSATION_TITLE_MAX_TOKENS,
        )
        title = _clean_title(resp.content or "", max_chars)
        if not title:
            return

        # 3. Atomic conditional write in a fresh session — only overwrites an
        #    empty/fallback title, so a preset/human title set during the LLM
        #    call is never clobbered (no stale-object re-check needed).
        async with AsyncSessionLocal() as db:
            updated = await ConversationRepository.update_title_if_overwritable(
                db, conversation_id, title, fallback_title,
            )
        if updated:
            logger.info(
                "Conversation title summarized — conv_id=%s title=%r",
                conversation_id, title,
            )
    except Exception:  # noqa: BLE001 — best-effort, must never break chat
        logger.warning(
            "Conversation title summary failed — conv_id=%s",
            conversation_id, exc_info=True,
        )


def schedule_title_summary(
    conversation_id: int, user_message: str, assistant_message: str
) -> None:
    """Fire-and-forget: schedule summary generation without blocking the caller."""
    if not settings.CONVERSATION_TITLE_ENABLED:
        return
    if not conversation_id or not user_message or not assistant_message:
        return
    task = asyncio.create_task(
        _generate_and_store(conversation_id, user_message, assistant_message)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
