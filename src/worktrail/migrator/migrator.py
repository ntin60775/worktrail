"""Main migration logic for converting task-centric-knowledge v1 → worktrail.

Usage::

    migrator = Migrator(
        source_knowledge_path=Path("./knowledge"),
        project_root=Path("."),
    )
    if migrator.validate_source():
        report = migrator.migrate()
        print(report)
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from worktrail.core import (
    Checkpoint,
    Repository,
    Session,
    Task,
    get_db_path,
    init_worktrail_dir,
)
from worktrail.git_bridge import install_hooks, run_git
from worktrail.migrator.parser import parse_v1_task, parse_v1_worklog

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Report dataclass
# ---------------------------------------------------------------------------


@dataclass
class MigrationReport:
    """Summary of a completed migration run.

    Attributes:
        tasks_migrated: Number of tasks inserted into the database.
        sessions_created: Number of sessions created from worklog entries.
        checkpoints_created: Number of checkpoints created from worklog entries.
        journal_entries_created: Number of journal entries imported.
        migration_branch: The git branch used for the migration.
        merge_command: Shell command to merge the migration branch into main.
        migration_commit_hash: Hash of the migration commit (if available).
        task_mapping: List of dicts with ``old_id``, ``name``, ``new_status``.
        errors: Any non-fatal errors encountered during migration.
    """

    tasks_migrated: int = 0
    sessions_created: int = 0
    checkpoints_created: int = 0
    journal_entries_created: int = 0
    migration_branch: str = "worktrail/migrate-v1"
    merge_command: str = "git checkout main && git merge worktrail/migrate-v1 --no-ff"
    migration_commit_hash: Optional[str] = None
    task_mapping: List[Dict[str, str]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Render the report as the MIGRATION-REPORT.md document."""
        lines: List[str] = [
            "# Миграция task-centric-knowledge v1 → worktrail",
            "",
            "## Статистика",
            f"- Задач мигрировано: {self.tasks_migrated}",
            f"- Сессий создано: {self.sessions_created}",
            f"- Чекпоинтов создано: {self.checkpoints_created}",
            f"- Записей журнала: {self.journal_entries_created}",
            "",
            "## Сопоставление ID",
            "| Старый ID | Имя задачи | Новый статус |",
            "|-----------|------------|-------------|",
        ]
        for mapping in self.task_mapping:
            task_id = mapping.get("old_id", "")
            name = mapping.get("name", "")
            status = mapping.get("new_status", "")
            lines.append(f"| {task_id} | {name} | {status} |")
        lines.extend([
            "",
            "## Откат",
            "```bash",
        ])
        if self.migration_commit_hash:
            lines.append(f"git revert {self.migration_commit_hash}")
        else:
            lines.append(
                f"# Find the commit hash on branch '{self.migration_branch}' "
                "and run: git revert <hash>"
            )
        lines.extend([
            "```",
            "",
        ])
        return "\n".join(lines)

    def __str__(self) -> str:
        parts = [
            f"MigrationReport(",
            f"  tasks_migrated={self.tasks_migrated}",
            f"  journal_entries_created={self.journal_entries_created}",
            f"  sessions_created={self.sessions_created}",
            f"  checkpoints_created={self.checkpoints_created}",
            f"  migration_branch={self.migration_branch!r}",
        ]
        if self.migration_commit_hash:
            parts.append(f"  migration_commit_hash={self.migration_commit_hash!r}")
        if self.errors:
            parts.append(f"  errors={self.errors!r}")
        parts.append(")")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Migrator
# ---------------------------------------------------------------------------


