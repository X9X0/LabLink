"""Default profiles are a starting point, not something restored on every boot.

`create_default_profiles()` ran on every startup and saved all seven defaults
unconditionally. `save_profile` stamps `modified_at`, so the shipped JSON was
rewritten each time -- which dirtied the working tree of anyone running the
server from a checkout, and silently discarded any edit a user had made to a
default profile.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.equipment.profiles import (EquipmentProfile,  # noqa: E402
                                       ProfileManager, create_default_profiles,
                                       profile_manager)


@pytest.fixture
def profile_dir(tmp_path, monkeypatch):
    """Point the shared profile_manager at a temporary directory."""
    monkeypatch.setattr(profile_manager, "profile_dir", tmp_path)
    monkeypatch.setattr(profile_manager, "enabled", True)
    return tmp_path


def _snapshot(directory: Path) -> dict:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(directory.glob("*.json"))}


class TestDefaultsAreWrittenOnce:
    def test_first_run_creates_them(self, profile_dir):
        create_default_profiles()

        assert len(list(profile_dir.glob("*.json"))) == 7

    def test_a_second_run_changes_nothing_on_disk(self, profile_dir):
        """The bug: every boot rewrote all seven, timestamps and all."""
        create_default_profiles()
        before = _snapshot(profile_dir)

        create_default_profiles()

        assert _snapshot(profile_dir) == before

    def test_an_edited_default_is_not_reverted(self, profile_dir):
        """The part that costs a user something, rather than just churn."""
        create_default_profiles()
        edited = profile_manager.load_profile("Oscilloscope - Debug Quick")
        edited.settings["timebase_scale"] = 0.05
        profile_manager.save_profile(edited)

        create_default_profiles()

        after = profile_manager.load_profile("Oscilloscope - Debug Quick")
        assert after.settings["timebase_scale"] == 0.05

    def test_a_deleted_default_comes_back(self, profile_dir):
        """Skipping existing ones must not mean never writing them again."""
        create_default_profiles()
        profile_manager.delete_profile("Oscilloscope - Debug Quick")

        create_default_profiles()

        assert profile_manager.load_profile("Oscilloscope - Debug Quick") is not None


class TestProfileExists:
    def test_reports_absence_and_presence(self, profile_dir):
        manager = ProfileManager()
        manager.profile_dir = profile_dir
        manager.enabled = True

        assert manager.profile_exists("Nothing Here") is False

        manager.save_profile(
            EquipmentProfile(
                name="Nothing Here",
                equipment_type="power_supply",
                model="generic",
                settings={},
            )
        )

        assert manager.profile_exists("Nothing Here") is True

    def test_it_matches_the_name_sanitising_used_to_save(self, profile_dir):
        """Names become filenames; the check must use the same mapping."""
        manager = ProfileManager()
        manager.profile_dir = profile_dir
        manager.enabled = True
        manager.save_profile(
            EquipmentProfile(
                name="Power Supply - 5V Logic",
                equipment_type="power_supply",
                model="generic",
                settings={},
            )
        )

        assert manager.profile_exists("Power Supply - 5V Logic") is True
