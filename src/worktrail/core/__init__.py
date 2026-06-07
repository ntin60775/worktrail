"""worktrail.core — data models, SQLite schema, configuration, and repository.

This module is the foundation of the worktrail runtime. It provides:

* **Models** — :class:`Task`, :class:`Session`, :class:`Checkpoint`, :class:`JournalEntry`, :class:`Config`
* **Database** — connection helpers, schema creation, and migrations
* **Repository** — CRUD operations for all entities
* **Config** — YAML-based configuration loading / saving
* **Discovery** — project-root discovery by walking the directory tree
"""

from pathlib import Path
from typing import Optional

from worktrail.core.config import get_config_path, load_config, save_config
from worktrail.core.db import (
    get_connection,
    get_db_path,
    init_db,
    init_worktrail_dir,
    migrate_schema,
)
from worktrail.core.models import Checkpoint, Config, JournalEntry, Session, Task
from worktrail.core.repository import Repository

__all__ = [
    # Models
    "Task",
    "Session",
    "Checkpoint",
    "JournalEntry",
    "Config",
    # Database
    "get_db_path",
    "init_db",
    "init_worktrail_dir",
    "migrate_schema",
    "get_connection",
    # Repository
    "Repository",
    # Config
    "load_config",
    "save_config",
    "get_config_path",
    # Discovery
    "find_project_root",
]


# ---------------------------------------------------------------------------
# Project-root discovery
# ---------------------------------------------------------------------------


def find_project_root(marker: str = ".git", cwd: Optional[Path] = None) -> Path | None:
    """Walk upward from *cwd* looking for a directory that contains *marker*.

    The *marker* can be either a file or a directory inside the candidate
    parent directory.

    Args:
        marker: Name of the file/directory that identifies a project root.
            Defaults to ``'.git'``.
        cwd: Starting directory.  Defaults to the current working directory.

    Returns:
        The absolute :class:`~pathlib.Path` of the project root, or ``None``
        if no matching directory was found.
    """
    start = (cwd or Path.cwd()).resolve()
    for directory in [start, *start.parents]:
        candidate = directory / marker
        if candidate.exists():
            return directory
    return None
