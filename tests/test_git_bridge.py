"""Comprehensive pytest suite for worktrail.git_bridge (parser + hooks).

Every test that needs a git repository creates a fresh temporary one via
``tempfile.TemporaryDirectory`` + ``git init`` so that we exercise the real
``git`` subprocess helpers rather than mocking them (except where explicitly
noted).
"""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
from pathlib import Path

import pytest

from worktrail.git_bridge.parser import (
    extract_task_from_branch,
    get_current_branch,
    get_last_commit_info,
    get_repo_root,
    is_task_branch,
    run_git,
)
from worktrail.git_bridge.hooks import (
    _WORKTRAIL_HOOK_MARKER,
    _write_hook,
    are_hooks_installed,
    install_hooks,
    remove_hooks,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_git_repo():
    """Yield the Path of a fully-initialised temporary git repository.

    The repo contains one commit on the default branch so that HEAD exists.
    """
    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        subprocess.run(["git", "init"], cwd=str(root), check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=str(root),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=str(root),
            check=True,
            capture_output=True,
        )
        # Create an initial commit so HEAD exists
        (root / "README.md").write_text("# test\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "README.md"], cwd=str(root), check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=str(root),
            check=True,
            capture_output=True,
        )
        yield root


@pytest.fixture
def tmp_non_git_dir():
    """Yield the Path of a plain directory that is *not* a git repository."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td).resolve()


# ---------------------------------------------------------------------------
# parser.py – get_repo_root
# ---------------------------------------------------------------------------


def test_get_repo_root_finds_git_by_walking_up(tmp_git_repo):
    """get_repo_root must locate the repository root from a nested sub-directory."""
    nested = tmp_git_repo / "src" / "deep" / "package"
    nested.mkdir(parents=True)
    # Also create a sub-dir git repo to make sure we walk *up* correctly
    result = get_repo_root(nested)
    assert result is not None
    assert result.resolve() == tmp_git_repo.resolve()


def test_get_repo_root_returns_none_outside_git(tmp_non_git_dir):
    """get_repo_root must return None when started outside any git repository."""
    result = get_repo_root(tmp_non_git_dir)
    assert result is None


def test_get_repo_root_finds_git_from_root_itself(tmp_git_repo):
    """get_repo_root must return the directory itself when called at the repo root."""
    result = get_repo_root(tmp_git_repo)
    assert result is not None
    assert result.resolve() == tmp_git_repo.resolve()


# ---------------------------------------------------------------------------
# parser.py – get_current_branch
# ---------------------------------------------------------------------------


def test_get_current_branch_returns_branch_name(tmp_git_repo):
    """After init the default branch should be detected and returned."""
    branch = get_current_branch(tmp_git_repo)
    # Git default branch name can be "master" or "main" depending on version
    assert branch in ("master", "main")


# ---------------------------------------------------------------------------
# parser.py – extract_task_from_branch
# ---------------------------------------------------------------------------


def test_extract_task_from_branch_standard_slug():
    """Parse a conventional task branch with trailing slug."""
    assert extract_task_from_branch("task/TASK-001-slug") == "TASK-001"


def test_extract_task_from_branch_without_slug():
    """Parse a task branch that has no trailing slug."""
    assert extract_task_from_branch("task/DU-042") == "DU-042"


def test_extract_task_from_branch_cyrillic():
    """Parse a task branch using Cyrillic prefix (e.g. Russian)."""
    assert extract_task_from_branch("task/ЗАКАЗ-2025-имя") == "ЗАКАЗ-2025"


def test_extract_task_from_branch_returns_none_for_non_task_branch():
    """Non-task branches must yield None."""
    assert extract_task_from_branch("feature/something") is None
    assert extract_task_from_branch("main") is None
    assert extract_task_from_branch("master") is None


def test_extract_task_from_branch_du_prefix():
    """The 'du/' prefix is also valid for task branches."""
    assert extract_task_from_branch("du/DU-999-fix-bug") == "DU-999"


# ---------------------------------------------------------------------------
# parser.py – is_task_branch
# ---------------------------------------------------------------------------


def test_is_task_branch_true_for_task_prefix():
    """Branches starting with 'task/' are task branches."""
    assert is_task_branch("task/TASK-001-slug") is True


def test_is_task_branch_true_for_du_prefix():
    """Branches starting with 'du/' are task branches."""
    assert is_task_branch("du/DU-042") is True


def test_is_task_branch_false_for_main_and_master():
    """Mainline branches are not task branches."""
    assert is_task_branch("main") is False
    assert is_task_branch("master") is False


def test_is_task_branch_false_for_feature_branch():
    """Feature and other arbitrary branches are not task branches."""
    assert is_task_branch("feature/login") is False
    assert is_task_branch("bugfix/crash") is False
    assert is_task_branch("release/1.0") is False


# ---------------------------------------------------------------------------
# parser.py – get_last_commit_info
# ---------------------------------------------------------------------------


def test_get_last_commit_info_returns_dict(tmp_git_repo):
    """get_last_commit_info must return a dict with expected keys."""
    info = get_last_commit_info(tmp_git_repo)
    assert isinstance(info, dict)
    assert "hash" in info
    assert "message" in info
    assert "timestamp" in info
    # hash should be a 40-char hex SHA-1
    assert len(info["hash"]) == 40
    assert info["message"] == "Initial commit"
    # timestamp should be a non-empty string ending with Z (UTC normalised)
    assert info["timestamp"].endswith("Z")


# ---------------------------------------------------------------------------
# parser.py – run_git
# ---------------------------------------------------------------------------


def test_run_git_success(tmp_git_repo):
    """run_git must return stdout for a valid git command."""
    output = run_git(["rev-parse", "--is-inside-work-tree"], tmp_git_repo)
    assert output == "true"


def test_run_git_failure_raises(tmp_non_git_dir):
    """run_git must raise CalledProcessError in a non-git directory."""
    with pytest.raises(subprocess.CalledProcessError):
        run_git(["status"], tmp_non_git_dir)


# ---------------------------------------------------------------------------
# hooks.py – install_hooks
# ---------------------------------------------------------------------------


def test_install_hooks_creates_post_commit_and_post_checkout(tmp_git_repo):
    """install_hooks must create both hook files."""
    assert install_hooks(tmp_git_repo) is True
    hooks_dir = tmp_git_repo / ".git" / "hooks"
    assert (hooks_dir / "post-commit").is_file()
    assert (hooks_dir / "post-checkout").is_file()


def test_install_hooks_makes_hooks_executable(tmp_git_repo):
    """Hook files must have the executable bit set."""
    install_hooks(tmp_git_repo)
    hooks_dir = tmp_git_repo / ".git" / "hooks"
    for name in ("post-commit", "post-checkout"):
        hook_path = hooks_dir / name
        mode = hook_path.stat().st_mode
        assert mode & stat.S_IXUSR, f"{name} is not user-executable"
        assert mode & stat.S_IXGRP, f"{name} is not group-executable"
        assert mode & stat.S_IXOTH, f"{name} is not other-executable"


def test_install_hooks_idempotent(tmp_git_repo):
    """Calling install_hooks twice must not fail and must still leave hooks present."""
    assert install_hooks(tmp_git_repo) is True
    assert install_hooks(tmp_git_repo) is True
    hooks_dir = tmp_git_repo / ".git" / "hooks"
    assert (hooks_dir / "post-commit").is_file()
    assert (hooks_dir / "post-checkout").is_file()
    # Content should still contain the worktrail marker
    content = (hooks_dir / "post-commit").read_text(encoding="utf-8")
    assert _WORKTRAIL_HOOK_MARKER in content


# ---------------------------------------------------------------------------
# hooks.py – are_hooks_installed
# ---------------------------------------------------------------------------


def test_are_hooks_installed_true_after_install(tmp_git_repo):
    """are_hooks_installed must return True after install_hooks runs."""
    install_hooks(tmp_git_repo)
    assert are_hooks_installed(tmp_git_repo) is True


def test_are_hooks_installed_false_before_install(tmp_git_repo):
    """In a fresh repo are_hooks_installed must return False."""
    assert are_hooks_installed(tmp_git_repo) is False


def test_are_hooks_installed_false_when_hook_missing(tmp_git_repo):
    """If only one hook is present, are_hooks_installed must be False."""
    hooks_dir = tmp_git_repo / ".git" / "hooks"
    # Create only post-commit
    (hooks_dir / "post-commit").write_text(
        f"#!/bin/bash\n{_WORKTRAIL_HOOK_MARKER}commit hook\n", encoding="utf-8"
    )
    assert are_hooks_installed(tmp_git_repo) is False


def test_are_hooks_installed_false_for_non_worktrail_hook(tmp_git_repo):
    """A hook without the worktrail marker must not be recognised."""
    hooks_dir = tmp_git_repo / ".git" / "hooks"
    (hooks_dir / "post-commit").write_text("#!/bin/bash\necho hello\n", encoding="utf-8")
    (hooks_dir / "post-checkout").write_text("#!/bin/bash\necho world\n", encoding="utf-8")
    assert are_hooks_installed(tmp_git_repo) is False


# ---------------------------------------------------------------------------
# hooks.py – remove_hooks
# ---------------------------------------------------------------------------


def test_remove_hooks_deletes_worktrail_hooks(tmp_git_repo):
    """remove_hooks must delete hooks that contain the worktrail marker."""
    install_hooks(tmp_git_repo)
    assert are_hooks_installed(tmp_git_repo) is True
    assert remove_hooks(tmp_git_repo) is True
    assert are_hooks_installed(tmp_git_repo) is False
    hooks_dir = tmp_git_repo / ".git" / "hooks"
    assert not (hooks_dir / "post-commit").exists()
    assert not (hooks_dir / "post-checkout").exists()


def test_remove_hooks_leaves_non_worktrail_hooks_intact(tmp_git_repo):
    """remove_hooks must not touch hooks that lack the worktrail marker."""
    hooks_dir = tmp_git_repo / ".git" / "hooks"
    custom_commit = "#!/bin/bash\n# custom post-commit\necho done\n"
    custom_checkout = "#!/bin/bash\n# custom post-checkout\necho done\n"
    (hooks_dir / "post-commit").write_text(custom_commit, encoding="utf-8")
    (hooks_dir / "post-checkout").write_text(custom_checkout, encoding="utf-8")

    assert remove_hooks(tmp_git_repo) is False  # nothing was removed
    assert (hooks_dir / "post-commit").read_text(encoding="utf-8") == custom_commit
    assert (hooks_dir / "post-checkout").read_text(encoding="utf-8") == custom_checkout


def test_remove_hooks_returns_false_when_no_hooks_dir(tmp_non_git_dir):
    """remove_hooks must return False when .git/hooks/ does not exist."""
    assert remove_hooks(tmp_non_git_dir) is False


# ---------------------------------------------------------------------------
# hooks.py – hook content
# ---------------------------------------------------------------------------


def test_hooks_contain_worktrail_marker(tmp_git_repo):
    """Every installed hook must include the worktrail marker comment."""
    install_hooks(tmp_git_repo)
    hooks_dir = tmp_git_repo / ".git" / "hooks"
    for name in ("post-commit", "post-checkout"):
        content = (hooks_dir / name).read_text(encoding="utf-8")
        assert _WORKTRAIL_HOOK_MARKER in content, f"{name} lacks worktrail marker"


def test_hooks_contain_expected_commands(tmp_git_repo):
    """post-commit must reference 'git rev-parse HEAD'; post-checkout must reference branch checkout."""
    install_hooks(tmp_git_repo)
    hooks_dir = tmp_git_repo / ".git" / "hooks"
    post_commit = (hooks_dir / "post-commit").read_text(encoding="utf-8")
    post_checkout = (hooks_dir / "post-checkout").read_text(encoding="utf-8")
    assert "git rev-parse HEAD" in post_commit
    assert "worktrail checkpoint" in post_commit
    assert 'BRANCH_CHECKOUT="1"' in post_checkout or 'BRANCH_CHECKOUT=$3' in post_checkout
    assert "worktrail git-checkout-hook" in post_checkout


# ---------------------------------------------------------------------------
# hooks.py – _write_hook helper
# ---------------------------------------------------------------------------


def test_write_hook_sets_executable_bit(tmp_git_repo):
    """_write_hook must write content and chmod +x the file."""
    hooks_dir = tmp_git_repo / ".git" / "hooks"
    _write_hook(hooks_dir, "test-hook", "#!/bin/bash\necho hello\n")
    hook_path = hooks_dir / "test-hook"
    assert hook_path.is_file()
    assert hook_path.read_text(encoding="utf-8") == "#!/bin/bash\necho hello\n"
    mode = hook_path.stat().st_mode
    assert mode & stat.S_IXUSR
    assert mode & stat.S_IXGRP
    assert mode & stat.S_IXOTH


# ---------------------------------------------------------------------------
# hooks.py – install_hooks with missing .git/hooks dir
# ---------------------------------------------------------------------------


def test_install_hooks_returns_false_when_no_hooks_dir(tmp_non_git_dir):
    """install_hooks must return False when .git/hooks/ does not exist."""
    assert install_hooks(tmp_non_git_dir) is False


# ---------------------------------------------------------------------------
# End-to-end: branch switching on real repo
# ---------------------------------------------------------------------------


def test_get_current_branch_after_switching(tmp_git_repo):
    """Creating and checking out a new branch must reflect in get_current_branch."""
    subprocess.run(
        ["git", "checkout", "-b", "task/TASK-123-test"],
        cwd=str(tmp_git_repo),
        check=True,
        capture_output=True,
    )
    branch = get_current_branch(tmp_git_repo)
    assert branch == "task/TASK-123-test"


def test_extract_task_from_current_branch(tmp_git_repo):
    """Switch to a task branch and verify task extraction from it."""
    subprocess.run(
        ["git", "checkout", "-b", "task/PROJ-999-foo-bar"],
        cwd=str(tmp_git_repo),
        check=True,
        capture_output=True,
    )
    branch = get_current_branch(tmp_git_repo)
    task_id = extract_task_from_branch(branch)
    assert task_id == "PROJ-999"
    assert is_task_branch(branch) is True


def test_get_last_commit_info_after_second_commit(tmp_git_repo):
    """Adding a second commit must update last-commit info accordingly."""
    # Initial state already has "Initial commit"
    info_before = get_last_commit_info(tmp_git_repo)
    (tmp_git_repo / "second.txt").write_text("second\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "second.txt"], cwd=str(tmp_git_repo), check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Second commit"],
        cwd=str(tmp_git_repo),
        check=True,
        capture_output=True,
    )
    info_after = get_last_commit_info(tmp_git_repo)
    assert info_after["message"] == "Second commit"
    assert info_after["hash"] != info_before["hash"]
    assert info_after["timestamp"].endswith("Z")
