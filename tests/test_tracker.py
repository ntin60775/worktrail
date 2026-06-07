"""Comprehensive pytest tests for worktrail.tracker module.

Tests cover:
  - TrackerEngine session lifecycle (start, stop, pause, resume)
  - Checkpoint recording and queries
  - IdleMonitor filesystem-based idle detection
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from freezegun import freeze_time

from worktrail.core.db import init_db
from worktrail.core.repository import Repository
from worktrail.tracker.engine import TrackerEngine
from worktrail.tracker.idle import IdleMonitor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Create a temporary project root with initialized database."""
    worktrail_dir = tmp_path / ".worktrail"
    worktrail_dir.mkdir(parents=True, exist_ok=True)
    db_path = worktrail_dir / "runtime.db"
    init_db(db_path)
    return tmp_path


@pytest.fixture
def engine(temp_db: Path) -> TrackerEngine:
    """Return a TrackerEngine backed by a temporary database."""
    db_path = temp_db / ".worktrail" / "runtime.db"
    repo = Repository(db_path)
    return TrackerEngine(repo=repo, project_root=temp_db)


# ---------------------------------------------------------------------------
# TrackerEngine — Session lifecycle
# ---------------------------------------------------------------------------


def test_start_creates_session_and_task(engine: TrackerEngine) -> None:
    """start() creates both a session and the task if it doesn't exist."""
    session = engine.start("TASK-001", "Fix login bug")

    assert session is not None
    assert session.task_id == "TASK-001"
    assert session.status == "active"
    assert session.total_seconds == 0
    assert session.id is not None

    # Verify task was also created.
    current = engine.current()
    assert current is not None
    assert current["task"].id == "TASK-001"
    assert current["task"].name == "Fix login bug"


def test_start_autostops_existing_active_session(engine: TrackerEngine) -> None:
    """Starting a new session auto-stops any existing active session."""
    with freeze_time("2024-01-01 12:00:00") as frozen:
        session1 = engine.start("TASK-001", "First task")
        assert session1.status == "active"

        # Advance time by 10 seconds before starting the next session.
        frozen.tick(10)
        session2 = engine.start("TASK-002", "Second task")

    # First session should now be ended.
    repo = engine._repo
    ended_session1 = repo.get_session(session1.id)
    assert ended_session1 is not None
    assert ended_session1.status == "ended"
    assert ended_session1.total_seconds > 0

    # Second session should be active.
    assert session2.status == "active"
    assert session2.task_id == "TASK-002"


def test_stop_ends_session_with_positive_total_seconds(engine: TrackerEngine) -> None:
    """stop() ends the active session and accumulates elapsed time."""
    with freeze_time("2024-01-01 12:00:00") as frozen:
        engine.start("TASK-001", "Test task")
        frozen.tick(10)
        stopped = engine.stop()

    assert stopped is not None
    assert stopped.status == "ended"
    assert stopped.ended_at is not None
    assert stopped.total_seconds > 0


def test_stop_returns_none_when_no_active_session(engine: TrackerEngine) -> None:
    """stop() returns None if there is no active session."""
    result = engine.stop()
    assert result is None


def test_pause_changes_status_to_paused(engine: TrackerEngine) -> None:
    """pause() changes the session status from active to paused."""
    with freeze_time("2024-01-01 12:00:00") as frozen:
        engine.start("TASK-001", "Test task")
        frozen.tick(10)
        paused = engine.pause()

    assert paused is not None
    assert paused.status == "paused"
    assert paused.total_seconds > 0


def test_resume_changes_status_back_to_active(engine: TrackerEngine) -> None:
    """resume() changes the paused session back to active."""
    engine.start("TASK-001", "Test task")
    time.sleep(0.1)
    engine.pause()

    resumed = engine.resume()
    assert resumed is not None
    assert resumed.status == "active"

    # Verify no active session exception — should be active now.
    current = engine.current()
    assert current is not None
    assert current["session"].status == "active"


def test_pause_returns_none_when_no_active_session(engine: TrackerEngine) -> None:
    """pause() returns None when there is no active session."""
    result = engine.pause()
    assert result is None


def test_resume_returns_none_when_no_paused_session(engine: TrackerEngine) -> None:
    """resume() returns None when there is no paused session."""
    result = engine.resume()
    assert result is None


# ---------------------------------------------------------------------------
# TrackerEngine — Checkpoint operations
# ---------------------------------------------------------------------------


def test_checkpoint_adds_checkpoint_to_active_session(engine: TrackerEngine) -> None:
    """checkpoint() records a checkpoint in the active session."""
    session = engine.start("TASK-001", "Test task")
    cp = engine.checkpoint("Implemented form validation")

    assert cp is not None
    assert cp.session_id == session.id
    assert cp.message == "Implemented form validation"
    assert cp.source == "manual"
    assert cp.id is not None


