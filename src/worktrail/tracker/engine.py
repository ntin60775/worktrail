"""Main tracking engine for worktrail.

Provides :class:`TrackerEngine` which manages the full session lifecycle
(active → paused → ended), auto-pauses on idle, and records checkpoints.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from worktrail.core import Checkpoint, Repository, Session, Task
from worktrail.core.config import load_config
from worktrail.core.db import get_db_path
from worktrail.tracker.idle import IdleMonitor


class TrackerEngine:
    """Central time-tracking orchestrator.

    Usage::

        engine = TrackerEngine()
        session = engine.start("TASK-001", "Fix login bug")
        ... work ...
        engine.checkpoint("Implemented form validation")
        ...
        engine.stop()

    Args:
        repo: Optional :class:`Repository` instance.  If omitted, one is
            created automatically (and the database is auto-located).
        project_root: Root of the project.  Used for idle detection.
            If omitted, the directory containing ``.worktrail/`` is used.
    """

    def __init__(
        self,
        repo: Optional[Repository] = None,
        project_root: Optional[Path] = None,
    ) -> None:
        if project_root is not None:
            self._project_root = project_root
            db_path = project_root / ".worktrail" / "runtime.db"
            self._repo = repo or Repository(db_path)
        else:
            self._repo = repo or Repository()
            # Derive project root from the database location.
            db_path = self._repo._db_path or get_db_path()
            self._project_root = db_path.parent.parent

        # Resolve idle timeout from config (default 15 min).
        try:
            config = load_config(self._project_root / ".worktrail" / "config.yaml")
        except FileNotFoundError:
            config = {}
        idle_timeout: int = config.get("idle_timeout", 900)

        self._idle_monitor = IdleMonitor(idle_timeout=idle_timeout)

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start(self, task_id: str, task_name: str | None = None) -> Session:
        """Start a new tracking session for *task_id*.

        - If another session is already active it is auto-stopped first.
        - If *task_id* does not exist in the database it is created;
          *task_name* is used as the human-readable name when provided,
          otherwise *task_id* is used as a fallback.
        - If the task exists and is in ``draft`` status, it is
          automatically promoted to ``active``.

        Args:
            task_id: Unique task identifier.
            task_name: Human-readable name for the task (used only when
                the task is created).

        Returns:
            The newly created :class:`Session`.
        """
        # Auto-stop any active session first.
        active = self._repo.get_active_session()
        if active is not None:
            self.stop()

        # Ensure the task exists.
        task = self._repo.get_task(task_id)
        if task is None:
            name = task_name or task_id
            self._repo.create_task(task_id, name, status="active")
        elif task.status == "draft":
            self._repo.update_task_status(task_id, "active")

        session = self._repo.create_session(task_id)
        return session

    def stop(self) -> Session | None:
        """Stop the currently active session.

        Accumulates any time elapsed since the session started (or was
        last resumed) into ``total_seconds`` and marks the session as
        ``'ended'``.

        Returns:
            The ended :class:`Session`, or ``None`` if there was no active
            session.
        """
        session = self._repo.get_active_session()
        if session is None:
            return None

        # Accumulate elapsed time.
        elapsed = self._elapsed_since(session.started_at)
        new_total = session.total_seconds + elapsed
        self._repo.update_session_duration(session.id, new_total)
        self._repo.end_session(session.id)

        # Refresh and return.
        return self._repo.get_session(session.id)

    def pause(self) -> Session | None:
        """Pause the currently active session.

        Records accumulated time up to now and changes status to
        ``'paused'``.

        Returns:
            The paused :class:`Session`, or ``None`` if there was no active
            session.
        """
        session = self._repo.get_active_session()
        if session is None:
            return None

        # Accumulate elapsed time into total_seconds.
        elapsed = self._elapsed_since(session.started_at)
        new_total = session.total_seconds + elapsed
        self._repo.update_session_duration(session.id, new_total)
        self._repo.pause_session(session.id)

        return self._repo.get_session(session.id)

    def resume(self) -> Session | None:
        """Resume the most recently paused session.

        Updates ``started_at`` to the current time so that future
        elapsed-time calculations start from now.  The accumulated
        ``total_seconds`` is preserved.

        Returns:
            The resumed :class:`Session`, or ``None`` if there was no
            paused session.
        """
        # Find the most recent paused session.
        with self._repo.conn() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE status = 'paused' ORDER BY id DESC LIMIT 1"
            ).fetchone()

        if row is None:
            return None

        session_id = row["id"]
        now = self._now()

        with self._repo.conn() as conn:
            conn.execute(
                "UPDATE sessions SET started_at = ?, status = 'active' WHERE id = ?",
                (now, session_id),
            )
            conn.commit()

        return self._repo.get_session(session_id)

    # ------------------------------------------------------------------
    # Checkpoint
    # ------------------------------------------------------------------

    def checkpoint(
        self,
        message: str,
        source: str = "manual",
        commit_hash: str | None = None,
    ) -> Checkpoint:
        """Record a progress checkpoint in the active session.

        Also resets the idle timer (this call counts as activity).

        Args:
            message: Checkpoint description.
            source: Origin of the checkpoint — ``'manual'``,
                ``'git-hook'``, or ``'auto'``.
            commit_hash: Optional git commit hash (for git-hook checkpoints).

        Returns:
            The newly created :class:`Checkpoint`.

        Raises:
            RuntimeError: If there is no active session.
        """
        session = self._repo.get_active_session()
        if session is None:
            raise RuntimeError("No active session — cannot record checkpoint.")

        cp = self._repo.add_checkpoint(
            session_id=session.id,
            message=message,
            source=source,
            commit_hash=commit_hash,
        )
        return cp

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def current(self) -> dict | None:
        """Return information about the currently active session.

        The returned dictionary contains:

        * ``session`` — the :class:`Session` object
        * ``task`` — the associated :class:`Task`
        * ``elapsed_seconds`` — total accumulated seconds including the
          current running segment
        * ``checkpoints_count`` — number of checkpoints recorded so far

        Returns:
            Dictionary with active session info, or ``None`` if no session
            is active.
        """
        session = self._repo.get_active_session()
        if session is None:
            return None

        task = self._repo.get_task(session.task_id)
        elapsed = self._total_elapsed(session)
        checkpoints = self._repo.get_checkpoints_for_session(session.id)

        return {
            "session": session,
            "task": task,
            "elapsed_seconds": elapsed,
            "checkpoints_count": len(checkpoints),
        }

    def get_task_summary(self, task_id: str, date: str | None = None) -> dict:
        """Return a time summary for *task_id*.

        Args:
            task_id: The task to summarise.
            date: If provided, only sessions that intersect this calendar
                day (ISO8601 ``YYYY-MM-DD``) are included.

        Returns:
            Dictionary with keys ``task``, ``total_seconds``,
            ``sessions``, and ``checkpoints``.
        """
        task = self._repo.get_task(task_id)
        if task is None:
            raise ValueError(f"Task '{task_id}' not found.")

        # Fetch all sessions for the task.
        with self._repo.conn() as conn:
            if date:
                # Sessions that started on or before the end of the date
                # and ended after the start of the date (or are still active).
                date_end = f"{date}T23:59:59"
                rows = conn.execute(
                    """
                    SELECT * FROM sessions
                    WHERE task_id = ?
                      AND started_at <= ?
                      AND (ended_at >= ? OR ended_at IS NULL)
                    ORDER BY started_at
                    """,
                    (task_id, date_end, f"{date}T00:00:00"),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM sessions WHERE task_id = ? ORDER BY started_at",
                    (task_id,),
                ).fetchall()

        sessions: List[Session] = [
            Session(
                id=r["id"],
                task_id=r["task_id"],
                started_at=r["started_at"],
                ended_at=r["ended_at"],
                status=r["status"],
                total_seconds=r["total_seconds"],
            )
            for r in rows
        ]

        # Compute total seconds — for active sessions add the running segment.
        total_seconds = 0
        for s in sessions:
            if s.status == "active":
                total_seconds += self._total_elapsed(s)
            else:
                total_seconds += s.total_seconds

        checkpoints = self._repo.get_checkpoints_for_task(task_id)

        return {
            "task": task,
            "total_seconds": total_seconds,
            "sessions": sessions,
            "checkpoints": checkpoints,
        }

    # ------------------------------------------------------------------
    # Idle check
    # ------------------------------------------------------------------

    def check_idle(self) -> bool:
        """Delegate to :class:`IdleMonitor`.

        Returns:
            ``True`` if the developer appears idle.
        """
        return self._idle_monitor.check_idle(self._project_root)

    def get_idle_seconds(self) -> float:
        """Return the number of seconds since the last filesystem activity.

        Returns:
            Seconds since last activity, or *idle_timeout* + 1 when no
            files are found.
        """
        ts = self._idle_monitor.get_activity_timestamp(self._project_root)
        if ts is None:
            return float(self._idle_monitor.idle_timeout + 1)
        return (datetime.now(timezone.utc) - ts).total_seconds()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _now() -> str:
        """Return the current UTC time as an ISO8601 string."""
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _elapsed_since(timestamp_iso: str) -> int:
        """Return the number of seconds between *timestamp_iso* and now.

        Args:
            timestamp_iso: An ISO8601 timestamp string.

        Returns:
            Integer seconds (always ≥ 0).
        """
        then = datetime.fromisoformat(timestamp_iso)
        now = datetime.now(timezone.utc)
        # Ensure both are timezone-aware.
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
        delta = (now - then).total_seconds()
        return max(0, int(delta))

    def _total_elapsed(self, session: Session) -> int:
        """Return total elapsed seconds for *session*.

        For active sessions this includes the currently running segment;
        for paused/ended sessions it returns the stored total.

        Args:
            session: The session to calculate elapsed time for.

        Returns:
            Total elapsed seconds.
        """
        if session.status == "active":
            return session.total_seconds + self._elapsed_since(session.started_at)
        return session.total_seconds
