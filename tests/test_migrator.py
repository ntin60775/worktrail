"""Comprehensive pytest tests for worktrail.migrator module.

Tests cover:
  - parser.py: parse_v1_task, parse_v1_worklog, _parse_frontmatter
  - migrator.py: Migrator, MigrationReport, get_merge_instructions
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Generator, List
from unittest.mock import MagicMock, patch

import pytest

from worktrail.migrator import Migrator, MigrationReport, parse_v1_task, parse_v1_worklog
from worktrail.migrator.parser import (
    _coerce_date,
    _extract_name_from_content,
    _extract_task_id_from_path,
    _normalise_status,
    _parse_duration,
    _parse_frontmatter,
    _parse_table,
    _parse_worklog_narrative,
    _VALID_ID_RE,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def fake_project() -> Generator[Path, None, None]:
    """Create a temporary directory with a valid knowledge/tasks structure."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Create a valid knowledge/ structure
        tasks_dir = root / "knowledge" / "tasks"
        task_dir = tasks_dir / "TASK-001-sample"
        task_dir.mkdir(parents=True)
        task_md = task_dir / "task.md"
        task_md.write_text(
            "---\n"
            "id: TASK-001\n"
            "name: Sample Task\n"
            "status: active\n"
            "created_at: 2024-01-15\n"
            "branch: feature/sample\n"
            "---\n\n"
            "# Sample Task\n\n"
            "Description here.\n",
            encoding="utf-8",
        )
        yield root


@pytest.fixture
def fake_project_with_worklog() -> Generator[Path, None, None]:
    """Create a temporary directory with task.md and worklog.md."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tasks_dir = root / "knowledge" / "tasks"
        task_dir = tasks_dir / "TASK-002-logged"
        task_dir.mkdir(parents=True)
        # task.md
        task_md = task_dir / "task.md"
        task_md.write_text(
            "---\n"
            "id: TASK-002\n"
            "name: Logged Task\n"
            "status: done\n"
            "---\n\n"
            "# Logged Task\n",
            encoding="utf-8",
        )
        # worklog.md
        worklog_md = task_dir / "worklog.md"
        worklog_md.write_text(
            "# Worklog\n\n"
            "2024-03-10: Initial implementation [2h]\n"
            "2024-03-10: Testing and bug fixes [1h]\n"
            "2024-03-11 — Code review [30m]\n"
            "2024-03-12: Deployment\n",
            encoding="utf-8",
        )
        yield root


# ============================================================================
# parse_v1_task — frontmatter extraction
# ============================================================================


class TestParseV1TaskFrontmatter:
    """Tests for parse_v1_task extracting id, name, status from frontmatter."""

    def test_extracts_id_name_status_from_frontmatter(self, fake_project: Path) -> None:
        """parse_v1_task extracts id, name, status from YAML frontmatter."""
        task_md = fake_project / "knowledge" / "tasks" / "TASK-001-sample" / "task.md"
        result = parse_v1_task(task_md)

        assert result["id"] == "TASK-001"
        assert result["name"] == "Sample Task"
        assert result["status"] == "active"
        assert result["branch"] == "feature/sample"
        assert result["parent_id"] is None
        assert "created_at" in result
        assert "raw" in result

    def test_task_without_frontmatter_uses_table(self) -> None:
        """parse_v1_task handles task.md without frontmatter, falls back to table."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_dir = root / "knowledge" / "tasks" / "TASK-003-no-fm"
            task_dir.mkdir(parents=True)
            task_md = task_dir / "task.md"
            task_md.write_text(
                "# My Table Task\n\n"
                "| Key   | Value        |\n"
                "|-------|------------- |\n"
                "| id    | TASK-003     |\n"
                "| name  | Table Task   |\n"
                "| status| paused       |\n"
                "| branch| feature/tab  |\n",
                encoding="utf-8",
            )
            result = parse_v1_task(task_md)

        assert result["id"] == "TASK-003"
        assert result["name"] == "Table Task"
        assert result["status"] == "blocked"
        assert result["branch"] == "feature/tab"

    def test_task_without_frontmatter_uses_heading(self) -> None:
        """parse_v1_task without frontmatter/table extracts name from H1 heading."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_dir = root / "knowledge" / "tasks" / "TASK-004-heading"
            task_dir.mkdir(parents=True)
            task_md = task_dir / "task.md"
            task_md.write_text(
                "# Heading Task Name\n\n"
                "Some description without any frontmatter or table.\n",
                encoding="utf-8",
            )
            result = parse_v1_task(task_md)

        assert result["id"] == "TASK-004"
        assert result["name"] == "Heading Task Name"

    def test_missing_file_raises_file_not_found(self) -> None:
        """parse_v1_task raises FileNotFoundError for a missing file."""
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nonexistent" / "task.md"
        with pytest.raises(FileNotFoundError):
            parse_v1_task(missing)


# ============================================================================
# parse_v1_task — Russian status handling
# ============================================================================


class TestParseV1TaskRussianStatus:
    """Tests for parse_v1_task handling Russian status names."""

    @pytest.mark.parametrize(
        "russian_status, expected",
        [
            ("в работе", "active"),
            ("активна", "active"),
            ("активный", "active"),
            ("начата", "active"),
            ("пауза", "blocked"),
            ("приостановлена", "blocked"),
            ("завершена", "done"),
            ("готово", "done"),
            ("выполнена", "done"),
            ("закрыта", "done"),
            ("архив", "archived"),
            ("в архиве", "archived"),
        ],
    )
    def test_russian_status_names(self, russian_status: str, expected: str) -> None:
        """parse_v1_task normalises Russian status to canonical values."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_dir = root / "knowledge" / "tasks" / "TASK-005-russian"
            task_dir.mkdir(parents=True)
            task_md = task_dir / "task.md"
            task_md.write_text(
                f"---\n"
                f"id: TASK-005\n"
                f"name: Russian Task\n"
                f"status: {russian_status}\n"
                f"---\n\n"
                f"# Russian Task\n",
                encoding="utf-8",
            )
            result = parse_v1_task(task_md)

        assert result["status"] == expected

