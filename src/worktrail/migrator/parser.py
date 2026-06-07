"""Parser for task-centric-knowledge v1 format files.

Handles ``task.md`` and ``worklog.md`` files found in
``knowledge/tasks/TASK-*/`` directories.

* ``parse_v1_task`` extracts task metadata from frontmatter or tables.
* ``parse_v1_worklog`` extracts dated time entries from worklog files.

Both Russian and English status names are normalised to worktrail's
seven canonical values: ``draft``, ``active``, ``blocked``, ``review``,
``done``, ``archived``, ``cancelled``.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _parse_frontmatter(content: str) -> Optional[Dict[str, Any]]:
    """Parse YAML frontmatter from markdown content.

    Falls back to a basic key:value parser when PyYAML is not installed.

    Args:
        content: Raw markdown text.

    Returns:
        Parsed frontmatter dict, or ``None`` if no frontmatter is found.
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return None

    frontmatter_text = match.group(1)

    if yaml is not None:
        try:
            data = yaml.safe_load(frontmatter_text)
            if isinstance(data, dict):
                return data
        except yaml.YAMLError:
            pass
        return None

    # Fallback: basic key:value parser (one level, no nesting)
    result: Dict[str, Any] = {}
    for line in frontmatter_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if value.lower() in ("true", "yes"):
                value = True
            elif value.lower() in ("false", "no"):
                value = False
            elif value.isdigit():
                value = int(value)
            result[key] = value
    return result if result else None

# ---------------------------------------------------------------------------
# Status normalisation
# ---------------------------------------------------------------------------

# Maps various Russian/English status strings to canonical worktrail values.
_STATUS_MAP: Dict[str, str] = {
    # Russian
    "в работе": "active",
    "активна": "active",
    "активный": "active",
    "начата": "active",
    "пауза": "blocked",
    "приостановлена": "blocked",
    "черновик": "draft",
    "завершена": "done",
    "готово": "done",
    "выполнена": "done",
    "закрыта": "done",
    "на проверке": "review",
    "заблокирована": "blocked",
    "отменена": "cancelled",
    "архив": "archived",
    "в архиве": "archived",
    # English
    "active": "active",
    "in progress": "active",
    "started": "active",
    "paused": "blocked",
    "pause": "blocked",
    "on hold": "blocked",
    "draft": "draft",
    "blocked": "blocked",
    "review": "review",
    "done": "done",
    "completed": "done",
    "finished": "done",
    "closed": "done",
    "cancelled": "cancelled",
    "archived": "archived",
}

_VALID_ID_RE = re.compile(r"^TASK-\d+(-\d+)?((\.\d+)+)?$")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


# Regex for frontmatter delimiters
_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n",
    re.DOTALL,
)

# Regex for markdown table row: | key | value |
_TABLE_ROW_RE = re.compile(r"\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|")

