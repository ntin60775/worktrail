"""Initiative management command handlers.

Provides:
* ``initiative`` — create a new initiative (bare form)
* ``initiative list`` — list all initiatives
* ``initiative show`` — show initiative details and subtasks
"""

from __future__ import annotations

import argparse
import re
import sys

from worktrail.cli.commands import (
    arg,
    command,
    ensure_project_root,
    ensure_worktrail_dir,
)
from worktrail.core import Repository


def _generate_initiative_id(repo: Repository) -> str:
    """Generate the next initiative ID like INIT-001, INIT-002, etc."""
    initiatives = repo.list_tasks(kind="initiative")
    max_num = 0
    for t in initiatives:
        m = re.match(r"INIT-(\d+)", t.id)
        if m:
            num = int(m.group(1))
            if num > max_num:
                max_num = num
    return f"INIT-{max_num + 1:03d}"


@command("initiative", help="Создать новую инициативу")
@arg("name", help="Название инициативы")
def cmd_initiative(args: argparse.Namespace) -> int:
    """Handle ``worktrail initiative <name>``."""
    project_root = ensure_project_root()
    ensure_worktrail_dir(project_root)

    db_path = project_root / ".worktrail" / "runtime.db"
    repo = Repository(db_path)

    initiative_id = _generate_initiative_id(repo)
    task = repo.create_task(
        task_id=initiative_id,
        name=args.name,
        kind="initiative",
        status="active",
    )

    print(f"Инициатива создана: {task.id} — {task.name}")
    return 0


@command("initiative list", help="Список инициатив")
def cmd_initiative_list(args: argparse.Namespace) -> int:
    """Handle ``worktrail initiative list``."""
    project_root = ensure_project_root()
    ensure_worktrail_dir(project_root)

    db_path = project_root / ".worktrail" / "runtime.db"
    repo = Repository(db_path)

    initiatives = repo.list_tasks(kind="initiative")
    if not initiatives:
        print("Нет инициатив")
        return 0

    for t in initiatives:
        subtasks = repo.get_subtasks(t.id)
        print(f"  {t.id}: {t.name} ({len(subtasks)} задач, статус: {t.status})")
    return 0


@command("initiative show", help="Показать инициативу")
@arg("initiative_id", help="Идентификатор инициативы (например, INIT-001)")
def cmd_initiative_show(args: argparse.Namespace) -> int:
    """Handle ``worktrail initiative show <initiative-id>``."""
    project_root = ensure_project_root()
    ensure_worktrail_dir(project_root)

    db_path = project_root / ".worktrail" / "runtime.db"
    repo = Repository(db_path)

    task = repo.get_task(args.initiative_id)
    if task is None:
        print(f"Ошибка: инициатива {args.initiative_id} не найдена", file=sys.stderr)
        return 1

    if task.kind != "initiative":
        print(f"Ошибка: {args.initiative_id} не является инициативой", file=sys.stderr)
        return 1

    print(f"Инициатива: {task.id} — {task.name}")
    print(f"Статус: {task.status}")
    subtasks = repo.get_subtasks(task.id)
    if subtasks:
        print(f"Задачи ({len(subtasks)}):")
        for st in subtasks:
            print(f"  - {st.id}: {st.name} [{st.status}]")
    else:
        print("Задач нет")
    return 0