# ============================================================================
# parse_v1_worklog
# ============================================================================


class TestParseV1Worklog:
    """Tests for parse_v1_worklog extracting dated entries."""

    def test_extracts_dated_entries(self, fake_project_with_worklog: Path) -> None:
        """parse_v1_worklog extracts dated entries with messages and durations."""
        worklog_md = (
            fake_project_with_worklog
            / "knowledge"
            / "tasks"
            / "TASK-002-logged"
            / "worklog.md"
        )
        entries = parse_v1_worklog(worklog_md)

        assert len(entries) == 4

        # Check first entry
        assert entries[0]["date"] == "2024-03-10"
        assert entries[0]["message"] == "Initial implementation"
        assert entries[0]["duration_minutes"] == 120

        # Check second entry (same date)
        assert entries[1]["date"] == "2024-03-10"
        assert entries[1]["message"] == "Testing and bug fixes"
        assert entries[1]["duration_minutes"] == 60

        # Check third entry (em dash separator)
        assert entries[2]["date"] == "2024-03-11"
        assert entries[2]["message"] == "Code review"
        assert entries[2]["duration_minutes"] == 30

        # Check fourth entry (no duration)
        assert entries[3]["date"] == "2024-03-12"
        assert entries[3]["message"] == "Deployment"
        assert entries[3]["duration_minutes"] is None

    def test_missing_file_returns_empty_list(self) -> None:
        """parse_v1_worklog returns an empty list for a missing file."""
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "no_worklog.md"
        result = parse_v1_worklog(missing)
        assert result == []

    def test_empty_file_returns_empty_list(self) -> None:
        """parse_v1_worklog returns an empty list for an empty file."""
        with tempfile.TemporaryDirectory() as tmp:
            empty_file = Path(tmp) / "empty_worklog.md"
            empty_file.write_text("\n", encoding="utf-8")
        result = parse_v1_worklog(empty_file)
        assert result == []

    def test_russian_duration_formats(self) -> None:
        """parse_v1_worklog handles Russian duration formats like [2 ч], [30 мин]."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worklog = root / "worklog.md"
            worklog.write_text(
                "2024-04-01: Meeting [2 ч]\n"
                "2024-04-01: Standup [30 мин]\n",
                encoding="utf-8",
            )
            entries = parse_v1_worklog(worklog)

        assert len(entries) == 2
        assert entries[0]["duration_minutes"] == 120
        assert entries[0]["message"] == "Meeting"
        assert entries[1]["duration_minutes"] == 30
        assert entries[1]["message"] == "Standup"


# ============================================================================
# _parse_frontmatter
# ============================================================================


class TestParseFrontmatter:
    """Tests for _parse_frontmatter with and without PyYAML."""

    def test_frontmatter_with_yaml_available(self) -> None:
        """Frontmatter parsing with PyYAML available returns correct dict."""
        content = (
            "---\n"
            "id: TASK-100\n"
            "name: YAML Task\n"
            "status: active\n"
            "nested:\n"
            "  key: value\n"
            "---\n\n"
            "# Heading\n"
        )
        result = _parse_frontmatter(content)

        assert result is not None
        assert result["id"] == "TASK-100"
        assert result["name"] == "YAML Task"
        assert result["status"] == "active"
        assert result["nested"] == {"key": "value"}

    def test_frontmatter_no_frontmatter_returns_none(self) -> None:
        """_parse_frontmatter returns None when no frontmatter delimiters present."""
        content = "# Just a heading\n\nSome text.\n"
        result = _parse_frontmatter(content)
        assert result is None

    def test_frontmatter_fallback_without_yaml(self) -> None:
        """Frontmatter fallback parsing works without PyYAML (basic key:value)."""
        content = (
            "---\n"
            "id: TASK-200\n"
            "name: Fallback Task\n"
            "active: true\n"
            "count: 42\n"
            "---\n\n"
            "# Heading\n"
        )
        # Patch yaml to None to simulate PyYAML not being installed
        import worktrail.migrator.parser as parser_module

        with patch.object(parser_module, "yaml", None):
            result = _parse_frontmatter(content)

        assert result is not None
        assert result["id"] == "TASK-200"
        assert result["name"] == "Fallback Task"
        assert result["active"] is True
        assert result["count"] == 42

    def test_frontmatter_fallback_skips_comments(self) -> None:
        """Fallback parser skips lines starting with #."""
        content = (
            "---\n"
            "# This is a comment\n"
            "id: TASK-300\n"
            "---\n\n"
            "# Heading\n"
        )
        import worktrail.migrator.parser as parser_module

        with patch.object(parser_module, "yaml", None):
            result = _parse_frontmatter(content)

        assert result is not None
        assert "id" in result
        assert "# This is a comment" not in result.keys()

    def test_frontmatter_fallback_strips_quotes(self) -> None:
        """Fallback parser strips surrounding quotes from values."""
        content = (
            '---\n'
            'id: "TASK-400"\n'
            "name: 'Quoted Task'\n"
            '---\n\n'
            '# Heading\n'
        )
        import worktrail.migrator.parser as parser_module

        with patch.object(parser_module, "yaml", None):
            result = _parse_frontmatter(content)

        assert result is not None
        assert result["id"] == "TASK-400"
        assert result["name"] == "Quoted Task"


