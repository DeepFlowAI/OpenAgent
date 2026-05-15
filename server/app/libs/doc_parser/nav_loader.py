"""
Load and validate schema/nav.yaml for knowledge base navigation ordering.

Returns the parsed `nav` array (list of file/folder entries) or None if the
file is absent or unparseable. Never raises — sync must not break because of
a malformed nav config.
"""
import logging
import os

import yaml

logger = logging.getLogger(__name__)


def load_nav_config(repo_path: str) -> list | None:
    """Read schema/nav.yaml from a repo checkout and return the `nav` array."""
    nav_path = os.path.join(repo_path, "schema", "nav.yaml")
    if not os.path.isfile(nav_path):
        return None

    try:
        with open(nav_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as exc:
        logger.warning("Failed to parse schema/nav.yaml: %s", exc)
        return None

    if not isinstance(data, dict):
        logger.warning("schema/nav.yaml root is not a mapping, ignoring")
        return None

    nav = data.get("nav")
    if not isinstance(nav, list):
        logger.warning("schema/nav.yaml missing or invalid 'nav' key, ignoring")
        return None

    return nav
