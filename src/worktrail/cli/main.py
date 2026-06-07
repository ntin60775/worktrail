"""Main CLI entry-point for worktrail.

Plugin-based routing: builds the argument parser dynamically from the
command registry and dispatches to decorated handler functions.

All user-facing text is in Russian.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from worktrail import __version__
from worktrail.cli.commands import get_aliases, get_commands, resolve_command

# Auto-register all handlers via their @command decorators
from worktrail.cli.handlers import archive, explore, initiative, journal, migrate, report, system, task  # noqa: F401


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level argument parser from the command registry.

    Walks the global :data:`_COMMANDS` dict and adds a subparser for each
    registered command.  Any arguments attached via :func:`@arg
    <worktrail.cli.commands.arg>` are forwarded to ``add_argument``.
    """
    parser = argparse.ArgumentParser(
        prog="worktrail",
        description="worktrail — учёт рабочего времени разработчика",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Доступные команды")

    for name, func in sorted(get_commands().items()):
        sub = subparsers.add_parser(name, help=func._help)
        if hasattr(func, "_args"):
            for argspec in func._args:
                sub.add_argument(*argspec.args, **argspec.kwargs)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Main entry-point for the worktrail CLI.

    Args:
        argv: Command-line arguments (defaults to :data:`sys.argv[1:]`).

    Returns:
        Exit code (``0`` for success, ``1`` for error,
        ``130`` on keyboard interrupt).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    handler = resolve_command(args.command)
    if handler is None:
        parser.print_help()
        return 1

    try:
        return handler(args)
    except KeyboardInterrupt:
        print("\nПрервано пользователем.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
