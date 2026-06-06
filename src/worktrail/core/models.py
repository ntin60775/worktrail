"""Data models for worktrail core module.

All datetime fields use ISO8601 format (UTC).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Task:
    """Represents a tracked task.

    Attributes:
        id: Unique task identifier (e.g. 'TASK-2025-0042').
        name: Human-readable task name.
        status: Task status — one of 'active', 'paused', 'done', 'archived'.
        created_at: ISO8601 timestamp of creation (UTC).
        updated_at: ISO8601 timestamp of last update (UTC).
        parent_id: Optional parent task identifier for hierarchical tasks.
    """

    id: str
    name: str
    status: str = "active"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    parent_id: Optional[str] = None


@dataclass
class Session:
    """Represents a work session tied to a task.

    Attributes:
        id: Auto-incremented session identifier.
        task_id: Reference to the task being worked on.
        started_at: ISO8601 timestamp when the session started (UTC).
        ended_at: ISO8601 timestamp when the session ended, or None if active.
        status: Session status — one of 'active', 'paused', 'ended'.
        total_seconds: Accumulated work time in seconds.
    """

    task_id: str
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ended_at: Optional[str] = None
    status: str = "active"
    total_seconds: int = 0
    id: Optional[int] = None


@dataclass
class Checkpoint:
    """Represents a progress checkpoint within a session.

    Attributes:
        id: Auto-incremented checkpoint identifier.
        session_id: Reference to the session this checkpoint belongs to.
        message: Checkpoint message describing the progress.
        timestamp: ISO8601 timestamp when the checkpoint was created (UTC).
        source: Source of the checkpoint — 'manual', 'git-hook', or 'auto'.
        commit_hash: Optional git commit hash for git-hook checkpoints.
    """

    session_id: int
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "manual"
    commit_hash: Optional[str] = None
    id: Optional[int] = None


@dataclass
class Config:
    """Runtime configuration for worktrail.

    Attributes:
        idle_timeout: Seconds of inactivity before auto-pause (default: 900 = 15min).
        git_hooks_enabled: Whether git hooks are enabled (default: True).
    """

    idle_timeout: int = 900
    git_hooks_enabled: bool = True
