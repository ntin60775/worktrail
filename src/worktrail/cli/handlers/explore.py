"""Exploration task commands.

Provides:
* ``explore`` — create a new exploration task
"""

from __future__ import annotations

import argparse
import re

from worktrail.cli.commands import arg, command, ensure_project_root, ensure_worktrail_dir
from worktrail.core import Repository


_EXP_ID_RE = re.compile(r"^EXP-(\d+)$")


def _next_exploration_id(repo: Repository) -> str:
    """Auto-generate the next exploration task ID (EXP-001, EXP-002, ...)."""
    existing = repo.list_tasks(kind="exploration")
    max_n = 0
    for task in existing:
        m = _EXP_ID_RE.match(task.id)
        if m:
            n = int(m.group(1))
            if n > max_n:
                max_n = n
    return f"EXP-{max_n + 1:03d}"


@command("explore", help="Создать исследование")
@arg("description", help="Тема исследования")
@arg("--parent", default=None, metavar="TASK-ID", help="Родительская задача")
def cmd_explore(args: argparse.Namespace) -> int:
    """Handle ``worktrail explore <description> [--parent TASK-ID]``."""
    project_root = ensure_project_root()
    ensure_worktrail_dir(project_root)

    db_path = project_root / ".worktrail" / "runtime.db"
    repo = Repository(db_path)

    task_id = _next_exploration_id(repo)
    repo.create_task(
        task_id=task_id,
        name=args.description,
        parent_id=args.parent,
        kind="exploration",
        status="active",
    )

    print(f"Исследование создано: {task_id} — {args.description}")
    return 0
