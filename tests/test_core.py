"""Comprehensive pytest unit tests for worktrail.core module.

Tests cover db.py, models.py, repository.py, and config.py.
All tests use isolated temporary directories and fixtures.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

import pytest

from worktrail.core import find_project_root
from worktrail.core.config import get_config_path, load_config, save_config
from worktrail.core.db import get_connection, get_db_path, init_db, init_worktrail_dir
from worktrail.core.models import Checkpoint, Config, Session, Task
from worktrail.core.repository import Repository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory for isolated tests."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def temp_db(tmp_dir: Path) -> Generator[Path, None, None]:
    """Create an initialised database file in a temp directory."""
    db_path = tmp_dir / "runtime.db"
    init_db(db_path)
    yield db_path


@pytest.fixture
def temp_project(tmp_dir: Path) -> Generator[Path, None, None]:
    """Create a full .worktrail project directory in a temp directory."""
    # Create a fake git repo root so find_project_root(".git") works
    (tmp_dir / ".git").mkdir()
    init_worktrail_dir(tmp_dir)
    yield tmp_dir


@pytest.fixture
def repo(temp_db: Path) -> Repository:
    """Provide a Repository backed by a temp database."""
    return Repository(temp_db)


# ---------------------------------------------------------------------------
# db.py tests
# ---------------------------------------------------------------------------


class TestInitDb:
    def test_init_db_creates_all_tables(self, tmp_dir: Path) -> None:
        """init_db should create tasks, sessions, checkpoints, config tables."""
        db_path = tmp_dir / "runtime.db"
        init_db(db_path)

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = {row[0] for row in cursor.fetchall()}

        assert "tasks" in tables
        assert "sessions" in tables
        assert "checkpoints" in tables
        assert "config" in tables

    def test_init_db_is_idempotent(self, tmp_dir: Path) -> None:
        """Calling init_db twice on the same file should not raise."""
        db_path = tmp_dir / "runtime.db"
        init_db(db_path)
        init_db(db_path)  # should not raise

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM tasks")
            assert cursor.fetchone()[0] == 0


class TestInitWorktrailDir:
    def test_creates_directory_structure(self, tmp_dir: Path) -> None:
        """init_worktrail_dir creates .worktrail/, runtime.db, config.yaml, reports/, hooks/."""
        project_root = tmp_dir / "myproject"
        project_root.mkdir()
        wt_dir = init_worktrail_dir(project_root)

        assert wt_dir == project_root / ".worktrail"
        assert wt_dir.is_dir()
        assert (wt_dir / "runtime.db").exists()
        assert (wt_dir / "config.yaml").exists()
        assert (wt_dir / "reports").is_dir()
        assert (wt_dir / "hooks").is_dir()

    def test_returns_worktrail_dir_path(self, tmp_dir: Path) -> None:
        """The function returns the path to the .worktrail directory."""
        wt_dir = init_worktrail_dir(tmp_dir)
        assert isinstance(wt_dir, Path)
        assert wt_dir.name == ".worktrail"

    def test_config_yaml_has_defaults(self, tmp_dir: Path) -> None:
        """config.yaml should be created with default values."""
        init_worktrail_dir(tmp_dir)
        config_text = (tmp_dir / ".worktrail" / "config.yaml").read_text()
        assert "idle_timeout" in config_text
        assert "git_hooks_enabled" in config_text


class TestGetDbPath:
    def test_finds_worktrail_dir_walking_up(self, tmp_dir: Path) -> None:
        """get_db_path walks upward from cwd to find .worktrail/runtime.db."""
        project_root = tmp_dir / "repo"
        project_root.mkdir()
        (project_root / ".git").mkdir()
        init_worktrail_dir(project_root)

        sub_dir = project_root / "src" / "nested"
        sub_dir.mkdir(parents=True)

        found = get_db_path(cwd=sub_dir)
        assert found == (project_root / ".worktrail" / "runtime.db").resolve()

    def test_raises_when_no_worktrail(self, tmp_dir: Path) -> None:
        """get_db_path raises FileNotFoundError when .worktrail does not exist."""
        with pytest.raises(FileNotFoundError):
            get_db_path(cwd=tmp_dir)


class TestGetConnection:
    def test_yields_sqlite_connection(self, tmp_dir: Path) -> None:
        """get_connection yields a sqlite3.Connection with row_factory set."""
        db_path = tmp_dir / "test.db"
        init_db(db_path)

        with get_connection(db_path) as conn:
            assert isinstance(conn, sqlite3.Connection)
            assert conn.row_factory is sqlite3.Row

    def test_connection_is_closed_after_context(self, tmp_dir: Path) -> None:
        """Connection is closed after exiting the context manager."""
        db_path = tmp_dir / "test.db"
        init_db(db_path)

        conn_ref: sqlite3.Connection | None = None
        with get_connection(db_path) as conn:
            conn_ref = conn
            # connection should be open inside context
            conn.execute("SELECT 1")

        # After context exit, connection should be closed
        with pytest.raises(sqlite3.ProgrammingError):
            conn_ref.execute("SELECT 1")

    def test_connection_executes_queries(self, tmp_dir: Path) -> None:
        """Queries can be executed inside the connection context."""
        db_path = tmp_dir / "test.db"
        init_db(db_path)

        with get_connection(db_path) as conn:
            row = conn.execute("SELECT 42 AS answer").fetchone()
            assert row["answer"] == 42


# ---------------------------------------------------------------------------
# models.py tests
# ---------------------------------------------------------------------------


class TestTask:
    def test_instantiation_with_defaults(self) -> None:
        """Task can be instantiated with default values."""
        task = Task(id="TASK-001", name="Test Task")
        assert task.id == "TASK-001"
        assert task.name == "Test Task"
        assert task.status == "active"
        assert task.parent_id is None

    def test_default_status_is_active(self) -> None:
        """Default status should be 'active'."""
        task = Task(id="TASK-002", name="Another Task")
        assert task.status == "active"

    def test_created_at_is_iso8601(self) -> None:
        """created_at should be a valid ISO8601 string."""
        task = Task(id="TASK-003", name="Time Test")
        # Should be parseable as datetime
        dt = datetime.fromisoformat(task.created_at)
        assert dt.tzinfo is not None

    def test_custom_values(self) -> None:
        """Task accepts all field values explicitly."""
        now = datetime.now(timezone.utc).isoformat()
        task = Task(
            id="TASK-004",
            name="Custom",
            status="done",
            created_at=now,
            updated_at=now,
            parent_id="TASK-001",
        )
        assert task.status == "done"
        assert task.parent_id == "TASK-001"
        assert task.created_at == now


class TestSession:
    def test_instantiation_with_defaults(self) -> None:
        """Session can be instantiated with default values."""
        session = Session(task_id="TASK-001")
        assert session.task_id == "TASK-001"
        assert session.status == "active"
        assert session.total_seconds == 0
        assert session.ended_at is None
        assert session.id is None

    def test_started_at_is_iso8601(self) -> None:
        """started_at should be a valid ISO8601 string."""
        session = Session(task_id="TASK-002")
        dt = datetime.fromisoformat(session.started_at)
        assert dt.tzinfo is not None

    def test_custom_values(self) -> None:
        """Session accepts explicit values for all fields."""
        now = datetime.now(timezone.utc).isoformat()
        session = Session(
            task_id="TASK-003",
            started_at=now,
            ended_at=now,
            status="ended",
            total_seconds=3600,
            id=42,
        )
        assert session.status == "ended"
        assert session.total_seconds == 3600
        assert session.id == 42
        assert session.ended_at == now


class TestCheckpoint:
    def test_instantiation_with_defaults(self) -> None:
        """Checkpoint can be instantiated with default values."""
        cp = Checkpoint(session_id=1, message="First checkpoint")
        assert cp.session_id == 1
        assert cp.message == "First checkpoint"
        assert cp.source == "manual"
        assert cp.commit_hash is None
        assert cp.id is None

    def test_timestamp_is_iso8601(self) -> None:
        """timestamp should be a valid ISO8601 string."""
        cp = Checkpoint(session_id=1, message="Time check")
        dt = datetime.fromisoformat(cp.timestamp)
        assert dt.tzinfo is not None

    def test_custom_values(self) -> None:
        """Checkpoint accepts explicit values for all fields."""
        now = datetime.now(timezone.utc).isoformat()
        cp = Checkpoint(
            session_id=2,
            message="Git commit",
            timestamp=now,
            source="git-hook",
            commit_hash="abc123",
            id=5,
        )
        assert cp.source == "git-hook"
        assert cp.commit_hash == "abc123"
        assert cp.id == 5


class TestConfigModel:
    def test_default_values(self) -> None:
        """Config has correct default values."""
        cfg = Config()
        assert cfg.idle_timeout == 900
        assert cfg.git_hooks_enabled is True

    def test_custom_values(self) -> None:
        """Config accepts explicit values."""
        cfg = Config(idle_timeout=300, git_hooks_enabled=False)
        assert cfg.idle_timeout == 300
        assert cfg.git_hooks_enabled is False


class TestNowUtc:
    def test_returns_iso8601_utc_string(self) -> None:
        """The default factory for datetime fields returns an ISO8601 UTC string."""
        now_str = datetime.now(timezone.utc).isoformat()
        # Verify it's a valid ISO8601 string with timezone info
        dt = datetime.fromisoformat(now_str)
        assert dt.tzinfo is not None
        # Should end with '+00:00' for UTC
        assert now_str.endswith("+00:00")


# ---------------------------------------------------------------------------
# repository.py tests
# ---------------------------------------------------------------------------


class TestCreateTask:
    def test_create_and_get_task_roundtrip(self, repo: Repository) -> None:
        """create_task returns a Task; get_task retrieves it."""
        created = repo.create_task("TASK-001", "My First Task")
        fetched = repo.get_task("TASK-001")
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.name == "My First Task"
        assert fetched.status == "active"

    def test_create_task_with_parent(self, repo: Repository) -> None:
        """create_task with parent_id stores the parent reference."""
        repo.create_task("PARENT-001", "Parent Task")
        child = repo.create_task("CHILD-001", "Child Task", parent_id="PARENT-001")
        assert child.parent_id == "PARENT-001"
        fetched = repo.get_task("CHILD-001")
        assert fetched is not None
        assert fetched.parent_id == "PARENT-001"

    def test_get_task_returns_none_for_missing(self, repo: Repository) -> None:
        """get_task returns None when the task does not exist."""
        assert repo.get_task("NONEXISTENT") is None


class TestUpdateTaskStatus:
    def test_update_changes_status(self, repo: Repository) -> None:
        """update_task_status changes the task's status."""
        repo.create_task("TASK-002", "Status Test")
        result = repo.update_task_status("TASK-002", "done")
        assert result is True
        task = repo.get_task("TASK-002")
        assert task is not None
        assert task.status == "done"

    def test_update_returns_false_for_missing_task(self, repo: Repository) -> None:
        """update_task_status returns False when task does not exist."""
        result = repo.update_task_status("NONEXISTENT", "done")
        assert result is False

    def test_update_updates_updated_at(self, repo: Repository) -> None:
        """update_task_status also updates the updated_at timestamp."""
        repo.create_task("TASK-003", "Time Update Test")
        before = repo.get_task("TASK-003")
        assert before is not None
        repo.update_task_status("TASK-003", "paused")
        after = repo.get_task("TASK-003")
        assert after is not None
        assert after.updated_at != before.updated_at


