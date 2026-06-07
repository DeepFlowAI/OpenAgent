import os

from pydantic import Field
from pydantic_settings import BaseSettings

ENV = os.getenv("APP_ENV", "dev")
ENV_FILE = f".env.{ENV}"


class Settings(BaseSettings):
    APP_NAME: str = Field(default="OpenAgent")
    APP_VERSION: str = Field(default="0.1.0")
    DEBUG: bool = Field(default=False)
    LOG_FORMAT: str = Field(
        default="text",
        description="Log output format: 'text' (human-readable) or 'json' (structured, one JSON object per line)",
    )

    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/openagent"
    )
    AUTO_MIGRATE: bool = Field(
        default=True, description="Run alembic upgrade head on startup"
    )

    REDIS_URL: str | None = Field(default=None)

    SECRET_KEY: str = Field(default="change-me")

    # JWT
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_EXPIRE_MINUTES: int = Field(default=1440)  # 24 hours

    # SMTP (optional — required for password reset)
    SMTP_HOST: str | None = Field(default=None)
    SMTP_PORT: int = Field(default=465)
    SMTP_USER: str | None = Field(default=None)
    SMTP_PASSWORD: str | None = Field(default=None)
    SMTP_FROM: str | None = Field(default=None)
    SMTP_USE_SSL: bool = Field(default=True)

    # LLM Provider (OpenAI-compatible)
    LLM_API_KEY: str = Field(default="")
    LLM_BASE_URL: str = Field(default="https://api.openai.com/v1")

    # OpenRouter (via LiteLLM). Override OPENROUTER_BASE_URL to route through
    # a private proxy / mirror; defaults to the public OpenRouter endpoint.
    OPENROUTER_API_KEY: str = Field(default="")
    OPENROUTER_BASE_URL: str = Field(default="https://openrouter.ai/api/v1")
    # DeepSeek official OpenAI-compatible API
    DEEPSEEK_API_KEY: str = Field(default="")
    DEEPSEEK_API_BASE_URL: str = Field(default="https://api.deepseek.com")
    # Alibaba Bailian OpenAI-compatible API — preferred route for supported domestic models
    ALIYUN_BAILIAN_API_KEY: str = Field(default="")
    ALIYUN_BAILIAN_BASE_URL: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    # MiniMax official API — reserved for direct MiniMax provider access
    MINIMAX_API_KEY: str = Field(default="")
    MINIMAX_BASE_URL: str = Field(default="https://api.minimax.io/v1")
    # Moonshot / Kimi official OpenAI-compatible API
    MOONSHOT_API_KEY: str = Field(default="")
    MOONSHOT_BASE_URL: str = Field(default="https://api.moonshot.cn/v1")
    # Zhipu official OpenAI-compatible API
    ZHIPU_API_KEY: str = Field(default="")
    ZHIPU_BASE_URL: str = Field(default="https://open.bigmodel.cn/api/paas/v4")
    # Same-model retries for transient errors (429/5xx/timeouts). See LiteLLM reliable_completions.
    LLM_NUM_RETRIES: int = Field(default=2, ge=0, le=10)
    # Per-request HTTP timeout (seconds); None = library default. Streaming agent rounds can be long.
    LLM_REQUEST_TIMEOUT_SEC: float | None = Field(default=None)

    # ── Stream-level reliability (stream-level retry spec) ──
    # Master switch — set to false to fall back to legacy behavior (no stream-level retries).
    LLM_STREAM_RETRY_ENABLED: bool = Field(default=True)
    # Wait for the *first* chunk after acompletion returns. Generous to absorb thinking startup.
    LLM_FIRST_CHUNK_TIMEOUT_SEC: float = Field(default=30.0, gt=0)
    # Max gap allowed between two consecutive chunks once streaming has started.
    LLM_IDLE_TIMEOUT_SEC: float = Field(default=15.0, gt=0)
    # Total wall-clock cap for a single LLM stream — exceeding it raises LLMAPIError without retry.
    LLM_HARD_TIMEOUT_SEC: float = Field(default=180.0, gt=0)
    # Max stream-level retry attempts per LLM round (does not count the first attempt).
    LLM_STREAM_RETRY_MAX: int = Field(default=2, ge=0, le=5)
    # Base backoff seconds; the Nth retry waits min(base * 2^(N-1), 4) seconds.
    LLM_STREAM_RETRY_BACKOFF_SEC: float = Field(default=0.5, ge=0)
    # If we have already streamed more than this many visible chars to the client,
    # do NOT retry (avoid duplicating large chunks of output).
    LLM_STREAM_RESET_MAX_CHARS: int = Field(default=50, ge=0)

    # Comma-separated Agent UI model list: ``id`` or ``id:Label`` (e.g.
    # ``kimi-k2.6:Kimi K2.6,glm-5.1:GLM-5.1``). Empty = full built-in catalog.
    LLM_UI_MODELS: str = Field(default="")
    # Comma-separated provider channels in fallback order (e.g. ``aliyun-bailian`` or
    # ``aliyun-bailian,openrouter``). Empty = built-in multi-provider fallback chain.
    LLM_PROVIDER_CHANNELS: str = Field(default="")

    # ── Conversation title summary ──
    # After a conversation's first round completes, asynchronously generate a
    # short one-line summary title and store it on ``conversations.title`` for
    # the Web SDK history list. Best-effort: failures keep the first-user-message
    # fallback title untouched and never affect the chat hot path.
    CONVERSATION_TITLE_ENABLED: bool = Field(default=True)
    CONVERSATION_TITLE_MODEL: str = Field(default="qwen3.6-flash")
    CONVERSATION_TITLE_MAX_CHARS: int = Field(default=15, ge=4, le=40)
    CONVERSATION_TITLE_TEMPERATURE: float = Field(default=0.3, ge=0.0, le=1.0)
    CONVERSATION_TITLE_MAX_TOKENS: int = Field(default=30, ge=8, le=128)

    # ── Default Tenant (auto-provisioned on first startup) ────────────────
    # On first boot, if the `tenants` table is empty, the seed step creates
    # one tenant using these values. Open-source users log in at `/login`
    # with: tenant=DEFAULT_TENANT_ID, username=DEFAULT_ADMIN_USERNAME,
    # password=DEFAULT_ADMIN_PASSWORD — then change the password immediately.
    # Once any tenant exists, this section is a no-op forever.
    DEFAULT_TENANT_ID: str = Field(default="default")
    DEFAULT_TENANT_NAME: str = Field(default="Default Workspace")
    DEFAULT_ADMIN_USERNAME: str = Field(default="admin")
    DEFAULT_ADMIN_PASSWORD: str = Field(default="Admin123456")

    # Tenant Platform API Key — only used by the closed-source tenants
    # extension (multi-tenant builds). Open-source builds never read it.
    TENANT_PLATFORM_API_KEY: str = Field(default="")

    # SiliconFlow API (Embedding & Reranker)
    SILICONFLOW_API_KEY: str = Field(default="")
    SILICONFLOW_BASE_URL: str = Field(default="https://api.siliconflow.cn/v1")
    # Knowledge-base backends: siliconflow | aliyun-bailian. Empty = auto from API keys.
    EMBEDDING_PROVIDER: str = Field(default="")
    RERANKER_PROVIDER: str = Field(default="")
    EMBEDDING_MODEL: str = Field(default="Pro/BAAI/bge-m3")
    # Backup embedding model used when the primary model keeps failing
    # (same provider). Empty disables failover. See SiliconFlowEmbeddingProvider.
    EMBEDDING_FALLBACK_MODEL: str = Field(default="BAAI/bge-m3")
    RERANKER_MODEL: str = Field(default="Pro/BAAI/bge-reranker-v2-m3")
    EMBEDDING_DIMENSION: int = Field(default=1024, ge=64)
    EMBEDDING_BATCH_SIZE: int = Field(default=10, ge=1, le=25)
    EMBEDDING_BATCH_CONCURRENCY: int = Field(default=3, ge=1, le=8)
    ALIYUN_BAILIAN_RERANK_URL: str = Field(
        default="https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
    )

    # Alibaba Cloud OSS
    OSS_ACCESS_KEY: str = Field(default="")
    OSS_SECRET_KEY: str = Field(default="")
    OSS_ADDR: str = Field(default="", description="Public access URL prefix, e.g. https://bucket.oss-cn-beijing.aliyuncs.com")
    OSS_URL: str = Field(default="", description="OSS endpoint, e.g. https://oss-cn-beijing.aliyuncs.com")
    OSS_BUCKET: str = Field(default="")

    # ── Observability (vendor-neutral, OTLP/OpenTelemetry-based) ──
    # Backend selector: "otel" → OTLP exporter; "noop" → disabled (zero overhead).
    # Defaults to "noop" so unconfigured environments stay silent.
    OBSERVABILITY_BACKEND: str = Field(default="noop")

    # Service identity (written to every span/log as `resource_attributes`)
    OTEL_SERVICE_NAME: str = Field(default="openagent-api")
    OTEL_DEPLOYMENT_ENVIRONMENT: str = Field(default="dev")

    # OTLP transport (any OpenTelemetry-compatible backend works here:
    # Grafana Cloud / Tempo, SigNoz, vendor APMs, self-hosted collectors…).
    OTEL_EXPORTER_OTLP_ENDPOINT: str = Field(default="")
    # Comma-separated "k=v,k=v" — typically: Authorization=Basic <base64(user:pass)>
    OTEL_EXPORTER_OTLP_HEADERS: str = Field(default="")

    # ── Vendor-specific extras (GreptimeDB-compatible pipelines etc.) ──
    # Extra header injected on the traces signal so GreptimeDB flattens span attrs.
    OTEL_TRACES_PIPELINE_NAME: str = Field(default="greptime_trace_v1")
    # Extra header injected on the logs signal so GreptimeDB writes to this table.
    OTEL_LOGS_TABLE_NAME: str = Field(default="otel_logs")

    # Whether to capture the full LLM request/response message bodies as span
    # attributes. Off by default for PII safety. Can be flipped per-environment.
    OTEL_CAPTURE_LLM_CONTENT: bool = Field(default=False)

    # ── Frontend telemetry (batch event ingest) ──
    # Master switch for /public/channels/{token}/telemetry/events. When False
    # the endpoint accepts requests (still validates schema) but does NOT call
    # logger — useful for emergency cost cutoff without a deploy.
    TELEMETRY_ENABLED: bool = Field(default=True)

    # Comma-separated browser origins (e.g. https://app.example.com). When empty,
    # the API uses Access-Control-Allow-Origin: *.
    CORS_ALLOW_ORIGINS: str = Field(default="")
    # Cross-origin cookies are not needed for Bearer-token auth; keep disabled
    # unless a deployment explicitly relies on browser credentials.
    CORS_ALLOW_CREDENTIALS: bool = Field(default=False)

    # ── Help Center (3.6) ──
    # Default platform docs host used to compose visitor URLs:
    #   https://{PUBLIC_DOCS_HOST}/hc/{help_center_slug}/...
    # Host only — no scheme, no trailing slash. Self-custom domains are out of scope this release.
    PUBLIC_DOCS_HOST: str = Field(default="docs.example.com")

    model_config = {"env_file": ENV_FILE, "env_file_encoding": "utf-8"}


settings = Settings()
