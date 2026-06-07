"""Journal command handlers.

Provides:
* ``journal`` — add a journal entry to a task
* ``journal list`` — list journal entries for a task
* ``journal show`` — show full details of a journal entry
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


VALID_KINDS = ("proposal", "design", "spec", "decision", "note", "artifact")


# ---------------------------------------------------------------------------
# journal add (top-level "journal")
# ---------------------------------------------------------------------------


@command("journal", help="Добавить запись в журнал задачи")
@arg("task_id", help="Идентификатор задачи (например, TASK-001)")
@arg("--kind", required=True, choices=VALID_KINDS, help="Тип записи")
@arg("--title", default=None, help="Заголовок записи")
@arg("--body", default=None, help="Текст записи (Markdown)")
def cmd_journal_add(args: argparse.Namespace) -> int:
    """Handle ``worktrail journal <task-id> --kind ... [--title ...] [--body ...]``."""
    project_root = ensure_project_root()
    ensure_worktrail_dir(project_root)

    task_id: str = args.task_id
    kind: str = args.kind
    title: str | None = args.title
    body: str | None = args.body

    repo = Repository()
    entry = repo.add_journal_entry(
        task_id=task_id,
        kind=kind,
        title=title,
        body=body,
    )

    kind_label = _translate_kind(kind)
    print(f"✓ Запись [{kind_label}] добавлена в {task_id} (ID: {entry.id})")
    return 0


# ---------------------------------------------------------------------------
# journal list
# ---------------------------------------------------------------------------


@command("journal list", help="Список записей журнала задачи")
@arg("task_id", help="Идентификатор задачи")
def cmd_journal_list(args: argparse.Namespace) -> int:
    """Handle ``worktrail journal list <task-id>``."""
    project_root = ensure_project_root()
    ensure_worktrail_dir(project_root)

    task_id: str = args.task_id

    repo = Repository()
    entries = repo.list_journal_entries(task_id)

    if not entries:
        print(f"В задаче {task_id} нет записей журнала.")
        return 0

    print(f"Записи журнала для {task_id}:")
    for entry in entries:
        kind_label = _translate_kind(entry.kind)
        title_str = f" — {entry.title}" if entry.title else ""
        print(f"  [{entry.id}] {kind_label}{title_str} ({entry.created_at})")

    return 0


# ---------------------------------------------------------------------------
# journal show
# ---------------------------------------------------------------------------


@command("journal show", help="Показать запись журнала")
@arg("entry_id", type=int, help="Идентификатор записи")
@arg("task_id", help="Идентификатор задачи")
def cmd_journal_show(args: argparse.Namespace) -> int:
    """Handle ``worktrail journal show <task-id> <entry-id>``."""
    project_root = ensure_project_root()
    ensure_worktrail_dir(project_root)

    task_id: str = args.task_id
    entry_id: int = args.entry_id

    repo = Repository()
    entry = repo.get_journal_entry(entry_id)

    if entry is None:
        print(f"Запись {entry_id} не найдена.")
        return 1

    kind_label = _translate_kind(entry.kind)
    print(f"Задача:     {entry.task_id}")
    print(f"ID:         {entry.id}")
    print(f"Тип:        {kind_label}")
    print(f"Заголовок:  {entry.title or '—'}")
    print(f"Создано:    {entry.created_at}")
    if entry.body:
        print(f"Содержимое:\n{entry.body}")

    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _translate_kind(kind: str) -> str:
    """Translate a journal entry kind into a Russian label."""
    mapping = {
        "proposal": "Предложение",
        "design": "Дизайн",
        "spec": "Спецификация",
        "decision": "Решение",
        "note": "Заметка",
        "artifact": "Артефакт",
    }
    return mapping.get(kind, kind)
