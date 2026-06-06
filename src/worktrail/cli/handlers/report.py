"""Report generation command handler.

Provides:
* ``report`` — generate daily, weekly, or task-specific reports
"""

from __future__ import annotations

import argparse

from worktrail.cli.commands import (
    arg,
    command,
    ensure_project_root,
    ensure_worktrail_dir,
)
from worktrail.core import Repository
from worktrail.reporter import ReportGenerator, render_terminal


@command("report", help="Сгенерировать отчёт")
@arg("--today", action="store_true", help="Отчёт за сегодня (по умолчанию)")
@arg("--week", action="store_true", help="Отчёт за текущую неделю")
@arg("--task", default=None, help="Отчёт по конкретной задаче")
@arg("--date", default=None, help="Отчёт за дату (YYYY-MM-DD)")
@arg("--save", action="store_true", help="Сохранить отчёт в .worktrail/reports/")
def cmd_report(args: argparse.Namespace) -> int:
    """Handle ``worktrail report`` with various filters."""
    project_root = ensure_project_root()
    ensure_worktrail_dir(project_root)

    db_path = project_root / ".worktrail" / "runtime.db"
    repo = Repository(db_path)
    generator = ReportGenerator(repo)

    # Determine which report to generate
    if args.task:
        try:
            report = generator.generate_task_report(args.task)
        except ValueError as exc:
            print(f"Ошибка: {exc}", file=__import__("sys").stderr)
            return 1
    elif args.week:
        report = generator.generate_week_report()
    elif args.date:
        report = generator.generate_daily_report(args.date)
    else:
        # Default: today
        report = generator.generate_daily_report()

    # Render to terminal
    print(render_terminal(report))

    # Save if requested
    if args.save:
        output_path = generator.save_report(report)
        print(f"\n✓ Отчёт сохранён: {output_path}")

    return 0