class TestListTasks:
    def test_list_tasks_returns_all(self, repo: Repository) -> None:
        """list_tasks returns all created tasks."""
        repo.create_task("A-001", "Task A")
        repo.create_task("B-002", "Task B")
        repo.create_task("C-003", "Task C")
        tasks = repo.list_tasks()
        assert len(tasks) == 3
        ids = {t.id for t in tasks}
        assert ids == {"A-001", "B-002", "C-003"}

    def test_list_tasks_empty(self, repo: Repository) -> None:
        """list_tasks returns empty list when no tasks exist."""
        assert repo.list_tasks() == []

    def test_list_tasks_filters_by_status(self, repo: Repository) -> None:
        """list_tasks(status=...) filters to matching status only."""
        repo.create_task("T-001", "Active Task")
        repo.create_task("T-002", "Done Task")
        repo.update_task_status("T-002", "done")

        active = repo.list_tasks(status="active")
        done = repo.list_tasks(status="done")

        assert len(active) == 1
        assert active[0].id == "T-001"
        assert len(done) == 1
        assert done[0].id == "T-002"

    def test_list_tasks_no_match(self, repo: Repository) -> None:
        """list_tasks(status=...) returns empty list when no tasks match."""
        repo.create_task("T-001", "A Task")
        assert repo.list_tasks(status="archived") == []

    def test_list_active_tasks(self, repo: Repository) -> None:
        """list_active_tasks is a convenience wrapper for status='active'."""
        repo.create_task("T-001", "Active")
        repo.create_task("T-002", "Done")
        repo.update_task_status("T-002", "done")
        active = repo.list_active_tasks()
        assert len(active) == 1
        assert active[0].id == "T-001"


