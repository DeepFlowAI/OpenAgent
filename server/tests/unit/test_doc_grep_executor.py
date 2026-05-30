"""
Unit tests for the doc_grep tool executor.
"""
import pytest

from app.models.document import Document
from app.services.tool_executors.base import ToolContext
from app.services.tool_executors.doc_grep_executor import DocGrepToolExecutor


class _FakeResult:
    def __init__(self, doc: Document | None) -> None:
        self._doc = doc

    def scalar_one_or_none(self) -> Document | None:
        return self._doc


class _FakeDb:
    def __init__(self, doc: Document | None) -> None:
        self._doc = doc

    async def execute(self, _stmt):
        return _FakeResult(self._doc)


def _ctx(doc: Document | None) -> ToolContext:
    return ToolContext(
        db=_FakeDb(doc),  # type: ignore[arg-type]
        conversation_id=1,
        tenant_id="T_TEST_001",
        agent_id=1,
    )


def _doc(markdown: str) -> Document:
    return Document(
        id=10,
        knowledge_base_id=1,
        tenant_id="T_TEST_001",
        file_path="policy.md",
        markdown_content=markdown,
    )


class TestDocGrepToolExecutor:
    @pytest.mark.asyncio
    async def test_execute_literal_pattern_returns_context(self):
        executor = DocGrepToolExecutor()
        result = await executor.execute(
            {"brief": "find return policy", "doc_id": "10", "pattern": "退换货", "context_lines": 1},
            {},
            _ctx(_doc("第一行\n用户可申请退换货\n最后一行")),
        )

        assert '<grep_results doc_id="10" pattern="退换货" total_matches="1" showing="1">' in result
        assert '<match line="2">' in result
        assert "1| 第一行" in result
        assert "2| 用户可申请退换货" in result
        assert "3| 最后一行" in result

    @pytest.mark.asyncio
    async def test_execute_defaults_to_ignore_case(self):
        executor = DocGrepToolExecutor()
        result = await executor.execute(
            {"brief": "find api", "doc_id": "10", "pattern": "api", "context_lines": 0},
            {},
            _ctx(_doc("OpenAPI")),
        )

        assert 'total_matches="1"' in result

    @pytest.mark.asyncio
    async def test_execute_can_disable_ignore_case(self):
        executor = DocGrepToolExecutor()
        result = await executor.execute(
            {
                "brief": "find api",
                "doc_id": "10",
                "pattern": "api",
                "ignore_case": False,
                "context_lines": 0,
            },
            {},
            _ctx(_doc("OpenAPI")),
        )

        assert 'total_matches="0"' in result

    @pytest.mark.asyncio
    async def test_execute_merges_overlapping_context_windows(self):
        executor = DocGrepToolExecutor()
        result = await executor.execute(
            {"brief": "find hits", "doc_id": "10", "pattern": "命中", "context_lines": 1},
            {},
            _ctx(_doc("a\n命中一\n命中二\nd")),
        )

        assert result.count("<match line=") == 1
        assert '<match line="2">' in result
        assert "2| 命中一" in result
        assert "3| 命中二" in result

    @pytest.mark.asyncio
    async def test_execute_truncates_showing_but_counts_total_matches(self):
        executor = DocGrepToolExecutor()
        markdown = "\n".join(f"hit {i}" for i in range(25))
        result = await executor.execute(
            {"brief": "find all hits", "doc_id": "10", "pattern": "hit", "context_lines": 0},
            {},
            _ctx(_doc(markdown)),
        )

        assert 'total_matches="25"' in result
        assert 'showing="20"' in result
        assert result.count("<match line=") == 1
        assert '<match line="1">' in result
        assert "20| hit 19" in result
        assert "21| hit 20" not in result

    @pytest.mark.asyncio
    async def test_execute_returns_error_for_invalid_pattern(self):
        executor = DocGrepToolExecutor()
        result = await executor.execute(
            {"brief": "bad regex", "doc_id": "10", "pattern": "("},
            {},
            _ctx(_doc("content")),
        )

        assert "Error: Invalid pattern" in result
        assert "re.error" in result

    @pytest.mark.asyncio
    async def test_execute_returns_error_for_pattern_too_long(self):
        executor = DocGrepToolExecutor()
        result = await executor.execute(
            {"brief": "long regex", "doc_id": "10", "pattern": "a" * 201},
            {},
            _ctx(_doc("content")),
        )

        assert "Error: Pattern too long" in result

    @pytest.mark.asyncio
    async def test_execute_returns_error_when_document_not_found(self):
        executor = DocGrepToolExecutor()
        result = await executor.execute(
            {"brief": "missing doc", "doc_id": "10", "pattern": "content"},
            {},
            _ctx(None),
        )

        assert "Error: Document not found (doc_id=10)." in result
