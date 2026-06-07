"""Comprehensive pytest tests for worktrail.reporter module.

Tests cover:
  - formatter.py: checkpoint grouping, report item building, daily/task reports,
    total hours calculation, empty-session handling.
  - writer.py: terminal rendering, markdown rendering, file writing,
    content verification (task IDs, hours, no git jargon).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from worktrail.core.db import init_db
from worktrail.core.models import Checkpoint, Session
from worktrail.core.repository import Repository
from worktrail.reporter.formatter import (
    GROUPING_WINDOW_MINUTES,
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
from worktrail.reporter import ReportGenerator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project root with .worktrail directory."""
    wt_dir = tmp_path / ".worktrail"
    wt_dir.mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def temp_db(tmp_project: Path) -> tuple[Path, Repository]:
    """Create a fresh database, seed it with tasks/sessions/checkpoints, return (db_path, repo)."""
    db_path = tmp_project / ".worktrail" / "runtime.db"
    init_db(db_path)
    repo = Repository(db_path)

    base_date = datetime(2026, 5, 29, 9, 0, 0, tzinfo=timezone.utc)

    # --- Task 1 (active) ---
    repo.create_task("TASK-001", "Implement feature X")
    with repo.conn() as conn:
        conn.execute(
            """
            INSERT INTO sessions (task_id, started_at, ended_at, status, total_seconds)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "TASK-001",
                (base_date).isoformat(),
                (base_date + timedelta(hours=2)).isoformat(),
                "ended",
                7200,
            ),
        )
        conn.execute(
            """
            INSERT INTO sessions (task_id, started_at, ended_at, status, total_seconds)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "TASK-001",
                (base_date + timedelta(hours=3)).isoformat(),
                (base_date + timedelta(hours=4, minutes=30)).isoformat(),
                "ended",
                5400,
            ),
        )
        conn.commit()

    # --- Task 2 (done) ---
    repo.create_task("TASK-002", "Fix bug Y")
    with repo.conn() as conn:
        conn.execute(
            """
            INSERT INTO sessions (task_id, started_at, ended_at, status, total_seconds)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "TASK-002",
                (base_date + timedelta(hours=5)).isoformat(),
                (base_date + timedelta(hours=5, minutes=45)).isoformat(),
                "ended",
                2700,
            ),
        )
        conn.commit()

    # --- Task 3 (active, no sessions — used for empty-report test) ---
    repo.create_task("TASK-003", "Future work")
    # Update status to done
    repo.update_task_status("TASK-002", "done")

    # Add checkpoints for TASK-001 sessions
    # Session 1 (id=1): three checkpoints within 10 min, then gap > 30 min
    with repo.conn() as conn:
        conn.execute(
            "INSERT INTO checkpoints (session_id, message, timestamp, source) VALUES (?, ?, ?, ?)",
            (1, "Started work", (base_date + timedelta(minutes=0)).isoformat(), "manual"),
        )
        conn.execute(
            "INSERT INTO checkpoints (session_id, message, timestamp, source) VALUES (?, ?, ?, ?)",
            (1, "Made progress", (base_date + timedelta(minutes=10)).isoformat(), "manual"),
        )
        conn.execute(
            "INSERT INTO checkpoints (session_id, message, timestamp, source) VALUES (?, ?, ?, ?)",
            (1, "Almost done", (base_date + timedelta(minutes=50)).isoformat(), "manual"),
        )
        # Session 2 (id=2): single checkpoint
        conn.execute(
            "INSERT INTO checkpoints (session_id, message, timestamp, source) VALUES (?, ?, ?, ?)",
            (2, "Session 2 start", (base_date + timedelta(hours=3)).isoformat(), "manual"),
        )
        conn.execute(
            "INSERT INTO checkpoints (session_id, message, timestamp, source) VALUES (?, ?, ?, ?)",
            (2, "Session 2 middle", (base_date + timedelta(hours=3, minutes=20)).isoformat(), "manual"),
        )
        conn.execute(
            "INSERT INTO checkpoints (session_id, message, timestamp, source) VALUES (?, ?, ?, ?)",
            (2, "Session 2 end", (base_date + timedelta(hours=4, minutes=10)).isoformat(), "manual"),
        )
        # Session 3 (id=3): checkpoints for TASK-002
        conn.execute(
            "INSERT INTO checkpoints (session_id, message, timestamp, source) VALUES (?, ?, ?, ?)",
            (3, "Bug identified", (base_date + timedelta(hours=5)).isoformat(), "manual"),
        )
        conn.execute(
            "INSERT INTO checkpoints (session_id, message, timestamp, source) VALUES (?, ?, ?, ?)",
            (3, "Fix applied", (base_date + timedelta(hours=5, minutes=30)).isoformat(), "manual"),
        )
        conn.commit()

    return db_path, repo


@pytest.fixture
def generator(temp_db: tuple[Path, Repository]) -> ReportGenerator:
    """Return a ReportGenerator backed by the seeded temp DB."""
    db_path, repo = temp_db
    return ReportGenerator(repo)


@pytest.fixture
def sample_report() -> Report:
    """Return a hand-crafted Report for writer tests."""
    return Report(
        title="Отчёт за 29.05.2026",
        period="29.05.2026",
        total_hours=3.5,
        items=[
            ReportItem(
                task_id="TASK-001",
                task_name="Implement feature X",
                total_hours=2.0,
                blocks=[
                    Block(description="Started feature implementation", hours=1.0),
                    Block(description="Completed testing", hours=1.0),
                ],
                status="в работе",
            ),
            ReportItem(
                task_id="TASK-002",
                task_name="Fix bug Y",
                total_hours=1.5,
                blocks=[
                    Block(description="Bug identified and fixed", hours=1.5),
                ],
                status="завершена",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# _group_checkpoints tests
# ---------------------------------------------------------------------------


class TestGroupCheckpoints:
    """Tests for the _group_checkpoints function."""

    def test_groups_within_30_min_window(self) -> None:
        """Checkpoints within 30 min of each other should be grouped into one block."""
        base = datetime(2026, 5, 29, 9, 0, 0, tzinfo=timezone.utc)
        checkpoints = [
            Checkpoint(session_id=1, message="cp1", timestamp=(base).isoformat()),
            Checkpoint(session_id=1, message="cp2", timestamp=(base + timedelta(minutes=10)).isoformat()),
            Checkpoint(session_id=1, message="cp3", timestamp=(base + timedelta(minutes=25)).isoformat()),
        ]
        blocks = _group_checkpoints(checkpoints, session_end=None)
        assert len(blocks) == 1
        assert "cp1; cp2; cp3" in blocks[0].description

    def test_splits_when_gap_exceeds_30_min(self) -> None:
        """Checkpoints > 30 min apart should be split into separate blocks."""
        base = datetime(2026, 5, 29, 9, 0, 0, tzinfo=timezone.utc)
        checkpoints = [
            Checkpoint(session_id=1, message="cp1", timestamp=(base).isoformat()),
            Checkpoint(session_id=1, message="cp2", timestamp=(base + timedelta(minutes=10)).isoformat()),
            Checkpoint(session_id=1, message="cp3", timestamp=(base + timedelta(minutes=45)).isoformat()),
        ]
        blocks = _group_checkpoints(checkpoints, session_end=None)
        # cp1 + cp2 within 30 min => group 1; cp3 is 35 min after cp2 (>30) => group 2
        assert len(blocks) == 2
        assert "cp1; cp2" in blocks[0].description
        assert "cp3" in blocks[1].description

    def test_last_block_uses_remaining_time_not_capped(self) -> None:
        """Last block should get remaining time to session_end, not capped at 15 min."""
        base = datetime(2026, 5, 29, 9, 0, 0, tzinfo=timezone.utc)
        session_end = base + timedelta(hours=3)
        checkpoints = [
            Checkpoint(session_id=1, message="only_cp", timestamp=(base).isoformat()),
        ]
        blocks = _group_checkpoints(checkpoints, session_end=session_end)
        assert len(blocks) == 1
        # Duration = session_end - first_cp = 3 hours, NOT 15 min default
        assert blocks[0].hours == 3.0

    def test_last_block_uses_default_when_no_session_end(self) -> None:
        """When session_end is None, last block uses DEFAULT_BLOCK_MINUTES (15 min = 0.25h)."""
        base = datetime(2026, 5, 29, 9, 0, 0, tzinfo=timezone.utc)
        checkpoints = [
            Checkpoint(session_id=1, message="only_cp", timestamp=(base).isoformat()),
        ]
        blocks = _group_checkpoints(checkpoints, session_end=None)
        assert len(blocks) == 1
        assert blocks[0].hours == 0.2  # 15 min = 0.25h rounded to 1 decimal = 0.2 or 0.3
        # Actually 15/60 = 0.25, round(_, 1) = 0.2 -- no, round(0.25, 1) = 0.2 in Python
        # Wait: round(0.25, 1) = 0.2 in Python due to banker's rounding? Let me check...
        # 0.25 is exactly halfway between 0.2 and 0.3. Python uses banker's rounding.
        # Actually: round(0.25, 1) -> 0.2 (even number). But the test should just check it's the default.
        # Let me use a looser assertion.
        assert blocks[0].hours > 0

    def test_empty_checkpoints_returns_empty(self) -> None:
        """Empty checkpoint list should return an empty block list."""
        assert _group_checkpoints([], session_end=None) == []

    def test_description_truncated_at_100_chars(self) -> None:
        """Description should be truncated to 100 characters with '...' suffix."""
        base = datetime(2026, 5, 29, 9, 0, 0, tzinfo=timezone.utc)
        long_msg = "a" * 60
        checkpoints = [
            Checkpoint(session_id=1, message=long_msg, timestamp=(base).isoformat()),
            Checkpoint(session_id=1, message=long_msg, timestamp=(base + timedelta(minutes=5)).isoformat()),
        ]
        blocks = _group_checkpoints(checkpoints, session_end=None)
        desc = blocks[0].description
        assert len(desc) <= 100
        assert desc.endswith("...")


# ---------------------------------------------------------------------------
# build_report_item tests
# ---------------------------------------------------------------------------


class TestBuildReportItem:
    """Tests for the build_report_item function."""

    def test_creates_correct_report_item(self) -> None:
        """build_report_item should produce a ReportItem with correct fields."""
        base = datetime(2026, 5, 29, 9, 0, 0, tzinfo=timezone.utc)
        session = Session(
            task_id="TASK-001",
            started_at=base.isoformat(),
            ended_at=(base + timedelta(hours=2)).isoformat(),
            status="ended",
            total_seconds=7200,
            id=1,
        )
        checkpoints = [
            Checkpoint(session_id=1, message="cp1", timestamp=(base).isoformat()),
            Checkpoint(session_id=1, message="cp2", timestamp=(base + timedelta(minutes=20)).isoformat()),
        ]
        item = build_report_item(
            task_id="TASK-001",
            task_name="Test Task",
            task_status="active",
            sessions_with_checkpoints=[(session, checkpoints)],
        )
        assert isinstance(item, ReportItem)
        assert item.task_id == "TASK-001"
        assert item.task_name == "Test Task"
        assert item.status == "в работе"
        assert len(item.blocks) >= 1
        assert item.total_hours > 0

    def test_total_hours_calculation(self) -> None:
        """ReportItem total_hours should be the sum of all block hours."""
        base = datetime(2026, 5, 29, 9, 0, 0, tzinfo=timezone.utc)
        session = Session(
            task_id="TASK-001",
            started_at=base.isoformat(),
            ended_at=(base + timedelta(hours=2)).isoformat(),
            status="ended",
            total_seconds=7200,
            id=1,
        )
        checkpoints = [
            Checkpoint(session_id=1, message="cp1", timestamp=(base).isoformat()),
            Checkpoint(session_id=1, message="cp2", timestamp=(base + timedelta(minutes=20)).isoformat()),
            Checkpoint(session_id=1, message="cp3", timestamp=(base + timedelta(minutes=50)).isoformat()),
        ]
        item = build_report_item(
            task_id="TASK-001",
            task_name="Test Task",
            task_status="active",
            sessions_with_checkpoints=[(session, checkpoints)],
        )
        # cp1 at 0, cp2 at 20min (within 30), cp3 at 50min (30min from cp2? 50-20=30 <= 30)
        # So all 3 in one group. Duration = session_end - first_cp = 2h.
        expected_total = round(2.0, 1)
        assert item.total_hours == expected_total


# ---------------------------------------------------------------------------
# ReportGenerator tests
# ---------------------------------------------------------------------------


class TestDailyReport:
    """Tests for generate_daily_report."""

    def test_returns_report_with_correct_structure(self, generator: ReportGenerator) -> None:
        """generate_daily_report should return a Report with title, period, items, total_hours."""
        report = generator.generate_daily_report("2026-05-29")
        assert isinstance(report, Report)
        assert "29.05.2026" in report.title
        assert report.period == "29.05.2026"
        assert isinstance(report.items, list)
        assert report.total_hours >= 0

    def test_correct_total_hours(self, generator: ReportGenerator) -> None:
        """Report total_hours should match sum of all task hours."""
        report = generator.generate_daily_report("2026-05-29")
        expected = round(sum(item.total_hours for item in report.items), 1)
        assert report.total_hours == expected

    def test_empty_sessions_produce_empty_report(self, generator: ReportGenerator) -> None:
        """A date with no sessions should produce a report with zero hours and no items."""
        report = generator.generate_daily_report("2025-01-01")
        assert report.total_hours == 0.0
        assert report.items == []


class TestTaskReport:
    """Tests for generate_task_report."""

    def test_returns_report_for_specific_task(self, generator: ReportGenerator) -> None:
        """generate_task_report should return a Report with a single task's data."""
        report = generator.generate_task_report("TASK-001")
        assert isinstance(report, Report)
        assert "TASK-001" in report.title
        assert len(report.items) == 1
        assert report.items[0].task_id == "TASK-001"

    def test_task_not_found_raises(self, generator: ReportGenerator) -> None:
        """generate_task_report should raise ValueError for non-existent task."""
        with pytest.raises(ValueError, match="не найдена"):
            generator.generate_task_report("TASK-NONEXISTENT")

    def test_report_contains_task_name_and_hours(self, generator: ReportGenerator) -> None:
        """Task report should contain the task name and non-negative hours."""
        report = generator.generate_task_report("TASK-002")
        item = report.items[0]
        assert item.task_name == "Fix bug Y"
        assert item.total_hours >= 0
        assert item.status == "завершена"


# ---------------------------------------------------------------------------
# writer.py — render_terminal tests
# ---------------------------------------------------------------------------


class TestRenderTerminal:
    """Tests for render_terminal."""

    def test_returns_string_with_task_info(self, sample_report: Report) -> None:
        """render_terminal should return a string containing task IDs and names."""
        output = render_terminal(sample_report)
        assert isinstance(output, str)
        assert "TASK-001" in output
        assert "Implement feature X" in output
        assert "TASK-002" in output
        assert "Fix bug Y" in output

    def test_contains_hours(self, sample_report: Report) -> None:
        """render_terminal should include formatted hours."""
        output = render_terminal(sample_report)
        assert "2.0ч" in output
        assert "1.5ч" in output
        assert "3.5ч" in output or f"{sample_report.total_hours:.1f}ч" in output

    def test_no_git_jargon(self, sample_report: Report) -> None:
        """render_terminal output should NOT contain git jargon like 'commit', 'hash', 'branch'."""
        output = render_terminal(sample_report).lower()
        git_terms = ["commit", "hash", "branch", "merge", "pull", "push"]
        for term in git_terms:
            assert term not in output, f"Git jargon '{term}' found in terminal output"

    def test_empty_report_handling(self) -> None:
        """render_terminal should handle a report with no items gracefully."""
        empty_report = Report(
            title="Отчёт за 01.01.2025",
            period="01.01.2025",
            total_hours=0.0,
            items=[],
        )
        output = render_terminal(empty_report)
        assert "Нет данных" in output
        assert "0.0ч" in output


# ---------------------------------------------------------------------------
# writer.py — render_markdown tests
# ---------------------------------------------------------------------------


class TestRenderMarkdown:
    """Tests for render_markdown."""

    def test_returns_markdown_formatted_string(self, sample_report: Report) -> None:
        """render_markdown should return a string with markdown formatting."""
        output = render_markdown(sample_report)
        assert isinstance(output, str)
        assert output.startswith("# ")
        assert "**Период:**" in output
        assert "## TASK-001:" in output
        assert "## TASK-002:" in output

    def test_contains_task_id_and_hours(self, sample_report: Report) -> None:
        """render_markdown should include task IDs and formatted hours."""
        output = render_markdown(sample_report)
        assert "TASK-001" in output
        assert "TASK-002" in output
        assert "2.0ч" in output
        assert "1.5ч" in output

    def test_no_git_jargon(self, sample_report: Report) -> None:
        """render_markdown output should NOT contain git jargon."""
        output = render_markdown(sample_report).lower()
        git_terms = ["commit", "hash", "branch", "merge", "pull", "push"]
        for term in git_terms:
            assert term not in output, f"Git jargon '{term}' found in markdown output"


# ---------------------------------------------------------------------------
# writer.py — write_report_to_file tests
# ---------------------------------------------------------------------------


class TestWriteReportToFile:
    """Tests for write_report_to_file."""

    def test_creates_file_on_disk(self, sample_report: Report, tmp_path: Path) -> None:
        """write_report_to_file should create the output file on disk."""
        output_path = tmp_path / "report.md"
        result = write_report_to_file(sample_report, output_path)
        assert result.exists()
        assert result.read_text(encoding="utf-8").startswith("# ")

    def test_output_contains_task_id_and_hours(self, sample_report: Report, tmp_path: Path) -> None:
        """The written file should contain task IDs and hours."""
        output_path = tmp_path / "report.md"
        write_report_to_file(sample_report, output_path)
        content = output_path.read_text(encoding="utf-8")
        assert "TASK-001" in content
        assert "2.0ч" in content

    def test_creates_parent_directories(self, sample_report: Report, tmp_path: Path) -> None:
        """write_report_to_file should create missing parent directories."""
        output_path = tmp_path / "nested" / "deep" / "report.md"
        result = write_report_to_file(sample_report, output_path)
        assert result.exists()


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    """Tests for small helper functions."""

    def test_parse_iso(self) -> None:
        """_parse_iso should correctly parse ISO8601 strings."""
        ts = "2026-05-29T09:00:00+00:00"
        dt = _parse_iso(ts)
        assert dt.year == 2026
        assert dt.month == 5
        assert dt.day == 29
        assert dt.hour == 9

    def test_parse_iso_with_z(self) -> None:
        """_parse_iso should handle 'Z' suffix."""
        ts = "2026-05-29T09:00:00Z"
        dt = _parse_iso(ts)
        assert dt.year == 2026
        assert dt.day == 29

    def test_translate_status(self) -> None:
        """_translate_status should map status codes to Russian."""
        assert _translate_status("draft") == "черновик"
        assert _translate_status("active") == "в работе"
        assert _translate_status("blocked") == "заблокирована"
        assert _translate_status("review") == "на проверке"
        assert _translate_status("done") == "завершена"
        assert _translate_status("archived") == "в архиве"
        assert _translate_status("cancelled") == "отменена"
        assert _translate_status("unknown") == "unknown"
