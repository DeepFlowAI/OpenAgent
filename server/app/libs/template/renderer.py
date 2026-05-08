"""
Mustache-style template renderer for system prompt variable substitution.

Supports:
- {{variable}} — replaced with value, or empty string if absent
- {{#variable}} ... {{/variable}} — conditional block, removed entirely if value is falsy
- {{.}} inside conditional block — replaced with block's context variable value
"""
import re

_BLOCK_RE = re.compile(
    r"\{\{#(\w+)\}\}(.*?)\{\{/\1\}\}",
    re.DOTALL,
)
_VAR_RE = re.compile(r"\{\{(\w+|\.)\}\}")


def render_template(template: str, variables: dict[str, str]) -> str:
    """Render a Mustache-style template with the given variables."""

    def _replace_block(match: re.Match) -> str:
        var_name = match.group(1)
        block_body = match.group(2)
        value = variables.get(var_name, "")
        if not value:
            return ""
        rendered = _VAR_RE.sub(
            lambda m: value if m.group(1) == "." else variables.get(m.group(1), ""),
            block_body,
        )
        return rendered.strip()

    result = _BLOCK_RE.sub(_replace_block, template)
    result = _VAR_RE.sub(lambda m: variables.get(m.group(1), ""), result)

    # Clean up excessive blank lines left by removed blocks
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()
