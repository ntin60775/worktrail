"""Archive command handler.

Provides:

* ``archive`` — move a done task to archive
"""

from __future__ import annotations

import argparse
import sys

from worktrail.cli.commands import arg, command, ensure_project_root, ensure_worktrail_dir
from worktrail.core import Repository


@command("archive", help="Переместить задачу в архив")
@arg("task_id", help="Идентификатор задачи (например, TASK-001)")
@arg("--force", action="store_true", help="Архивировать, даже если задача не завершена")
def cmd_archive(args: argparse.Namespace) -> int:
    """Handle ``worktrail archive <task-id> [--force]``."""
    project_root = ensure_project_root()
    ensure_worktrail_dir(project_root)

    db_path = project_root / ".worktrail" / "runtime.db"
    repo = Repository(db_path)

    task = repo.get_task(args.task_id)
    if task is None:
        print(f"Ошибка: задача {args.task_id} не найдена", file=sys.stderr)
        return 1

    if not args.force and task.status != "done":
        print(
            f"Ошибка: задача {args.task_id} не завершена (статус: {task.status}). "
            f"Используйте --force для принудительного архивирования",
            file=sys.stderr,
        )
        return 1

    repo.archive_task(args.task_id)
    print(f"Задача {args.task_id} перемещена в архив")
    return 0
