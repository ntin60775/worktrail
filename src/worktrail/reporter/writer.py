"""Output writers for worktrail reports.

Provides two renderers:

* :func:`render_terminal` — pretty-print a report to the terminal using box-drawing characters.
* :func:`render_markdown` — produce a Markdown representation of the report.

Both renderers use the same report structure but adapt it to their respective output formats.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from worktrail.reporter.formatter import Block, Report, ReportItem


def _format_hours(hours: float) -> str:
    """Format hours with exactly one decimal place, Russian suffix."""
    return f"{hours:.1f}ч"


# ---------------------------------------------------------------------------
# Terminal renderer
# ---------------------------------------------------------------------------


def render_terminal(report: Report) -> str:
    """Render a report as a human-readable terminal string.

    Uses box-drawing characters for a tree-like visual hierarchy.

    Args:
        report: The report to render.

    Returns:
        Multi-line string ready for ``print()``.
    """
    lines: list[str] = []

    # Title
    lines.append(report.title)
    lines.append("═" * len(report.title))
    lines.append("")

    if not report.items:
        lines.append("Нет данных за указанный период.")
        lines.append("")
        lines.append("─" * 20)
        lines.append(f"{'День' if '—' not in report.period else 'Неделя'}: 0.0ч")
        return "\n".join(lines)

    for item in report.items:
        # Task header
        lines.append(f"Задача {item.task_id}: {item.task_name}")

        # Blocks as tree items
        for idx, block in enumerate(item.blocks):
            is_last = idx == len(item.blocks) - 1
            prefix = "└──" if is_last else "├──"
            lines.append(f"{prefix} [{_format_hours(block.hours)}] {block.description}")

        # Task summary
        lines.append(f"Итого: {_format_hours(item.total_hours)} | Статус: {item.status}")
        lines.append("")

    # Grand total
    lines.append("─" * 20)
    period_label = "Неделя" if "—" in report.period else "День"
    lines.append(f"{period_label}: {_format_hours(report.total_hours)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def render_markdown(report: Report) -> str:
    """Render a report as a Markdown document.

    Uses headers, bullet lists, and horizontal rules for structure.

    Args:
        report: The report to render.

    Returns:
        Multi-line Markdown string.
    """
    lines: list[str] = []

    # Title
    lines.append(f"# {report.title}")
    lines.append("")
    lines.append(f"**Период:** {report.period}")
    lines.append("")

    if not report.items:
        lines.append("*Нет данных за указанный период.*")
        lines.append("")
        period_label = "День" if "—" not in report.period else "Неделя"
        lines.append(f"**{period_label}:** 0.0ч")
        return "\n".join(lines)

    for item in report.items:
        # Task header as H2
        lines.append(f"## {item.task_id}: {item.task_name}")
        lines.append("")

        # Blocks as bullet list
        for block in item.blocks:
            lines.append(f"- **[{_format_hours(block.hours)}]** {block.description}")

        lines.append("")
        lines.append(
            f"**Итого:** {_format_hours(item.total_hours)} | "
            f"**Статус:** {item.status}"
        )
        lines.append("")

    # Grand total
    lines.append("---")
    period_label = "Неделя" if "—" in report.period else "День"
    lines.append(f"**{period_label}:** {_format_hours(report.total_hours)}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# File writer
# ---------------------------------------------------------------------------


def write_report_to_file(report: Report, output_path: Path) -> Path:
    """Save a report as a Markdown file.

    The parent directory is created automatically if it does not exist.

    Args:
        report: The report to save.
        output_path: Destination file path.

    Returns:
        The path the file was written to.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(report)
    output_path.write_text(markdown, encoding="utf-8")
    return output_path