# Regex for worklog entries:
# - "2024-01-15: сообщение"  or  "2024-01-15 — сообщение"
# With optional duration: "[2h]", "[30m]", "[1.5h]", "[2 ч]", "[30 мин]"
_WORKLOG_ENTRY_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})\s*[:\-—]\s*(.*?)$",
    re.MULTILINE,
)
_DURATION_RE = re.compile(
    r"\[(\d+(?:\.\d+)?)\s*(h|ч|m|мин|hours?|minutes?)\]",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_status(raw: Optional[str]) -> str:
    """Convert a raw status string to a canonical worktrail status.

    Args:
        raw: The status string from the v1 file (may be Russian or English).

    Returns:
        One of ``'draft'``, ``'active'``, ``'blocked'``, ``'review'``,
        ``'done'``, ``'archived'``, ``'cancelled'``.
        Falls back to ``'draft'`` when the input is unrecognised.
    """
    if not raw:
        return "draft"
    key = raw.strip().lower()
    return _STATUS_MAP.get(key, "draft")


def _extract_task_id_from_path(task_md_path: Path) -> Optional[str]:
    """Derive a task ID from the directory name.

    Typical layout: ``knowledge/tasks/TASK-001-slug/task.md``.

    Args:
        task_md_path: Path to the ``task.md`` file.

    Returns:
        The extracted task ID (e.g. ``'TASK-001'``) or ``None``.
    """
    # Walk up to find a directory that looks like TASK-XXX
    for parent in task_md_path.parents:
        match = re.match(r"(TASK-\d+(?:-\d+)?(?:\.\d+)*)", parent.name, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return None


def _parse_table(content: str) -> Dict[str, str]:
    """Extract key/value pairs from the first markdown table found.

    Only the first table is parsed — subsequent tables are ignored.
    The header row (before the ``|---|---|`` separator) is skipped.
    For tables with >2 columns, only the first two are used (key, value).

    Args:
        content: Raw markdown text.

    Returns:
        Dictionary of lower-cased keys to raw string values.
    """
    result: Dict[str, str] = {}
    lines = content.splitlines()
    in_table = False
    seen_separator = False
    prev_line = ""
    for line in lines:
        stripped = line.strip()
        # Detect separator row: |---|...|
        is_sep = bool(re.match(r"\s*\|[-:\|\s]+\|\s*", stripped))
        if is_sep:
            seen_separator = True
            in_table = True
            continue
        if not stripped.startswith("|"):
            if in_table:
                break  # table ended
            continue
        if not in_table:
            continue
        # Skip the header row (the line immediately before separator)
        # We track prev_line for this
        match = _TABLE_ROW_RE.match(stripped)
        if match:
            key = match.group(1).strip().lower()
            value = match.group(2).strip().strip('`')
            result[key] = value
    return result


def _coerce_date(raw: Any) -> Optional[str]:
    """Convert various date representations to ISO8601 string.

    Args:
        raw: A date string, datetime object, or other value.

    Returns:
        ISO8601 date string, or ``None`` if not parseable.
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.isoformat()
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return datetime(raw.year, raw.month, raw.day, tzinfo=timezone.utc).isoformat()
    raw_str = str(raw).strip()
    # Try ISO format
    try:
        dt = datetime.fromisoformat(raw_str.replace("Z", "+00:00"))
        return dt.isoformat()
    except ValueError:
        pass
    # Try YYYY-MM-DD only
    if _DATE_RE.fullmatch(raw_str):
        return datetime(
            int(raw_str[:4]),
            int(raw_str[5:7]),
            int(raw_str[8:10]),
            tzinfo=timezone.utc,
        ).isoformat()
    return None


def _extract_name_from_content(content: str) -> Optional[str]:
    """Try to extract the task name from the first H1 heading.

    Args:
        content: Raw markdown text.

    Returns:
        The heading text (without ``#``), or ``None``.
    """
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def _parse_duration(text: str) -> Optional[int]:
    """Extract duration in minutes from a text fragment.

    Looks for patterns like ``[2h]``, ``[30m]``, ``[1.5h]``, ``[2 ч]``.

    Args:
        text: The text to scan.

    Returns:
        Duration in minutes, or ``None`` if no duration marker is found.
    """
    match = _DURATION_RE.search(text)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).lower()
    if unit in ("h", "ч", "hours", "hour"):
        return int(value * 60)
    elif unit in ("m", "мин", "minutes", "minute"):
        return int(value)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_v1_task(task_md_path: Path) -> Dict[str, Any]:
    """Parse a v1 ``task.md`` file and return extracted metadata.

    The function first attempts to read YAML frontmatter, then falls back
    to parsing the first markdown table.  The task ID is taken from the
    frontmatter ``id`` field, or derived from the parent directory name
    (``TASK-XXX-slug`` → ``TASK-XXX``).

    Args:
        task_md_path: Path to the ``task.md`` file.

    Returns:
        Dictionary with keys (all optional except ``id``):

        * ``id`` — task identifier (upper-case)
        * ``name`` — human-readable task name
        * ``status`` — canonical status (draft/active/blocked/review/done/archived/cancelled)
        * ``branch`` — associated git branch
        * ``created_at`` — ISO8601 timestamp string
        * ``updated_at`` — ISO8601 timestamp string
        * ``parent_id`` — parent task identifier
        * ``raw`` — the raw frontmatter/table dict for debugging

    Raises:
        FileNotFoundError: If *task_md_path* does not exist.
    """
    if not task_md_path.is_file():
        raise FileNotFoundError(f"Task file not found: {task_md_path}")

    content = task_md_path.read_text(encoding="utf-8")
    return _extract_task_fields(task_md_path, content)





def _extract_task_fields(source_path: Path, content: str) -> Dict[str, Any]:
    """Extract task fields from markdown content.

    First tries YAML frontmatter, then falls back to the first markdown table.
    """
    # 1. Try frontmatter
    raw_data = _parse_frontmatter(content)
    # 2. Fall back to table
    if raw_data is None:
        raw_data = _parse_table(content)
    result: Dict[str, Any] = {"raw": raw_data}

    # --- ID ---
    task_id: Optional[str] = None
    for key in ("id", "task_id", "идентификатор", "id задачи"):
        if raw_data and key in raw_data and raw_data[key]:
            task_id = str(raw_data[key]).strip().upper()
            break
    if task_id is None:
        task_id = _extract_task_id_from_path(source_path)
    if task_id is None:
        raise ValueError(
            f"Cannot determine task ID from {source_path}"
        )
    if task_id and not _VALID_ID_RE.match(task_id):
        raise ValueError(
            f"Invalid task ID format {task_id!r} from {source_path}; "
            f"expected TASK-NNN, TASK-NNN-NNNN, or TASK-NNN-NNNN.N"
        )
    result["id"] = task_id

    # --- Name ---
    name: Optional[str] = None
    for key in ("name", "title", "название", "имя", "заголовок", "краткое имя"):
        if raw_data and key in raw_data and raw_data[key]:
            name = str(raw_data[key]).strip()
            break
    if name is None:
        name = _extract_name_from_content(content)
    if name is None:
        # Fallback: use directory name or task ID
        name = source_path.parent.name
    result["name"] = name

    # --- Status ---
    status_raw: Optional[str] = None
    for key in ("status", "state", "статус", "состояние"):
        if raw_data and key in raw_data and raw_data[key]:
            status_raw = str(raw_data[key]).strip()
            break
    result["status"] = _normalise_status(status_raw)

    # --- Branch ---
    branch: Optional[str] = None
    for key in ("branch", "git_branch", "ветка"):
        if raw_data and key in raw_data and raw_data[key]:
            branch = str(raw_data[key]).strip()
            break
    result["branch"] = branch

    # --- Dates ---
    created_at: Optional[str] = None
    for key in ("created_at", "created", "start_date", "дата создания"):
        if raw_data and key in raw_data and raw_data[key]:
            created_at = _coerce_date(raw_data[key])
            if created_at:
                break
    if created_at is None:
        # Fallback: use file modification time
        mtime = source_path.stat().st_mtime
        created_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    result["created_at"] = created_at

    updated_at: Optional[str] = None
    for key in ("updated_at", "updated", "дата обновления"):
        if raw_data and key in raw_data and raw_data[key]:
            updated_at = _coerce_date(raw_data[key])
            if updated_at:
                break
    result["updated_at"] = updated_at or created_at

    # --- Parent ---
    parent_id: Optional[str] = None
    for key in ("parent_id", "parent", "parent id", "родитель"):
        if raw_data and key in raw_data and raw_data[key]:
            raw_parent = str(raw_data[key]).strip().strip('`').upper()
            # Treat empty markers as no parent
            if raw_parent not in ("", "—", "-", "–", "НЕТ", "NULL", "NONE", "N/A", "Н/Д"):
                parent_id = raw_parent
            break
    result["parent_id"] = parent_id

    return result


def parse_v1_worklog(worklog_path: Path) -> List[Dict[str, Any]]:
    """Parse a v1 ``worklog.md`` file and return a list of time entries.

    Each entry is a dict with:

    * ``date`` — ISO8601 date string (``YYYY-MM-DD``)
    * ``message`` — description of work done
    * ``duration_minutes`` — optional integer duration in minutes

    Supported line formats::

        2024-01-15: Implemented validation
        2024-01-15 — Fixed bug [2h]
        2024-01-15: Review [30m]

    Args:
        worklog_path: Path to the ``worklog.md`` file.

    Returns:
        List of entry dictionaries.  Returns an empty list if the file
        does not exist or contains no recognised entries.
    """
    if not worklog_path.is_file():
        return []

    content = worklog_path.read_text(encoding="utf-8")

    # Try line-based format first (YYYY-MM-DD: message)
    entries = _parse_worklog_lines(content)
    if entries:
        return entries

    # Fall back to narrative format (## YYYY-MM-DD sections)
    return _parse_worklog_narrative(content)


def _parse_worklog_lines(content: str) -> List[Dict[str, Any]]:
    """Parse line-based worklog: ``YYYY-MM-DD: message [2h]``."""
    entries: List[Dict[str, Any]] = []
    for match in _WORKLOG_ENTRY_RE.finditer(content):
        entry_date = match.group(1)
        message = match.group(2).strip()
        duration = _parse_duration(message)
        clean_message = _DURATION_RE.sub("", message).strip()
        entries.append({
            "date": entry_date,
            "message": clean_message,
            "duration_minutes": duration,
        })
    return entries


# Regex for narrative worklog: ## YYYY-MM-DD sections
_WORKLOG_NARRATIVE_RE = re.compile(
    r"^## (\d{4}-\d{2}-\d{2})\s*$(.*?)(?=^## |\Z)",
    re.MULTILINE | re.DOTALL,
)


def _parse_worklog_narrative(content: str) -> List[Dict[str, Any]]:
    """Parse narrative worklog: ``## YYYY-MM-DD`` sections with text body.

    Each section title (## YYYY-MM-DD) becomes a date.  The body text
    of the section becomes the message.  Sub-headings (### ...) are kept.
    """
    entries: List[Dict[str, Any]] = []
    for match in _WORKLOG_NARRATIVE_RE.finditer(content):
        entry_date = match.group(1)
        body = match.group(2).strip()
        if not body:
            continue
        # Take first meaningful line as summary, rest as detail
        lines = body.splitlines()
        message = lines[0].lstrip("# ").strip() if lines else body[:200]
        if len(body) > 500:
            message = body[:500] + "…"
        else:
            message = body
        entries.append({
            "date": entry_date,
            "message": message.strip(),
            "duration_minutes": _parse_duration(body),
        })
    return entries
