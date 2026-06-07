"""SQLite database connection, schema creation, and migration utilities.

All datetime values are stored as ISO8601 strings (UTC).
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional


# ---------------------------------------------------------------------------
# Schema definition
# ---------------------------------------------------------------------------

_SCHEMA_SQL: str = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'active', 'blocked', 'review',
                          'delivery', 'done', 'archived', 'cancelled')),
    parent_id TEXT REFERENCES tasks(id),
    kind TEXT NOT NULL DEFAULT 'task'
        CHECK (kind IN ('task', 'exploration', 'initiative')),
    branch TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    total_seconds INTEGER DEFAULT 0,
    CHECK (status IN ('active', 'paused', 'ended'))
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    message TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    commit_hash TEXT
);

CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    kind TEXT NOT NULL
        CHECK (kind IN ('proposal', 'design', 'spec', 'decision', 'note', 'artifact')),
    title TEXT,
    body TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_db_path(cwd: Optional[Path] = None) -> Path:
    """Walk upward from *cwd* looking for ``.worktrail/runtime.db``.

    Args:
        cwd: Starting directory. Defaults to the current working directory.

    Returns:
        Absolute path to the SQLite database file.

    Raises:
        FileNotFoundError: No ``.worktrail/`` directory is found in the
            directory tree.
    """
    # Local import to avoid circular imports during package initialisation.
    from worktrail.core import find_project_root

    start = (cwd or Path.cwd()).resolve()
    # Prefer a directory that already has .worktrail/...
    root = find_project_root(".worktrail", cwd=start)
    if root is not None:
        candidate = root / ".worktrail" / "runtime.db"
        if candidate.exists():
            return candidate.resolve()
    # ...fallback to any git repo (user may have cwd inside a sub-dir).
    root = find_project_root(".git", cwd=start)
    if root is not None:
        candidate = root / ".worktrail" / "runtime.db"
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(
        "Could not find .worktrail/runtime.db. "
        "Run 'worktrail init' first."
    )


def migrate_schema(db_path: Path) -> None:
    """Apply schema migrations for existing databases.

    Detects the current schema version and applies any missing ALTER TABLE
    statements to bring the database up to the latest version.  Safe to call
    on a freshly-created database — it will be a no-op.

    Args:
        db_path: Path to the SQLite database file.
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(tasks)")}
        if "kind" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN kind TEXT NOT NULL DEFAULT 'task'")
        if "branch" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN branch TEXT")
        conn.commit()

def init_db(db_path: Path) -> None:
    """Create tables (if they do not already exist) in *db_path*.

    After table creation, applies any pending schema migrations for
    databases created with an older version of worktrail.

    Args:
        db_path: Path to the SQLite database file.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
    migrate_schema(db_path)


def init_worktrail_dir(project_root: Path) -> Path:
    """Create the ``.worktrail/`` directory structure inside *project_root*.

    Creates:
        - ``.worktrail/``
        - ``.worktrail/runtime.db`` (with schema)
        - ``.worktrail/config.yaml`` (with default values)
        - ``.worktrail/reports/``

    Args:
        project_root: Root directory of the git project.

    Returns:
        Path to the newly created ``.worktrail/`` directory.
    """
    worktrail_dir = project_root / ".worktrail"
    worktrail_dir.mkdir(parents=True, exist_ok=True)

    db_path = worktrail_dir / "runtime.db"
    init_db(db_path)

    reports_dir = worktrail_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    config_path = worktrail_dir / "config.yaml"
    if not config_path.exists():
        default_config = (
            "idle_timeout: 900\n"
            "git_hooks_enabled: true\n"
        )
        config_path.write_text(default_config, encoding="utf-8")

    hooks_dir = worktrail_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    return worktrail_dir


# ---------------------------------------------------------------------------
# Connection context manager
# ---------------------------------------------------------------------------


@contextmanager
def get_connection(
    db_path: Optional[Path] = None,
) -> Generator[sqlite3.Connection, None, None]:
    """Yield a SQLite connection with row-factory set to ``sqlite3.Row``.

    If *db_path* is omitted, ``get_db_path()`` is used to locate the
    database automatically.

    Args:
        db_path: Explicit path to the SQLite database.

    Yields:
        An open ``sqlite3.Connection``.
    """
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
