"""
Chat request/response schemas for SSE streaming chat endpoint.
"""
from pydantic import BaseModel, Field


class CustomerContext(BaseModel):
    """Optional customer context for auto-create conversation in chat."""
    external_user_id: str | None = Field(None, max_length=128)
    display_name: str | None = Field(None, max_length=128)
    email: str | None = Field(None, max_length=256)
    phone: str | None = Field(None, max_length=32)
    avatar_url: str | None = Field(None, max_length=1024)
    source: str | None = Field(None, pattern=r"^(chat|api|embed)$")
    title: str | None = None
    metadata: dict | None = None


class ChatRequest(BaseModel):
    """Request body for the chat SSE endpoint."""
    message: str = Field(..., min_length=1, max_length=32000)
    conversation_id: int | None = Field(
        None, description="Existing conversation ID. Null to create a new one."
    )
    conversation_external_id: str | None = Field(
        None,
        max_length=64,
        description="User-facing conversation id (e.g. conv_jwdi78u4). Optional — "
        "logged at request entry so operators can grep your log backend by this id "
        "to recover the trace_id, then expand into the full request trail.",
    )
    request_id: str | None = Field(
        None,
        max_length=64,
        description="Optional client-supplied per-request correlation id (e.g. "
        "req_abc123). Logged at request entry so operators / AI agents can grep "
        "your log backend for this id to find the matching trace_id, then expand "
        "into the full request trail.",
    )
    customer_context: CustomerContext | None = Field(
        None,
        description="Customer context for auto-create conversation. "
        "Only used when conversation_id is null.",
    )
    resume: bool = Field(
        False,
        description="Resume an interrupted stream. When true, replays saved steps "
        "for the current round and continues from where the stream broke.",
    )
    client_message_id: str | None = Field(
        None,
        max_length=64,
        description="Stable per-user-turn idempotency key (sub-req 3). The client "
        "generates one UUID per `sendChatMessage` call and reuses it across all "
        "retries of the same logical turn. The server uses (conversation_id, "
        "client_message_id) to detect duplicate submissions and auto-resume.",
    )
    last_event_id: str | None = Field(
        None,
        max_length=64,
        pattern=r"^r\d+-e\d+$",
        description="SSE Last-Event-ID resume cursor (sub-req 4). When the "
        "client reconnects mid-round, it sends the id of the last event it "
        "received (e.g. `r3-e42`). The server replays events with `seq > 42` "
        "from its in-memory ring buffer, avoiding both the duplicate "
        "displays and the full assistant_reset that the older step-replay "
        "fallback caused. If the buffer evicted the cursor's window, the "
        "server transparently falls back to step-replay.",
    )