# ============================================================================
# Migrator.validate_source
# ============================================================================


class TestMigratorValidateSource:
    """Tests for Migrator.validate_source."""

    def test_valid_knowledge_structure(self, fake_project: Path) -> None:
        """validate_source returns True for a valid knowledge/ structure."""
        migrator = Migrator(
            source_knowledge_path=fake_project / "knowledge",
            project_root=fake_project,
        )
        assert migrator.validate_source() is True

    def test_invalid_path(self) -> None:
        """validate_source returns False for an invalid path."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
        migrator = Migrator(
            source_knowledge_path=root / "nonexistent" / "knowledge",
            project_root=root,
        )
        assert migrator.validate_source() is False

    def test_no_task_md_files(self) -> None:
        """validate_source returns False when no TASK-*/task.md files exist."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Create empty tasks directory
            (root / "knowledge" / "tasks").mkdir(parents=True)
            # Create a directory but no task.md inside
            (root / "knowledge" / "tasks" / "TASK-999-empty").mkdir(parents=True)

        migrator = Migrator(
            source_knowledge_path=root / "knowledge",
            project_root=root,
        )
        assert migrator.validate_source() is False


# ============================================================================
# MigrationReport dataclass
# ============================================================================


class TestMigrationReport:
    """Tests for MigrationReport dataclass fields and methods."""

    def test_default_fields(self) -> None:
        """MigrationReport has correct default field values."""
        report = MigrationReport()
        assert report.tasks_migrated == 0
        assert report.sessions_created == 0
        assert report.checkpoints_created == 0
        assert report.migration_branch == "worktrail/migrate-v1"
        assert report.merge_command == "git checkout main && git merge worktrail/migrate-v1 --no-ff"
        assert report.migration_commit_hash is None
        assert report.task_mapping == []
        assert report.errors == []

    def test_custom_fields(self) -> None:
        """MigrationReport accepts custom field values."""
        report = MigrationReport(
            tasks_migrated=5,
            sessions_created=3,
            checkpoints_created=12,
            migration_branch="custom/branch",
            migration_commit_hash="abc123",
            task_mapping=[
                {"old_id": "TASK-001", "name": "Task One", "new_status": "active"},
            ],
            errors=["Some warning"],
        )
        assert report.tasks_migrated == 5
        assert report.sessions_created == 3
        assert report.checkpoints_created == 12
        assert report.migration_branch == "custom/branch"
        assert report.migration_commit_hash == "abc123"
        assert len(report.task_mapping) == 1
        assert report.errors == ["Some warning"]

    def test_to_markdown_contains_stats(self) -> None:
        """to_markdown includes migration statistics."""
        report = MigrationReport(
            tasks_migrated=2,
            sessions_created=1,
            checkpoints_created=4,
        )
        md = report.to_markdown()
        assert "2" in md  # tasks_migrated count
        assert "1" in md  # sessions_created count
        assert "4" in md  # checkpoints_created count

    def test_str_representation(self) -> None:
        """__str__ produces a readable representation."""
        report = MigrationReport(tasks_migrated=1)
        text = str(report)
        assert "MigrationReport" in text
        assert "tasks_migrated=1" in text


