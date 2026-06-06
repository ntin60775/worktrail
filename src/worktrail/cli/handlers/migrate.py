"""Migration command handler.

Provides:
* ``migrate`` — migrate data from task-centric-knowledge v1
"""

from __future__ import annotations

import argparse
from pathlib import Path

from worktrail.cli.commands import (
    arg,
    command,
    ensure_project_root,
)
from worktrail.migrator import Migrator


@command("migrate", help="Миграция из task-centric-knowledge v1")
@arg(
    "--from",
    dest="from_path",
    required=True,
    type=Path,
    help="Путь к knowledge/ директории v1",
)
def cmd_migrate(args: argparse.Namespace) -> int:
    """Handle ``worktrail migrate --from <path>``."""
    project_root = ensure_project_root()
    source_path: Path = args.from_path

    if not source_path.exists():
        print(f"Ошибка: путь не найден: {source_path}", file=__import__("sys").stderr)
        return 1

    migrator = Migrator(
        source_knowledge_path=source_path,
        project_root=project_root,
    )
    report = migrator.migrate()

    print(report)
    print()
    print(migrator.get_merge_instructions())
    return 0 if not report.errors else 1
