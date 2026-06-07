"""Task tracking command handlers.

Provides:
* ``start`` — begin a tracking session
* ``stop`` — end the current session
* ``pause`` — pause the active session
* ``resume`` — resume a paused session
* ``checkpoint`` — record a checkpoint
* ``status`` — show current session info
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from worktrail.cli.commands import (
    arg,
    command,
    ensure_project_root,
    ensure_worktrail_dir,
    fmt_seconds,
    get_engine,
    pluralize,
)
from worktrail.core import Repository


def _derive_task_name(project_root: Path, task_id: str) -> str | None:
    """Try to derive a human-readable task name from the current git branch.

    For task branches (``task/TASK-001-slug`` / ``du/DU-042-fix-bug``),
    the slug after the task ID is extracted and hyphenated words are
    joined with spaces.  For any other branch the full branch name is
    used.  Returns ``None`` when git is unavailable.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        branch = result.stdout.strip()
        if not branch or branch == "HEAD":
            return None
    except Exception:
        return None


    # Task branch: extract slug after task ID
    pattern = r"^(?:task|du)/" + re.escape(task_id) + r"-(.+)$"
    match = re.match(pattern, branch)
    if match:
        return match.group(1).replace("-", " ")

    # Feature-like branches: strip prefix, use remainder as name
    for prefix in ("task/", "du/", "feature/", "bugfix/", "fix/", "hotfix/"):
        if branch.startswith(prefix):
            return branch[len(prefix):].replace("-", " ")

    # Mainline branches — fall back to task_id
    if branch in ("main", "master", "develop", "HEAD"):
        return None

    # Other named branches — use as-is
    return branch


@command("start", help="Начать сессию для задачи")
@arg("task_id", help="Идентификатор задачи (например, TASK-001)")
@arg("--name", default=None, help="Название задачи (если не указано — выводится из git-ветки)")
def cmd_start(args: argparse.Namespace) -> int:
    """Handle ``worktrail start <task-id> [--name ...]``."""
    project_root = ensure_project_root()
    ensure_worktrail_dir(project_root)

    task_id: str = args.task_id
    task_name: str | None = args.name

    if task_name is None:
        task_name = _derive_task_name(project_root, task_id)

    engine = get_engine(project_root)
    try:
        engine.start(task_id, task_name)
    except ValueError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    info = engine.current()
    elapsed_str = fmt_seconds(info["elapsed_seconds"]) if info else "0с"
    name_display = f' "{task_name}"' if task_name else ""
    print(f"▶ Сессия запущена: {task_id}{name_display} — {elapsed_str}")
    return 0


@command("stop", help="Остановить текущую сессию")
def cmd_stop(args: argparse.Namespace) -> int:
    """Handle ``worktrail stop``."""
    project_root = ensure_project_root()
    ensure_worktrail_dir(project_root)

    engine = get_engine(project_root)
    session = engine.stop()

    if session is None:
        print("Нет активной сессии для остановки.", file=__import__("sys").stderr)
        return 1

    total_str = fmt_seconds(session.total_seconds)
    print(f"■ Сессия остановлена. Всего: {total_str}")
    return 0


@command("pause", help="Поставить сессию на паузу")
def cmd_pause(args: argparse.Namespace) -> int:
    """Handle ``worktrail pause``."""
    project_root = ensure_project_root()
    ensure_worktrail_dir(project_root)

    engine = get_engine(project_root)
    session = engine.pause()

    if session is None:
        print("Нет активной сессии для паузы.", file=__import__("sys").stderr)
        return 1

    print("⏸ Сессия на паузе.")
    return 0


@command("resume", help="Возобновить приостановленную сессию")
def cmd_resume(args: argparse.Namespace) -> int:
    """Handle ``worktrail resume``."""
    project_root = ensure_project_root()
    ensure_worktrail_dir(project_root)

    engine = get_engine(project_root)
    session = engine.resume()

    if session is None:
        print(
            "Нет приостановленной сессии для возобновления.",
            file=__import__("sys").stderr,
        )
        return 1

    print("▶ Сессия возобновлена.")
    return 0


@command("checkpoint", help="Записать чекпоинт")
@arg("message", help="Сообщение чекпоинта")
@arg("--auto", action="store_true", help=argparse.SUPPRESS)
@arg("--commit", default=None, help=argparse.SUPPRESS)
def cmd_checkpoint(args: argparse.Namespace) -> int:
    """Handle ``worktrail checkpoint <message> [--auto] [--commit <hash>]``."""
    project_root = ensure_project_root()
    ensure_worktrail_dir(project_root)

    message: str = args.message
    source: str = "auto" if args.auto else "manual"
    commit_hash: str | None = args.commit

    engine = get_engine(project_root)
    try:
        cp = engine.checkpoint(message, source=source, commit_hash=commit_hash)
    except RuntimeError as exc:
        print(f"Ошибка: {exc}", file=__import__("sys").stderr)
        return 1

    print(f"✓ Чекпоинт записан: {cp.message}")
    return 0


@command("status", help="Показать текущую сессию или изменить статус задачи")
@arg("task_id", nargs="?", default=None, help="Идентификатор задачи для изменения статуса")
@arg("--set", dest="set_status", default=None,
     choices=["draft", "active", "blocked", "review", "done", "archived", "cancelled"],
     help="Установить статус задачи")
@arg("--note", default=None, help="Примечание при смене статуса")
def cmd_status(args: argparse.Namespace) -> int:
    """Handle ``worktrail status [<task-id> --set <status>]``."""
    project_root = ensure_project_root()
    ensure_worktrail_dir(project_root)

    if args.set_status:
        if args.task_id is None:
            print("Ошибка: укажите task_id для изменения статуса", file=sys.stderr)
            return 1
        db_path = project_root / ".worktrail" / "runtime.db"
        repo = Repository(db_path)
        task = repo.get_task(args.task_id)
        if task is None:
            print(f"Ошибка: задача {args.task_id} не найдена", file=sys.stderr)
            return 1
        repo.update_task_status(args.task_id, args.set_status)
        name_info = f' "{task.name}"' if task.name and task.name != task.id else ""
        note = f" ({args.note})" if args.note else ""
        print(f"Статус задачи {args.task_id}{name_info}: {task.status} → {args.set_status}{note}")
        return 0

    engine = get_engine(project_root)
    info = engine.current()

    if info is None:
        print("Нет активной сессии.")
        return 0

    task = info["task"]
    elapsed_str = fmt_seconds(info["elapsed_seconds"])
    cp_count: int = info["checkpoints_count"]

    task_name = task.name if task else "<неизвестная задача>"
    cp_word = pluralize(cp_count, "чекпоинт", "чекпоинта", "чекпоинтов")

    print(f"Задача {task.id} ({elapsed_str}) — {cp_count} {cp_word}")
    if task_name and task_name != task.id:
        print(f"  Название: {task_name}")
    return 0