def test_checkpoint_fails_when_no_active_session(engine: TrackerEngine) -> None:
    """checkpoint() raises RuntimeError when there is no active session."""
    with pytest.raises(RuntimeError, match="No active session"):
        engine.checkpoint("Should fail")


def test_multiple_checkpoints_in_one_session(engine: TrackerEngine) -> None:
    """Multiple checkpoints can be added to a single session."""
    session = engine.start("TASK-001", "Test task")

    cp1 = engine.checkpoint("First milestone")
    cp2 = engine.checkpoint("Second milestone")
    cp3 = engine.checkpoint("Third milestone")

    assert cp1.session_id == session.id
    assert cp2.session_id == session.id
    assert cp3.session_id == session.id

    current = engine.current()
    assert current is not None
    assert current["checkpoints_count"] == 3


# ---------------------------------------------------------------------------
# TrackerEngine — Query operations
# ---------------------------------------------------------------------------


def test_current_returns_none_when_no_active_session(engine: TrackerEngine) -> None:
    """current() returns None when no session is active."""
    result = engine.current()
    assert result is None


def test_current_returns_session_info_with_elapsed_time(engine: TrackerEngine) -> None:
    """current() returns session info including elapsed_seconds."""
    engine.start("TASK-001", "Test task")
    time.sleep(0.1)

    info = engine.current()
    assert info is not None
    assert "session" in info
    assert "task" in info
    assert "elapsed_seconds" in info
    assert "checkpoints_count" in info

    assert info["session"].task_id == "TASK-001"
    assert info["task"].name == "Test task"
    assert info["elapsed_seconds"] >= 0
    assert info["checkpoints_count"] == 0


def test_get_task_summary_returns_aggregated_data(engine: TrackerEngine) -> None:
    """get_task_summary() returns aggregated data for a task."""
    with freeze_time("2024-01-01 12:00:00") as frozen:
        engine.start("TASK-001", "Test task")
        frozen.tick(10)
        engine.checkpoint("cp1")
        engine.stop()

    summary = engine.get_task_summary("TASK-001")

    assert summary is not None
    assert summary["task"].id == "TASK-001"
    assert summary["task"].name == "Test task"
    assert summary["total_seconds"] > 0
    assert len(summary["sessions"]) == 1
    assert len(summary["checkpoints"]) == 1
    assert summary["checkpoints"][0].message == "cp1"


def test_get_task_summary_raises_for_missing_task(engine: TrackerEngine) -> None:
    """get_task_summary() raises ValueError for nonexistent task."""
    with pytest.raises(ValueError, match="Task 'NONEXISTENT' not found"):
        engine.get_task_summary("NONEXISTENT")


# ---------------------------------------------------------------------------
# TrackerEngine — Multiple start/stop cycles
# ---------------------------------------------------------------------------


def test_multiple_start_stop_cycles_for_same_task(engine: TrackerEngine) -> None:
    """Multiple start/stop cycles for the same task accumulate properly."""
    with freeze_time("2024-01-01 12:00:00") as frozen:
        # First cycle.
        engine.start("TASK-001", "Recurring task")
        frozen.tick(10)
        engine.checkpoint("Cycle 1 done")
        engine.stop()

        # Second cycle.
        frozen.tick(1)
        engine.start("TASK-001")
        frozen.tick(10)
        engine.checkpoint("Cycle 2 done")
        engine.stop()

        # Third cycle.
        frozen.tick(1)
        engine.start("TASK-001")
        frozen.tick(10)
        engine.checkpoint("Cycle 3 done")
        engine.stop()

    summary = engine.get_task_summary("TASK-001")
    assert len(summary["sessions"]) == 3
    assert len(summary["checkpoints"]) == 3
    assert summary["total_seconds"] > 0


# ---------------------------------------------------------------------------
# IdleMonitor — Filesystem-based idle detection
# ---------------------------------------------------------------------------


def test_check_idle_returns_false_when_files_recently_modified(tmp_path: Path) -> None:
    """check_idle() returns False when files were recently modified."""
    # Create a project root with a recently modified file.
    project_root = tmp_path / "project"
    project_root.mkdir()
    src_file = project_root / "main.py"
    src_file.write_text("print('hello')")

    # Idle timeout of 5 seconds — file was just touched, so not idle.
    monitor = IdleMonitor(idle_timeout=5)
    is_idle = monitor.check_idle(project_root)
    assert is_idle is False


