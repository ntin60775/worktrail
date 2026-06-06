"""Filesystem-based idle detection for worktrail.

Monitors the project directory by walking the filesystem and examining file
mtimes.  Directories that are not project source (``.git``, ``.worktrail``,
``__pycache__``, ``node_modules``, ``.venv``) are skipped.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Set


# Directories that are excluded from the mtime walk.
_EXCLUDED_DIRS: Set[str] = {
    ".git",
    ".worktrail",
    "__pycache__",
    "node_modules",
    ".venv",
}


class IdleMonitor:
    """Detects developer idle state by looking at the most recent filesystem
    modification time inside *project_root*.

    Attributes:
        idle_timeout: Seconds of inactivity before considering the user idle.
    """

    def __init__(self, idle_timeout: int = 900) -> None:
        self.idle_timeout = idle_timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_idle(self, project_root: Path) -> bool:
        """Return ``True`` if the developer appears to be idle.

        Walks *project_root* (excluding well-known non-source directories) and
        compares the most recent file ``mtime`` against the current time.
        If the delta exceeds *idle_timeout* the user is considered idle.

        Args:
            project_root: Root of the project to monitor.

        Returns:
            ``True`` when idle is detected, ``False`` otherwise.
        """
        last_activity = self.get_activity_timestamp(project_root)
        if last_activity is None:
            # No files found — treat as idle to be safe.
            return True

        now = datetime.now(timezone.utc)
        delta = (now - last_activity).total_seconds()
        return delta > self.idle_timeout

    def get_activity_timestamp(self, project_root: Path) -> Optional[datetime]:
        """Return the most recent filesystem modification time found in
        *project_root*.

        Args:
            project_root: Root of the project to monitor.

        Returns:
            A timezone-aware UTC datetime representing the latest file
            modification, or ``None`` if no eligible files were found.
        """
        latest_mtime: Optional[float] = None

        for dirpath, dirnames, filenames in os.walk(project_root):
            # Filter out excluded directories in-place so os.walk doesn't
            # descend into them.
            dirnames[:] = [
                d for d in dirnames if d not in _EXCLUDED_DIRS and not d.startswith(".")
            ]

            for fname in filenames:
                # Skip hidden files as well.
                if fname.startswith("."):
                    continue

                fpath = Path(dirpath) / fname
                try:
                    mtime = fpath.stat().st_mtime
                except (OSError, PermissionError):
                    continue

                if latest_mtime is None or mtime > latest_mtime:
                    latest_mtime = mtime

        if latest_mtime is None:
            return None

        return datetime.fromtimestamp(latest_mtime, tz=timezone.utc)
