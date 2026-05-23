"""
Runtime-safe agent message preprocessing.
"""
import logging
from dataclasses import dataclass
from typing import Any

import regex
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_message_preprocessing_rule_repository import (
    AgentMessagePreprocessingRuleRepository,
)

logger = logging.getLogger(__name__)

MAX_PROCESSED_MESSAGE_LENGTH = 32000
MAX_RULES_PER_MESSAGE = 20
MAX_MATCHES_PER_RULE = 1000
REGEX_TIMEOUT_SECONDS = 0.05
SNAPSHOT_KEY = "message_preprocessing"
SNAPSHOT_VERSION = 1


class _RuleLimitExceeded(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class MessagePreprocessingResult:
    text: str
    metadata: dict[str, Any]

    @property
    def changed(self) -> bool:
        snapshot = self.metadata.get(SNAPSHOT_KEY, {})
        return bool(snapshot.get("changed"))


class AgentMessagePreprocessor:
    """Prepare the current user message for LLM/runtime use."""

    @staticmethod
    async def prepare_current_user_message(
        db: AsyncSession,
        tenant_id: str,
        agent_id: int,
        text: str,
    ) -> MessagePreprocessingResult:
        rules = await AgentMessagePreprocessingRuleRepository.list_by_agent(
            db, tenant_id, agent_id
        )
        return AgentMessagePreprocessor.apply_rules(text, rules)

    @staticmethod
    def apply_rules(
        text: str,
        rules: list,
        *,
        max_length: int = MAX_PROCESSED_MESSAGE_LENGTH,
        max_rules: int = MAX_RULES_PER_MESSAGE,
        max_matches_per_rule: int = MAX_MATCHES_PER_RULE,
        regex_timeout_seconds: float = REGEX_TIMEOUT_SECONDS,
    ) -> MessagePreprocessingResult:
        result = text
        applied_rules: list[dict[str, Any]] = []
        skipped_rules: list[dict[str, Any]] = []

        if len(rules) > max_rules:
            skipped_rules.append({
                "reason": "too_many_rules",
                "count": len(rules) - max_rules,
            })

        for rule in rules[:max_rules]:
            rule_id = getattr(rule, "id", None)
            try:
                next_result, match_count = (
                    AgentMessagePreprocessor._apply_rule_to_text(
                        result,
                        rule,
                        max_length=max_length,
                        max_matches_per_rule=max_matches_per_rule,
                        regex_timeout_seconds=regex_timeout_seconds,
                    )
                )
            except regex.error as exc:
                skipped_rules.append({"id": rule_id, "reason": "invalid_regex"})
                logger.warning(
                    "Skipping invalid preprocessing rule id=%s: %s",
                    rule_id,
                    exc,
                )
                continue
            except TimeoutError:
                skipped_rules.append({"id": rule_id, "reason": "regex_timeout"})
                logger.warning(
                    "Skipping timed-out preprocessing rule id=%s timeout=%.3fs",
                    rule_id,
                    regex_timeout_seconds,
                )
                continue
            except _RuleLimitExceeded as exc:
                skipped_rules.append({"id": rule_id, "reason": exc.reason})
                logger.warning(
                    "Skipping limited preprocessing rule id=%s reason=%s",
                    rule_id,
                    exc.reason,
                )
                continue
            except ValueError as exc:
                skipped_rules.append({"id": rule_id, "reason": "invalid_action"})
                logger.warning(
                    "Skipping invalid preprocessing rule id=%s: %s",
                    rule_id,
                    exc,
                )
                continue

            if match_count > 0:
                result = next_result
                applied_rules.append({
                    "id": rule_id,
                    "action": getattr(rule, "action", None),
                    "matches": match_count,
                })

        return MessagePreprocessingResult(
            text=result,
            metadata={
                SNAPSHOT_KEY: {
                    "version": SNAPSHOT_VERSION,
                    "processed_content": result,
                    "changed": result != text,
                    "original_length": len(text),
                    "processed_length": len(result),
                    "applied_rule_ids": [
                        item["id"]
                        for item in applied_rules
                        if item.get("id") is not None
                    ],
                    "applied_rules": applied_rules,
                    "skipped_rules": skipped_rules,
                    "limits": {
                        "max_length": max_length,
                        "max_rules": max_rules,
                        "max_matches_per_rule": max_matches_per_rule,
                        "regex_timeout_seconds": regex_timeout_seconds,
                    },
                }
            },
        )

    @staticmethod
    def get_snapshot_processed_content(metadata: dict | None) -> str | None:
        if not isinstance(metadata, dict):
            return None
        snapshot = metadata.get(SNAPSHOT_KEY)
        if not isinstance(snapshot, dict):
            return None
        processed_content = snapshot.get("processed_content")
        return processed_content if isinstance(processed_content, str) else None

    @staticmethod
    def _apply_rule_to_text(
        text: str,
        rule,
        *,
        max_length: int,
        max_matches_per_rule: int,
        regex_timeout_seconds: float,
    ) -> tuple[str, int]:
        pattern = regex.compile(rule.condition)
        value = rule.value or ""
        action = rule.action
        match_count = 0
        projected_length = len(text)

        def replace(match) -> str:
            nonlocal match_count, projected_length
            match_count += 1
            if match_count > max_matches_per_rule:
                raise _RuleLimitExceeded("too_many_matches")
            projected_length += len(value)
            if projected_length > max_length:
                raise _RuleLimitExceeded("processed_message_too_long")

            matched_text = match.group(0)
            if action == "prefix":
                return f"{value}{matched_text}"
            if action == "suffix":
                return f"{matched_text}{value}"
            raise ValueError(f"Unsupported preprocessing action: {action}")

        next_text = pattern.sub(replace, text, timeout=regex_timeout_seconds)
        if len(next_text) > max_length:
            raise _RuleLimitExceeded("processed_message_too_long")
        return next_text, match_count
