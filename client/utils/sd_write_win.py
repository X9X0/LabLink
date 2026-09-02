"""Write an image to an SD card on Windows.

Raw device access needs administrator rights on Windows, so this module is
also the elevated helper: the GUI runs it again through ShellExecute with the
``runas`` verb, which is what raises the UAC prompt. A process cannot elevate
itself, so there is no way to avoid the second process.

That is the *only* thing here that needs elevation. Building an image needs
none, on any platform, which is the point of ``pi_image_native``. Putting a
finished image onto a card is a different operation, and Raspberry Pi Imager
prompts for it too.

Identifying the card is the dangerous part, not writing it. The previous
implementation derived the device from the drive letter::

    f"\\\\.\\PhysicalDrive{ord(letter) - ord('A')}"   # D: -> PhysicalDrive3

Drive letters have no relationship to physical disk numbers. On the machine
that produced that line there is only PHYSICALDRIVE0, so it named a disk that
did not exist -- and on a machine where disk 3 does exist, it would have
written a 3 GB image over it. Nothing caught it because the write itself was
never implemented.

So the disk is identified two ways here, and both must agree with the user:

* enumeration through ``Get-Disk``, which reports the real disk number
  alongside ``IsSystem``/``IsBoot`` and the bus type, and
* by *appearance* -- the caller snapshots the disks, asks the user to insert
  the card, and takes the disk that shows up. A card reader that reports
  itself as a fixed disk (many do) is still unmistakably the one that was not
  there a moment ago.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import subprocess
import sys
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

ProgressFn = Callable[[int, str], None]

CHUNK = 1024 * 1024  # a whole number of 512-byte sectors

# Bus types that a card reader plausibly presents as. Anything else needs the
# override, because it is more likely to be a disk somebody wants to keep.
REMOVABLE_BUS_TYPES = {"USB", "SD", "MMC"}


class SDWriteError(RuntimeError):
    """Raised when a card cannot be written."""


@dataclass
class Disk:
    """One physical disk, as ``Get-Disk`` sees it."""

    number: int
    name: str
    size: int
    bus_type: str = ""
    is_system: bool = False
    is_boot: bool = False
    drive_letters: List[str] = field(default_factory=list)

    @property
    def device_path(self) -> str:
        """The real path, from the disk number rather than a drive letter."""
        return f"\\\\.\\PhysicalDrive{self.number}"

    @property
    def looks_removable(self) -> bool:
        return self.bus_type.upper() in REMOVABLE_BUS_TYPES

    @property
    def size_gb(self) -> float:
        return round(self.size / (1024 ** 3), 1)

    def describe(self) -> str:
        letters = ", ".join(f"{d}:" for d in self.drive_letters) or "no drive letters"
        return (f"Disk {self.number}: {self.name or 'unknown'} "
                f"({self.size_gb} GB, {self.bus_type or 'unknown bus'}, {letters})")


_PS_LIST_DISKS = r"""
$parts = @{}
foreach ($p in Get-Partition) {
    if ($p.DriveLetter) {
        if (-not $parts.ContainsKey([int]$p.DiskNumber)) { $parts[[int]$p.DiskNumber] = @() }
        $parts[[int]$p.DiskNumber] += [string]$p.DriveLetter
    }
}
Get-Disk | ForEach-Object {
    [PSCustomObject]@{
        Number   = [int]$_.Number
        Name     = [string]$_.FriendlyName
        Size     = [int64]$_.Size
        BusType  = [string]$_.BusType
        IsSystem = [bool]$_.IsSystem
        IsBoot   = [bool]$_.IsBoot
        Letters  = @($parts[[int]$_.Number])
    }
} | ConvertTo-Json -Depth 3 -Compress
"""


def list_disks() -> List[Disk]:
    """Every physical disk, with the real disk number.

    Uses ``Get-Disk`` rather than drive letters, because the mapping between
    the two does not exist.
    """
    if not sys.platform.startswith("win"):
        raise SDWriteError("This module only runs on Windows.")

    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_LIST_DISKS],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SDWriteError(f"Could not list disks: {exc}") from exc

    out = (completed.stdout or "").strip()
    if not out:
        raise SDWriteError(
            "Could not list disks; PowerShell returned nothing.\n"
            + (completed.stderr or "").strip()
        )

    try:
        raw = json.loads(out)
    except json.JSONDecodeError as exc:
        raise SDWriteError(f"Could not parse the disk list: {exc}") from exc

    if isinstance(raw, dict):  # a single disk does not come back as a list
        raw = [raw]

    disks = []
    for item in raw:
        letters = item.get("Letters") or []
        if isinstance(letters, str):
            letters = [letters]
        disks.append(Disk(
            number=int(item["Number"]),
            name=item.get("Name") or "",
            size=int(item.get("Size") or 0),
            bus_type=item.get("BusType") or "",
            is_system=bool(item.get("IsSystem")),
            is_boot=bool(item.get("IsBoot")),
            drive_letters=[str(x) for x in letters if x],
        ))
    return disks


def snapshot_disk_numbers() -> set:
    """Disk numbers present right now, for detecting one appearing."""
    return {d.number for d in list_disks()}


def newly_appeared(before: set) -> List[Disk]:
    """Disks present now that were not in ``before``.

    This is how the card is identified: the user is asked to insert it (or
    remove and reinsert it), and whatever turns up is the target. It needs no
    guess about which reader reports itself how.
    """
    return [d for d in list_disks() if d.number not in before]


def check_target(disk: Disk, image_size: int, override: bool = False) -> None:
    """Raise unless it is safe to write ``disk``.

    ``override`` relaxes the removable-media check for someone who genuinely
    knows what they are doing. It does not relax the system-disk check: a
    write there destroys the running machine part-way through, and no answer
    to a dialog makes that a thing anybody wanted.
    """
    if disk.is_system or disk.is_boot:
        raise SDWriteError(
            f"{disk.describe()}\n\n"
            "This is the disk Windows is running from. Refusing to write to "
            "it. This cannot be overridden."
        )

    if disk.size <= 0:
        raise SDWriteError(f"{disk.describe()}\n\nThis disk reports no size.")

    if image_size > disk.size:
        raise SDWriteError(
            f"{disk.describe()}\n\n"
            f"The image is {image_size / (1024 ** 3):.1f} GB and the card "
            f"holds {disk.size_gb} GB. It will not fit."
        )

    if not disk.looks_removable and not override:
        raise SDWriteError(
            f"{disk.describe()}\n\n"
            f"This is not removable media (bus type {disk.bus_type or 'unknown'}). "
            "Refusing by default."
        )


# ---------------------------------------------------------------------------
# Raw write
# ---------------------------------------------------------------------------

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

FSCTL_LOCK_VOLUME = 0x00090018
FSCTL_DISMOUNT_VOLUME = 0x00090020
FSCTL_ALLOW_EXTENDED_DASD_IO = 0x00090083


def _kernel32():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateFileW.restype = wintypes.HANDLE
    k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                              wintypes.HANDLE]
    k.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID,
                                  wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                  ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
    k.WriteFile.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD,
                            ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
    k.ReadFile.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                           ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
    return k


def _open(path: str, k) -> int:
    handle = k.CreateFileW(path, GENERIC_READ | GENERIC_WRITE,
                           FILE_SHARE_READ | FILE_SHARE_WRITE,
                           None, OPEN_EXISTING, 0, None)
    if handle == INVALID_HANDLE_VALUE:
        err = ctypes.get_last_error()
        if err == 5:
            raise SDWriteError(
                f"Access denied opening {path}. This needs administrator "
                "rights; the elevated helper was not used."
            )
        raise SDWriteError(f"Could not open {path} (Windows error {err}).")
    return handle


def _ioctl(handle: int, code: int, k) -> bool:
    returned = wintypes.DWORD()
    return bool(k.DeviceIoControl(handle, code, None, 0, None, 0,
                                  ctypes.byref(returned), None))


def write_image(image_path: str, disk: Disk, progress: Optional[ProgressFn] = None,
                verify: bool = True, override: bool = False) -> None:
    """Write ``image_path`` to ``disk``, raw.

    The volumes on the disk are locked and dismounted first and held that way
    for the whole write. Skipping that lets Windows keep its own cached view
    of a filesystem that is being overwritten underneath it, and the result is
    a card that looks written and is quietly corrupt.
    """
    def report(pct: int, msg: str) -> None:
        if progress:
            progress(pct, msg)

    image_size = os.path.getsize(image_path)
    check_target(disk, image_size, override=override)

    k = _kernel32()
    volume_handles = []
    device = None

    try:
        report(2, f"Locking {len(disk.drive_letters) or 'no'} volume(s)...")
        for letter in disk.drive_letters:
            vol = _open(f"\\\\.\\{letter}:", k)
            volume_handles.append(vol)
            if not _ioctl(vol, FSCTL_LOCK_VOLUME, k):
                raise SDWriteError(
                    f"Could not lock volume {letter}:. Close anything using "
                    "the card and try again."
                )
            _ioctl(vol, FSCTL_DISMOUNT_VOLUME, k)

        report(5, f"Opening {disk.device_path}...")
        device = _open(disk.device_path, k)
        _ioctl(device, FSCTL_ALLOW_EXTENDED_DASD_IO, k)

        written = 0
        with open(image_path, "rb") as src:
            while True:
                chunk = src.read(CHUNK)
                if not chunk:
                    break
                if len(chunk) % 512:  # the tail, padded to a whole sector
                    chunk += b"\0" * (512 - len(chunk) % 512)
                n = wintypes.DWORD()
                if not k.WriteFile(device, chunk, len(chunk), ctypes.byref(n), None):
                    raise SDWriteError(
                        f"Write failed at {written} bytes "
                        f"(Windows error {ctypes.get_last_error()})."
                    )
                written += n.value
                report(5 + int(70 * written / image_size),
                       f"Writing: {written // (1024*1024)} / "
                       f"{image_size // (1024*1024)} MB")

        k.FlushFileBuffers(device)
        report(76, "Flushed.")

        if verify:
            _verify(device, image_path, image_size, k, report)

    finally:
        if device:
            k.CloseHandle(device)
        for vol in volume_handles:
            k.CloseHandle(vol)  # releases the lock, Windows remounts

    report(100, "Card written.")


def _verify(device: int, image_path: str, image_size: int, k, report: ProgressFn) -> None:
    """Read the card back and compare. A silent bad write is the failure mode."""
    import hashlib

    k.SetFilePointer = k.SetFilePointer
    k.SetFilePointer.argtypes = [wintypes.HANDLE, ctypes.c_long,
                                 ctypes.POINTER(ctypes.c_long), wintypes.DWORD]
    k.SetFilePointer(device, 0, None, 0)  # FILE_BEGIN

    on_card = hashlib.sha256()
    in_file = hashlib.sha256()
    read_back = 0

    with open(image_path, "rb") as src:
        while read_back < image_size:
            want = min(CHUNK, image_size - read_back)
            if want % 512:
                want += 512 - want % 512
            buf = ctypes.create_string_buffer(want)
            n = wintypes.DWORD()
            if not k.ReadFile(device, buf, want, ctypes.byref(n), None) or not n.value:
                raise SDWriteError(
                    f"Verify failed: could not read back at {read_back} bytes."
                )
            expected = src.read(n.value)
            on_card.update(buf.raw[:len(expected)])
            in_file.update(expected)
            read_back += len(expected)
            report(76 + int(23 * read_back / image_size),
                   f"Verifying: {read_back // (1024*1024)} / "
                   f"{image_size // (1024*1024)} MB")

    if on_card.hexdigest() != in_file.hexdigest():
        raise SDWriteError(
            "Verify failed: the card does not match the image. Do not use it."
        )


# ---------------------------------------------------------------------------
# Elevation
# ---------------------------------------------------------------------------


def is_elevated() -> bool:
    """True when this process is already running as administrator."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_elevated(image_path: str, disk_number: int, progress_file: str,
                 override: bool = False, verify: bool = True) -> int:
    """Re-run this module elevated. Returns the ShellExecute result.

    A process cannot elevate itself, so this starts a second one. The UAC
    prompt the user sees comes from here.
    """
    params = [
        "-m", "client.utils.sd_write_win",
        "--image", image_path,
        "--disk", str(disk_number),
        "--progress-file", progress_file,
    ]
    if override:
        params.append("--override")
    if not verify:
        params.append("--no-verify")

    quoted = " ".join(f'"{p}"' if " " in p else p for p in params)
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))

    result = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, quoted, repo_root, 1
    )
    if result <= 32:
        if result == 1223:  # ERROR_CANCELLED
            raise SDWriteError("The administrator prompt was declined.")
        raise SDWriteError(f"Could not start the elevated writer (code {result}).")
    return result