class Migrator:
    """Orchestrates migration from task-centric-knowledge v1 to worktrail.

    Args:
        source_knowledge_path: Path to the ``knowledge/`` directory.
        project_root: Path to the git repository root.
    """

    def __init__(
        self,
        source_knowledge_path: Path,
        project_root: Path,
    ) -> None:
        self.source_knowledge_path = source_knowledge_path.resolve()
        self.project_root = project_root.resolve()
        self._tasks_dir = self.source_knowledge_path / "tasks"
        self._report = MigrationReport()
        self._repo: Optional[Repository] = None

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_source(self) -> bool:
        """Check whether *source_knowledge_path* looks like a v1 layout.

        A valid v1 source has:

        * A ``knowledge/tasks/`` subdirectory.
        * At least one ``TASK-*/task.md`` file inside it.

        Returns:
            ``True`` if the source looks like v1 format.
        """
        if not self._tasks_dir.is_dir():
            logger.warning(
                "Expected tasks directory does not exist: %s", self._tasks_dir
            )
            return False

        found = any(self._tasks_dir.glob("TASK-*/task.md"))
        if not found:
            logger.warning(
                "No TASK-*/task.md files found in %s", self._tasks_dir
            )
            return False

        logger.info("Source validated: %s", self._tasks_dir)
        return True

    # ------------------------------------------------------------------
    # Main migration entry point
    # ------------------------------------------------------------------

    def migrate(self) -> MigrationReport:
        """Run the full migration pipeline.

        Steps:

        1. Create git branch ``worktrail/migrate-v1``.
        2. Initialise ``.worktrail/`` (runtime.db, config.yaml, hooks, reports).
        3. Parse all ``knowledge/tasks/TASK-*/task.md`` → database.
        4. Parse worklogs → sessions + checkpoints.
        5. Install git hooks.
        6. Remove ``knowledge/`` (``git rm -rf``).
        7. Create ``MIGRATION-REPORT.md``.
        8. Git add + commit.
        9. Return :class:`MigrationReport`.

        The method is designed to be recoverable: if a step fails, the
        ``MigrationReport.errors`` list is populated and subsequent steps
        are skipped where dependencies are missing.

        Returns:
            A :class:`MigrationReport` summarising the migration.
        """
        self._report = MigrationReport()

        # Step 1 — create branch
        if not self._git_create_branch():
            return self._report

        # Step 2 — init .worktrail/
        if not self._init_worktrail():
            return self._report

        # Steps 3 & 4 — parse tasks and worklogs
        self._migrate_tasks()

        # Step 5 — install hooks
        self._install_hooks()

        # Step 6 — remove knowledge/
        self._remove_knowledge_dir()

        # Step 7 — write MIGRATION-REPORT.md
        self._write_migration_report()

        # Step 8 — git add + commit
        self._git_commit()

        return self._report

    # ------------------------------------------------------------------
    # Internal steps
    # ------------------------------------------------------------------

    def _git_create_branch(self) -> bool:
        """Create the migration branch.  Reuses existing branch if present.

        Returns:
            ``True`` on success.
        """
        try:
            # Check if branch already exists (non-fatal)
            result = subprocess.run(
                ["git", "branch", "--list", self._report.migration_branch],
                cwd=str(self.project_root),
                check=False,
                capture_output=True,
                text=True,
            )
            if result.stdout.strip():
                # Branch exists — check it out (force reset to current HEAD)
                run_git(["checkout", self._report.migration_branch], self.project_root)
                logger.info("Reused existing branch %s", self._report.migration_branch)
            else:
                # Create fresh branch
                run_git(["checkout", "-b", self._report.migration_branch], self.project_root)
                logger.info("Created branch %s", self._report.migration_branch)
            return True
        except subprocess.CalledProcessError as exc:
            msg = f"Failed to create migration branch: {exc.stderr or exc.stdout}"
            logger.error(msg)
            self._report.errors.append(msg)
            return False

    def _init_worktrail(self) -> bool:
        """Create ``.worktrail/`` directory structure and open Repository.

        Returns:
            ``True`` on success.
        """
        try:
            worktrail_dir = init_worktrail_dir(self.project_root)
            db_path = worktrail_dir / "runtime.db"
            self._repo = Repository(db_path)
            logger.info("Initialised .worktrail/ at %s", worktrail_dir)
            return True
        except Exception as exc:
            msg = f"Failed to init .worktrail/: {exc}"
            logger.error(msg)
            self._report.errors.append(msg)
            return False

    def _migrate_tasks(self) -> None:
        """Parse all TASK-*/task.md files and insert into the database.

        Also parses worklogs and creates sessions/checkpoints from them.
        """
        if self._repo is None:
            self._report.errors.append("Repository not available; skipping task migration.")
            return

        task_md_files = sorted(self._tasks_dir.glob("TASK-*/task.md"))
        logger.info("Found %d task.md files to migrate", len(task_md_files))

        for task_md_path in task_md_files:
            try:
                parsed = parse_v1_task(task_md_path)
            except Exception as exc:
                msg = f"Failed to parse {task_md_path}: {exc}"
                logger.warning(msg)
                self._report.errors.append(msg)
                continue

            task_id = parsed["id"]
            task_name = parsed["name"]
            task_status = parsed["status"]

            # Insert task into DB
            try:
                # Check if task already exists (idempotent)
                existing = self._repo.get_task(task_id)
                if existing is None:
                    self._repo.create_task(
                        task_id=task_id,
                        name=task_name,
                        parent_id=parsed.get("parent_id"),
                        branch=parsed.get("branch"),
                    )
                    if task_status != "draft":
                        self._repo.update_task_status(task_id, task_status)
                else:
                    # Update existing task status if needed
                    self._repo.update_task_status(task_id, task_status)
                self._report.tasks_migrated += 1
                self._report.task_mapping.append({
                    "old_id": task_id,
                    "name": task_name,
                    "new_status": task_status,
                })
                logger.info("Migrated task %s: %s", task_id, task_name)
            except Exception as exc:
                msg = f"Failed to insert task {task_id}: {exc}"
                logger.warning(msg)
                self._report.errors.append(msg)
                continue

            # Parse worklog if present
            worklog_path = task_md_path.parent / "worklog.md"
            try:
                self._migrate_worklog(task_id, worklog_path)
            except Exception as exc:
                logger.warning("Failed to migrate worklog for %s: %s", task_id, exc)

            # Import knowledge files as journal entries
            try:
                self._migrate_journal(task_id, task_md_path.parent)
            except Exception as exc:
                logger.warning("Failed to migrate journal for %s: %s", task_id, exc)
    def _migrate_worklog(self, task_id: str, worklog_path: Path) -> None:
        """Parse a worklog and create sessions + checkpoints.

        Strategy:

        * Consecutive entries on the same date are grouped into a single
          session.
        * Each entry becomes a checkpoint within that session.
        * The session total_seconds is the sum of all explicit durations
          for that date (if given), otherwise a default of 1 hour per
          entry with no duration.

        Args:
            task_id: The task ID to associate sessions with.
            worklog_path: Path to the ``worklog.md`` file.
        """
        if self._repo is None:
            return

        entries = parse_v1_worklog(worklog_path)
        if not entries:
            return

        # Group entries by date
        by_date: Dict[str, List[Dict[str, Any]]] = {}
        for entry in entries:
            by_date.setdefault(entry["date"], []).append(entry)

        for entry_date, day_entries in sorted(by_date.items()):
            try:
                # Create one session per date
                started_at = datetime.fromisoformat(f"{entry_date}T09:00:00+00:00")
                session = Session(
                    task_id=task_id,
                    started_at=started_at.isoformat(),
                    ended_at=None,
                    status="ended",  # historical sessions are ended
                    total_seconds=0,
                    id=None,
                )
                with self._repo.conn() as conn:
                    cur = conn.execute(
                        """
                        INSERT INTO sessions (task_id, started_at, ended_at, status, total_seconds)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (session.task_id, session.started_at,
                         session.ended_at, session.status, session.total_seconds),
                    )
                    conn.commit()
                    session.id = cur.lastrowid

                total_minutes = 0
                for entry in day_entries:
                    duration = entry.get("duration_minutes")
                    if duration:
                        total_minutes += duration
                    else:
                        # Default 1 hour per entry without explicit duration
                        total_minutes += 60

                    # Add checkpoint
                    checkpoint_ts = datetime.fromisoformat(
                        f"{entry_date}T09:00:00+00:00"
                    )
                    self._repo.add_checkpoint(
                        session_id=session.id,
                        message=entry["message"],
                        source="manual",
                    )
                    self._report.checkpoints_created += 1

                # Update session with total duration and end time
                total_seconds = total_minutes * 60
                ended_at = datetime.fromisoformat(
                    f"{entry_date}T17:00:00+00:00"
                )
                with self._repo.conn() as conn:
                    conn.execute(
                        """
                        UPDATE sessions
                        SET total_seconds = ?, ended_at = ?
                        WHERE id = ?
                        """,
                        (total_seconds, ended_at.isoformat(), session.id),
                    )
                    conn.commit()

                self._report.sessions_created += 1
                logger.info(
                    "Created session for %s on %s (%d checkpoints)",
                    task_id, entry_date, len(day_entries),
                )
            except Exception as exc:
                msg = f"Failed to migrate worklog for {task_id} on {entry_date}: {exc}"
                logger.warning(msg)
                self._report.errors.append(msg)
    def _migrate_journal(self, task_id: str, task_dir: Path) -> None:
        """Import knowledge files from *task_dir* as journal entries.

        Looks for:
        - ``sdd.md`` / ``sdd.json`` → kind='spec'
        - ``decisions.md`` → kind='decision'
        - ``plan.md`` → kind='design'
        - ``task.md`` description section → kind='proposal'

        Args:
            task_id: The task identifier to associate entries with.
            task_dir: Directory containing the knowledge files.
        """
        if self._repo is None:
            return

        # sdd.md / sdd.json → spec

        # sdd.md / sdd.json → spec
        for sdd_name in ("sdd.md", "sdd.json"):
            sdd_path = task_dir / sdd_name
            if sdd_path.is_file():
                try:
                    body = sdd_path.read_text(encoding="utf-8")
                    self._repo.add_journal_entry(
                        task_id=task_id,
                        kind="spec",
                        title="Спецификация",
                        body=body[:10000],
                    )
                    self._report.journal_entries_created += 1
                except Exception as exc:
                    logger.debug("Failed to import sdd for %s: %s", task_id, exc)
                break
        # decisions.md → decision entries
        decisions_path = task_dir / "decisions.md"
        if decisions_path.is_file():
            try:
                content = decisions_path.read_text(encoding="utf-8")
                # Split by ## headers for individual decisions
                sections = re.split(r"\n## ", content)
                for section in sections:
                    section = section.strip()
                    if not section:
                        continue
                    lines = section.split("\n", 1)
                    title = lines[0].lstrip("# ").strip()
                    body_text = lines[1].strip() if len(lines) > 1 else ""
                    self._repo.add_journal_entry(
                        task_id=task_id,
                        kind="decision",
                        title=title,
                        body=body_text[:10000],
                    )
                    self._report.journal_entries_created += 1
            except Exception as exc:
                logger.debug("Failed to import decisions for %s: %s", task_id, exc)

        # plan.md → design
        plan_path = task_dir / "plan.md"
        if plan_path.is_file():
            try:
                body = plan_path.read_text(encoding="utf-8")
                self._repo.add_journal_entry(
                    task_id=task_id,
                    kind="design",
                    title="План реализации",
                    body=body[:10000],
                )
                self._report.journal_entries_created += 1
            except Exception as exc:
                logger.debug("Failed to import plan for %s: %s", task_id, exc)

        # task.md sections → journal entries
        task_md_path = task_dir / "task.md"
        if task_md_path.is_file():
            try:
                content = task_md_path.read_text(encoding="utf-8")
                # ## Цель or ## Описание → proposal
                for section_re, kind, title in [
                    (r"## Цель\s*\n+(.*?)(?=\n## |\Z)", "proposal", "Цель задачи"),
                    (r"## Описание\s*\n+(.*?)(?=\n## |\Z)", "proposal", "Описание задачи"),
                    (r"## Итог\s*\n+(.*?)(?=\n## |\Z)", "note", "Итог"),
                ]:
                    m = re.search(section_re, content, re.DOTALL)
                    if m:
                        body = m.group(1).strip()
                        if body and len(body) > 10:
                            self._repo.add_journal_entry(
                                task_id=task_id,
                                kind=kind,
                                title=title,
                                body=body[:10000],
                            )
                            self._report.journal_entries_created += 1
            except Exception as exc:
                logger.debug("Failed to import task.md description for %s: %s", task_id, exc)

    def _install_hooks(self) -> None:
        try:
            success = install_hooks(self.project_root)
            if success:
                logger.info("Git hooks installed.")
            else:
                msg = "Git hook installation returned False (no .git/hooks/?)"
                logger.warning(msg)
                self._report.errors.append(msg)
        except Exception as exc:
            msg = f"Failed to install git hooks: {exc}"
            logger.warning(msg)
            self._report.errors.append(msg)

    def _remove_knowledge_dir(self) -> None:
        """Remove ``knowledge/`` from disk and stage the deletion in git."""
        import shutil

        try:
            rel_path = str(self.source_knowledge_path.relative_to(self.project_root))
            # Try git rm first (for tracked files)
            result = subprocess.run(
                ["git", "rm", "-rf", "--cached", rel_path],
                cwd=str(self.project_root),
                check=False,
                capture_output=True,
                text=True,
            )
            # Also remove from disk (handles untracked files)
            if self.source_knowledge_path.exists():
                shutil.rmtree(self.source_knowledge_path)
            # Stage any remaining changes
            subprocess.run(
                ["git", "add", "-A"],
                cwd=str(self.project_root),
                check=False,
                capture_output=True,
            )
            logger.info("Removed %s", self.source_knowledge_path)
        except Exception as exc:
            msg = f"Failed to remove knowledge/: {exc}"
            logger.warning(msg)
            self._report.errors.append(msg)

    def _write_migration_report(self) -> None:
        """Write ``MIGRATION-REPORT.md`` to the project root."""
        try:
            report_path = self.project_root / "MIGRATION-REPORT.md"
            report_path.write_text(self._report.to_markdown(), encoding="utf-8")
            logger.info("Written %s", report_path)
        except Exception as exc:
            msg = f"Failed to write MIGRATION-REPORT.md: {exc}"
            logger.warning(msg)
            self._report.errors.append(msg)

    def _git_commit(self) -> None:
        """Stage all changes and create the migration commit."""
        try:
            run_git(["add", "-A"], self.project_root)
            run_git(
                [
                    "commit",
                    "-m",
                    "migrate: task-centric-knowledge v1 → worktrail\n\n"
                    "- Migrated tasks from knowledge/tasks/TASK-*/\n"
                    "- Created .worktrail/ runtime directory\n"
                    "- Converted worklogs to sessions and checkpoints\n"
                    "- Installed git hooks\n"
                    "- Removed legacy knowledge/ directory\n"
                    "\nRollback: git revert <this-commit>",
                ],
                self.project_root,
            )
            logger.info("Migration committed.")

            # Try to capture commit hash
            try:
                commit_hash = run_git(["rev-parse", "HEAD"], self.project_root)
                if commit_hash:
                    self._report.migration_commit_hash = commit_hash
            except Exception:
                pass

        except subprocess.CalledProcessError as exc:
            msg = f"Failed to commit migration: {exc.stderr or exc.stdout}"
            logger.warning(msg)
            self._report.errors.append(msg)

    # ------------------------------------------------------------------
    # Post-migration helpers
    # ------------------------------------------------------------------

    def get_merge_instructions(self) -> str:
        """Return human-readable merge instructions after migration.

        Returns:
            Multi-line string with the git commands needed to complete
            the migration by merging the migration branch into main.
        """
        lines = [
            "=== Следующие шаги ===",
            "",
            f"  git checkout main",
            f"  git merge {self._report.migration_branch} --no-ff",
            "",
            "Откат: git revert <commit-hash>",
        ]
        return "\n".join(lines)
