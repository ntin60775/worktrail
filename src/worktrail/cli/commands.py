"""CLI command registry and decorators for the plugin-based command system.

Provides:
* :func:`command` — decorator to register a CLI command
* :func:`arg` — decorator to register arguments for a command
* :func:`get_commands` — retrieve all registered commands
* :func:`get_aliases` — retrieve command aliases
* :func:`resolve_command` — resolve a name (or alias) to a handler function
* Shared helper utilities used by handlers
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from worktrail.core import Repository
from worktrail.git_bridge import get_repo_root
from worktrail.tracker import TrackerEngine

# ---------------------------------------------------------------------------
# Argument specification
# ---------------------------------------------------------------------------


@dataclass
class ArgSpec:
    """Specification for a single argparse argument.

    Attributes:
        args: Positional argument flags (e.g. ``["--name"]``).
        kwargs: Keyword arguments forwarded to
            :meth:`argparse.ArgumentParser.add_argument`.
    """

    args: list[str] = field(default_factory=list)
    kwargs: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_COMMANDS: dict[str, Callable] = {}
_ALIASES: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


def command(
    name: str,
    help: str,
    aliases: list[str] | None = None,
) -> Callable:
    """Register a CLI command.

    Args:
        name: Primary command name (e.g. ``"start"``).
        help: Short help text displayed in the subparser list.
        aliases: Optional list of alias names that resolve to *name*.

    Returns:
        A decorator that registers the wrapped function.
    """
    def decorator(func: Callable) -> Callable:
        _COMMANDS[name] = func
        func._help = help
        if aliases:
            for alias in aliases:
                _ALIASES[alias] = name
        return func
    return decorator


def arg(*args: str, **kwargs: Any) -> Callable:
    """Register an argparse argument for a command.

    Usage::

        @command("start", help="Start a task")
        @arg("task_id", help="Task identifier")
        @arg("--name", default=None, help="Optional task name")
        def cmd_start(args):
            ...

    Args:
        *args: Positional argument flags (e.g. ``"task_id"`` or ``"--name"``).
        **kwargs: Keyword arguments forwarded to ``add_argument``.

    Returns:
        A decorator that attaches the argument spec to the wrapped function.
    """
    def decorator(func: Callable) -> Callable:
        if not hasattr(func, "_args"):
            func._args: list[ArgSpec] = []
        func._args.append(ArgSpec(list(args), kwargs))
        return func
    return decorator


# ---------------------------------------------------------------------------
# Registry queries
# ---------------------------------------------------------------------------


def get_commands() -> dict[str, Callable]:
    """Return a shallow copy of the registered commands mapping.

    Returns:
        Mapping from command name to handler function.
    """
    return _COMMANDS.copy()


def get_aliases() -> dict[str, str]:
    """Return a shallow copy of the aliases mapping.

    Returns:
        Mapping from alias name to primary command name.
    """
    return _ALIASES.copy()


def resolve_command(name: str) -> Callable | None:
    """Resolve a command name (or alias) to its handler function.

    Args:
        name: Command name or alias.

    Returns:
        The handler function, or ``None`` if not found.
    """
    if name in _COMMANDS:
        return _COMMANDS[name]
    if name in _ALIASES:
        return _COMMANDS[_ALIASES[name]]
    return None


# ---------------------------------------------------------------------------
# Shared helpers used by multiple handlers
# ---------------------------------------------------------------------------


def find_project_root() -> Path | None:
    """Walk up from *cwd* to find a directory containing ``.worktrail/`` or ``.git/``.

    Prefers directories that contain ``.worktrail/``; falls back to the git
    repository root.

    Returns:
        Absolute :class:`~pathlib.Path` of the project root, or ``None``.
    """
    cwd = Path.cwd().resolve()
    for directory in [cwd, *cwd.parents]:
        if (directory / ".worktrail").is_dir():
            return directory
    return get_repo_root()


def ensure_project_root() -> Path:
    """Like :func:`find_project_root` but prints an error and exits when ``None``.

    Returns:
        Absolute path to the project root.
    """
    root = find_project_root()
    if root is None:
        print(
            "Ошибка: не найден git-репозиторий. "
            "Запустите 'git init' или выполните команду внутри репо.",
            file=sys.stderr,
        )
        sys.exit(1)
    return root


def ensure_worktrail_dir(project_root: Path) -> None:
    """Print an error and exit if ``.worktrail/`` does not exist.

    Args:
        project_root: The discovered project root path.
    """
    if not (project_root / ".worktrail").is_dir():
        print(
            f"Ошибка: worktrail не инициализирован в {project_root}. "
            "Запустите 'worktrail init'.",
            file=sys.stderr,
        )
        sys.exit(1)


def fmt_seconds(total_seconds: int) -> str:
    """Format seconds as a human-readable Russian string.

    Examples::

        >>> fmt_seconds(8100)
        '2ч 15м'
        >>> fmt_seconds(45)
        '45с'
    """
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}ч")
    if minutes:
        parts.append(f"{minutes}м")
    if not parts:
        parts.append(f"{seconds}с")
    return " ".join(parts)


def get_engine(project_root: Path) -> TrackerEngine:
    """Create a :class:`TrackerEngine` bound to *project_root*.

    Args:
        project_root: Absolute path to the project root.

    Returns:
        Configured :class:`TrackerEngine` instance.
    """
    db_path = project_root / ".worktrail" / "runtime.db"
    repo = Repository(db_path)
    return TrackerEngine(repo=repo, project_root=project_root)


def pluralize(n: int, one: str, few: str, many: str) -> str:
    """Russian pluralization helper.

    Args:
        n: The number to pluralize for.
        one: Form for ``n % 10 == 1 and n % 100 != 11``.
        few: Form for ``2 <= n % 10 <= 4`` (except teens).
        many: Default form.

    Returns:
        The appropriate Russian plural form.
    """
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return few
    return many
