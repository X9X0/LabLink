"""Tests for the client self-update flag and relaunch helpers."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from client.utils import self_update  # noqa: E402


@pytest.mark.unit
def test_flag_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(self_update, "UPDATE_FLAG_FILE", tmp_path / ".client_update")
    assert self_update.check_update_flag() is None
    assert self_update.mark_for_update("feature/x", "development")
    assert self_update.check_update_flag() == {"ref": "feature/x", "mode": "development"}
    assert self_update.clear_update_flag()
    assert self_update.check_update_flag() is None


@pytest.mark.unit
def test_relaunch_command_source_checkout(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "argv", ["main.py", "--debug"])
    cmd = self_update.build_relaunch_command()
    assert cmd[0] == sys.executable
    assert cmd[1] == str(self_update.CLIENT_MAIN)
    assert cmd[2:] == ["--debug"]


@pytest.mark.unit
def test_relaunch_command_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "argv", ["LabLink.exe", "--debug"])
    assert self_update.build_relaunch_command() == [sys.executable, "--debug"]


@pytest.mark.unit
def test_relaunch_client_starts_detached_process(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "argv", ["main.py"])
    with patch.object(self_update.subprocess, "Popen") as popen:
        assert self_update.relaunch_client() is True
        args, kwargs = popen.call_args
        assert args[0][1] == str(self_update.CLIENT_MAIN)
        assert kwargs["cwd"] in (str(self_update.CLIENT_DIR), str(self_update.PROJECT_ROOT))
        if self_update.os.name == "nt":
            assert kwargs["creationflags"]
        else:
            assert kwargs["start_new_session"] is True


@pytest.mark.unit
def test_relaunch_client_reports_failure(monkeypatch):
    with patch.object(self_update.subprocess, "Popen", side_effect=OSError("boom")):
        assert self_update.relaunch_client() is False


@pytest.mark.unit
def test_git_operations_run_from_repo_root():
    from client.utils import git_operations

    assert git_operations._REPO_ROOT == self_update.PROJECT_ROOT
    assert (git_operations._REPO_ROOT / "client" / "main.py").exists()