def test_check_idle_returns_true_when_no_recent_activity(tmp_path: Path) -> None:
    """check_idle() returns True when files haven't been modified recently."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    src_file = project_root / "old_file.py"
    src_file.write_text("old code")

    # Use a very short idle timeout.
    monitor = IdleMonitor(idle_timeout=1)

    # Wait for the idle threshold to be exceeded.
    time.sleep(1.5)
    is_idle = monitor.check_idle(project_root)
    assert is_idle is True


def test_get_activity_timestamp_returns_recent_mtime(tmp_path: Path) -> None:
    """get_activity_timestamp() returns the most recent file mtime."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    src_file = project_root / "recent.py"
    src_file.write_text("recent code")

    monitor = IdleMonitor(idle_timeout=900)
    ts = monitor.get_activity_timestamp(project_root)

    assert ts is not None
    # Timestamp should be very recent (within last few seconds).
    now = datetime.now(timezone.utc)
    delta = (now - ts).total_seconds()
    assert delta < 5.0


def test_idle_respects_git_and_worktrail_exclusions(tmp_path: Path) -> None:
    """IdleMonitor skips .git/ and .worktrail/ directories."""
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create a .git directory with a very old file.
    git_dir = project_root / ".git"
    git_dir.mkdir()
    old_git_file = git_dir / "old_commit"
    old_git_file.write_text("ancient")

    # Create a .worktrail directory with a very old file.
    wt_dir = project_root / ".worktrail"
    wt_dir.mkdir()
    old_wt_file = wt_dir / "old_state"
    old_wt_file.write_text("ancient")

    # Create a recent file in the normal source tree.
    src_file = project_root / "main.py"
    src_file.write_text("print('hello')")

    # Short idle timeout — should NOT be idle because .git/ and .worktrail/
    # are excluded and main.py is recent.
    monitor = IdleMonitor(idle_timeout=3)
    is_idle = monitor.check_idle(project_root)
    assert is_idle is False

    # Verify get_activity_timestamp returns the recent mtime, not the old one.
    ts = monitor.get_activity_timestamp(project_root)
    assert ts is not None
    now = datetime.now(timezone.utc)
    delta = (now - ts).total_seconds()
    assert delta < 5.0  # Recent, not the ancient file


# ---------------------------------------------------------------------------
# IdleMonitor — Edge cases
# ---------------------------------------------------------------------------


def test_check_idle_empty_directory_returns_true(tmp_path: Path) -> None:
    """check_idle() returns True for an empty directory (no files found)."""
    project_root = tmp_path / "empty_project"
    project_root.mkdir()

    monitor = IdleMonitor(idle_timeout=1)
    is_idle = monitor.check_idle(project_root)
    assert is_idle is True


def test_get_activity_timestamp_empty_directory_returns_none(tmp_path: Path) -> None:
    """get_activity_timestamp() returns None for an empty directory."""
    project_root = tmp_path / "empty_project"
    project_root.mkdir()

    monitor = IdleMonitor(idle_timeout=1)
    ts = monitor.get_activity_timestamp(project_root)
    assert ts is None


# ---------------------------------------------------------------------------
# TrackerEngine — Task creation contract (name required, draft→active)
# ---------------------------------------------------------------------------


def test_start_falls_back_to_task_id_when_name_missing(
    engine: TrackerEngine,
) -> None:
    """start() uses task_id as the task name when task_name is None or empty."""
    engine.start("FALLBACK-001")
    task = engine._repo.get_task("FALLBACK-001")
    assert task is not None
    assert task.name == "FALLBACK-001"
    assert task.status == "active"

    engine.start("FALLBACK-002", "")
    task2 = engine._repo.get_task("FALLBACK-002")
    assert task2 is not None
    assert task2.name == "FALLBACK-002"
    assert task2.status == "active"


def test_start_auto_transitions_draft_to_active(engine: TrackerEngine) -> None:
    """start() promotes a draft task to active when a session begins."""
    # Create task manually in draft status
    engine._repo.create_task("DRAFT-001", "Draft task", status="draft")
    task_before = engine._repo.get_task("DRAFT-001")
    assert task_before is not None
    assert task_before.status == "draft"

    # Start a session — should auto-promote
    engine.start("DRAFT-001", "Draft task")

    task_after = engine._repo.get_task("DRAFT-001")
    assert task_after is not None
    assert task_after.status == "active"


def test_start_does_not_change_non_draft_status(engine: TrackerEngine) -> None:
    """start() does not alter status for tasks that are not draft."""
    # Create task in a non-draft status
    engine._repo.create_task("REVIEW-001", "Review task", status="review")

    engine.start("REVIEW-001", "Review task")

    task = engine._repo.get_task("REVIEW-001")
    assert task is not None
    assert task.status == "review"  # unchanged
