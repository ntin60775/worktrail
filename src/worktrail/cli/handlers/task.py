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

from worktrail.cli.commands import (
    arg,
    command,
    ensure_project_root,
    ensure_worktrail_dir,
    fmt_seconds,
    get_engine,
    pluralize,
)


@command("start", help="Начать сессию для задачи")
@arg("task_id", help="Идентификатор задачи (например, TASK-001)")
@arg("--name", default=None, help="Название задачи")
def cmd_start(args: argparse.Namespace) -> int:
    """Handle ``worktrail start <task-id> [--name ...]``."""
    project_root = ensure_project_root()
    ensure_worktrail_dir(project_root)

    task_id: str = args.task_id
    task_name: str | None = args.name

    engine = get_engine(project_root)
    engine.start(task_id, task_name)

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


@command("status", help="Показать текущую сессию и время")
def cmd_status(args: argparse.Namespace) -> int:
    """Handle ``worktrail status``."""
    project_root = ensure_project_root()
    ensure_worktrail_dir(project_root)

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
