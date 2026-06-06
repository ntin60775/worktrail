"""worktrail.reporter — report generation module.

Provides human-readable reports (terminal + Markdown) for tracked work time.
All user-facing text is in Russian.  No git jargon is used.

Usage::

    from worktrail.core import Repository
    from worktrail.reporter import ReportGenerator

    repo = Repository()
    gen = ReportGenerator(repo)

    # Daily report
    report = gen.generate_daily_report("2026-05-29")
    print(report.to_terminal())
    gen.save_report(report)

    # Weekly report
    week_report = gen.generate_week_report()
    print(week_report.to_terminal())

    # Task report
    task_report = gen.generate_task_report("TASK-001")
    print(task_report.to_terminal())
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from worktrail.core import Checkpoint, Repository, Session, get_db_path
from worktrail.reporter.formatter import (
    Block,
    Report,
    ReportItem,
    _group_checkpoints,
    _parse_iso,
    _translate_status,
    build_report_item,
)
from worktrail.reporter.writer import (
    render_markdown,
    render_terminal,
    write_report_to_file,
)

__all__ = [
    "Block",
    "Report",
    "ReportItem",
    "ReportGenerator",
]


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _today_iso() -> str:
    """Return today's date as 'YYYY-MM-DD'."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _monday_of_current_week() -> str:
    """Return the Monday of the current week as 'YYYY-MM-DD'."""
    today = datetime.now(timezone.utc).date()
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()


