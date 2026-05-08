"""
Permission engine — evaluates deny rules against subject context,
compiles matching rules into SQLAlchemy exclusion filters on slice rows.

§6 of the permission engine spec: default-visible, deny-only, OR across rules.
"""
import logging
from typing import Any

from sqlalchemy import and_, or_, not_, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.slice import Slice
from app.repositories.kb_permission_rule_repository import KbPermissionRuleRepository

logger = logging.getLogger(__name__)

# The JSONB column and key where access_keywords tokens are stored on slice rows.
# doc_meta is inherited from the document; effective_access_keywords = doc_meta.access_keywords
# unless overridden at slice level (future: slice_meta.access_keywords).
_AK_COLUMN = Slice.doc_meta
_AK_KEY = "access_keywords"


class PermissionEngine:
    """Evaluate KB permission rules and produce SQLAlchemy deny filters."""

    @staticmethod
    async def build_deny_filters(
        db: AsyncSession,
        kb_id: int,
        subject_context: dict | None,
    ) -> list:
        """Return a list of SQLAlchemy WHERE conditions that EXCLUDE denied rows.

        If no rules are enabled or subject_context is None, returns [].
        The caller should append these conditions to the search query's WHERE clause.

        Each returned condition is a NOT(...) predicate — rows matching it are hidden.
        Multiple conditions are independent (caller ANDs them → OR-deny semantics:
        any single deny rule that matches hides the row).
        """
        if not subject_context:
            logger.debug("Permission skip — no subject_context provided")
            return []

        rules = await KbPermissionRuleRepository.list_enabled_by_kb(db, kb_id)
        if not rules:
            logger.debug("Permission skip — no enabled rules for kb_id=%s", kb_id)
            return []

        # Build the evaluation dict: start with nested metadata, then overlay
        # top-level subject fields (email, display_name, external_user_id, etc.)
        # so permission rules can reference both conversation fields and custom metadata.
        metadata = dict(subject_context.get("metadata") or {})
        for key in ("email", "display_name", "external_user_id", "phone"):
            val = subject_context.get(key)
            if val is not None and key not in metadata:
                metadata[key] = val
        logger.info(
            "Permission eval — kb_id=%s, subject_keys=%s, eval_fields=%s, rules=%d",
            kb_id,
            [k for k in subject_context if k != "metadata"],
            list(metadata.keys()) or "∅",
            len(rules),
        )
        deny_conditions = []

        for rule in rules:
            matched = _evaluate_user_conditions(rule.user_conditions, metadata)
            if not matched:
                logger.info(
                    "Permission rule skipped — rule=%r (id=%s), user_conditions not met, "
                    "conditions=%s, metadata=%s",
                    rule.name, rule.id, rule.user_conditions, metadata,
                )
                continue

            # User conditions matched → compile scope into exclusion filter
            scope_filter = _compile_scope_filter(
                rule.scope_operator, rule.scope_labels
            )
            if scope_filter is not None:
                deny_conditions.append(not_(scope_filter))
                try:
                    compiled = str(scope_filter.compile(compile_kwargs={"literal_binds": True}))
                except Exception:
                    compiled = repr(scope_filter)
                logger.info(
                    "Permission deny applied — rule=%r (id=%s), operator=%s, "
                    "labels=%s, compiled_sql=%s",
                    rule.name, rule.id, rule.scope_operator,
                    rule.scope_labels, compiled,
                )
            else:
                logger.warning(
                    "Permission deny compile failed — rule=%r (id=%s), "
                    "operator=%s, labels=%s → scope_filter is None",
                    rule.name, rule.id, rule.scope_operator, rule.scope_labels,
                )

        return deny_conditions


# ---------------------------------------------------------------------------
# User condition evaluation (§6.2.1)
# ---------------------------------------------------------------------------

def _evaluate_user_conditions(conditions: list[dict], metadata: dict) -> bool:
    """Evaluate a list of user conditions against conversation metadata.

    All conditions must be true (AND logic).  Returns True if ALL conditions
    are satisfied, meaning the deny rule applies to this user.
    """
    if not conditions:
        return False

    for cond in conditions:
        field = cond.get("field", "")
        operator = cond.get("operator", "")
        expected = cond.get("value")

        actual = metadata.get(field)
        result = _eval_single_condition(operator, actual, expected)

        logger.debug(
            "  user_cond: field=%r, operator=%s, expected=%r, actual=%r → %s",
            field, operator, expected, actual, result,
        )

        if not result:
            return False

    return True


