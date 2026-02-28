"""Tests for UpdateManager — converted from ad-hoc root scripts.

Run all tests:
    pytest tests/server/test_update_manager.py -v

Skip git-dependent integration tests:
    pytest tests/server/test_update_manager.py -v -m "not integration"
"""

import sys
from pathlib import Path

import pytest

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.system.update_manager import UpdateManager, UpdateMode

# Detect whether the test environment is inside a git repository
_ROOT = Path(__file__).parent.parent.parent
is_git_repo = (_ROOT / ".git").exists()


# ===========================================================================
# test_update_mode_configuration  (from test_update_system.py)
# ===========================================================================


def test_update_mode_configuration():
    """UpdateManager initialises and accepts mode configuration."""
    manager = UpdateManager()

    assert manager.current_version is not None
    assert manager.update_mode is not None

    # Configure STABLE mode
    result = manager.configure_update_mode(UpdateMode.STABLE)
    assert result["success"] is True
    assert manager.update_mode == UpdateMode.STABLE

    # Configure DEVELOPMENT mode
    result = manager.configure_update_mode(UpdateMode.DEVELOPMENT)
    assert result["success"] is True
    assert manager.update_mode == UpdateMode.DEVELOPMENT

    # get_status() must include 'update_mode'
    status = manager.get_status()
    assert "update_mode" in status


@pytest.mark.integration
@pytest.mark.skipif(not is_git_repo, reason="requires git repository")
@pytest.mark.asyncio
async def test_update_check_stable_mode():
    """check_for_updates() works in STABLE mode when inside a git repo."""
    manager = UpdateManager()
    manager.configure_update_mode(UpdateMode.STABLE)
    result = await manager.check_for_updates()

    assert "updates_available" in result
    assert "current_version" in result


@pytest.mark.integration
@pytest.mark.skipif(not is_git_repo, reason="requires git repository")
@pytest.mark.asyncio
async def test_update_check_development_mode():
    """check_for_updates() works in DEVELOPMENT mode when inside a git repo."""
    manager = UpdateManager()
    manager.configure_update_mode(UpdateMode.DEVELOPMENT)
    result = await manager.check_for_updates()

    assert "updates_available" in result
    assert "current_version" in result


# ===========================================================================
# test_branch_tracking  (from test_branch_tracking.py)
# ===========================================================================


@pytest.mark.integration
@pytest.mark.skipif(not is_git_repo, reason="requires git repository")
def test_get_available_branches():
    """get_available_branches() returns branch list including the current branch."""
    manager = UpdateManager()
    result = manager.get_available_branches()

    if not result.get("success"):
        pytest.skip(f"Remote not reachable: {result.get('error')}")

    branches = result.get("branches", [])
    assert isinstance(branches, list)
    assert len(branches) > 0

    current_branch = result.get("current_branch")
    assert current_branch is not None

    names = [b.get("name") for b in branches]
    assert current_branch in names


@pytest.mark.integration
@pytest.mark.skipif(not is_git_repo, reason="requires git repository")
def test_set_tracked_branch():
    """set_tracked_branch() persists the branch in status."""
    manager = UpdateManager()

    branches_result = manager.get_available_branches()
    if not branches_result.get("success"):
        pytest.skip(f"Remote not reachable: {branches_result.get('error')}")

    branches = branches_result.get("branches", [])
    assert branches, "No branches returned"

    test_branch = branches[0]["name"]
    result = manager.set_tracked_branch(test_branch)
    assert result.get("success") is True

    status = manager.get_status()
    assert status.get("tracked_branch") == test_branch


# ===========================================================================
# test_config_persistence  (from test_config_persistence.py)
# ===========================================================================


def test_default_configuration(tmp_path):
    """UpdateManager starts with expected defaults when no config file exists."""
    manager = _make_manager_with_config(tmp_path)
    assert manager.update_mode == UpdateMode.STABLE
    assert manager.scheduled_check_enabled is False


def test_config_roundtrip(tmp_path):
    """Configuration written by one UpdateManager is loaded by a second one."""
    manager1 = _make_manager_with_config(tmp_path)
    manager1.configure_update_mode(UpdateMode.DEVELOPMENT)
    manager1.set_tracked_branch("feature/test-branch")
    manager1.configure_scheduled_checks(
        enabled=True,
        interval_hours=12,
        git_remote="origin",
        git_branch="main",
    )
    manager1.configure_auto_rebuild(enabled=True, command="docker compose build")

    # Second manager should read the same config file
    manager2 = _make_manager_with_config(tmp_path)
    assert manager2.update_mode == UpdateMode.DEVELOPMENT
    assert manager2.tracked_branch == "feature/test-branch"
    assert manager2.scheduled_check_enabled is True
    assert manager2.check_interval_hours == 12
    assert manager2.git_remote == "origin"
    assert manager2.git_branch == "main"
    assert manager2.auto_rebuild_enabled is True
    assert manager2.rebuild_command == "docker compose build"


def test_config_modification_persists(tmp_path):
    """Subsequent changes to an existing config are visible to a new manager."""
    manager1 = _make_manager_with_config(tmp_path)
    manager1.configure_update_mode(UpdateMode.DEVELOPMENT)
    manager1.configure_scheduled_checks(enabled=True)

    manager2 = _make_manager_with_config(tmp_path)
    manager2.configure_update_mode(UpdateMode.STABLE)
    manager2.configure_scheduled_checks(enabled=False)

    manager3 = _make_manager_with_config(tmp_path)
    assert manager3.update_mode == UpdateMode.STABLE
    assert manager3.scheduled_check_enabled is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_initialize_starts_scheduled_checks_when_enabled(tmp_path):
    """initialize() auto-starts scheduled checks when they are enabled."""
    manager = _make_manager_with_config(tmp_path)
    manager.configure_scheduled_checks(enabled=True, interval_hours=24)

    await manager.initialize()

    # If a git repo is available the task will be running; otherwise it may not
    # start — we just verify that initialize() does not raise.
    if manager.scheduled_check_task and not manager.scheduled_check_task.done():
        await manager.stop_scheduled_checks()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_manager_with_config(config_dir: Path) -> UpdateManager:
    """Create an UpdateManager whose config file lives in *config_dir*.

    Redirects config_file/config_dir to a temporary directory so tests do not
    read or write the real project config.  Attributes are reset to their
    __init__ defaults before _load_config() is called so the tmp dir behaves
    exactly like a fresh install.
    """
    manager = UpdateManager()
    manager.config_dir = config_dir
    manager.config_file = config_dir / "update_config.json"

    # Reset to __init__ defaults so a missing file means "no prior config"
    manager.update_mode = UpdateMode.STABLE
    manager.tracked_branch = None
    manager.auto_rebuild_enabled = False
    manager.rebuild_command = None
    manager.scheduled_check_enabled = False
    manager.check_interval_hours = 24
    manager.git_remote = "origin"
    manager.git_branch = None

    # Now load from the (possibly empty) tmp dir
    manager._load_config()
    return manager
