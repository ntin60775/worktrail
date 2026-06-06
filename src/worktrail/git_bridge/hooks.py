"""Git hook management for worktrail.

Handles installation, verification, and removal of post-commit and post-checkout
git hooks that bridge git events into worktrail time tracking.
"""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

# ---------------------------------------------------------------------------
# Hook script contents
# ---------------------------------------------------------------------------

_POST_COMMIT_SCRIPT = r"""#!/bin/bash
# worktrail post-commit hook
COMMIT_HASH=$(git rev-parse HEAD)
COMMIT_MSG=$(git log -1 --pretty=%B)
worktrail checkpoint --auto "Commit: $COMMIT_MSG" --commit "$COMMIT_HASH" 2>/dev/null || true
"""

_POST_CHECKOUT_SCRIPT = r"""#!/bin/bash
# worktrail post-checkout hook
PREV_HEAD=$1
NEW_HEAD=$2
BRANCH_CHECKOUT=$3
if [ "$BRANCH_CHECKOUT" = "1" ]; then
    worktrail git-checkout-hook "$PREV_HEAD" "$NEW_HEAD" 2>/dev/null || true
fi
"""

_WORKTRAIL_HOOK_MARKER = "# worktrail post-"
"""Marker string present in every worktrail-managed hook for identification."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def install_hooks(project_root: Path) -> bool:
    """Install worktrail hooks into the project's .git/hooks/ directory.

    Creates the source ``.worktrail/hooks/`` directory, copies the
    ``post-commit`` and ``post-checkout`` scripts, and makes them
    executable.  The operation is idempotent — calling it multiple times
    overwrites any existing worktrail hooks with fresh content.

    Args:
        project_root: Absolute path to the git repository root.

    Returns:
        ``True`` if both hooks were installed successfully.
    """
    git_hooks_dir = project_root / ".git" / "hooks"
    if not git_hooks_dir.is_dir():
        return False

    # Ensure the source hooks directory exists for reference.
    worktrail_hooks_dir = project_root / ".worktrail" / "hooks"
    worktrail_hooks_dir.mkdir(parents=True, exist_ok=True)

    _write_hook(git_hooks_dir, "post-commit", _POST_COMMIT_SCRIPT)
    _write_hook(git_hooks_dir, "post-checkout", _POST_CHECKOUT_SCRIPT)

    # Also keep a copy in .worktrail/hooks/ as the canonical reference.
    _write_hook(worktrail_hooks_dir, "post-commit", _POST_COMMIT_SCRIPT)
    _write_hook(worktrail_hooks_dir, "post-checkout", _POST_CHECKOUT_SCRIPT)

    return True


def are_hooks_installed(project_root: Path) -> bool:
    """Check whether worktrail hooks are present in ``.git/hooks/``.

    A hook is considered "installed" when the corresponding file exists
    and contains the worktrail marker comment.

    Args:
        project_root: Absolute path to the git repository root.

    Returns:
        ``True`` if both *post-commit* and *post-checkout* hooks are
        present and recognised as worktrail hooks.
    """
    git_hooks_dir = project_root / ".git" / "hooks"
    for name in ("post-commit", "post-checkout"):
        hook_path = git_hooks_dir / name
        if not hook_path.is_file():
            return False
        content = hook_path.read_text(encoding="utf-8")
        if _WORKTRAIL_HOOK_MARKER not in content:
            return False
    return True


def remove_hooks(project_root: Path) -> bool:
    """Remove worktrail hooks from ``.git/hooks/``.

    Only removes hooks that contain the worktrail marker comment.
    Non-worktrail hooks are left untouched.

    Args:
        project_root: Absolute path to the git repository root.

    Returns:
        ``True`` if the hooks directory exists and the operation completed.
    """
    git_hooks_dir = project_root / ".git" / "hooks"
    if not git_hooks_dir.is_dir():
        return False

    removed_any = False
    for name in ("post-commit", "post-checkout"):
        hook_path = git_hooks_dir / name
        if hook_path.is_file():
            content = hook_path.read_text(encoding="utf-8")
            if _WORKTRAIL_HOOK_MARKER in content:
                hook_path.unlink()
                removed_any = True

    return removed_any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_hook(hooks_dir: Path, name: str, content: str) -> None:
    """Write *content* to *hooks_dir/name* and set the executable bit."""
    hook_path = hooks_dir / name
    hook_path.write_text(content, encoding="utf-8")
    # chmod +x
    current_mode = hook_path.stat().st_mode
    hook_path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
