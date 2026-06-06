"""CRUD repository for worktrail entities.

All methods return dataclass instances rather than raw tuples.
Connection pooling is handled via the context manager from :mod:`worktrail.core.db`.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from worktrail.core.db import get_connection, get_db_path
from worktrail.core.models import Checkpoint, Session, Task


class Repository:
    """Provides CRUD operations for all worktrail database entities.

    Usage::

        repo = Repository()                     # auto-locates runtime.db
        repo = Repository("/path/to/runtime.db")  # explicit path

        with repo.conn() as conn:
            ...
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path = db_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def conn(self) -> get_connection:
        """Return a connection context manager.

        This is a thin wrapper around :func:`worktrail.core.db.get_connection`
        that passes the repository's ``db_path``.
        """
        return get_connection(self._db_path)

    @staticmethod
    def _now() -> str:
        """Return the current UTC time as an ISO8601 string."""
        return datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Task operations
    # ------------------------------------------------------------------

    def create_task(self, task_id: str, name: str, parent_id: Optional[str] = None) -> Task:
        """Insert a new task and return the created instance.

        Args:
            task_id: Unique task identifier.
            name: Human-readable task name.
            parent_id: Optional parent task reference.

        Returns:
            The newly created :class:`Task`.
        """
        now = self._now()
        task = Task(
            id=task_id,
            name=name,
            status="active",
            created_at=now,
            updated_at=now,
            parent_id=parent_id,
        )
        with self.conn() as conn:
            conn.execute(
                """
                INSERT INTO tasks (id, name, status, parent_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (task.id, task.name, task.status, task.parent_id, task.created_at, task.updated_at),
            )
            conn.commit()
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """Fetch a task by its identifier.

        Args:
            task_id: The task identifier to look up.

        Returns:
            The :class:`Task` if found, otherwise ``None``.
        """
        with self.conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        if row is None:
            return None
        return Task(
            id=row["id"],
            name=row["name"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            parent_id=row["parent_id"],
        )

    def update_task_status(self, task_id: str, status: str) -> bool:
        """Update the status of a task.

        Args:
            task_id: The task to update.
            status: New status value.

        Returns:
            ``True`` if a row was updated, ``False`` otherwise.
        """
        now = self._now()
        with self.conn() as conn:
            cur = conn.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, task_id),
            )
            conn.commit()
        return cur.rowcount > 0

    def list_tasks(self, status: Optional[str] = None) -> List[Task]:
        """Return all tasks, optionally filtered by status.

        Args:
            status: If provided, only tasks with this status are returned.

        Returns:
            List of :class:`Task` instances.
        """
        with self.conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY created_at",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tasks ORDER BY created_at"
                ).fetchall()
        return [
            Task(
                id=r["id"],
                name=r["name"],
                status=r["status"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                parent_id=r["parent_id"],
            )
            for r in rows
        ]

    def list_active_tasks(self) -> List[Task]:
        """Return all tasks with status ``'active'``.

        Returns:
            List of active :class:`Task` instances.
        """
        return self.list_tasks(status="active")

    # ------------------------------------------------------------------
    # Session operations
    # ------------------------------------------------------------------

    def create_session(self, task_id: str) -> Session:
        """Create a new active session for *task_id*.

        Args:
            task_id: The task to associate with the session.

        Returns:
            The newly created :class:`Session`.
        """
        now = self._now()
        session = Session(
            task_id=task_id,
            started_at=now,
            ended_at=None,
            status="active",
            total_seconds=0,
            id=None,
        )
        with self.conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO sessions (task_id, started_at, ended_at, status, total_seconds)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session.task_id, session.started_at, session.ended_at,
                 session.status, session.total_seconds),
            )
            conn.commit()
            session.id = cur.lastrowid
        return session

    def get_active_session(self) -> Optional[Session]:
        """Return the currently active session, if any.

        Returns:
            The active :class:`Session`, or ``None``.
        """
        with self.conn() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE status = 'active' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return Session(
            id=row["id"],
            task_id=row["task_id"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            status=row["status"],
            total_seconds=row["total_seconds"],
        )

    def get_session(self, session_id: int) -> Optional[Session]:
        """Fetch a session by its identifier.

        Args:
            session_id: The session identifier to look up.

        Returns:
            The :class:`Session` if found, otherwise ``None``.
        """
        with self.conn() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        if row is None:
            return None
        return Session(
            id=row["id"],
            task_id=row["task_id"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            status=row["status"],
            total_seconds=row["total_seconds"],
        )

    def end_session(self, session_id: int) -> bool:
        """Mark a session as ended and set *ended_at*.

        Args:
            session_id: The session to end.

        Returns:
            ``True`` if a row was updated, ``False`` otherwise.
        """
        now = self._now()
        with self.conn() as conn:
            cur = conn.execute(
                "UPDATE sessions SET status = 'ended', ended_at = ? WHERE id = ?",
                (now, session_id),
            )
            conn.commit()
        return cur.rowcount > 0

    def pause_session(self, session_id: int) -> bool:
        """Pause a session.

        Args:
            session_id: The session to pause.

        Returns:
            ``True`` if a row was updated, ``False`` otherwise.
        """
        with self.conn() as conn:
            cur = conn.execute(
                "UPDATE sessions SET status = 'paused' WHERE id = ?",
                (session_id,),
            )
            conn.commit()
        return cur.rowcount > 0

    def resume_session(self, session_id: int) -> bool:
        """Resume a paused session.

        Args:
            session_id: The session to resume.

        Returns:
            ``True`` if a row was updated, ``False`` otherwise.
        """
        with self.conn() as conn:
            cur = conn.execute(
                "UPDATE sessions SET status = 'active' WHERE id = ?",
                (session_id,),
            )
            conn.commit()
        return cur.rowcount > 0

    def update_session_duration(self, session_id: int, total_seconds: int) -> bool:
        """Update the accumulated duration of a session.

        Args:
            session_id: The session to update.
            total_seconds: New total seconds value.

        Returns:
            ``True`` if a row was updated, ``False`` otherwise.
        """
        with self.conn() as conn:
            cur = conn.execute(
                "UPDATE sessions SET total_seconds = ? WHERE id = ?",
                (total_seconds, session_id),
            )
            conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Checkpoint operations
    # ------------------------------------------------------------------

    def add_checkpoint(
        self,
        session_id: int,
        message: str,
        source: str = "manual",
        commit_hash: Optional[str] = None,
    ) -> Checkpoint:
        """Add a checkpoint to a session.

        Args:
            session_id: The session to attach the checkpoint to.
            message: Checkpoint message.
            source: Checkpoint source — ``'manual'``, ``'git-hook'``, or ``'auto'``.
            commit_hash: Optional git commit hash.

        Returns:
            The newly created :class:`Checkpoint`.
        """
        now = self._now()
        checkpoint = Checkpoint(
            session_id=session_id,
            message=message,
            timestamp=now,
            source=source,
            commit_hash=commit_hash,
            id=None,
        )
        with self.conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO checkpoints (session_id, message, timestamp, source, commit_hash)
                VALUES (?, ?, ?, ?, ?)
                """,
                (checkpoint.session_id, checkpoint.message, checkpoint.timestamp,
                 checkpoint.source, checkpoint.commit_hash),
            )
            conn.commit()
            checkpoint.id = cur.lastrowid
        return checkpoint

    def get_checkpoints_for_session(self, session_id: int) -> List[Checkpoint]:
        """Return all checkpoints belonging to a session.

        Args:
            session_id: The session identifier.

        Returns:
            List of :class:`Checkpoint` instances ordered by timestamp.
        """
        with self.conn() as conn:
            rows = conn.execute(
                "SELECT * FROM checkpoints WHERE session_id = ? ORDER BY timestamp",
                (session_id,),
            ).fetchall()
        return [
            Checkpoint(
                id=r["id"],
                session_id=r["session_id"],
                message=r["message"],
                timestamp=r["timestamp"],
                source=r["source"],
                commit_hash=r["commit_hash"],
            )
            for r in rows
        ]

    def get_checkpoints_for_task(self, task_id: str) -> List[Checkpoint]:
        """Return all checkpoints for every session of a task.

        Args:
            task_id: The task identifier.

        Returns:
            List of :class:`Checkpoint` instances ordered by timestamp.
        """
        with self.conn() as conn:
            rows = conn.execute(
                """
                SELECT c.* FROM checkpoints c
                JOIN sessions s ON c.session_id = s.id
                WHERE s.task_id = ?
                ORDER BY c.timestamp
                """,
                (task_id,),
            ).fetchall()
        return [
            Checkpoint(
                id=r["id"],
                session_id=r["session_id"],
                message=r["message"],
                timestamp=r["timestamp"],
                source=r["source"],
                commit_hash=r["commit_hash"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Config operations (key/value store)
    # ------------------------------------------------------------------

    def get_config(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Return the config value for *key*, or *default*.

        Args:
            key: Config key to look up.
            default: Fallback value if the key does not exist.

        Returns:
            The stored value, or *default*.
        """
        with self.conn() as conn:
            row = conn.execute(
                "SELECT value FROM config WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return default
        return row["value"]

    def set_config(self, key: str, value: str) -> None:
        """Upsert a config key/value pair.

        Args:
            key: Config key.
            value: Config value.
        """
        with self.conn() as conn:
            conn.execute(
                """
                INSERT INTO config (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
            conn.commit()

    def get_config_int(self, key: str, default: int = 0) -> int:
        """Return the config value as an integer.

        Args:
            key: Config key to look up.
            default: Fallback value if the key does not exist or is not
                a valid integer.

        Returns:
            The integer value, or *default*.
        """
        raw = self.get_config(key)
        if raw is None:
            return default
        try:
            return int(raw)
        except (ValueError, TypeError):
            return default

    def get_config_bool(self, key: str, default: bool = False) -> bool:
        """Return the config value as a boolean.

        Recognises ``'true'``, ``'1'``, ``'yes'`` (case-insensitive) as truthy.

        Args:
            key: Config key to look up.
            default: Fallback value if the key does not exist.

        Returns:
            The boolean value, or *default*.
        """
        raw = self.get_config(key)
        if raw is None:
            return default
        return raw.strip().lower() in ("true", "1", "yes")
