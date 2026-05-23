"""
Search Pydantic schemas — aligned with OData 4.01 $filter semantics.
"""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FilterNode(BaseModel):
    """OData-aligned filter AST node.

    Node types:
    - Leaf comparison: { field, op, value } (op: eq/ne/gt/ge/lt/le/in)
    - Logic: { op: "and"/"or", value: [FilterNode...] } or { op: "not", value: FilterNode }
    - String function: { fn, field, value } (fn: contains/startswith/endswith/matchesPattern)
    - Collection lambda: { op: "any"/"all", field, var, predicate: FilterNode }
    """
    field: str | None = None
    op: str | None = None
    value: Any = None
    fn: str | None = None
    var: str | None = None
    predicate: "FilterNode | None" = None

    @model_validator(mode="after")
    def _coerce_nested(self) -> "FilterNode":
        """Recursively parse nested dicts in 'value' into FilterNode instances."""
        op = self.op or ""
        if op in ("and", "or") and isinstance(self.value, list):
            self.value = [
                FilterNode.model_validate(v) if isinstance(v, dict) else v
                for v in self.value
            ]
        elif op == "not" and isinstance(self.value, dict):
            self.value = FilterNode.model_validate(self.value)
        return self


FilterNode.model_rebuild()

# Backward compatibility alias
FilterCondition = FilterNode


class SearchFilter(BaseModel):
    doc_ids: list[str] | None = None
    doc_meta: list[FilterNode] | None = None
    slice_meta: list[FilterNode] | None = None

    @model_validator(mode="before")
    @classmethod
    def _wrap_single_node(cls, data: Any) -> Any:
        """Accept a single FilterNode dict for doc_meta/slice_meta (wrap in list)."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        for key in ("doc_meta", "slice_meta"):
            val = data.get(key)
            if isinstance(val, dict):
                data[key] = [val]
        return data


class BM25Config(BaseModel):
    enabled: bool = True
    weight: float = Field(0.3, ge=0, le=1)


class VectorConfig(BaseModel):
    enabled: bool = True
    weight: float = Field(0.7, ge=0, le=1)


class SearchConfig(BaseModel):
    mode: str = Field("hybrid", pattern=r"^(hybrid|bm25|vector)$")
    bm25: BM25Config = Field(default_factory=BM25Config)
    vector: VectorConfig = Field(default_factory=VectorConfig)


class RerankerConfig(BaseModel):
    enabled: bool = False
    model: str | None = None
    top_n: int | None = None
    min_score: float | None = Field(None, ge=0, le=1)


class HighlightConfig(BaseModel):
    enabled: bool = False
    pre_tag: str = "<mark>"
    post_tag: str = "</mark>"


class PaginationConfig(BaseModel):
    limit: int = Field(10, ge=1, le=500)
    offset: int = Field(0, ge=0)


class SubjectContext(BaseModel):
    """Subject context for permission engine evaluation (§6.4 of design 2.9).
    Mirrors conversation customer context from §2.8."""
    external_user_id: str | None = None
    display_name: str | None = None
    email: str | None = None
    source: str | None = None
    channel_id: int | str | None = None
    channel_source: str | None = None
    metadata: dict[str, Any] | None = None


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=512)
    filter: SearchFilter | None = None
    search: SearchConfig = Field(default_factory=SearchConfig)
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)
    highlight: HighlightConfig = Field(default_factory=HighlightConfig)
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)
    subject_context: SubjectContext | None = Field(
        None, description="Subject context for permission engine; auto-loaded in chat pipeline"
    )


class ScoresDetail(BaseModel):
    bm25: float | None = None
    vector: float | None = None
    reranker: float | None = None


class HighlightResult(BaseModel):
    content: str


class SearchResultItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slice_id: int
    doc_id: int
    content: str
    toc_path: list[str] | None = None
    toc_ancestors: str | None = None
    score: float = 0.0
    scores: ScoresDetail = Field(default_factory=ScoresDetail)
    source_url: str | None = None
    markdown_url: str | None = None
    doc_meta: dict[str, Any] | None = None
    slice_meta: dict[str, Any] | None = None
    highlight: HighlightResult | None = None


class SearchResponse(BaseModel):
    total: int
    items: list[SearchResultItem]
