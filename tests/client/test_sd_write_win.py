"""Tests for the Windows SD card writer's safety rules.

The write itself is not exercised here and must not be: there is no way to
test writing to a raw physical device without a raw physical device to lose.
What is tested is everything that decides *which* device gets written, which
is where the damage comes from.

The bug that motivated all of this was in exactly that layer. The old
enumeration derived the device from the drive letter::

    f"\\\\.\\PhysicalDrive{ord(letter) - ord('A')}"

so D: meant PhysicalDrive3 and C: meant PhysicalDrive2, on a machine whose
only disk is 0. It never fired because the write was a stub, and it would
have written a 3 GB image over whatever disk 3 was.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from client.utils.sd_write_win import (  # noqa: E402
    REMOVABLE_BUS_TYPES,
    Disk,
    SDWriteError,
    check_target,
    newly_appeared,
)

GB = 1024 ** 3
IMAGE = 3 * GB


def disk(number=1, size=32 * GB, bus="USB", system=False, boot=False,
         letters=("E",), name="Generic STORAGE DEVICE"):
    return Disk(number=number, name=name, size=size, bus_type=bus,
                is_system=system, is_boot=boot, drive_letters=list(letters))


class TestDevicePath:
    """The path comes from the disk number, never from a drive letter."""

    @pytest.mark.parametrize("number", [0, 1, 3, 11])
    def test_path_is_built_from_the_disk_number(self, number):
        assert disk(number=number).device_path == f"\\\\.\\PhysicalDrive{number}"

    def test_drive_letters_do_not_influence_the_path(self):
        """The old code made D: mean PhysicalDrive3. Nothing may do that."""
        a = disk(number=1, letters=("D",))
        b = disk(number=1, letters=("Z",))
        c = disk(number=1, letters=())

        assert a.device_path == b.device_path == c.device_path
        assert a.device_path == "\\\\.\\PhysicalDrive1"


class TestSystemDiskIsNeverWritten:
    """The one rule the override does not reach."""

    @pytest.mark.parametrize("flags", [
        {"system": True}, {"boot": True}, {"system": True, "boot": True},
    ])
    def test_refused(self, flags):
        with pytest.raises(SDWriteError, match="Windows is running from"):
            check_target(disk(**flags), IMAGE)

    @pytest.mark.parametrize("flags", [
        {"system": True}, {"boot": True}, {"system": True, "boot": True},
    ])
    def test_refused_even_with_override(self, flags):
        """"I know what I am doing" cannot mean this."""
        with pytest.raises(SDWriteError, match="cannot be overridden"):
            check_target(disk(**flags), IMAGE, override=True)

    def test_refused_even_when_it_looks_removable(self, ):
        """A system disk on a USB bus is still the system disk."""
        with pytest.raises(SDWriteError, match="Windows is running from"):
            check_target(disk(bus="USB", system=True), IMAGE, override=True)


class TestRemovableMediaRule:
    @pytest.mark.parametrize("bus", sorted(REMOVABLE_BUS_TYPES))
    def test_removable_buses_are_allowed(self, bus):
        check_target(disk(bus=bus), IMAGE)  # must not raise

    @pytest.mark.parametrize("bus", ["NVMe", "SATA", "RAID", "iSCSI", ""])
    def test_other_buses_are_refused_by_default(self, bus):
        with pytest.raises(SDWriteError, match="not removable media"):
            check_target(disk(bus=bus), IMAGE)

    @pytest.mark.parametrize("bus", ["NVMe", "SATA", "RAID", "iSCSI", ""])
    def test_other_buses_are_allowed_with_the_override(self, bus):
        """The escape hatch, for someone who knows their hardware."""
        check_target(disk(bus=bus), IMAGE, override=True)  # must not raise

    def test_bus_check_is_case_insensitive(self):
        check_target(disk(bus="usb"), IMAGE)


class TestSizeRules:
    def test_image_larger_than_the_card_is_refused(self):
        with pytest.raises(SDWriteError, match="will not fit"):
            check_target(disk(size=2 * GB), IMAGE)

    def test_too_small_is_refused_even_with_override(self):
        """Overriding the media type cannot make a card bigger."""
        with pytest.raises(SDWriteError, match="will not fit"):
            check_target(disk(size=2 * GB, bus="NVMe"), IMAGE, override=True)

    def test_exactly_the_same_size_fits(self):
        check_target(disk(size=IMAGE), IMAGE)

    @pytest.mark.parametrize("size", [0, -1])
    def test_a_disk_reporting_no_size_is_refused(self, size):
        with pytest.raises(SDWriteError, match="reports no size"):
            check_target(disk(size=size), IMAGE)


class TestAppearanceDetection:
    """Identify the card as the one that was not there a moment ago."""

    def _patch(self, monkeypatch, disks):
        import client.utils.sd_write_win as mod
        monkeypatch.setattr(mod, "list_disks", lambda: disks)

    def test_finds_the_disk_that_appeared(self, monkeypatch):
        self._patch(monkeypatch, [disk(number=0, bus="NVMe"), disk(number=2)])

        found = newly_appeared({0})

        assert [d.number for d in found] == [2]

    def test_nothing_appeared(self, monkeypatch):
        self._patch(monkeypatch, [disk(number=0), disk(number=2)])

        assert newly_appeared({0, 2}) == []

    def test_two_at_once_are_both_reported(self, monkeypatch):
        """The caller must refuse to guess; it cannot do that if we pick one."""
        self._patch(monkeypatch,
                    [disk(number=0), disk(number=2), disk(number=3)])

        assert len(newly_appeared({0})) == 2

    def test_a_removed_disk_is_not_a_new_one(self, monkeypatch):
        self._patch(monkeypatch, [disk(number=0)])

        assert newly_appeared({0, 5}) == []

    def test_detection_does_not_care_what_the_reader_claims_to_be(
            self, monkeypatch):
        """Many card readers report as fixed disks; appearing is the signal."""
        self._patch(monkeypatch,
                    [disk(number=0, bus="NVMe"), disk(number=4, bus="SATA")])

        found = newly_appeared({0})

        assert [d.number for d in found] == [4]
        assert not found[0].looks_removable, (
            "the fixture is meant to look non-removable, so the caller still "
            "has to confirm before writing"
        )