# ============================================================================
# Migrator.get_merge_instructions
# ============================================================================


class TestGetMergeInstructions:
    """Tests for Migrator.get_merge_instructions."""

    def test_returns_string_with_git_commands(self, fake_project: Path) -> None:
        """get_merge_instructions returns a string containing git commands."""
        migrator = Migrator(
            source_knowledge_path=fake_project / "knowledge",
            project_root=fake_project,
        )
        instructions = migrator.get_merge_instructions()

        assert isinstance(instructions, str)
        assert "git checkout main" in instructions
        assert "git merge worktrail/migrate-v1 --no-ff" in instructions
        assert "Откат" in instructions  # Rollback hint


# ============================================================================
# Migrator.migrate — integration-style with mocks
# ============================================================================


class TestMigratorMigrate:
    """Tests for Migrator.migrate covering branch, init, removal steps."""

    def test_migration_creates_branch(
        self, fake_project: Path
    ) -> None:
        """Migration creates the worktrail/migrate-v1 branch."""
        migrator = Migrator(
            source_knowledge_path=fake_project / "knowledge",
            project_root=fake_project,
        )

        with patch("worktrail.migrator.migrator.run_git") as mock_run_git, \
             patch("worktrail.migrator.migrator.init_worktrail_dir") as mock_init, \
             patch("worktrail.migrator.migrator.Repository") as mock_repo_cls, \
             patch("worktrail.migrator.migrator.install_hooks") as mock_install, \
             patch("worktrail.migrator.migrator.subprocess.run") as mock_subprocess:

            # Mock git branch check (no existing branch)
            mock_subprocess.return_value = MagicMock(stdout="", strip=lambda: "")
            # Mock run_git return values
            mock_run_git.return_value = ""
            # Mock init returns a path
            worktrail_dir = fake_project / ".worktrail"
            worktrail_dir.mkdir(exist_ok=True)
            mock_init.return_value = worktrail_dir
            # Mock Repository
            mock_repo = MagicMock()
            mock_repo.get_task.return_value = None
            mock_repo.conn.return_value.__enter__ = MagicMock(
                return_value=MagicMock(
                    execute=MagicMock(return_value=MagicMock(lastrowid=1)),
                    commit=MagicMock(),
                )
            )
            mock_repo.conn.return_value.__exit__ = MagicMock(return_value=None)
            mock_repo_cls.return_value = mock_repo
            # Mock install_hooks
            mock_install.return_value = True

            report = migrator.migrate()

        # Verify branch creation was attempted
        branch_calls = [
            call for call in mock_run_git.call_args_list
            if "checkout" in str(call) and "worktrail/migrate-v1" in str(call)
        ]
        assert len(branch_calls) >= 1

    def test_migration_initializes_worktrail_dir(
        self, fake_project: Path
    ) -> None:
        """Migration initializes .worktrail/ directory."""
        migrator = Migrator(
            source_knowledge_path=fake_project / "knowledge",
            project_root=fake_project,
        )

        with patch("worktrail.migrator.migrator.run_git") as mock_run_git, \
             patch("worktrail.migrator.migrator.init_worktrail_dir") as mock_init, \
             patch("worktrail.migrator.migrator.Repository") as mock_repo_cls, \
             patch("worktrail.migrator.migrator.install_hooks") as mock_install, \
             patch("worktrail.migrator.migrator.subprocess.run") as mock_subprocess:

            mock_subprocess.return_value = MagicMock(stdout="", strip=lambda: "")
            mock_run_git.return_value = ""
            worktrail_dir = fake_project / ".worktrail"
            worktrail_dir.mkdir(exist_ok=True)
            mock_init.return_value = worktrail_dir

            mock_repo = MagicMock()
            mock_repo.get_task.return_value = None
            mock_repo.conn.return_value.__enter__ = MagicMock(
                return_value=MagicMock(
                    execute=MagicMock(return_value=MagicMock(lastrowid=1)),
                    commit=MagicMock(),
                )
            )
            mock_repo.conn.return_value.__exit__ = MagicMock(return_value=None)
            mock_repo_cls.return_value = mock_repo
            mock_install.return_value = True

            report = migrator.migrate()

        mock_init.assert_called_once_with(fake_project)

    def test_migration_removes_knowledge_dir(
        self, fake_project: Path
    ) -> None:
        """Migration removes the knowledge/ directory."""
        migrator = Migrator(
            source_knowledge_path=fake_project / "knowledge",
            project_root=fake_project,
        )

        with patch("worktrail.migrator.migrator.run_git") as mock_run_git, \
             patch("worktrail.migrator.migrator.init_worktrail_dir") as mock_init, \
             patch("worktrail.migrator.migrator.Repository") as mock_repo_cls, \
             patch("worktrail.migrator.migrator.install_hooks") as mock_install, \
             patch("worktrail.migrator.migrator.subprocess.run") as mock_subprocess:

            mock_subprocess.return_value = MagicMock(stdout="", strip=lambda: "")
            mock_run_git.return_value = ""
            worktrail_dir = fake_project / ".worktrail"
            worktrail_dir.mkdir(exist_ok=True)
            mock_init.return_value = worktrail_dir

            mock_repo = MagicMock()
            mock_repo.get_task.return_value = None
            mock_repo.conn.return_value.__enter__ = MagicMock(
                return_value=MagicMock(
                    execute=MagicMock(return_value=MagicMock(lastrowid=1)),
                    commit=MagicMock(),
                )
            )
            mock_repo.conn.return_value.__exit__ = MagicMock(return_value=None)
            mock_repo_cls.return_value = mock_repo
            mock_install.return_value = True

            report = migrator.migrate()

        # Verify git rm -rf was called for knowledge/
        rm_calls = [
            call for call in mock_subprocess.call_args_list
            if "rm" in str(call) and "knowledge" in str(call)
        ]
        assert len(rm_calls) >= 1


