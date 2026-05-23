"""
Unit tests for the notebook tool executor and prompt variable rendering.
"""
from types import SimpleNamespace

import pytest

from app.schemas.agent_tool import NOTEBOOK_PARAMETERS_SCHEMA
from app.services.agent_engine_service import _render_system_prompt, _runtime_parameters_schema
from app.services.tool_executors.base import ToolContext
from app.services.tool_executors.notebook_executor import (
    NOTEBOOK_EMPTY_OUTPUT,
    NotebookToolExecutor,
    render_notebook_output,
)


class _FakeResult:
    def __init__(self, items=None, scalar=None) -> None:
        self._items = items or []
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return self._items

    def scalar_one_or_none(self):
        return self._scalar


class _FakeDb:
    def __init__(self, steps=None) -> None:
        self.steps = steps or []

    async def execute(self, _stmt):
        return _FakeResult(items=self.steps)


def _ctx(steps=None) -> ToolContext:
    return ToolContext(
        db=_FakeDb(steps),  # type: ignore[arg-type]
        conversation_id=1,
        tenant_id="T_TEST_001",
        agent_id=1,
    )


def _tool_step(order: int, args: dict, response: str | None = None):
    return SimpleNamespace(
        conversation_id=1,
        round_number=1,
        step_order=order,
        step_type="tool_call",
        tool_name="notebook",
        tool_type="notebook",
        tool_arguments=args,
        tool_response=response,
    )


def _search_step(order: int, response: str):
    return SimpleNamespace(
        conversation_id=1,
        round_number=1,
        step_order=order,
        step_type="tool_call",
        tool_name="knowledge_search",
        tool_type="search",
        tool_arguments={"query": "policy"},
        tool_response=response,
    )


def _doc_grep_step(order: int, response: str):
    return SimpleNamespace(
        conversation_id=1,
        round_number=1,
        step_order=order,
        step_type="tool_call",
        tool_name="doc_grep",
        tool_type="doc_grep",
        tool_arguments={"doc_id": "6670", "pattern": "ANNEX"},
        tool_response=response,
    )


class TestNotebookToolExecutor:
    def test_runtime_schema_uses_canonical_notebook_schema(self):
        tool = SimpleNamespace(
            is_system=True,
            tool_type="notebook",
            name="notebook",
            parameters_schema={"type": "object", "properties": {}},
        )

        schema = _runtime_parameters_schema(tool)

        assert schema == NOTEBOOK_PARAMETERS_SCHEMA
        assert "line" in schema["properties"]["items"]["items"]["properties"]

    @pytest.mark.asyncio
    async def test_execute_add_returns_current_total(self):
        executor = NotebookToolExecutor()

        result = await executor.execute(
            {
                "brief": "save findings",
                "action": "add",
                "items": [{"text": "第一条"}, {"text": "第二条"}],
            },
            {},
            _ctx(),
        )

        assert '<notebook_response action="add">' in result
        assert "Added 2 item(s) to notebook." in result
        assert "Current total: 2 items." in result

    @pytest.mark.asyncio
    async def test_render_replays_add_and_remove_steps(self):
        steps = [
            _tool_step(1, {"action": "add", "items": [{"text": "保留 A"}]}),
            _tool_step(2, {"action": "add", "items": [{"text": "保留 B"}]}),
            _tool_step(3, {"action": "remove", "items": [{"id": "note_001"}]}),
        ]

        output = await render_notebook_output(_ctx(steps))

        assert '<note id="note_002" type="text">' in output
        assert "保留 B" in output
        assert "保留 A" not in output
        assert "note_001" not in output

    @pytest.mark.asyncio
    async def test_render_uses_prior_search_response_for_slice_notes(self):
        search_xml = (
            '<search_results>\n'
            '<result doc_id="7" slice_id="5" title="退换货政策">\n'
            "签收 15 天内支持处理。\n"
            "</result>\n"
            "</search_results>"
        )
        steps = [
            _search_step(1, search_xml),
            _tool_step(2, {"action": "add", "items": [{"slice_id": "5"}]}),
        ]

        output = await render_notebook_output(_ctx(steps))

        assert '<note id="note_001" type="slice">' in output
        assert 'slice_id="5" doc_id="7" title="退换货政策"' in output
        assert "签收 15 天内支持处理。" in output

    @pytest.mark.asyncio
    async def test_render_uses_prior_doc_grep_response_for_grep_match_notes(self):
        grep_xml = (
            '<grep_results doc_id="6670" pattern="ANNEX" total_matches="4" showing="4">\n'
            '<match line="1720">\n'
            "1719| \n"
            "1720| ## ANNEX 7 - INDICATION OF THE DOWNWARD INCLINATION\n"
            "1721| \n"
            "</match>\n"
            "</grep_results>"
        )
        steps = [
            _doc_grep_step(1, grep_xml),
            _tool_step(
                2,
                {
                    "action": "add",
                    "items": [
                        {"doc_id": "6670", "line": "1720", "text": "Annex heading"}
                    ],
                },
            ),
        ]

        output = await render_notebook_output(_ctx(steps))

        assert '<note id="note_001" type="grep_match">' in output
        assert 'doc_id="6670" line="1720" pattern="ANNEX"' in output
        assert "1720| ## ANNEX 7 - INDICATION OF THE DOWNWARD INCLINATION" in output
        assert "[annotation] Annex heading" in output

    @pytest.mark.asyncio
    async def test_empty_notebook_output(self):
        assert await render_notebook_output(_ctx()) == NOTEBOOK_EMPTY_OUTPUT

    @pytest.mark.asyncio
    async def test_system_prompt_injects_tool_notebook_output(self):
        steps = [_tool_step(1, {"action": "add", "items": [{"text": "跨轮事实"}]})]

        rendered = await _render_system_prompt(
            "当前笔记：\n{{tool_notebook_output}}",
            {},
            [{"name": "notebook", "tool_type": "notebook"}],
            _ctx(steps),
        )

        assert "<notebook>" in rendered
        assert "跨轮事实" in rendered
