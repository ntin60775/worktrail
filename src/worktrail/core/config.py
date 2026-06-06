"""Configuration loading and persistence for worktrail.

Uses PyYAML to read/write ``config.yaml`` inside the ``.worktrail/`` directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

import json

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

from worktrail.core.db import get_db_path


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG: Dict[str, Any] = {
    "idle_timeout": 900,
    "git_hooks_enabled": True,
}


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------


def get_config_path(cwd: Optional[Path] = None) -> Path:
    """Resolve the path to ``.worktrail/config.yaml``.

    Walks upward from *cwd* (or the current working directory) looking for
    ``.worktrail/`` and returns the path to ``config.yaml`` inside it.

    Args:
        cwd: Starting directory. Defaults to the current working directory.

    Returns:
        Absolute path to ``config.yaml``.
    """
    start = (cwd or Path.cwd()).resolve()
    for directory in [start, *start.parents]:
        candidate = directory / ".worktrail" / "config.yaml"
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(
        "Could not find .worktrail/config.yaml. Run 'worktrail init' first."
    )


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load configuration from YAML (or JSON fallback), merging with defaults.

    Args:
        config_path: Explicit path to ``config.yaml``. If omitted, the file
            is located automatically.

    Returns:
        Dictionary of configuration values with defaults applied for any
        missing keys.
    """
    path = config_path or get_config_path()
    config: Dict[str, Any] = dict(_DEFAULT_CONFIG)
    if path.exists():
        raw = path.read_text(encoding="utf-8")
        if yaml is not None:
            data = yaml.safe_load(raw)
        else:
            # Fallback: PyYAML not installed — try JSON
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = None
        if isinstance(data, dict):
            config.update(data)
    return config


def save_config(config: Dict[str, Any], config_path: Optional[Path] = None) -> None:
    """Save *config* dictionary to YAML file (or JSON fallback).

    Args:
        config: Configuration dictionary to persist.
        config_path: Explicit path to ``config.yaml``. If omitted, the file
            is located automatically.
    """
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        if yaml is not None:
            yaml.dump(config, fh, default_flow_style=False, sort_keys=False)
        else:
            # Fallback: write as JSON with comments
            json.dump(config, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