# ============================================================================
# Helper functions
# ============================================================================


class TestNormaliseStatus:
    """Tests for _normalise_status."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("active", "active"),
            ("in progress", "active"),
            ("started", "active"),
            ("paused", "blocked"),
            ("on hold", "blocked"),
            ("done", "done"),
            ("completed", "done"),
            ("finished", "done"),
            ("closed", "done"),
            ("archived", "archived"),
            (None, "draft"),
            ("", "draft"),
            ("unknown_value", "draft"),
        ],
    )
    def test_normalise_status(self, raw: str | None, expected: str) -> None:
        """_normalise_status maps various inputs to canonical values."""
        assert _normalise_status(raw) == expected


class TestExtractTaskIdFromPath:
    """Tests for _extract_task_id_from_path."""

    def test_extracts_task_id(self) -> None:
        """_extract_task_id_from_path extracts TASK-XXX from parent directory."""
        path = Path("/some/path/knowledge/tasks/TASK-042-slug/task.md")
        assert _extract_task_id_from_path(path) == "TASK-042"

    def test_returns_none_when_no_match(self) -> None:
        """_extract_task_id_from_path returns None when no TASK- pattern found."""
        path = Path("/some/path/regular-folder/task.md")
        assert _extract_task_id_from_path(path) is None

    def test_case_insensitive(self) -> None:
        """_extract_task_id_from_path is case-insensitive."""
        path = Path("/some/path/knowledge/tasks/task-099/task.md")
        assert _extract_task_id_from_path(path) == "TASK-099"


class TestExtractNameFromContent:
    """Tests for _extract_name_from_content."""

    def test_extracts_h1_heading(self) -> None:
        """_extract_name_from_content extracts the first H1 heading."""
        content = "# My Task Name\n\nSome description.\n"
        assert _extract_name_from_content(content) == "My Task Name"

    def test_no_heading_returns_none(self) -> None:
        """_extract_name_from_content returns None when no H1 heading."""
        content = "Just some text without any heading.\n"
        assert _extract_name_from_content(content) is None


class TestCoerceDate:
    """Tests for _coerce_date."""

    def test_iso_date_string(self) -> None:
        """_coerce_date parses ISO date string."""
        result = _coerce_date("2024-03-15")
        assert result is not None
        assert "2024-03-15" in result

    def test_none_returns_none(self) -> None:
        """_coerce_date returns None for None input."""
        assert _coerce_date(None) is None


class TestParseDuration:
    """Tests for _parse_duration."""

    def test_hours(self) -> None:
        """_parse_duration extracts hours correctly."""
        assert _parse_duration("Worked on feature [2h]") == 120
        assert _parse_duration("Meeting [1.5h]") == 90

    def test_minutes(self) -> None:
        """_parse_duration extracts minutes correctly."""
        assert _parse_duration("Quick fix [30m]") == 30

    def test_no_duration_returns_none(self) -> None:
        """_parse_duration returns None when no duration marker."""
        assert _parse_duration("Just a regular message") is None

    def test_russian_units(self) -> None:
        """_parse_duration handles Russian units."""
        assert _parse_duration("Работа [2 ч]") == 120
        assert _parse_duration("Встреча [30 мин]") == 30


class TestParseTable:
    """Tests for _parse_table."""

    def test_extracts_key_value_pairs(self) -> None:
        """_parse_table extracts key-value pairs from markdown table."""
        content = (
            "| Key    | Value      |\n"
            "|--------|----------- |\n"
            "| id     | TASK-100   |\n"
            "| name   | My Task    |\n"
            "| status | active     |\n"
        )
        result = _parse_table(content)
        assert result["id"] == "TASK-100"
        assert result["name"] == "My Task"
        assert result["status"] == "active"

    def test_skips_header_separator(self) -> None:
        """_parse_table skips the |---|---| separator line."""
        content = (
            "| Key | Value |\n"
            "|-----|-------|\n"
            "| a   | 1     |\n"
        )
        result = _parse_table(content)
        assert "a" in result
        assert "---" not in result


# ============================================================================
# End-to-end parser integration
# ============================================================================


class TestEndToEndParser:
    """End-to-end parser tests combining task + worklog."""

    def test_full_task_with_worklog(self, fake_project_with_worklog: Path) -> None:
        """Parsing task.md and worklog.md together produces consistent data."""
        task_md = (
            fake_project_with_worklog
            / "knowledge"
            / "tasks"
            / "TASK-002-logged"
            / "task.md"
        )
        worklog_md = task_md.parent / "worklog.md"

        task = parse_v1_task(task_md)
        entries = parse_v1_worklog(worklog_md)

        assert task["id"] == "TASK-002"
        assert task["status"] == "done"
        assert len(entries) == 4
        # Verify dates in entries are valid
        for entry in entries:
            assert len(entry["date"]) == 10  # YYYY-MM-DD
            assert entry["date"][4] == "-"
            assert entry["date"][7] == "-"


# ============================================================================
# Phase 2 tests — audit 2026-06-07
# ============================================================================


class TestParseTable:
    """Tests for the rewritten _parse_table (first-table-only, skip header)."""

    def test_parses_first_table_only(self) -> None:
        """Only the first markdown table is parsed."""
        content = (
            "| Поле | Значение |\n"
            "|------|----------|\n"
            "| id   | TASK-001 |\n"
            "\n"
            "| Другая | Таблица |\n"
            "|--------|---------|\n"
            "| другой ключ | другое значение |\n"
        )
        result = _parse_table(content)
        assert result == {"id": "TASK-001"}

    def test_skips_header_row(self) -> None:
        """The header row before the separator is skipped."""
        content = (
            "| id | статус |\n"
            "|----|--------|\n"
            "| TASK-002 | done |\n"
        )
        result = _parse_table(content)
        # Header row 'id → статус' is skipped; only data rows are parsed
        assert result == {"task-002": "done"}

    def test_multi_column_uses_first_two(self) -> None:
        """Tables with >2 columns use only col 1 (key) and col 2 (value)."""
        content = (
            "| ID | Статус | Каталог |\n"
            "|----|--------|--------|\n"
            "| TASK-001 | done | path/to/dir |\n"
        )
        result = _parse_table(content)
        assert result == {"task-001": "done"}

    def test_backtick_values_stripped(self) -> None:
        """Backtick-wrapped values have backticks removed."""
        content = (
            "| Поле | Значение |\n"
            "|------|----------|\n"
            "| ID задачи | `TASK-003` |\n"
            "| Статус | `завершена` |\n"
        )
        result = _parse_table(content)
        assert result == {"id задачи": "TASK-003", "статус": "завершена"}

    def test_empty_content_returns_empty(self) -> None:
        """Content with no table returns empty dict."""
        assert _parse_table("") == {}
        assert _parse_table("## Just a heading\n\nSome text.\n") == {}


class TestNormaliseStatus:
    """Tests for _normalise_status with the 7-status model."""

    @pytest.mark.parametrize("raw,expected", [
        # New Russian statuses
        ("черновик", "draft"),
        ("на проверке", "review"),
        ("заблокирована", "blocked"),
        ("отменена", "cancelled"),
        # New English identity mappings
        ("draft", "draft"),
        ("blocked", "blocked"),
        ("review", "review"),
        ("cancelled", "cancelled"),
        # Existing ones still work
        ("в работе", "active"),
        ("завершена", "done"),
        ("архив", "archived"),
        ("active", "active"),
        ("done", "done"),
        ("archived", "archived"),
        # Fallback
        ("unknown_value", "draft"),
        (None, "draft"),
        ("", "draft"),
    ])
    def test_all_statuses(self, raw: Any, expected: str) -> None:
        """All 7 statuses and fallback work correctly."""
        assert _normalise_status(raw) == expected


class TestExtractTaskIdFromPath:
    """Tests for _extract_task_id_from_path with full ID extraction."""

    def test_short_id(self) -> None:
        """Short IDs like TASK-001 are extracted."""
        path = Path("/tmp/knowledge/tasks/TASK-001-slug/task.md")
        assert _extract_task_id_from_path(path) == "TASK-001"

    def test_full_id(self) -> None:
        """Full IDs like TASK-2026-0048 are extracted."""
        path = Path("/tmp/knowledge/tasks/TASK-2026-0048-slug/task.md")
        assert _extract_task_id_from_path(path) == "TASK-2026-0048"

    def test_subtask_id(self) -> None:
        """Subtask IDs like TASK-2026-0048.1 are extracted."""
        path = Path("/tmp/knowledge/tasks/TASK-2026-0048-main/subtasks/TASK-2026-0048.1-slug/task.md")
        assert _extract_task_id_from_path(path) == "TASK-2026-0048.1"

    def test_deep_subtask_id(self) -> None:
        """Deep subtask IDs like TASK-2026-0048.1.1 are extracted."""
        path = Path("/tmp/knowledge/tasks/TASK-2026-0048-main/subtasks/TASK-2026-0048.1.1-slug/task.md")
        assert _extract_task_id_from_path(path) == "TASK-2026-0048.1.1"

    def test_no_tasks_dir(self) -> None:
        """Path without TASK- prefix returns None."""
        path = Path("/tmp/other/file.md")
        assert _extract_task_id_from_path(path) is None


class TestValidIdRegex:
    """Tests for _VALID_ID_RE — task ID validation."""

    @pytest.mark.parametrize("task_id, valid", [
        ("TASK-001", True),
        ("TASK-2026-0001", True),
        ("TASK-2026-0048", True),
        ("TASK-2026-0048.1", True),
        ("TASK-2026-0048.1.1", True),
        ("TASK-2026-0053.1.1", True),
        # Invalid
        ("СТАТУС", False),
        ("TASK-2026", True),  # structurally valid (year-only), garbage caught elsewhere
        ("INV-1", False),
        ("task-2026-0001", False),  # lowercase
        ("", False),
    ])
    def test_validation(self, task_id: str, valid: bool) -> None:
        """_VALID_ID_RE accepts valid IDs, rejects garbage."""
        match = _VALID_ID_RE.match(task_id)
        if valid:
            assert match is not None, f"Expected {task_id!r} to be valid"
        else:
            assert match is None, f"Expected {task_id!r} to be invalid"


class TestParentIdEmptyMarkers:
    """Tests for parent_id extraction with empty-marker filtering."""

    def _parse_with_table(self, table_content: str) -> Dict[str, Any]:
        """Helper: create a task.md with given table and parse it."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_dir = root / "knowledge" / "tasks" / "TASK-001-test"
            task_dir.mkdir(parents=True)
            task_md = task_dir / "task.md"
            task_md.write_text(table_content, encoding="utf-8")
            return parse_v1_task(task_md)

    def test_em_dash_is_none(self) -> None:
        """Em-dash (—) in parent ID is treated as no parent."""
        content = (
            "| Поле | Значение |\n"
            "|------|----------|\n"
            "| ID задачи | TASK-001 |\n"
            "| Parent ID | `—` |\n"
            "| Статус | done |\n"
        )
        result = self._parse_with_table(content)
        assert result["parent_id"] is None

    def test_hyphen_is_none(self) -> None:
        """Hyphen (-) in parent ID is treated as no parent."""
        content = (
            "| Поле | Значение |\n"
            "|------|----------|\n"
            "| ID задачи | TASK-001 |\n"
            "| parent id | - |\n"
            "| Статус | done |\n"
        )
        result = self._parse_with_table(content)
        assert result["parent_id"] is None

    def test_net_is_none(self) -> None:
        """"нет" in parent ID is treated as no parent."""
        content = (
            "| Поле | Значение |\n"
            "|------|----------|\n"
            "| ID задачи | TASK-001 |\n"
            "| родитель | нет |\n"
            "| Статус | done |\n"
        )
        result = self._parse_with_table(content)
        assert result["parent_id"] is None

    def test_real_parent_id_preserved(self) -> None:
        """A real parent ID is preserved."""
        content = (
            "| Поле | Значение |\n"
            "|------|----------|\n"
            "| ID задачи | TASK-001 |\n"
            "| parent_id | TASK-000 |\n"
            "| Статус | done |\n"
        )
        result = self._parse_with_table(content)
        assert result["parent_id"] == "TASK-000"




