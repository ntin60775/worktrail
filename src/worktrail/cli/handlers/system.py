"""System-level commands: list tasks, uninstall worktrail."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Optional

import argparse

from worktrail.cli.commands import (
    arg,
    command,
    ensure_project_root,
    ensure_worktrail_dir,
    fmt_seconds,
)
from worktrail.cli.doctor import print_report as print_doctor_report, run_diagnostics
from worktrail.core import Repository, init_worktrail_dir
from worktrail.git_bridge import install_hooks, remove_hooks


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


@command("init", help="Инициализировать worktrail в репозитории")
def cmd_init(args: argparse.Namespace) -> int:
    """Handle ``worktrail init``."""
    project_root = ensure_project_root()
    init_worktrail_dir(project_root)
    install_hooks(project_root)
    print(f"✓ worktrail инициализирован в {project_root / '.worktrail'}")
    return 0


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


@command("doctor", help="Диагностика")
def cmd_doctor(args: argparse.Namespace) -> int:
    """Handle ``worktrail doctor``."""
    project_root = ensure_project_root()
    results = run_diagnostics(project_root)
    return print_doctor_report(results)


# ---------------------------------------------------------------------------
# git-checkout-hook (hidden — used by post-checkout git hook)
# ---------------------------------------------------------------------------


@command("git-checkout-hook", help=argparse.SUPPRESS)
@arg("prev_head")
@arg("new_head")
def cmd_git_checkout_hook(args: argparse.Namespace) -> int:
    """Handle branch switches — auto-start/stop tasks based on branch name."""
    from worktrail.git_bridge.parser import extract_task_from_branch

    project_root = ensure_project_root()
    db_path = project_root / ".worktrail" / "runtime.db"
    repo = Repository(db_path)
    active = repo.get_active_session()

    # Check if switched TO a task branch
    import subprocess
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
    )
    current_branch = result.stdout.strip()
    task_id = extract_task_from_branch(current_branch)

    if task_id and active is None:
        print(f"■ Переключено на task-ветку {current_branch}")
        print(f"  Запустите: worktrail start {task_id}")
        return 0
    elif task_id is None and active is not None:
        print(f"■ Ушли с task-ветки. Активная сессия: {active.task_id}")
        print("  Запустите: worktrail stop")
        return 0
    return 0


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@command("list", help="Список всех задач")
@arg("--status", default=None, help="Фильтр по статусу (draft, active, blocked, review, delivery, done, cancelled)")
@arg("--kind", default=None, choices=["task", "exploration", "initiative"], help="Фильтр по типу задачи")
@arg("--parent", default=None, metavar="TASK-ID", help="Показать подзадачи родительской задачи")
@arg("--archived", action="store_true", help="Включить архивные задачи")
def cmd_list(args: argparse.Namespace) -> int:
    """Handle ``worktrail list [--status] [--kind] [--parent] [--archived]``."""
    project_root = ensure_project_root()
    ensure_worktrail_dir(project_root)

    db_path = project_root / ".worktrail" / "runtime.db"
    repo = Repository(db_path)

    tasks = repo.list_tasks(
        status=args.status,
        kind=args.kind,
        parent_id=args.parent,
        include_archived=args.archived,
    )

    if not tasks:
        filters = []
        if args.status:
            filters.append(f"статус: {args.status}")
        if args.kind:
            filters.append(f"тип: {args.kind}")
        filter_str = f" ({'; '.join(filters)})" if filters else ""
        print(f"Нет задач{filter_str}.")
        return 0

    # Column widths
    max_id_len = max(len(t.id) for t in tasks)
    status_width = 10
    kind_width = 6

    for task in tasks:
        total_seconds = 0
        with repo.conn() as conn:
            rows = conn.execute(
                "SELECT total_seconds FROM sessions WHERE task_id = ?",
                (task.id,),
            ).fetchall()
        for row in rows:
            total_seconds += row["total_seconds"] or 0

        time_str = fmt_seconds(total_seconds)
        status_display = _translate_status(task.status)
        kind_display = task.kind[:3] if task.kind else " — "
        name_display = task.name if task.name and task.name != task.id else ""

        line = f"{task.id:<{max_id_len}}  {kind_display:<{kind_width}}  {status_display:<{status_width}}  {time_str:>6}"
        if name_display:
            line += f"   {name_display}"
        print(line)

    return 0


# ---------------------------------------------------------------------------
# uninstall
# ---------------------------------------------------------------------------


@command("uninstall", help="Удалить worktrail из репозитория")
def cmd_uninstall(args: argparse.Namespace) -> int:
    """Handle ``worktrail uninstall``.

    1. Stop any active session.
    2. Remove git hooks.
    3. Ask confirmation.
    4. Remove ``.worktrail/`` directory.
    """
    project_root = ensure_project_root()
    ensure_worktrail_dir(project_root)

    # 1. Stop any active session
    db_path = project_root / ".worktrail" / "runtime.db"
    repo = Repository(db_path)
    active = repo.get_active_session()
    if active is not None:
        repo.end_session(active.id)
        total_str = fmt_seconds(active.total_seconds)
        print(f"■ Активная сессия {active.task_id} остановлена. Всего: {total_str}")

    # 2. Remove git hooks
    remove_hooks(project_root)

    # 3. Ask confirmation
    answer = input("Удалить .worktrail/ и git hooks? (yes/no): ").strip().lower()
    if answer not in ("yes", "y"):
        print("Удаление отменено.")
        return 0

    # 4. Remove .worktrail/ directory
    worktrail_dir = project_root / ".worktrail"
    try:
        shutil.rmtree(worktrail_dir)
    except OSError as exc:
        print(f"Ошибка при удалении {worktrail_dir}: {exc}", file=sys.stderr)
        return 1

    # 5. Success message
    print("worktrail удалён. Данные в .worktrail/ удалены безвозвратно.")
    return 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _translate_status(status: str) -> str:
    """Translate a task status code into a human-readable label."""
    mapping = {
        "draft":     "Черновик",
        "active":    "В работе",
        "blocked":   "Заблок.",
        "review":    "Ревью",
        "delivery":  "Доставка",
        "done":      "Заверш.",
        "archived":  "Архив",
        "cancelled": "Отмен.",
    }
    return mapping.get(status, status.capitalize())