class TestCreateSession:
    def test_create_and_get_active_session_roundtrip(self, repo: Repository) -> None:
        """create_session returns a Session; get_active_session retrieves it."""
        repo.create_task("TASK-S1", "Session Test")
        session = repo.create_session("TASK-S1")
        assert session.task_id == "TASK-S1"
        assert session.status == "active"
        assert session.total_seconds == 0
        assert session.id is not None

        active = repo.get_active_session()
        assert active is not None
        assert active.id == session.id

    def test_get_active_session_returns_none_when_none_active(self, repo: Repository) -> None:
        """get_active_session returns None when no session is active."""
        assert repo.get_active_session() is None

    def test_get_active_session_returns_most_recent(self, repo: Repository) -> None:
        """get_active_session returns the most recently created active session."""
        repo.create_task("TASK-S2", "Multi Session")
        s1 = repo.create_session("TASK-S2")
        s2 = repo.create_session("TASK-S2")
        active = repo.get_active_session()
        assert active is not None
        assert active.id == s2.id  # most recent


class TestEndSession:
    def test_end_session_sets_status_and_ended_at(self, repo: Repository) -> None:
        """end_session changes status to 'ended' and sets ended_at."""
        repo.create_task("TASK-E1", "End Test")
        session = repo.create_session("TASK-E1")
        result = repo.end_session(session.id)
        assert result is True

        fetched = repo.get_session(session.id)
        assert fetched is not None
        assert fetched.status == "ended"
        assert fetched.ended_at is not None

    def test_end_session_returns_false_for_missing(self, repo: Repository) -> None:
        """end_session returns False for nonexistent session."""
        assert repo.end_session(99999) is False


