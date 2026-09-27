"""The update mode has to survive a restart.

The manager saved update_config.json into config/. In Docker that is
/opt/lablink/config mounted read-only -- correct, since it is the
shipped configuration -- so every save failed:

    Failed to save update configuration:
    [Errno 30] Read-only file system: '/app/config/update_config.json'

The default is STABLE, so the mode silently reverted to stable on every
restart. Somebody selecting the development branch got stable back
with nothing to say so, and reasonably put it down to their own
mis-click.

It now writes to data/, which is a writable volume and already holds
the security and discovery databases and the JWT secret. The old
location is still read once, so a setting saved before the move is not
lost.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from server.system.update_manager import UpdateManager, UpdateMode


@pytest.fixture
def manager(tmp_path, monkeypatch):
    """An update manager rooted in a throwaway directory."""
    monkeypatch.setattr(UpdateManager, "_find_project_root",
                        lambda self: tmp_path)
    made = UpdateManager()
    return made


class TestItWritesWhereItCan:
    def test_the_config_lives_under_data(self, manager, tmp_path):
        """Not config/, which Docker mounts read-only."""
        assert manager.config_file.parent == tmp_path / "data", (
            manager.config_file)

    def test_a_saved_mode_comes_back(self, manager):
        manager.update_mode = UpdateMode.DEVELOPMENT
        manager.tracked_branch = "feature/instrument-panels"
        manager._save_config()

        assert manager.config_file.exists(), "nothing was written"
        written = json.loads(manager.config_file.read_text(encoding="utf-8"))
        assert written["update_mode"] == UpdateMode.DEVELOPMENT.value
        assert written["tracked_branch"] == "feature/instrument-panels"

    def test_it_survives_a_restart(self, manager, tmp_path, monkeypatch):
        """The whole point: a second manager, as after a container
        restart, must come up in the mode that was chosen."""
        manager.update_mode = UpdateMode.DEVELOPMENT
        manager.tracked_branch = "feature/instrument-panels"
        manager._save_config()

        monkeypatch.setattr(UpdateManager, "_find_project_root",
                            lambda self: tmp_path)
        restarted = UpdateManager()
        restarted._load_config()

        assert restarted.update_mode == UpdateMode.DEVELOPMENT, (
            "the mode went back to stable across a restart, which is the "
            "bug this exists to prevent")
        assert restarted.tracked_branch == "feature/instrument-panels"


class TestTheOldLocationIsNotOrphaned:
    def test_a_setting_saved_before_the_move_is_read(self, tmp_path,
                                                     monkeypatch):
        legacy = tmp_path / "config"
        legacy.mkdir(parents=True, exist_ok=True)
        (legacy / "update_config.json").write_text(
            json.dumps({"update_mode": "development",
                        "tracked_branch": "old-branch"}),
            encoding="utf-8")

        monkeypatch.setattr(UpdateManager, "_find_project_root",
                            lambda self: tmp_path)
        made = UpdateManager()
        made._load_config()

        assert made.update_mode == UpdateMode.DEVELOPMENT
        assert made.tracked_branch == "old-branch"

    def test_the_new_location_wins(self, tmp_path, monkeypatch):
        """Once saved in data/, that is the answer -- the stale copy in
        config/ must not override it."""
        legacy = tmp_path / "config"
        legacy.mkdir(parents=True, exist_ok=True)
        (legacy / "update_config.json").write_text(
            json.dumps({"update_mode": "stable"}), encoding="utf-8")
        current = tmp_path / "data"
        current.mkdir(parents=True, exist_ok=True)
        (current / "update_config.json").write_text(
            json.dumps({"update_mode": "development"}), encoding="utf-8")

        monkeypatch.setattr(UpdateManager, "_find_project_root",
                            lambda self: tmp_path)
        made = UpdateManager()
        made._load_config()

        assert made.update_mode == UpdateMode.DEVELOPMENT


class TestAFailedSaveSaysWhatItCosts:
    def test_it_names_the_consequence(self, manager, monkeypatch, caplog):
        """A warning that says only "failed to save" is what let this
        run for months. The operator needs to know the mode will not
        survive a restart."""
        import logging

        def refuse(*a, **k):
            raise OSError(30, "Read-only file system")

        monkeypatch.setattr("builtins.open", refuse)
        with caplog.at_level(logging.ERROR):
            manager._save_config()

        assert "restart" in caplog.text.lower(), caplog.text
        assert "stable" in caplog.text.lower(), caplog.text
