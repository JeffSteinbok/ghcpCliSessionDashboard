"""Session grouping logic for the Copilot Dashboard.

Derives a project/area group name from session metadata using a generic
algorithm. Supports optional user-defined custom group mappings via
~/.copilot/dashboard-config.json.
"""

from __future__ import annotations

import json
import os
import re

# Directories to skip when deriving group from CWD path segments
_SKIP_DIRS = {
    "",
    "c:",
    "d:",
    "e:",
    "q:",
    "users",
    "home",
    "src",
    "documents",
    "desktop",
    "projects",
    "repos",
    "github",
}

_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".copilot", "dashboard-config.json")

# Loaded once on first call
_custom_config: dict | None = None


def _load_config() -> dict:
    """Load optional user config from ~/.copilot/dashboard-config.json.

    Expected format:
    {
        "grouping": {
            "skip_dirs": ["myuser"],
            "mappings": {
                "keyword_or_path": "Group Name",
                "myrepo": "My Project"
            }
        }
    }
    """
    global _custom_config
    if _custom_config is not None:
        return _custom_config
    _custom_config = {}
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, encoding="utf-8") as f:
                _custom_config = json.load(f)
        except Exception:
            pass
    return _custom_config


def get_group_name(session: dict) -> str:
    """Derive a project/area group name from session metadata.

    Strategy (in order):
    1. Check user-defined custom mappings
    2. Use repository field if available (owner/repo → repo)
    3. Extract from CWD path (last meaningful segment)
    4. Content-based keyword matching as fallback
    """
    config = _load_config()
    grouping = config.get("grouping", {})
    custom_mappings: dict[str, str] = grouping.get("mappings", {})
    extra_skip: list[str] = grouping.get("skip_dirs", [])

    cwd = (session.get("cwd") or "").replace("\\", "/")
    repository = session.get("repository") or ""
    summary = (session.get("summary") or "").lower()
    first_msg = (session.get("first_msg") or "").lower()
    last_cp = (session.get("last_cp_overview") or "").lower()
    context = f"{summary} {first_msg} {last_cp} {cwd.lower()}"

    # --- 1. Custom mappings (user-defined keywords/paths → group names) ---
    for keyword, group_name in custom_mappings.items():
        if keyword.lower() in context:
            return group_name

    # --- 2. Repository-based grouping ---
    if repository:
        # "owner/repo" → "repo", or just use as-is
        repo_name = repository.split("/")[-1] if "/" in repository else repository
        if repo_name:
            return repo_name

    # --- 3. CWD-based: last meaningful directory segment ---
    if cwd:
        skip = _SKIP_DIRS | {d.lower() for d in extra_skip}
        parts = cwd.rstrip("/").split("/")
        # Filter out drive letters, common dirs, and user-configured skips
        meaningful = [p for p in parts if p.lower() not in skip and not re.match(r"^[a-zA-Z]:$", p)]
        if meaningful:
            return meaningful[-1]

    # --- 4. Content-based keyword matching (fallback) ---
    keyword_groups: list[tuple[list[str], str]] = [
        (["code review", "pr review"], "PR Reviews"),
        (["pipeline", "build pipeline", "ci/cd"], "CI/CD Pipelines"),
        (["prune", "cleanup", "delete branch", "stale"], "Branch Cleanup"),
        (["dashboard", "monitor"], "Session Dashboard"),
        (["spec", "specification", "document"], "Specifications"),
    ]
    for keywords, group_name in keyword_groups:
        if any(kw in context for kw in keywords):
            return group_name

    return "General"
