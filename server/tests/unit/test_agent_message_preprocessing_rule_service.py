"""
Unit tests for agent message preprocessing rules.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.exceptions import ValidationError
from app.schemas.agent_message_preprocessing_rule import (
    AgentMessagePreprocessingRuleCreate,
)
from app.services.agent_message_preprocessor import AgentMessagePreprocessor
from app.services.agent_message_preprocessing_rule_service import (
    AgentMessagePreprocessingRuleService,
)


def _rule(condition: str, action: str, value: str):
    return SimpleNamespace(
        id=1,
        condition=condition,
        action=action,
        value=value,
    )


class TestAgentMessagePreprocessingRuleService:

    def test_apply_rules_prefixes_each_regex_match(self):
        rules = [_rule(r"\d+", "prefix", "[编号]")]

        result = AgentMessagePreprocessor.apply_rules(
            "订单 123 和 456", rules
        )

        assert result.text == "订单 [编号]123 和 [编号]456"

    def test_apply_rules_suffixes_each_regex_match(self):
        rules = [_rule(r"[A-Z]{2}\d{2}", "suffix", " code")]

        result = AgentMessagePreprocessor.apply_rules(
            "AA12 and BB34", rules
        )

        assert result.text == "AA12 code and BB34 code"

    def test_apply_rules_uses_rule_order(self):
        rules = [
            _rule(r"^\d{20}$", "prefix", "[防伪码]"),
            _rule(r"$", "suffix", "[待核验]"),
        ]

        result = AgentMessagePreprocessor.apply_rules(
            "12345678901234567890", rules
        )

        assert result.text == "[防伪码]12345678901234567890[待核验]"

    def test_apply_rules_skips_rule_that_would_exceed_length_limit(self):
        rules = [_rule(r".", "prefix", "xxxxx")]

        result = AgentMessagePreprocessor.apply_rules("abc", rules, max_length=6)

        assert result.text == "abc"
        snapshot = result.metadata["message_preprocessing"]
        assert snapshot["skipped_rules"] == [
            {"id": 1, "reason": "processed_message_too_long"}
        ]

    def test_apply_rules_skips_rule_that_exceeds_match_limit(self):
        rules = [_rule(r".", "suffix", "x")]

        result = AgentMessagePreprocessor.apply_rules(
            "abc", rules, max_matches_per_rule=2
        )

        assert result.text == "abc"
        snapshot = result.metadata["message_preprocessing"]
        assert snapshot["skipped_rules"] == [
            {"id": 1, "reason": "too_many_matches"}
        ]

    def test_apply_rules_skips_timed_out_rule(self):
        rules = [_rule(r".", "suffix", "x")]

        with patch.object(
            AgentMessagePreprocessor,
            "_apply_rule_to_text",
            side_effect=TimeoutError,
        ):
            result = AgentMessagePreprocessor.apply_rules("abc", rules)

        assert result.text == "abc"
        snapshot = result.metadata["message_preprocessing"]
        assert snapshot["skipped_rules"] == [
            {"id": 1, "reason": "regex_timeout"}
        ]

    def test_snapshot_processed_content_round_trips(self):
        rules = [_rule(r"^\d+$", "prefix", "[编号]")]

        result = AgentMessagePreprocessor.apply_rules("123", rules)

        assert AgentMessagePreprocessor.get_snapshot_processed_content(
            result.metadata
        ) == "[编号]123"

    @pytest.mark.asyncio
    async def test_create_invalid_regex_raises_validation_error(self):
        db = AsyncMock()
        data = AgentMessagePreprocessingRuleCreate(
            condition="[",
            action="prefix",
            value="x",
        )

        with (
            patch(
                "app.services.agent_message_preprocessing_rule_service.AgentRepository"
            ) as agent_repo,
            patch(
                "app.services.agent_message_preprocessing_rule_service."
                "AgentMessagePreprocessingRuleRepository"
            ) as rule_repo,
        ):
            agent_repo.get_by_id = AsyncMock(
                return_value=SimpleNamespace(id=7, tenant_id="T_TEST")
            )
            rule_repo.create = AsyncMock()

            with pytest.raises(ValidationError, match="Invalid regular expression"):
                await AgentMessagePreprocessingRuleService.create(
                    db, "T_TEST", 7, data
                )

        rule_repo.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_preprocess_message_fetches_rules_and_applies_them(self):
        db = AsyncMock()

        with patch(
            "app.services.agent_message_preprocessor."
            "AgentMessagePreprocessingRuleRepository"
        ) as rule_repo:
            rule_repo.list_by_agent = AsyncMock(
                return_value=[_rule(r"^\d{20}$", "prefix", "[防伪码]")]
            )

            result = await AgentMessagePreprocessor.prepare_current_user_message(
                db, "T_TEST", 7, "12345678901234567890"
            )

        assert result.text == "[防伪码]12345678901234567890"
        rule_repo.list_by_agent.assert_awaited_once_with(db, "T_TEST", 7)
