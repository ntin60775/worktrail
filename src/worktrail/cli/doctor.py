"""Diagnostics command for worktrail.

The ``doctor`` subcommand checks the health of a worktrail installation
and prints a diagnostic report.
"""

from __future__ import annotations

import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

from worktrail.git_bridge import are_hooks_installed


@dataclass
class CheckResult:
    """Result of a single diagnostic check.

    Attributes:
        name: Human-readable check name (in Russian).
        passed: ``True`` if the check passed.
        message: Optional details message.
    """

    name: str
    passed: bool
    message: str = ""


def _check_git_available() -> CheckResult:
    """Check that the ``git`` executable is on ``PATH``."""
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
        return CheckResult(
            name="Git доступен",
            passed=True,
            message=result.stdout.strip(),
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return CheckResult(
            name="Git доступен",
            passed=False,
            message="git не найден в PATH",
        )


def _check_git_repo(project_root: Path | None) -> CheckResult:
    """Check that we are inside a git repository."""
    if project_root is None:
        return CheckResult(
            name="Git-репозиторий",
            passed=False,
            message="Не найден .git/ — запустите 'git init'",
        )
    return CheckResult(
        name="Git-репозиторий",
        passed=True,
        message=str(project_root),
    )


def _check_worktrail_dir(project_root: Path | None) -> CheckResult:
    """Check that ``.worktrail/`` exists."""
    if project_root is None:
        return CheckResult(
            name="Директория .worktrail/",
            passed=False,
            message="Git-репозиторий не найден",
        )
    wt_dir = project_root / ".worktrail"
    if wt_dir.is_dir():
        return CheckResult(
            name="Директория .worktrail/",
            passed=True,
            message=str(wt_dir),
        )
    return CheckResult(
        name="Директория .worktrail/",
        passed=False,
        message="Директория не найдена — запустите 'worktrail init'",
    )


def _check_database(project_root: Path | None) -> CheckResult:
    """Check that ``runtime.db`` exists and has the expected tables."""
    if project_root is None:
        return CheckResult(
            name="База данных runtime.db",
            passed=False,
            message="Git-репозиторий не найден",
        )
    db_path = project_root / ".worktrail" / "runtime.db"
    if not db_path.exists():
        return CheckResult(
            name="База данных runtime.db",
            passed=False,
            message=f"Файл не найден: {db_path}",
        )
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in cursor.fetchall()}
            expected = {"tasks", "sessions", "checkpoints", "config"}
            missing = expected - tables
            if missing:
                return CheckResult(
                    name="База данных runtime.db",
                    passed=False,
                    message=f"Отсутствуют таблицы: {', '.join(sorted(missing))}",
                )
            return CheckResult(
                name="База данных runtime.db",
                passed=True,
                message="Таблицы: tasks, sessions, checkpoints, config",
            )
    except sqlite3.Error as exc:
        return CheckResult(
            name="База данных runtime.db",
            passed=False,
            message=f"Ошибка SQLite: {exc}",
        )


def _check_hooks(project_root: Path | None) -> CheckResult:
    """Check that worktrail git hooks are installed."""
    if project_root is None:
        return CheckResult(
            name="Git hooks",
            passed=False,
            message="Git-репозиторий не найден",
        )
    if are_hooks_installed(project_root):
        return CheckResult(
            name="Git hooks",
            passed=True,
            message="post-commit и post-checkout установлены",
        )
    return CheckResult(
        name="Git hooks",
        passed=False,
        message="Hooks не установлены — запустите 'worktrail init'",
    )


def _check_global_skill() -> CheckResult:
    """Check whether the global agent skill file is installed.

    This is optional — a warning, not a failure.
    """
    skill_path = Path.home() / ".agents" / "skills" / "worktrail" / "SKILL.md"
    if skill_path.exists():
        return CheckResult(
            name="Глобальный навык (SKILL.md)",
            passed=True,
            message=f"{skill_path}",
        )
    return CheckResult(
        name="Глобальный навык (SKILL.md)",
        passed=False,
        message="Не установлен — агент не будет автоматически знать о worktrail. "
                f"Установите: mkdir -p ~/.agents/skills/worktrail && cp SKILL.md $_",
    )


def run_diagnostics(project_root: Path | None) -> list[CheckResult]:
    """Run all diagnostic checks.

    Args:
        project_root: The discovered project root (or ``None``).

    Returns:
        List of :class:`CheckResult` instances.
    """
    return [
        _check_git_available(),
        _check_git_repo(project_root),
        _check_worktrail_dir(project_root),
        _check_database(project_root),
        _check_hooks(project_root),
        _check_global_skill(),
    ]


def print_report(results: list[CheckResult]) -> int:
    """Print a diagnostic report and return an exit code.

    Args:
        results: List of check results.

    Returns:
        ``0`` if all mandatory checks passed, ``1`` if any mandatory check failed.
    """
    print("worktrail doctor — диагностика")
    print("=" * 40)
    all_passed = True
    for result in results:
        icon = "✓" if result.passed else "✗"
        print(f"{icon} {result.name}")
        if result.message:
            print(f"    {result.message}")
        if not result.passed:
            all_passed = False
    print("=" * 40)
    if all_passed:
        print("Все проверки пройдены ✓")
        return 0
    print("Обнаружены проблемы — см. выше")
    return 1