def _eval_single_condition(operator: str, actual: Any, expected: Any) -> bool:
    """Evaluate one user condition.  `actual` is the metadata value (may be None)."""

    if operator == "is_empty":
        return actual is None or actual == ""

    if operator == "is_not_empty":
        return actual is not None and actual != ""

    if operator == "equals":
        return str(actual) == str(expected) if actual is not None else False

    if operator == "not_equals":
        if actual is None:
            return True
        return str(actual) != str(expected)

    if operator == "contains":
        if actual is None:
            return False
        return str(expected) in str(actual)

    if operator == "not_contains":
        if actual is None:
            return True
        return str(expected) not in str(actual)

    if operator == "starts_with":
        if actual is None:
            return False
        return str(actual).startswith(str(expected))

    if operator == "ends_with":
        if actual is None:
            return False
        return str(actual).endswith(str(expected))

    if operator == "in":
        if actual is None:
            return False
        if isinstance(expected, list):
            return str(actual) in [str(v) for v in expected]
        return str(actual) == str(expected)

    if operator == "not_in":
        if actual is None:
            return True
        if isinstance(expected, list):
            return str(actual) not in [str(v) for v in expected]
        return str(actual) != str(expected)

    logger.warning("Unknown user condition operator: %s", operator)
    return False


# ---------------------------------------------------------------------------
# Scope filter compilation (§6.2 — against access_keywords on slice rows)
# ---------------------------------------------------------------------------

def _compile_scope_filter(
    scope_operator: str,
    scope_labels: list[str] | None,
) -> Any:
    """Compile a scope definition into a SQLAlchemy condition that MATCHES rows to deny.

    The caller wraps this in NOT(...) to exclude the matched rows.

    access_keywords may be stored as a JSONB array or a plain string:
        doc_meta = {"access_keywords": ["vip_only", "sales"]}   -- array form
        doc_meta = {"access_keywords": "member_only"}           -- string form (from YAML scalar)

    We normalise to array before comparison using:
        CASE WHEN jsonb_typeof(val)='array' THEN val ELSE jsonb_build_array(val) END
    """
    ak_json = _AK_COLUMN[_AK_KEY]

    # Normalise: if the stored value is a bare string, wrap it into a single-element array
    ak_normalised = func.cast(
        text(
            "CASE WHEN jsonb_typeof(doc_meta->'access_keywords')='array' "
            "THEN doc_meta->'access_keywords' "
            "ELSE jsonb_build_array(doc_meta->'access_keywords') END"
        ),
        _AK_COLUMN.type,
    )

    if scope_operator == "equals":
        # Row's access_keywords set exactly equals the selected labels.
        if not scope_labels:
            return None
        labels_json = func.cast(
            func.jsonb_build_array(*scope_labels),
            _AK_COLUMN.type,
        )
        return and_(
            ak_normalised.op("@>")(labels_json),
            labels_json.op("@>")(ak_normalised),
        )

    if scope_operator == "not_equals":
        # Row's access_keywords != selected labels → deny those rows
        if not scope_labels:
            return None
        labels_json = func.cast(
            func.jsonb_build_array(*scope_labels),
            _AK_COLUMN.type,
        )
        return not_(and_(
            ak_normalised.op("@>")(labels_json),
            labels_json.op("@>")(ak_normalised),
        ))

    if scope_operator == "contains_any":
        # Row has at least one access_keywords token (non-empty value)
        return and_(
            ak_json.isnot(None),
            _AK_COLUMN[_AK_KEY].astext != "null",
            # Handle both array (length>0) and string (non-empty)
            or_(
                and_(
                    func.jsonb_typeof(ak_json) == "array",
                    func.jsonb_array_length(ak_json) > 0,
                ),
                func.jsonb_typeof(ak_json) == "string",
            ),
        )

    if scope_operator == "not_contains_any":
        # Row has NO access_keywords tokens (null, missing, or empty)
        return or_(
            ak_json.is_(None),
            _AK_COLUMN[_AK_KEY].astext == "null",
            and_(
                func.jsonb_typeof(ak_json) == "array",
                func.jsonb_array_length(ak_json) == 0,
            ),
        )

    logger.warning("Unknown scope operator: %s", scope_operator)
    return None
