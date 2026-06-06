"""Command handler package for worktrail CLI.

Handler modules are auto-imported in :mod:`worktrail.cli.main` so their
:func:`@command <worktrail.cli.commands.command>` decorators self-register.
"""

from worktrail.cli.handlers import migrate, report, system, task  # noqa: F401