def _format_russian_date(date_str: str) -> str:
    """Convert 'YYYY-MM-DD' to Russian 'DD.MM.YYYY'."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%d.%m.%Y")


def _russian_period(start_date: str, end_date: str) -> str:
    """Format a date range as Russian 'DD.MM.YYYY — DD.MM.YYYY'."""
    return f"{_format_russian_date(start_date)} — {_format_russian_date(end_date)}"


# ---------------------------------------------------------------------------
# ReportGenerator
# ---------------------------------------------------------------------------


class ReportGenerator:
    """Generate human-readable reports from a worktrail repository.

    Args:
        repository: A :class:`worktrail.core.Repository` instance.
    """

    def __init__(self, repository: Repository) -> None:
        self._repo = repository

    # ------------------------------------------------------------------
    # Internal query helpers
    # ------------------------------------------------------------------

    def _get_sessions_for_date(self, date_str: str) -> list[Session]:
        """Return all sessions that started on *date_str* ('YYYY-MM-DD')."""
        pattern = f"{date_str}%"
        with self._repo.conn() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE started_at LIKE ? ORDER BY started_at",
                (pattern,),
            ).fetchall()
        return [
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

    def _get_sessions_for_date_range(
        self, start_date: str, end_date: str
    ) -> list[Session]:
        """Return all sessions that started within [*start_date*, *end_date*]."""
        start_pattern = f"{start_date} 00:00:00"
        end_pattern = f"{end_date} 23:59:59"
        with self._repo.conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM sessions
                WHERE started_at >= ? AND started_at <= ?
                ORDER BY started_at
                """,
                (start_pattern, end_pattern),
            ).fetchall()
        return [
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

    def _get_sessions_for_task(self, task_id: str) -> list[Session]:
        """Return all sessions for a given task, ordered by start time."""
        with self._repo.conn() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE task_id = ? ORDER BY started_at",
                (task_id,),
            ).fetchall()
        return [
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

    def _get_task_info(self, task_id: str) -> tuple[str, str] | None:
        """Return (name, status) for a task, or ``None`` if not found."""
        with self._repo.conn() as conn:
            row = conn.execute(
                "SELECT name, status FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        if row is None:
            return None
        return row["name"], row["status"]

    def _get_checkpoints_for_session(self, session_id: int) -> list[Checkpoint]:
        """Return all checkpoints for a session ordered by timestamp."""
        return self._repo.get_checkpoints_for_session(session_id)

    # ------------------------------------------------------------------
    # Public report methods
    # ------------------------------------------------------------------

    def generate_daily_report(self, date_str: str | None = None) -> Report:
        """Generate a report for a single day.

        Args:
            date_str: Date in 'YYYY-MM-DD' format.  Defaults to today (UTC).

        Returns:
            A :class:`Report` instance for the requested day.
        """
        if date_str is None:
            date_str = _today_iso()

        sessions = self._get_sessions_for_date(date_str)
        return self._build_report_from_sessions(
            sessions,
            title=f"Отчёт за {_format_russian_date(date_str)}",
            period=_format_russian_date(date_str),
        )

    def generate_week_report(self, week_start: str | None = None) -> Report:
        """Generate a report for a 7-day week.

        Args:
            week_start: Monday in 'YYYY-MM-DD' format.  Defaults to the
                Monday of the current week (UTC).

        Returns:
            A :class:`Report` instance covering the 7-day period.
        """
        if week_start is None:
            week_start = _monday_of_current_week()

        start_dt = datetime.strptime(week_start, "%Y-%m-%d").date()
        end_dt = start_dt + timedelta(days=6)
        end_date = end_dt.isoformat()

        sessions = self._get_sessions_for_date_range(week_start, end_date)
        return self._build_report_from_sessions(
            sessions,
            title=f"Отчёт за неделю {_russian_period(week_start, end_date)}",
            period=_russian_period(week_start, end_date),
        )

    def generate_task_report(self, task_id: str) -> Report:
        """Generate a report for a specific task (all time).

        Args:
            task_id: The task identifier (e.g. 'TASK-001').

        Returns:
            A :class:`Report` instance covering all sessions for the task.

        Raises:
            ValueError: If the task does not exist in the database.
        """
        task_info = self._get_task_info(task_id)
        if task_info is None:
            raise ValueError(f"Задача {task_id} не найдена")

        task_name, task_status = task_info
        sessions = self._get_sessions_for_task(task_id)

        sessions_with_checkpoints: list[tuple[Session, list[Checkpoint]]] = []
        for session in sessions:
            checkpoints = self._get_checkpoints_for_session(session.id)
            sessions_with_checkpoints.append((session, checkpoints))

        item = build_report_item(
            task_id=task_id,
            task_name=task_name,
            task_status=task_status,
            sessions_with_checkpoints=sessions_with_checkpoints,
        )

        return Report(
            title=f"Отчёт по задаче {task_id}: {task_name}",
            period="всё время",
            total_hours=item.total_hours,
            items=[item],
        )

    def save_report(self, report: Report, output_path: Path | None = None) -> Path:
        """Save a report as a Markdown file.

        Args:
            report: The report to save.
            output_path: Destination path.  Defaults to
                ``.worktrail/reports/YYYY-MM-DD.md`` where *YYYY-MM-DD* is
                derived from the report period.

        Returns:
            The path the file was written to.
        """
        if output_path is None:
            db_path = get_db_path()
            reports_dir = db_path.parent / "reports"

            # Try to extract a date from the period string
            period = report.period
            if " — " in period:
                # Weekly report: use the start date
                start_ru = period.split(" — ")[0]
                try:
                    dt = datetime.strptime(start_ru, "%d.%m.%Y")
                    filename = dt.strftime("%Y-%m-%d") + "-week.md"
                except ValueError:
                    filename = "report.md"
            elif period == "всё время":
                # Task report
                safe_title = report.title.replace(" ", "_").replace(":", "-")
                filename = f"{safe_title}.md"
            else:
                # Daily report
                try:
                    dt = datetime.strptime(period, "%d.%m.%Y")
                    filename = dt.strftime("%Y-%m-%d") + ".md"
                except ValueError:
                    filename = "report.md"

            output_path = reports_dir / filename

        return write_report_to_file(report, output_path)

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _build_report_from_sessions(
        self,
        sessions: list[Session],
        title: str,
        period: str,
    ) -> Report:
        """Group sessions by task and build a :class:`Report`."""
        if not sessions:
            return Report(title=title, period=period, total_hours=0.0, items=[])

        # Group sessions by task_id
        by_task: dict[str, list[tuple[Session, list[Checkpoint]]]] = {}
        for session in sessions:
            checkpoints = self._get_checkpoints_for_session(session.id)
            by_task.setdefault(session.task_id, []).append((session, checkpoints))

        items: list[ReportItem] = []
        for task_id, sessions_with_checkpoints in by_task.items():
            task_info = self._get_task_info(task_id)
            if task_info is None:
                task_name = "<неизвестная задача>"
                task_status = "active"
            else:
                task_name, task_status = task_info

            item = build_report_item(
                task_id=task_id,
                task_name=task_name,
                task_status=task_status,
                sessions_with_checkpoints=sessions_with_checkpoints,
            )
            if item.total_hours > 0 or item.blocks:
                items.append(item)

        total_hours = round(sum(item.total_hours for item in items), 1)
        return Report(title=title, period=period, total_hours=total_hours, items=items)
