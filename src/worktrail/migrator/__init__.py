"""worktrail.migrator — Migration from task-centric-knowledge v1.

Provides the tools needed to migrate legacy ``knowledge/tasks/`` directories
into the worktrail runtime format.

Public API::

    from worktrail.migrator import Migrator, MigrationReport, parse_v1_task, parse_v1_worklog

    migrator = Migrator(
        source_knowledge_path=Path("./knowledge"),
        project_root=Path("."),
    )
    if migrator.validate_source():
        report = migrator.migrate()
        print(report)
"""

from __future__ import annotations

from worktrail.migrator.migrator import MigrationReport, Migrator
from worktrail.migrator.parser import parse_v1_task, parse_v1_worklog

__all__ = [
    "Migrator",
    "MigrationReport",
    "parse_v1_task",
    "parse_v1_worklog",
]