class TestParseWorklogNarrative:
    """Tests for _parse_worklog_narrative — ## YYYY-MM-DD format."""

    def test_single_section(self) -> None:
        """A single ## YYYY-MM-DD section is parsed."""
        content = (
            "## 2026-05-06\n\n"
            "### Этап 1\n"
            "- Сделано что-то важное\n"
            "- Ещё одно действие\n"
        )
        entries = _parse_worklog_narrative(content)
        assert len(entries) == 1
        assert entries[0]["date"] == "2026-05-06"
        assert "Этап 1" in entries[0]["message"]

    def test_multiple_sections(self) -> None:
        """Multiple ## YYYY-MM-DD sections are parsed."""
        content = (
            "## 2026-05-06\n\n"
            "День первый.\n\n"
            "## 2026-05-07\n\n"
            "День второй.\n"
        )
        entries = _parse_worklog_narrative(content)
        assert len(entries) == 2
        assert entries[0]["date"] == "2026-05-06"
        assert entries[1]["date"] == "2026-05-07"

    def test_empty_sections_skipped(self) -> None:
        """Sections with no body are skipped."""
        content = "## 2026-05-06\n\n## 2026-05-07\n\nДень второй.\n"
        entries = _parse_worklog_narrative(content)
        assert len(entries) == 1
        assert entries[0]["date"] == "2026-05-07"

    def test_no_sections(self) -> None:
        """Content with no ## YYYY-MM-DD returns empty list."""
        assert _parse_worklog_narrative("Just some text\n") == []
        assert _parse_worklog_narrative("") == []


