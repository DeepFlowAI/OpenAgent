"""
Unit tests for the search repository's filter clause builder.

These tests focus on the JSONB scalar comparison codepath that previously
used `str(value)`, which produced `"True"`/`"False"` for Python booleans
and never matched PostgreSQL's lowercase `jsonb ->>` rendering.
"""
from sqlalchemy.dialects import postgresql

from app.models.slice import Slice
from app.repositories.search_repository import (
    SearchRepository,
    _to_jsonb_text,
    normalize_filter_node,
)
from app.schemas.search import FilterNode


def _compile(clause) -> str:
    """Render a SQLAlchemy clause as a PostgreSQL literal SQL string."""
    return str(
        clause.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


class TestToJsonbText:
    def test_python_false_renders_lowercase(self):
        assert _to_jsonb_text(False) == "false"

    def test_python_true_renders_lowercase(self):
        assert _to_jsonb_text(True) == "true"

    def test_string_passthrough(self):
        assert _to_jsonb_text("foo") == "foo"

    def test_int_to_text(self):
        assert _to_jsonb_text(7) == "7"

    def test_none_to_null(self):
        assert _to_jsonb_text(None) == "null"


class TestEqOperatorOnBoolean:
    """`has_fragrance == false` must compile to lowercase `'false'`.

    Regression: previously used `str(False)` → `"False"`, which never matches
    the JSONB `->>` text representation.
    """

    def test_eq_false_emits_lowercase_literal(self):
        node = FilterNode(field="has_fragrance", op="eq", value=False)
        clause = SearchRepository._build_filter_condition(Slice.slice_meta, node)
        sql = _compile(clause)
        assert "'false'" in sql
        assert "'False'" not in sql

    def test_eq_true_emits_lowercase_literal(self):
        node = FilterNode(field="has_preservative", op="eq", value=True)
        clause = SearchRepository._build_filter_condition(Slice.slice_meta, node)
        sql = _compile(clause)
        assert "'true'" in sql
        assert "'True'" not in sql

    def test_ne_false_emits_lowercase_literal(self):
        node = FilterNode(field="has_fragrance", op="ne", value=False)
        clause = SearchRepository._build_filter_condition(Slice.slice_meta, node)
        sql = _compile(clause)
        assert "'false'" in sql
        assert "'False'" not in sql

    def test_in_with_booleans_emits_lowercase_literals(self):
        node = FilterNode(
            field="has_fragrance",
            op="in",
            value=[True, False],
        )
        clause = SearchRepository._build_filter_condition(Slice.slice_meta, node)
        sql = _compile(clause)
        assert "'true'" in sql
        assert "'false'" in sql
        assert "'True'" not in sql
        assert "'False'" not in sql


class TestEqOperatorOnString:
    """Non-boolean values still compile to their plain string form."""

    def test_eq_string_unchanged(self):
        node = FilterNode(field="product_category", op="eq", value="护臀膏")
        clause = SearchRepository._build_filter_condition(Slice.slice_meta, node)
        sql = _compile(clause)
        assert "'护臀膏'" in sql

    def test_eq_int_unchanged(self):
        node = FilterNode(field="year", op="eq", value=2024)
        clause = SearchRepository._build_filter_condition(Slice.slice_meta, node)
        sql = _compile(clause)
        assert "'2024'" in sql


class TestHasAnyMultiValue:
    """`keyword[]` console fixed_filters store multi selections as 'a,b,c' strings.

    Backend must split them so JSONB `@>` compares against each tag, not the
    literal CSV string.
    """

    def test_normalize_splits_csv_for_has_any(self):
        node = FilterNode(field="tags", op="has_any", value="优先参考产品,QA,货号")
        out = normalize_filter_node(node)
        assert out.op == "has_any"
        assert out.value == ["优先参考产品", "QA", "货号"]

    def test_normalize_trims_whitespace_and_blanks(self):
        node = FilterNode(field="tags", op="has_any", value=" A , B , ")
        out = normalize_filter_node(node)
        assert out.value == ["A", "B"]

    def test_normalize_keeps_real_list_unchanged(self):
        node = FilterNode(field="tags", op="has_any", value=["A", "B"])
        out = normalize_filter_node(node)
        assert out.value == ["A", "B"]

    def test_normalize_keeps_single_token_string_as_one_tag(self):
        node = FilterNode(field="tags", op="has_any", value="优先参考产品")
        out = normalize_filter_node(node)
        # No comma → no split; single-token path falls through unchanged
        assert out.value == "优先参考产品"

    def test_has_all_csv_also_split(self):
        node = FilterNode(field="tags", op="has_all", value="A,B")
        out = normalize_filter_node(node)
        assert out.op == "has_all"
        assert out.value == ["A", "B"]

    def test_has_any_csv_compiles_to_per_tag_jsonb_clauses(self):
        node = FilterNode(field="tags", op="has_any", value="优先参考产品,QA")
        clause = SearchRepository._build_filter_condition(Slice.doc_meta, node)
        sql = _compile(clause)
        assert "'优先参考产品'" in sql
        assert "'QA'" in sql
        # Whole CSV string must NOT appear as one literal tag
        assert "'优先参考产品,QA'" not in sql
        # Each tag should hit the JSONB containment path
        assert "@>" in sql

    def test_has_any_single_tag_matches_jsonb_array(self):
        node = FilterNode(field="tags", op="has_any", value=["优先参考产品"])
        clause = SearchRepository._build_filter_condition(Slice.doc_meta, node)
        sql = _compile(clause)
        assert "'优先参考产品'" in sql
        assert "@>" in sql


class TestInMultiValue:
    """`enum` console fixed_filters should treat CSV strings as multiple candidates."""

    def test_normalize_splits_csv_for_in(self):
        node = FilterNode(
            field="recommendation_tier",
            op="in",
            value="priority_reference,recommended",
        )
        out = normalize_filter_node(node)
        assert out.op == "in"
        assert out.value == ["priority_reference", "recommended"]

    def test_in_csv_compiles_to_membership_candidates(self):
        node = FilterNode(
            field="recommendation_tier",
            op="in",
            value="priority_reference,recommended",
        )
        clause = SearchRepository._build_filter_condition(Slice.doc_meta, node)
        sql = _compile(clause)
        assert "'priority_reference'" in sql
        assert "'recommended'" in sql
        assert "'priority_reference,recommended'" not in sql