class TestPauseResumeSession:
    def test_pause_session(self, repo: Repository) -> None:
        """pause_session changes status to 'paused'."""
        repo.create_task("TASK-PR1", "Pause Resume")
        session = repo.create_session("TASK-PR1")
        result = repo.pause_session(session.id)
        assert result is True
        fetched = repo.get_session(session.id)
        assert fetched is not None
        assert fetched.status == "paused"

    def test_resume_session(self, repo: Repository) -> None:
        """resume_session changes status back to 'active'."""
        repo.create_task("TASK-PR2", "Pause Resume 2")
        session = repo.create_session("TASK-PR2")
        repo.pause_session(session.id)
        result = repo.resume_session(session.id)
        assert result is True
        fetched = repo.get_session(session.id)
        assert fetched is not None
        assert fetched.status == "active"

    def test_pause_returns_false_for_missing(self, repo: Repository) -> None:
        """pause_session returns False for nonexistent session."""
        assert repo.pause_session(99999) is False

    def test_resume_returns_false_for_missing(self, repo: Repository) -> None:
        """resume_session returns False for nonexistent session."""
        assert repo.resume_session(99999) is False


class TestUpdateSessionDuration:
    def test_update_duration(self, repo: Repository) -> None:
        """update_session_duration sets total_seconds."""
        repo.create_task("TASK-D1", "Duration Test")
        session = repo.create_session("TASK-D1")
        result = repo.update_session_duration(session.id, 3600)
        assert result is True
        fetched = repo.get_session(session.id)
        assert fetched is not None
        assert fetched.total_seconds == 3600

    def test_update_duration_returns_false_for_missing(self, repo: Repository) -> None:
        """update_session_duration returns False for nonexistent session."""
        assert repo.update_session_duration(99999, 100) is False