def main(argv: Optional[list] = None) -> int:
    """The elevated helper. Not meant to be run by hand."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m client.utils.sd_write_win",
        description="Write an image to an SD card. Needs administrator rights.",
    )
    parser.add_argument("--image", required=True)
    parser.add_argument("--disk", required=True, type=int,
                        help="physical disk number from Get-Disk, not a drive letter")
    parser.add_argument("--progress-file", help="progress is appended here as JSON")
    parser.add_argument("--override", action="store_true",
                        help="allow a disk that is not removable media")
    parser.add_argument("--no-verify", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    handle = None
    if args.progress_file:
        handle = open(args.progress_file, "w", encoding="utf-8", buffering=1)

    def report(pct: int, msg: str) -> None:
        print(f"[{pct:3d}%] {msg}", flush=True)
        if handle:
            handle.write(json.dumps({"percent": pct, "message": msg}) + "\n")

    try:
        disk = next((d for d in list_disks() if d.number == args.disk), None)
        if disk is None:
            raise SDWriteError(
                f"Disk {args.disk} is gone. Was the card removed?"
            )
        write_image(args.image, disk, progress=report,
                    verify=not args.no_verify, override=args.override)
    except SDWriteError as exc:
        report(-1, f"error: {exc}")
        return 1
    except OSError as exc:
        report(-1, f"error: {exc}")
        return 1
    finally:
        if handle:
            handle.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
