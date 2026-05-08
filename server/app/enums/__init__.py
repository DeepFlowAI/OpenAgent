from enum import Enum


class TenantStatus(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"


class KnowledgeBaseAuthType(str, Enum):
    NONE = "none"
    TOKEN = "token"


class KnowledgeBaseStatus(str, Enum):
    ACTIVE = "active"
    DELETED = "deleted"


class AgentStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class ConversationStatus(str, Enum):
    ACTIVE = "active"
    ENDED = "ended"


class ConversationSource(str, Enum):
    CHAT = "chat"
    API = "api"


class StepType(str, Enum):
    USER_MESSAGE = "user_message"
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    ASSISTANT_MESSAGE = "assistant_message"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"


class UserConditionOperator(str, Enum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    IN = "in"
    NOT_IN = "not_in"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"


class ScopeOperator(str, Enum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS_ANY = "contains_any"
    NOT_CONTAINS_ANY = "not_contains_any"