class TestCheckpoints:
    def test_add_checkpoint_and_get_for_session(self, repo: Repository) -> None:
        """add_checkpoint creates a checkpoint; get_checkpoints_for_session retrieves it."""
        repo.create_task("TASK-CP1", "Checkpoint Test")
        session = repo.create_session("TASK-CP1")
        cp = repo.add_checkpoint(session.id, "Milestone 1")
        assert cp.session_id == session.id
        assert cp.message == "Milestone 1"
        assert cp.source == "manual"
        assert cp.id is not None

        checkpoints = repo.get_checkpoints_for_session(session.id)
        assert len(checkpoints) == 1
        assert checkpoints[0].message == "Milestone 1"

    def test_add_checkpoint_with_git_hook(self, repo: Repository) -> None:
        """add_checkpoint with git-hook source and commit_hash."""
        repo.create_task("TASK-CP2", "Git Checkpoint")
        session = repo.create_session("TASK-CP2")
        cp = repo.add_checkpoint(
            session.id,
            "Commit made",
            source="git-hook",
            commit_hash="deadbeef",
        )
        assert cp.source == "git-hook"
        assert cp.commit_hash == "deadbeef"

        checkpoints = repo.get_checkpoints_for_session(session.id)
        assert len(checkpoints) == 1
        assert checkpoints[0].commit_hash == "deadbeef"

    def test_get_checkpoints_for_session_empty(self, repo: Repository) -> None:
        """get_checkpoints_for_session returns empty list when none exist."""
        repo.create_task("TASK-CP3", "No Checkpoints")
        session = repo.create_session("TASK-CP3")
        assert repo.get_checkpoints_for_session(session.id) == []

    def test_get_checkpoints_for_session_order(self, repo: Repository) -> None:
        """get_checkpoints_for_session returns checkpoints ordered by timestamp."""
        repo.create_task("TASK-CP4", "Ordered Checkpoints")
        session = repo.create_session("TASK-CP4")
        from datetime import datetime, timezone

        t1 = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc).isoformat()
        t2 = datetime(2025, 1, 1, 11, 0, 0, tzinfo=timezone.utc).isoformat()
        t3 = datetime(2025, 1, 1, 9, 0, 0, tzinfo=timezone.utc).isoformat()

        with repo.conn() as conn:
            conn.execute(
                "INSERT INTO checkpoints (session_id, message, timestamp, source) VALUES (?, ?, ?, ?)",
                (session.id, "Second", t2, "manual"),
            )
            conn.execute(
                "INSERT INTO checkpoints (session_id, message, timestamp, source) VALUES (?, ?, ?, ?)",
                (session.id, "First", t1, "manual"),
            )
            conn.execute(
                "INSERT INTO checkpoints (session_id, message, timestamp, source) VALUES (?, ?, ?, ?)",
                (session.id, "Third", t3, "manual"),
            )
            conn.commit()

        checkpoints = repo.get_checkpoints_for_session(session.id)
        messages = [c.message for c in checkpoints]
        # Timestamps: t3=09:00, t1=10:00, t2=11:00 — ordered ascending
        assert messages == ["Third", "First", "Second"]  # ordered by timestamp

    def test_get_checkpoints_for_task(self, repo: Repository) -> None:
        """get_checkpoints_for_task returns checkpoints across all sessions for a task."""
        repo.create_task("TASK-CP5", "Task Checkpoints")
        s1 = repo.create_session("TASK-CP5")
        s2 = repo.create_session("TASK-CP5")

        cp1 = repo.add_checkpoint(s1.id, "Session 1 CP")
        cp2 = repo.add_checkpoint(s2.id, "Session 2 CP")

        checkpoints = repo.get_checkpoints_for_task("TASK-CP5")
        assert len(checkpoints) == 2
        messages = {c.message for c in checkpoints}
        assert messages == {"Session 1 CP", "Session 2 CP"}

    def test_get_checkpoints_for_task_empty(self, repo: Repository) -> None:
        """get_checkpoints_for_task returns empty list when task has no checkpoints."""
        repo.create_task("TASK-CP6", "No CPs")
        assert repo.get_checkpoints_for_task("TASK-CP6") == []

    def test_multiple_sessions_aggregate(self, repo: Repository) -> None:
        """Multiple sessions for the same task aggregate checkpoints correctly."""
        repo.create_task("TASK-AGG", "Aggregate")
        for _ in range(3):
            s = repo.create_session("TASK-AGG")
            repo.add_checkpoint(s.id, f"CP for session {s.id}")

        checkpoints = repo.get_checkpoints_for_task("TASK-AGG")
        assert len(checkpoints) == 3


# ---------------------------------------------------------------------------
# Config repository tests
# ---------------------------------------------------------------------------