class TestMigrationReportCounters:
    """Tests for MigrationReport counters."""

    def test_str_includes_journal_entries(self) -> None:
        """__str__ includes journal_entries_created."""
        report = MigrationReport()
        report.tasks_migrated = 5
        report.journal_entries_created = 12
        report.sessions_created = 2
        s = str(report)
        assert "tasks_migrated=5" in s
        assert "journal_entries_created=12" in s
        assert "sessions_created=2" in s

    def test_to_markdown_includes_all_fields(self) -> None:
        """to_markdown includes all counters."""
        report = MigrationReport()
        report.tasks_migrated = 3
        report.journal_entries_created = 7
        report.sessions_created = 1
        report.checkpoints_created = 4
        md = report.to_markdown()
        assert "3" in md
        assert "7" in md


class TestIdempotentJournalEntry:
    """Tests for idempotent add_journal_entry."""

    def test_duplicate_returns_existing(self, tmp_path: Path) -> None:
        """Adding the same (task_id, kind, title) twice returns existing."""
        from worktrail.core.db import init_db
        from worktrail.core.repository import Repository

        db_path = tmp_path / "test.db"
        init_db(db_path)
        repo = Repository(db_path)

        # First insert
        e1 = repo.add_journal_entry("TASK-001", "note", "Test", "Body")
        assert e1.id is not None

        # Second insert with same parameters
        e2 = repo.add_journal_entry("TASK-001", "note", "Test", "Body v2")
        # Should return existing entry, not create duplicate
        assert e2.id == e1.id

        # Verify only one row exists
        with repo.conn() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM journal WHERE task_id=? AND kind=? AND title=?",
                ("TASK-001", "note", "Test"),
            )
            assert cur.fetchone()[0] == 1

    def test_different_title_creates_new(self, tmp_path: Path) -> None:
        from worktrail.core.db import init_db
        from worktrail.core.repository import Repository

        db_path = tmp_path / "test.db"
        init_db(db_path)
        repo = Repository(db_path)

        e1 = repo.add_journal_entry("TASK-001", "note", "Title A", "Body")
        e2 = repo.add_journal_entry("TASK-001", "note", "Title B", "Body")
        assert e2.id != e1.id
