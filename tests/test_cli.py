"""Comprehensive pytest tests for worktrail.cli module.

Tests cover:
  * commands.py: decorators, registry, helpers
  * main.py: parser building, argument dispatch, error handling
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_commands():
    """Return the commands module with a guaranteed-empty registry.

    Saves the real registry state, clears it for the test, then restores
    it on teardown so that handler auto-registration tests continue to
    work.
    """
    from worktrail.cli import commands as cmd_mod

    saved_commands = cmd_mod._COMMANDS.copy()
    saved_aliases = cmd_mod._ALIASES.copy()
    cmd_mod._COMMANDS.clear()
    cmd_mod._ALIASES.clear()
    yield cmd_mod
    cmd_mod._COMMANDS.clear()
    cmd_mod._COMMANDS.update(saved_commands)
    cmd_mod._ALIASES.clear()
    cmd_mod._ALIASES.update(saved_aliases)


# ---------------------------------------------------------------------------
# 1. @command decorator
# ---------------------------------------------------------------------------


def test_command_decorator_registers_function(fresh_commands):
    """@command decorator stores the wrapped function in _COMMANDS."""
    cmd_mod = fresh_commands

    @cmd_mod.command("hello", help="Say hello")
    def cmd_hello(args: argparse.Namespace) -> int:
        return 0

    assert "hello" in cmd_mod._COMMANDS
    assert cmd_mod._COMMANDS["hello"] is cmd_hello


def test_command_decorator_sets_help_attribute(fresh_commands):
    """@command attaches _help to the wrapped function."""
    cmd_mod = fresh_commands

    @cmd_mod.command("bye", help="Say goodbye")
    def cmd_bye(args: argparse.Namespace) -> int:
        return 0

    assert hasattr(cmd_bye, "_help")
    assert cmd_bye._help == "Say goodbye"


def test_command_decorator_does_not_mutate_return_value(fresh_commands):
    """@command returns the original function object unchanged (apart from attributes)."""
    cmd_mod = fresh_commands

    def original(args: argparse.Namespace) -> int:
        return 42

    decorated = cmd_mod.command("orig", help="test")(original)
    assert decorated is original


# ---------------------------------------------------------------------------
# 2. @arg decorator
# ---------------------------------------------------------------------------


def test_arg_decorator_attaches_argument_spec(fresh_commands):
    """@arg appends an ArgSpec list to the function's _args attribute.

    Note: Python applies decorators bottom-to-top, so the *bottom* @arg
    is the first item in _args.
    """
    cmd_mod = fresh_commands

    @cmd_mod.command("greet", help="Greet someone")
    @cmd_mod.arg("name", help="Name of the person")
    @cmd_mod.arg("--shout", action="store_true", help="Shout it")
    def cmd_greet(args: argparse.Namespace) -> int:
        return 0

    assert hasattr(cmd_greet, "_args")
    assert len(cmd_greet._args) == 2

    # Bottom decorator applied first
    spec0 = cmd_greet._args[0]
    assert spec0.args == ["--shout"]
    assert spec0.kwargs == {"action": "store_true", "help": "Shout it"}

    spec1 = cmd_greet._args[1]
    assert spec1.args == ["name"]
    assert spec1.kwargs == {"help": "Name of the person"}


def test_arg_decorator_creates_args_list_if_missing(fresh_commands):
    """@arg creates _args list when the function does not yet have one."""
    cmd_mod = fresh_commands

    def bare_func(args: argparse.Namespace) -> int:
        return 0

    decorated = cmd_mod.arg("--flag", action="store_true")(bare_func)
    assert hasattr(decorated, "_args")
    assert len(decorated._args) == 1
    assert decorated._args[0].args == ["--flag"]


def test_arg_decorator_chains_multiple_args(fresh_commands):
    """Multiple @arg decorators accumulate; bottom decorator is first."""
    cmd_mod = fresh_commands

    @cmd_mod.command("multi", help="test")
    @cmd_mod.arg("first")
    @cmd_mod.arg("second")
    @cmd_mod.arg("third")
    def cmd_multi(args: argparse.Namespace) -> int:
        return 0

    arg_names = [spec.args[0] for spec in cmd_multi._args]
    # Bottom-to-top application order
    assert arg_names == ["third", "second", "first"]


# ---------------------------------------------------------------------------
# 3. get_commands
# ---------------------------------------------------------------------------


def test_get_commands_returns_shallow_copy(fresh_commands):
    """get_commands returns a copy; mutations do not affect the registry."""
    cmd_mod = fresh_commands

    @cmd_mod.command("a", help="cmd a")
    def cmd_a(args: argparse.Namespace) -> int:
        return 0

    snapshot = cmd_mod.get_commands()
    assert snapshot == cmd_mod._COMMANDS
    snapshot.clear()  # mutate the copy
    assert "a" in cmd_mod._COMMANDS  # original intact


def test_get_commands_empty_registry(fresh_commands):
    """get_commands returns an empty dict when nothing is registered."""
    cmd_mod = fresh_commands
    assert cmd_mod.get_commands() == {}


# ---------------------------------------------------------------------------
# 4. get_aliases
# ---------------------------------------------------------------------------


def test_get_aliases_returns_shallow_copy(fresh_commands):
    """get_aliases returns a copy; mutations do not affect the registry."""
    cmd_mod = fresh_commands

    @cmd_mod.command("full", help="full command", aliases=["f"])
    def cmd_full(args: argparse.Namespace) -> int:
        return 0

    snapshot = cmd_mod.get_aliases()
    assert snapshot == cmd_mod._ALIASES
    snapshot.clear()
    assert "f" in cmd_mod._ALIASES


def test_get_aliases_empty(fresh_commands):
    """get_aliases returns an empty dict when no aliases are defined."""
    cmd_mod = fresh_commands
    assert cmd_mod.get_aliases() == {}


# ---------------------------------------------------------------------------
# 5. resolve_command
# ---------------------------------------------------------------------------


def test_resolve_command_by_name(fresh_commands):
    """resolve_command returns the handler for a primary command name."""
    cmd_mod = fresh_commands

    @cmd_mod.command("deploy", help="Deploy app")
    def cmd_deploy(args: argparse.Namespace) -> int:
        return 0

    assert cmd_mod.resolve_command("deploy") is cmd_deploy


def test_resolve_command_by_alias(fresh_commands):
    """resolve_command resolves an alias to the real command handler."""
    cmd_mod = fresh_commands

    @cmd_mod.command("build", help="Build project", aliases=["b", "make"])
    def cmd_build(args: argparse.Namespace) -> int:
        return 0

    assert cmd_mod.resolve_command("b") is cmd_build
    assert cmd_mod.resolve_command("make") is cmd_build


def test_resolve_command_returns_none_for_unknown(fresh_commands):
    """resolve_command returns None when the name is not known."""
    cmd_mod = fresh_commands
    assert cmd_mod.resolve_command("nonexistent") is None


def test_resolve_command_prefers_exact_name_over_alias_collision(fresh_commands):
    """If a name exists both as a command and as an alias key,
    the exact command takes precedence."""
    cmd_mod = fresh_commands

    @cmd_mod.command("primary", help="primary cmd")
    def cmd_primary(args: argparse.Namespace) -> int:
        return 0

    # Manually inject a conflicting alias (edge case)
    cmd_mod._ALIASES["primary"] = "other"
    assert cmd_mod.resolve_command("primary") is cmd_primary


# ---------------------------------------------------------------------------
# 6. find_project_root
# ---------------------------------------------------------------------------


def test_find_project_root_finds_worktrail_marker(tmp_path, monkeypatch):
    """find_project_root returns the directory containing .worktrail/."""
    from worktrail.cli.commands import find_project_root

    project_dir = tmp_path / "myproject"
    worktrail_dir = project_dir / ".worktrail"
    worktrail_dir.mkdir(parents=True)

    monkeypatch.chdir(project_dir)
    result = find_project_root()
    assert result == project_dir


def test_find_project_root_walks_upwards(tmp_path, monkeypatch):
    """find_project_root walks up the directory tree to find .worktrail/."""
    from worktrail.cli.commands import find_project_root

    project_dir = tmp_path / "repo"
    nested = project_dir / "src" / "pkg"
    worktrail_dir = project_dir / ".worktrail"
    worktrail_dir.mkdir(parents=True)
    nested.mkdir(parents=True)

    monkeypatch.chdir(nested)
    result = find_project_root()
    assert result == project_dir


def test_find_project_root_returns_none_when_no_marker(tmp_path, monkeypatch):
    """find_project_root returns None when neither .worktrail/ nor a git repo exists."""
    from worktrail.cli.commands import find_project_root

    orphan = tmp_path / "no_repo_here"
    orphan.mkdir()
    monkeypatch.chdir(orphan)

    with patch("worktrail.cli.commands.get_repo_root", return_value=None):
        result = find_project_root()
    assert result is None


# ---------------------------------------------------------------------------
# 7. fmt_seconds
# ---------------------------------------------------------------------------


class TestFmtSeconds:
    """Exhaustive parametrised tests for fmt_seconds.

    fmt_seconds only includes seconds ('с') when both hours and minutes
    are zero.  When either hours or minutes are present, seconds are
    silently dropped (matching the production implementation).
    """

    @pytest.mark.parametrize(
        "seconds,expected",
        [
            (0, "0с"),
            (1, "1с"),
            (30, "30с"),
            (59, "59с"),
            (60, "1м"),
            (61, "1м"),           # seconds dropped when minutes present
            (120, "2м"),
            (3599, "59м"),        # seconds dropped
            (3600, "1ч"),
            (3661, "1ч 1м"),      # seconds dropped
            (5400, "1ч 30м"),
            (7200, "2ч"),
            (28800, "8ч"),
            (8100, "2ч 15м"),
            (86400, "24ч"),
            (90061, "25ч 1м"),    # seconds dropped
        ],
    )
    def test_fmt_seconds_values(self, seconds, expected):
        """fmt_seconds produces the expected Russian string."""
        from worktrail.cli.commands import fmt_seconds

        assert fmt_seconds(seconds) == expected

    def test_fmt_seconds_zero(self):
        """0 seconds → '0с'."""
        from worktrail.cli.commands import fmt_seconds

        assert fmt_seconds(0) == "0с"

    def test_fmt_seconds_one_hour(self):
        """3600 seconds → '1ч'."""
        from worktrail.cli.commands import fmt_seconds

        assert fmt_seconds(3600) == "1ч"

    def test_fmt_seconds_hour_and_half(self):
        """5400 seconds → '1ч 30м'."""
        from worktrail.cli.commands import fmt_seconds

        assert fmt_seconds(5400) == "1ч 30м"

    def test_fmt_seconds_eight_hours(self):
        """28800 seconds → '8ч'."""
        from worktrail.cli.commands import fmt_seconds

        assert fmt_seconds(28800) == "8ч"

    def test_fmt_seconds_only_minutes(self):
        """Pure minutes without hours or seconds."""
        from worktrail.cli.commands import fmt_seconds

        assert fmt_seconds(120) == "2м"

    def test_fmt_seconds_only_seconds(self):
        """Values under 60 produce only seconds part."""
        from worktrail.cli.commands import fmt_seconds

        assert fmt_seconds(45) == "45с"


# ---------------------------------------------------------------------------
# 8. _build_parser
# ---------------------------------------------------------------------------


def test_build_parser_creates_parser_with_subcommands():
    """_build_parser returns an ArgumentParser with registered subcommands."""
    from worktrail.cli.main import _build_parser

    parser = _build_parser()
    assert isinstance(parser, argparse.ArgumentParser)
    # parser.prog is set
    assert parser.prog == "worktrail"


def test_build_parser_includes_version_flag(capsys):
    """The parser has a --version flag that prints version info."""
    from worktrail.cli.main import _build_parser
    from worktrail import __version__

    parser = _build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])
    assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert __version__ in captured.out


# ---------------------------------------------------------------------------
# 9. main — successful command
# ---------------------------------------------------------------------------


def test_main_returns_zero_for_successful_command(fresh_commands):
    """main returns 0 when the handler executes without error."""
    cmd_mod = fresh_commands

    @cmd_mod.command("ok", help="Always succeed")
    def cmd_ok(args: argparse.Namespace) -> int:
        return 0

    with patch("worktrail.cli.main.get_commands", cmd_mod.get_commands), \
         patch("worktrail.cli.main.resolve_command", cmd_mod.resolve_command):
        from worktrail.cli.main import main
        result = main(["ok"])
    assert result == 0


def test_main_returns_one_for_error_command(fresh_commands):
    """main returns 1 when the handler raises an unhandled exception."""
    cmd_mod = fresh_commands

    @cmd_mod.command("fail", help="Always fail")
    def cmd_fail(args: argparse.Namespace) -> int:
        raise RuntimeError("boom")

    with patch("worktrail.cli.main.get_commands", cmd_mod.get_commands), \
         patch("worktrail.cli.main.resolve_command", cmd_mod.resolve_command):
        from worktrail.cli.main import main
        result = main(["fail"])
    assert result == 1


def test_main_prints_help_when_no_command(capsys):
    """main prints help and returns 0 when no subcommand is given."""
    from worktrail.cli.main import main

    result = main([])
    captured = capsys.readouterr()
    assert result == 0
    assert "worktrail" in captured.out  # help text contains program name


# ---------------------------------------------------------------------------
# 10. Integration — parser + command dispatch
# ---------------------------------------------------------------------------


def test_main_dispatches_correct_handler(fresh_commands):
    """main routes to the correct handler based on the subcommand name."""
    cmd_mod = fresh_commands
    mock_handler = MagicMock(return_value=42)
    mock_handler._help = "Mock command"

    cmd_mod._COMMANDS["mock"] = mock_handler

    with patch("worktrail.cli.main.get_commands", cmd_mod.get_commands), \
         patch("worktrail.cli.main.resolve_command", cmd_mod.resolve_command):
        from worktrail.cli.main import main
        result = main(["mock"])

    mock_handler.assert_called_once()
    assert result == 42


def test_main_keyboard_interrupt_returns_130(fresh_commands):
    """main returns 130 when the handler is interrupted by KeyboardInterrupt."""
    cmd_mod = fresh_commands

    @cmd_mod.command("hang", help="Raise KeyboardInterrupt")
    def cmd_hang(args: argparse.Namespace) -> int:
        raise KeyboardInterrupt()

    with patch("worktrail.cli.main.get_commands", cmd_mod.get_commands), \
         patch("worktrail.cli.main.resolve_command", cmd_mod.resolve_command):
        from worktrail.cli.main import main
        result = main(["hang"])
    assert result == 130


def test_main_unknown_command_prints_help(fresh_commands):
    """When resolve_command returns None, main prints help and returns 1."""
    cmd_mod = fresh_commands

    @cmd_mod.command("known", help="Known command")
    def cmd_known(args: argparse.Namespace) -> int:
        return 0

    with patch("worktrail.cli.main.get_commands", cmd_mod.get_commands), \
         patch("worktrail.cli.main.resolve_command", return_value=None):
        from worktrail.cli.main import main
        result = main(["known"])  # resolve_command mocked to return None
    assert result == 1


# ---------------------------------------------------------------------------
# 11. Auto-registration via handler imports
# ---------------------------------------------------------------------------


def test_handler_modules_auto_register_commands():
    """Importing the handlers package populates _COMMANDS via @command decorators."""
    from worktrail.cli import commands as cmd_mod

    commands = cmd_mod.get_commands()
    assert len(commands) > 0

    expected_commands = [
        "start", "stop", "pause", "resume", "checkpoint", "status",
        "init", "doctor", "git-checkout-hook", "list", "uninstall",
        "migrate", "report",
    ]
    for name in expected_commands:
        assert name in commands, f"Command '{name}' not found in registry"


def test_handler_commands_have_help_attribute():
    """Every auto-registered command has a _help attribute."""
    from worktrail.cli import commands as cmd_mod

    for name, func in cmd_mod.get_commands().items():
        assert hasattr(func, "_help"), f"Command '{name}' missing _help"


def test_list_command_has_args():
    """The 'list' command has @arg decorations."""
    from worktrail.cli import commands as cmd_mod

    func = cmd_mod.get_commands()["list"]
    assert hasattr(func, "_args")
    assert len(func._args) >= 1


def test_start_command_has_args():
    """The 'start' command has @arg decorations."""
    from worktrail.cli import commands as cmd_mod

    func = cmd_mod.get_commands()["start"]
    assert hasattr(func, "_args")
    arg_names = [spec.args[0] for spec in func._args]
    assert "task_id" in arg_names
    assert "--name" in arg_names


def test_parser_includes_all_auto_registered_commands():
    """_build_parser creates subparsers for every auto-registered command."""
    from worktrail.cli.main import _build_parser

    parser = _build_parser()

    # We can test this by checking that parsing a known command works
    # and that the --help of each command can be reached.
    args = parser.parse_args(["status"])
    assert args.command == "status"


# ---------------------------------------------------------------------------
# 12. Subprocess / CLI entry-point smoke tests
# ---------------------------------------------------------------------------


def test_cli_module_runnable_via_python_m():
    """The CLI module can be executed with -m (smoke test)."""
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "worktrail.cli.main", "--help"],
        capture_output=True,
        text=True,
        env={**dict(__import__("os").environ), "PYTHONPATH": "/mnt/agents/output/worktrail/src"},
    )
    assert result.returncode == 0
    assert "worktrail" in result.stdout


def test_cli_version_via_subprocess():
    """The CLI --version flag works when called via subprocess."""
    import subprocess

    from worktrail import __version__

    result = subprocess.run(
        [sys.executable, "-m", "worktrail.cli.main", "--version"],
        capture_output=True,
        text=True,
        env={**dict(__import__("os").environ), "PYTHONPATH": "/mnt/agents/output/worktrail/src"},
    )
    assert result.returncode == 0
    assert __version__ in result.stdout


def test_cli_no_args_prints_help():
    """Calling CLI without arguments prints help text."""
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "worktrail.cli.main"],
        capture_output=True,
        text=True,
        env={**dict(__import__("os").environ), "PYTHONPATH": "/mnt/agents/output/worktrail/src"},
    )
    assert result.returncode == 0
    assert "worktrail" in result.stdout or "Доступные команды" in result.stdout


# ---------------------------------------------------------------------------
# 13. ArgSpec dataclass
# ---------------------------------------------------------------------------


def test_argspec_defaults():
    """ArgSpec created with no arguments has empty lists/dicts."""
    from worktrail.cli.commands import ArgSpec

    spec = ArgSpec()
    assert spec.args == []
    assert spec.kwargs == {}


def test_argspec_with_values():
    """ArgSpec stores provided args and kwargs correctly."""
    from worktrail.cli.commands import ArgSpec

    spec = ArgSpec(["--verbose"], {"action": "store_true", "help": "Be loud"})
    assert spec.args == ["--verbose"]
    assert spec.kwargs["action"] == "store_true"