class TestRepositoryConfig:
    def test_get_config_returns_default(self, repo: Repository) -> None:
        """get_config returns the default when key does not exist."""
        val = repo.get_config("nonexistent_key", default="fallback")
        assert val == "fallback"

    def test_get_config_returns_none_without_default(self, repo: Repository) -> None:
        """get_config returns None when key does not exist and no default."""
        assert repo.get_config("nonexistent_key") is None

    def test_set_and_get_config_roundtrip(self, repo: Repository) -> None:
        """set_config stores a value; get_config retrieves it."""
        repo.set_config("theme", "dark")
        assert repo.get_config("theme") == "dark"

    def test_set_config_overwrites(self, repo: Repository) -> None:
        """set_config overwrites an existing key."""
        repo.set_config("theme", "dark")
        repo.set_config("theme", "light")
        assert repo.get_config("theme") == "light"

    def test_get_config_int(self, repo: Repository) -> None:
        """get_config_int returns integer value."""
        repo.set_config("timeout", "300")
        assert repo.get_config_int("timeout") == 300

    def test_get_config_int_default(self, repo: Repository) -> None:
        """get_config_int returns default when key missing."""
        assert repo.get_config_int("missing_key", default=42) == 42

    def test_get_config_int_default_zero(self, repo: Repository) -> None:
        """get_config_int returns 0 as default when not specified."""
        assert repo.get_config_int("missing_key") == 0

    def test_get_config_int_invalid_returns_default(self, repo: Repository) -> None:
        """get_config_int returns default when value is not a valid integer."""
        repo.set_config("bad_int", "not_a_number")
        assert repo.get_config_int("bad_int", default=99) == 99

    def test_get_config_bool_true_values(self, repo: Repository) -> None:
        """get_config_bool recognises truthy values."""
        for val in ("true", "True", "TRUE", "1", "yes", "Yes"):
            repo.set_config("flag", val)
            assert repo.get_config_bool("flag") is True, f"Failed for value: {val}"

    def test_get_config_bool_false_values(self, repo: Repository) -> None:
        """get_config_bool recognises falsy values."""
        for val in ("false", "False", "FALSE", "0", "no", "No", ""):
            repo.set_config("flag", val)
            assert repo.get_config_bool("flag") is False, f"Failed for value: {val}"

    def test_get_config_bool_default(self, repo: Repository) -> None:
        """get_config_bool returns default when key missing."""
        assert repo.get_config_bool("missing_flag", default=True) is True
        assert repo.get_config_bool("missing_flag", default=False) is False


# ---------------------------------------------------------------------------
# config.py tests
# ---------------------------------------------------------------------------


class TestConfigModule:
    def test_get_config_path_finds_yaml(self, tmp_dir: Path) -> None:
        """get_config_path walks up to find .worktrail/config.yaml."""
        project_root = tmp_dir / "repo"
        project_root.mkdir()
        init_worktrail_dir(project_root)

        sub_dir = project_root / "src" / "deep"
        sub_dir.mkdir(parents=True)

        found = get_config_path(cwd=sub_dir)
        assert found == (project_root / ".worktrail" / "config.yaml").resolve()

    def test_get_config_path_raises_when_missing(self, tmp_dir: Path) -> None:
        """get_config_path raises FileNotFoundError when config.yaml not found."""
        with pytest.raises(FileNotFoundError):
            get_config_path(cwd=tmp_dir)

    def test_load_config_returns_defaults(self, tmp_dir: Path) -> None:
        """load_config merges with defaults."""
        project_root = tmp_dir / "repo"
        project_root.mkdir()
        init_worktrail_dir(project_root)
        config = load_config(project_root / ".worktrail" / "config.yaml")
        assert config["idle_timeout"] == 900
        assert config["git_hooks_enabled"] is True

    def test_load_config_reads_custom_values(self, tmp_dir: Path) -> None:
        """load_config reads custom values from YAML."""
        config_path = tmp_dir / "custom_config.yaml"
        config_path.write_text("idle_timeout: 600\ngit_hooks_enabled: false\n")
        config = load_config(config_path)
        assert config["idle_timeout"] == 600
        assert config["git_hooks_enabled"] is False

    def test_save_config(self, tmp_dir: Path) -> None:
        """save_config writes a dictionary to YAML."""
        config_path = tmp_dir / "saved_config.yaml"
        save_config({"idle_timeout": 1200, "git_hooks_enabled": False}, config_path)
        loaded = load_config(config_path)
        assert loaded["idle_timeout"] == 1200
        assert loaded["git_hooks_enabled"] is False

    def test_save_and_load_roundtrip(self, tmp_dir: Path) -> None:
        """save_config followed by load_config roundtrips correctly."""
        config_path = tmp_dir / "roundtrip.yaml"
        original = {"idle_timeout": 777, "git_hooks_enabled": True, "custom_key": "hello"}
        save_config(original, config_path)
        loaded = load_config(config_path)
        assert loaded["idle_timeout"] == 777
        assert loaded["git_hooks_enabled"] is True
        assert loaded["custom_key"] == "hello"
