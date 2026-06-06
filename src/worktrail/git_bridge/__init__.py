"""git_bridge — Git integration for worktrail.

Handles git hook installation, branch parsing, and subprocess helpers that
connect git repository events to the worktrail time-tracking system.
"""

from __future__ import annotations

from worktrail.git_bridge.hooks import (
    are_hooks_installed,
    install_hooks,
    remove_hooks,
)
from worktrail.git_bridge.parser import (
    extract_task_from_branch,
    get_current_branch,
    get_last_commit_info,
    get_repo_root,
    is_task_branch,
    run_git,
)

__all__ = [
    "install_hooks",
    "are_hooks_installed",
    "remove_hooks",
    "get_current_branch",
    "extract_task_from_branch",
    "is_task_branch",
    "get_repo_root",
    "run_git",
    "get_last_commit_info",
]
