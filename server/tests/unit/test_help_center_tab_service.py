"""
Unit tests for Help Center Tab service helpers.
"""
import re

import pytest

from app.schemas.help_center_tab import TabFilterCondition, TAB_SLUG_PATTERN
from app.services.help_center_tab_service import HelpCenterTabService


_SLUG_RE = re.compile(TAB_SLUG_PATTERN)


class TestGenerateTabSlug:

    def test_matches_slug_pattern(self):
        for _ in range(20):
            slug = HelpCenterTabService.generate_tab_slug()
            assert _SLUG_RE.match(slug), f"generated slug invalid: {slug!r}"

    def test_starts_with_t_dash_prefix(self):
        slug = HelpCenterTabService.generate_tab_slug()
        assert slug.startswith("t-")

    def test_within_length_bounds(self):
        slug = HelpCenterTabService.generate_tab_slug()
        assert 3 <= len(slug) <= 48


class TestTabFilterConditionValidation:

    def test_eq_with_scalar_value_ok(self):
        c = TabFilterCondition(field="x", op="eq", value="abc")
        assert c.value == "abc"

    def test_in_requires_list(self):
        with pytest.raises(ValueError):
            TabFilterCondition(field="x", op="in", value="not-a-list")

    def test_in_with_list_value_ok(self):
        c = TabFilterCondition(field="x", op="in", value=["a", "b"])
        assert c.value == ["a", "b"]

    def test_non_in_op_rejects_list_value(self):
        with pytest.raises(ValueError):
            TabFilterCondition(field="x", op="eq", value=["a", "b"])

    def test_invalid_op_rejected(self):
        with pytest.raises(ValueError):
            TabFilterCondition(field="x", op="lte", value=1)
