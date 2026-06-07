"""Report formatting logic for worktrail reporter module.

Provides :class:`Report`, :class:`ReportItem`, and :class:`Block` dataclasses,
along with checkpoint grouping logic that merges checkpoints within a
30-minute window into a single block.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from worktrail.core.models import Checkpoint, Session

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GROUPING_WINDOW_MINUTES: int = 30
DEFAULT_BLOCK_MINUTES: int = 15
MAX_DESCRIPTION_LENGTH: int = 100


# ---------------------------------------------------------------------------
# Report dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Block:
    """A grouped block of checkpoints representing a contiguous work period.

    Attributes:
        description: Joined checkpoint messages (truncated to 100 chars).
        hours: Duration of the block in hours (one decimal precision).
    """

    description: str
    hours: float


@dataclass
class ReportItem:
    """A report entry for a single task.

    Attributes:
        task_id: Task identifier (e.g. 'TASK-001').
        task_name: Human-readable task name.
        total_hours: Sum of all block hours for this task.
        blocks: Grouped checkpoint blocks.
        status: Task status in Russian.
        journal_entries: Optional list of journal entry dicts with keys
            kind, title, body, created_at.
    """
    task_id: str
    task_name: str
    total_hours: float
    blocks: list[Block]
    status: str
    journal_entries: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class Report:
    """A complete report covering a specific period.

    Attributes:
        title: Report title in Russian (e.g. 'Отчёт за 29.05.2026').
        period: Period description in Russian.
        total_hours: Sum of hours across all tasks.
        items: Per-task report items.
    """

    title: str
    period: str
    total_hours: float
    items: list[ReportItem]


# ---------------------------------------------------------------------------
# Checkpoint grouping logic
# ---------------------------------------------------------------------------


def _parse_iso(timestamp: str) -> datetime:
    """Parse an ISO8601 timestamp string into a timezone-aware datetime."""
    ts = timestamp.replace("Z", "+00:00")
    return datetime.fromisoformat(ts)


def _format_hours(hours: float) -> str:
    """Format hours with exactly one decimal place, Russian suffix."""
    return f"{hours:.1f}ч"


def _group_checkpoints(
    checkpoints: list[Checkpoint],
    session_end: Optional[datetime] = None,
) -> list[Block]:
    """Group checkpoints into blocks using the 30-minute window rule.

    Checkpoints within ``GROUPING_WINDOW_MINUTES`` (30) of each other are
    merged into a single block.  Each block's duration is the time from its
    first checkpoint to the first checkpoint of the *next* block (or the
    session end / 15-minute default for the final block).

    Args:
        checkpoints: List of checkpoints ordered by timestamp.
        session_end: Optional session end time used for the last block.

    Returns:
        List of :class:`Block` instances.
    """
    if not checkpoints:
        return []

    # Ensure chronological order
    sorted_cps = sorted(checkpoints, key=lambda cp: cp.timestamp)
    parsed_times = [_parse_iso(cp.timestamp) for cp in sorted_cps]

    # Step 1: group checkpoint *indices* by the 30-minute window
    groups: list[list[int]] = []
    current_group: list[int] = [0]

    for i in range(1, len(sorted_cps)):
        gap = (parsed_times[i] - parsed_times[i - 1]).total_seconds()
        if gap <= GROUPING_WINDOW_MINUTES * 60:
            # Still within the window — extend current group
            current_group.append(i)
        else:
            # Gap exceeded the window — start a new group
            groups.append(current_group)
            current_group = [i]
    groups.append(current_group)

    # Step 2: build blocks from groups
    blocks: list[Block] = []
    for g_idx, group in enumerate(groups):
        first_cp_time = parsed_times[group[0]]

        # Determine duration
        if g_idx + 1 < len(groups):
            # There is a next group — duration = time to next group's first checkpoint
            next_group_first_time = parsed_times[groups[g_idx + 1][0]]
            duration_seconds = (next_group_first_time - first_cp_time).total_seconds()
        else:
            # Last group — use remaining time to session end, or default
            if session_end is not None:
                duration_seconds = max(0, (session_end - first_cp_time).total_seconds())
            else:
                duration_seconds = DEFAULT_BLOCK_MINUTES * 60

        duration_hours = round(duration_seconds / 3600, 1)
        duration_hours = max(0.0, duration_hours)

        # Build description: join messages with "; ", cap at 100 chars
        messages = [sorted_cps[i].message for i in group]
        description = "; ".join(messages)
        if len(description) > MAX_DESCRIPTION_LENGTH:
            description = description[: MAX_DESCRIPTION_LENGTH - 3] + "..."

        blocks.append(Block(description=description, hours=duration_hours))

    return blocks


def _translate_status(status: str) -> str:
    """Translate a task status code into a human-readable Russian string."""
    mapping = {
        "active": "в работе",
        "done": "завершена",
        "paused": "на паузе",
        "archived": "в архиве",
    }
    return mapping.get(status, status)


def build_report_item(
    task_id: str,
    task_name: str,
    task_status: str,
    sessions_with_checkpoints: list[tuple[Session, list[Checkpoint]]],
) -> ReportItem:
    """Build a :class:`ReportItem` from a task's sessions and checkpoints.

    All checkpoints across all sessions are collected and grouped into blocks,
    then aggregated into a single report item.

    Args:
        task_id: Task identifier.
        task_name: Human-readable task name.
        task_status: Raw status code from the database.
        sessions_with_checkpoints: Tuples of (session, checkpoints_for_session).

    Returns:
        A populated :class:`ReportItem`.
    """
    all_blocks: list[Block] = []

    for session, checkpoints in sessions_with_checkpoints:
        if not checkpoints:
            # Session with no checkpoints — account using total_seconds if available
            if session.total_seconds and session.total_seconds > 0:
                hours = round(session.total_seconds / 3600, 1)
                all_blocks.append(Block(description="Работа без чекпоинтов", hours=hours))
            continue

        session_end = None
        if session.ended_at:
            try:
                session_end = _parse_iso(session.ended_at)
            except (ValueError, TypeError):
                session_end = None

        blocks = _group_checkpoints(checkpoints, session_end=session_end)
        all_blocks.extend(blocks)

    total_hours = round(sum(b.hours for b in all_blocks), 1)

    return ReportItem(
        task_id=task_id,
        task_name=task_name,
        total_hours=total_hours,
        blocks=all_blocks,
        status=_translate_status(task_status),
    )
