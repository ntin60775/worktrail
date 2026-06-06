"""Git branch / task-id parsing and low-level git helpers.

This module contains thin wrappers around ``git`` subprocess calls as well
as pure functions that extract worktrail task identifiers from branch names.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Git subprocess helpers
# ---------------------------------------------------------------------------


def run_git(args: list[str], project_root: Path) -> str:
    """Run a git command and return its stdout stripped of trailing whitespace.

    Args:
        args: Git sub-command and flags (e.g. ``["rev-parse", "HEAD"]``).
        project_root: Absolute path to the git repository root.  Used as
            ``cwd`` for the subprocess.

    Returns:
        The command's standard output with trailing newlines stripped.

    Raises:
        subprocess.CalledProcessError: If git returns a non-zero exit code.
        FileNotFoundError: If the ``git`` executable is not on ``PATH``.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Branch / task parsing
# ---------------------------------------------------------------------------


def get_current_branch(project_root: Path) -> str | None:
    """Return the name of the current git branch, or ``None``.

    Returns ``None`` when HEAD is detached (e.g. during a rebase or when
    checked out to a raw commit).

    Args:
        project_root: Absolute path to the git repository root.
    """
    try:
        return run_git(["branch", "--show-current"], project_root)
    except subprocess.CalledProcessError:
        return None


_TASK_BRANCH_RE = re.compile(r"^(?:task|du)/([A-ZА-ЯЁ]+-\d+)(?:-.*)?$")
"""Pattern to extract a task ID from a task branch name.

Examples:
    ``task/TASK-001-slug``  →  ``TASK-001``
    ``du/DU-042``           →  ``DU-042``
"""


def extract_task_from_branch(branch: str) -> str | None:
    """Extract a task ID from a task branch name.

    Supports ``task/<task-id>`` and ``du/<task-id>`` prefixes.  The task
    ID itself must match ``<PREFIX>-<NUMBER>`` (e.g. ``TASK-001``).

    Args:
        branch: Git branch name such as ``"task/TASK-001-slug"``.

    Returns:
        The extracted task ID, or ``None`` if the branch does not match
        the expected pattern.
    """
    match = _TASK_BRANCH_RE.match(branch)
    if match:
        return match.group(1)
    return None


def is_task_branch(branch: str) -> bool:
    """Return ``True`` if *branch* looks like a worktrail task branch.

    A task branch starts with ``task/`` or ``du/``.

    Args:
        branch: Git branch name.
    """
    return branch.startswith(("task/", "du/"))


# ---------------------------------------------------------------------------
# Repository discovery
# ---------------------------------------------------------------------------


def get_repo_root(path: Path | None = None) -> Path | None:
    """Walk up the filesystem to find the git repository root.

    This is a thin wrapper around :func:`worktrail.core.find_project_root`
    that uses ``.git`` as the marker.

    Args:
        path: Starting directory.  Defaults to ``Path.cwd()``.

    Returns:
        The absolute ``Path`` of the repository root, or ``None`` if no
        git repository was found.
    """
    from worktrail.core import find_project_root

    return find_project_root(".git", cwd=path)


# ---------------------------------------------------------------------------
# Commit helpers
# ---------------------------------------------------------------------------


def get_last_commit_info(project_root: Path) -> dict[str, str]:
    """Return information about the most recent commit.

    Args:
        project_root: Absolute path to the git repository root.

    Returns:
        A dictionary with keys ``"hash"``, ``"message"``, and
        ``"timestamp"`` (ISO-8601 format in UTC).
    """
    hash_val = run_git(["rev-parse", "HEAD"], project_root)
    message = run_git(["log", "-1", "--pretty=%B"], project_root)
    # %ci = committer date, ISO-8601-like
    ts_raw = run_git(["log", "-1", "--pretty=%ci"], project_root)
    # Parse and normalise to UTC ISO-8601
    try:
        dt = datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S %z")
        dt_utc = dt.astimezone(timezone.utc)
        timestamp = dt_utc.isoformat().replace("+00:00", "Z")
    except ValueError:
        timestamp = ts_raw

    return {
        "hash": hash_val,
        "message": message,
        "timestamp": timestamp,
    }
