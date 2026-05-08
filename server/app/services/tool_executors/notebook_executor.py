"""
Notebook tool executor — manages a session-scoped scratch notebook.
Supports add/remove operations. State lives in conversation_step records.
"""
import logging
from xml.sax.saxutils import escape

from app.services.tool_executors.base import BaseToolExecutor, ToolContext

logger = logging.getLogger(__name__)


class NotebookToolExecutor(BaseToolExecutor):

    async def execute(self, args: dict, config: dict, ctx: ToolContext) -> str:
        action = args.get("action", "").lower()
        items = args.get("items", [])

        if action not in ("add", "remove"):
            return '<notebook_response action="error">Unsupported action. Use "add" or "remove".</notebook_response>'

        if not items:
            return f'<notebook_response action="{action}">No items provided.</notebook_response>'

        if action == "add":
            return self._handle_add(items)
        else:
            return self._handle_remove(items)

    def _handle_add(self, items: list[dict]) -> str:
        count = len(items)
        summaries = []
        for item in items:
            text = item.get("text", "")
            slice_id = item.get("slice_id")
            doc_id = item.get("doc_id")
            if slice_id:
                summaries.append(f"slice:{slice_id}")
            elif doc_id:
                summaries.append(f"doc:{doc_id}")
            elif text:
                summaries.append(text[:50])

        detail = ", ".join(summaries) if summaries else ""
        logger.info("Notebook add — %d items: %s", count, detail)
        return (
            f'<notebook_response action="add">'
            f'Added {count} item(s) to notebook.'
            f'</notebook_response>'
        )

    def _handle_remove(self, items: list[dict]) -> str:
        ids = [item.get("id", "") for item in items if item.get("id")]
        count = len(ids)
        logger.info("Notebook remove — %d items: %s", count, ids)
        return (
            f'<notebook_response action="remove">'
            f'Removed {count} item(s) from notebook.'
            f'</notebook_response>'
        )
