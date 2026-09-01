"""Build a customised Raspberry Pi image without root, bash or Linux.

The shell builder (`build-pi-image.sh`) loop-mounts the image, chroots into its
ext4 root filesystem under ARM emulation and needs root. That works only on
Linux, which is why the image-builder wizard could not run on Windows.

This module does the same job differently: it writes *only* to the FAT32 boot
partition, which is readable and writable in pure Python at a byte offset
inside the ``.img`` file. Everything that previously required ext4 access is
deferred to Raspberry Pi OS's own first-run mechanism — a script named in
``cmdline.txt`` via ``systemd.run=``, which the Pi executes as root on first
boot. That is the same mechanism Raspberry Pi Imager uses.

The result: no root, no loop devices, no bash, no qemu. Runs on Windows, macOS
and Linux alike.

Layout written to the boot partition:

    firstrun.sh                 early, offline setup; installs the service below
    lablink-first-boot.sh       network stage, run by that service after reboot
    lablink-admin-password      root-only, consumed and deleted on first boot
    userconf.txt                account creation, handled by Pi OS itself
    ssh                         enables sshd
    cmdline.txt                 patched to invoke firstrun.sh once
"""

from __future__ import annotations

import logging
import lzma
import re
import struct
import sys
import types
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Progress callback: (percent, message)
ProgressFn = Callable[[int, str], None]


def _install_pkg_resources_shim() -> None:
    """Let ``fs`` import on setuptools >= 81, which removed pkg_resources.

    ``pyfatfs`` depends on ``fs``, which still calls ``pkg_resources`` for a
    legacy namespace declaration and for entry-point discovery of URL openers.
    We use neither. Rather than pin setuptools back below 81 — which would
    reintroduce PYSEC-2026-3447 — provide the two attributes ``fs`` touches.

    Scoped to this process and only installed when the real module is absent.
    """
    if "pkg_resources" in sys.modules:
        return
    try:
        import pkg_resources  # noqa: F401
    except ImportError:
        stub = types.ModuleType("pkg_resources")
        stub.declare_namespace = lambda name: None  # type: ignore[attr-defined]
        stub.iter_entry_points = lambda *a, **k: iter(())  # type: ignore[attr-defined]
        sys.modules["pkg_resources"] = stub
        logger.debug("Installed a minimal pkg_resources shim for pyfatfs/fs")


# Raspberry Pi OS release the builder targets. These mirror the defaults in
# build-pi-image.sh; keep the two in step when moving to a newer release.
PI_OS_DIR_DATE = "2026-06-19"
PI_OS_FILE_DATE = "2026-06-18"
PI_OS_CODENAME = "trixie"


def base_image_url(pi_model: str = "5", variant: str = "lite") -> str:
    """Build the download URL for a Raspberry Pi OS base image."""
    arch = "armhf" if str(pi_model) == "3" else "arm64"
    if variant == "lite":
        repo, suffix = f"raspios_lite_{arch}", "-lite"
    elif variant in ("full", "desktop"):
        repo, suffix = f"raspios_{arch}", ""
    else:
        raise PiImageError(f"Unknown OS variant {variant!r}; expected 'lite' or 'full'")

    return (
        f"https://downloads.raspberrypi.org/{repo}/images/"
        f"{repo}-{PI_OS_DIR_DATE}/"
        f"{PI_OS_FILE_DATE}-raspios-{PI_OS_CODENAME}-{arch}{suffix}.img.xz"
    )


@dataclass
class ImageConfig:
    """Everything the built image needs to know."""

    output_path: str
    base_image_url: str
    hostname: str = "lablink"
    admin_user: str = "admin"
    admin_password: str = ""
    wifi_ssid: str = ""
    wifi_password: str = ""
    wifi_country: str = "US"
    enable_ssh: bool = True
    branch: str = "main"
    # True when admin_password was generated rather than chosen. The Pi shows
    # a generated password on its console after first boot, since nobody typed
    # it; a password the user chose is theirs and is never displayed.
    password_generated: bool = False
    extra_files: dict = field(default_factory=dict)


class PiImageError(RuntimeError):
    """Raised when an image cannot be built."""


# ---------------------------------------------------------------------------
# Partition table
# ---------------------------------------------------------------------------


def find_fat_partition(img_path: str) -> tuple[int, int]:
    """Return ``(offset, size)`` in bytes of the FAT boot partition.

    Reads the MBR directly rather than shelling out to ``parted``, which does
    not exist on Windows. Raspberry Pi images use a DOS partition table whose
    first entry is the FAT boot partition.
    """
    with open(img_path, "rb") as fh:
        mbr = fh.read(512)

    if mbr[510:512] != b"\x55\xaa":
        raise PiImageError(
            "This does not look like a disk image: the MBR boot signature is "
            "missing. Was the download truncated?"
        )

    fat_types = {0x01, 0x04, 0x06, 0x0B, 0x0C, 0x0E}
    for i in range(4):
        entry = mbr[446 + i * 16: 446 + (i + 1) * 16]
        ptype = entry[4]
        lba = struct.unpack_from("<I", entry, 8)[0]
        sectors = struct.unpack_from("<I", entry, 12)[0]
        if ptype in fat_types and sectors:
            return lba * 512, sectors * 512

    raise PiImageError("No FAT boot partition found in the image's partition table")


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

# Deliberately excludes 0/O and 1/l/I. This password is read off a screen or a
# console banner and typed by hand, and a character nobody can identify is a
# support problem rather than a security feature.
_PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


def generate_admin_password(groups: int = 4, group_size: int = 4) -> str:
    """Return a random password, grouped for legibility.

    Used when no password is given, so that a blank field produces an image
    with a *strong unique* login rather than either a known default or -- as
    it did before -- no account at all.

    Guarantees an upper-case letter and a digit, which the LabLink web account
    requires, and draws from an alphabet with no look-alike characters so it
    survives being copied off a first-boot banner by hand.
    """
    import secrets

    while True:
        parts = [
            "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(group_size))
            for _ in range(groups)
        ]
        candidate = "-".join(parts)
        if any(c.isupper() for c in candidate) and any(c.isdigit() for c in candidate):
            return candidate


def hash_password_for_userconf(password: str) -> str:
    """SHA-512 crypt hash, the format ``userconf.txt`` expects.

    The shell builder shells out to ``openssl passwd -6``, which Windows does
    not have. ``crypt`` was removed from the standard library in Python 3.13,
    so use passlib, which is pure Python and works everywhere.
    """
    try:
        from passlib.hash import sha512_crypt
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise PiImageError(
            "passlib is required to set the Pi account password.\n"
            "Install it with:  pip install passlib"
        ) from exc

    return sha512_crypt.using(rounds=5000).hash(password)


# ---------------------------------------------------------------------------
# Download and decompress
# ---------------------------------------------------------------------------


def download_base_image(url: str, dest: str, progress: Optional[ProgressFn] = None) -> str:
    """Download the compressed base image, resuming nothing, reporting progress."""

    def report(pct: int, msg: str) -> None:
        if progress:
            progress(pct, msg)

    report(2, "Contacting the Raspberry Pi OS download server...")
    request = urllib.request.Request(url, headers={"User-Agent": "LabLink-ImageBuilder"})
    with urllib.request.urlopen(request, timeout=60) as response:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        with open(dest, "wb") as out:
            while True:
                chunk = response.read(1024 * 512)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if total:
                    # 2%..30% of the overall build
                    report(2 + int(28 * done / total),
                           f"Downloading base image: {done // (1024*1024)} / "
                           f"{total // (1024*1024)} MB")
    report(30, "Base image downloaded")
    return dest


def decompress_image(xz_path: str, img_path: str, progress: Optional[ProgressFn] = None) -> str:
    """Decompress the ``.img.xz`` with the standard library."""

    def report(pct: int, msg: str) -> None:
        if progress:
            progress(pct, msg)

    report(32, "Decompressing the base image...")
    written = 0
    with lzma.open(xz_path, "rb") as src, open(img_path, "wb") as dst:
        while True:
            chunk = src.read(1024 * 1024 * 4)
            if not chunk:
                break
            dst.write(chunk)
            written += len(chunk)
            # 32%..70%, size is unknown up front so report throughput instead
            report(min(69, 32 + written // (1024 * 1024 * 64)),
                   f"Decompressing: {written // (1024*1024)} MB written")
    report(70, "Base image decompressed")
    return img_path


# ---------------------------------------------------------------------------
# Customisation
# ---------------------------------------------------------------------------


def _script_dir() -> Path:
    """Locate ``scripts/pi`` whether running from a checkout or an install."""
    here = Path(__file__).resolve()
    for base in (here.parents[2], here.parents[1], Path.cwd()):
        candidate = base / "scripts" / "pi"
        if (candidate / "firstrun.sh").exists():
            return candidate
    raise PiImageError(
        "Could not find scripts/pi/firstrun.sh. Run the builder from a LabLink "
        "checkout, or reinstall the client."
    )


# A git branch or tag, restricted to what is safe to paste into a URL inside a
# double-quoted shell string. Deliberately narrower than git's own rules.
_SAFE_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


def _no_control_chars(field_name: str, value: str) -> str:
    """Reject newlines and NULs in a value destined for a line-based file.

    A newline in an SSID would add arbitrary keys to the NetworkManager
    connection file, and in userconf.txt would corrupt the account record.
    Nothing legitimate needs one, and no Qt line edit can produce one, so
    refuse rather than trying to make it work.
    """
    if any(c in value for c in ("\n", "\r", "\0")):
        raise PiImageError(
            f"{field_name} may not contain a line break or a null character."
        )
    return value


def _sq(value: str) -> str:
    """Escape a value for use *inside* single quotes in a shell script.

    Every placeholder in firstrun.sh sits inside single quotes, and that script
    runs as root on first boot. A Wi-Fi password containing an apostrophe would
    otherwise end the quoted string early and have the remainder executed --
    a command injection reachable from a text field in the wizard.
    """
    return value.replace("'", "'\\''")


def _render(template: str, values: dict) -> str:
    """Substitute __PLACEHOLDER__ tokens, and normalise to Unix line endings.

    CRLF matters: these files are written on Windows but executed by bash on
    the Pi, where a trailing \\r makes the shebang line fail with a confusing
    "bad interpreter" error.
    """
    for key, value in values.items():
        template = template.replace(f"__{key}__", value)
    return template.replace("\r\n", "\n")


def _refresh_fsinfo(img_path: str, offset: int) -> None:
    """Recompute the FAT32 FSInfo free-cluster count after writing.

    pyfatfs allocates clusters without maintaining FSInfo, so a customised
    image reports more free space than it has and ``fsck.vfat`` flags it as
    dirty. The count is only a hint and Linux recomputes it, but an image that
    fails a filesystem check is one nobody can distinguish from a corrupt one.
    """
    with open(img_path, "r+b") as fh:
        fh.seek(offset)
        bpb = fh.read(512)
        bytes_per_sector = struct.unpack_from("<H", bpb, 11)[0]
        sectors_per_cluster = bpb[13]
        reserved = struct.unpack_from("<H", bpb, 14)[0]
        num_fats = bpb[16]
        sectors_per_fat = struct.unpack_from("<I", bpb, 36)[0]
        fsinfo_sector = struct.unpack_from("<H", bpb, 48)[0]
        if not fsinfo_sector or not sectors_per_fat or not sectors_per_cluster:
            return  # not FAT32, so there is no FSInfo to maintain

        # The FAT is padded out to a whole number of sectors, so it holds more
        # entries than there are clusters. Counting the padding as free space
        # inflates the total and fails fsck just as surely as not counting at
        # all, so derive the real cluster count from the BPB.
        total_sectors = (struct.unpack_from("<H", bpb, 19)[0]
                         or struct.unpack_from("<I", bpb, 32)[0])
        data_sectors = total_sectors - (reserved + num_fats * sectors_per_fat)
        cluster_count = data_sectors // sectors_per_cluster
        last_cluster = cluster_count + 1  # clusters are numbered from 2

        fh.seek(offset + fsinfo_sector * bytes_per_sector)
        fsinfo = fh.read(512)
        if (struct.unpack_from("<I", fsinfo, 0)[0] != 0x41615252
                or struct.unpack_from("<I", fsinfo, 484)[0] != 0x61417272):
            logger.warning("FSInfo signatures absent; leaving the free count alone")
            return

        fh.seek(offset + reserved * bytes_per_sector)
        fat = fh.read(sectors_per_fat * bytes_per_sector)

        free = 0
        first_free = 0xFFFFFFFF
        for cluster in range(2, min(last_cluster + 1, len(fat) // 4)):
            if struct.unpack_from("<I", fat, cluster * 4)[0] & 0x0FFFFFFF == 0:
                free += 1
                if first_free == 0xFFFFFFFF:
                    first_free = cluster

        fh.seek(offset + fsinfo_sector * bytes_per_sector + 488)
        fh.write(struct.pack("<II", free, first_free))
        fh.flush()
    logger.debug("FSInfo updated: %d free clusters, next free %d", free, first_free)


def _write_file(fs, name: str, content: str) -> None:
    """Replace a file on the boot partition, creating it if absent.

    Opening an existing file for writing frees its cluster chain but leaves
    the directory entry pointing at the old start cluster, so a subsequent
    multi-cluster write walks into free space and fails. Removing the entry
    first avoids that, and matters whenever the builder runs over an image
    that has already been customised.
    """
    try:
        fs.remove(name)
    except Exception:  # fs.errors.ResourceNotFound and friends
        pass
    with fs.open(name, "w") as handle:
        handle.write(content)


def customize_image(img_path: str, config: ImageConfig,
                    progress: Optional[ProgressFn] = None) -> None:
    """Write LabLink's configuration into the image's FAT boot partition."""

    def report(pct: int, msg: str) -> None:
        if progress:
            progress(pct, msg)

    _install_pkg_resources_shim()
    from pyfatfs.PyFatFS import PyFatFS

    offset, size = find_fat_partition(img_path)
    logger.info("Boot partition at offset %d, %d MB", offset, size // (1024 * 1024))
    report(74, "Opening the image's boot partition...")

    scripts = _script_dir()

    # The branch is interpolated into a URL inside a double-quoted string, where
    # single-quote escaping does not help. Restrict it instead.
    if not _SAFE_BRANCH.match(config.branch):
        raise PiImageError(
            f"Refusing to build with branch {config.branch!r}: only letters, "
            "digits, dot, underscore, slash and hyphen are allowed."
        )

    subs = {
        "LABLINK_HOSTNAME": _sq(_no_control_chars("Hostname", config.hostname)),
        "WIFI_SSID": _sq(_no_control_chars("Wi-Fi SSID", config.wifi_ssid)),
        "WIFI_PASSWORD": _sq(_no_control_chars("Wi-Fi password",
                                               config.wifi_password)),
        "WIFI_COUNTRY": _sq(_no_control_chars("Wi-Fi country",
                                              config.wifi_country)),
        "ADMIN_USER": _sq(_no_control_chars("Admin user", config.admin_user)),
        "LABLINK_BRANCH": config.branch,
    }
    _no_control_chars("Admin password", config.admin_password)

    # pyfatfs can mount a filesystem at a byte offset inside a larger file,
    # so the partition needs no extraction and no loop device.
    fs = PyFatFS(filename=img_path, offset=offset, read_only=False)
    try:
        # cmdline.txt: append the first-run hook, without disturbing the rest
        report(78, "Patching cmdline.txt...")
        with fs.open("/cmdline.txt", "r") as fh:
            cmdline = fh.read()
        if any(p.startswith("init=") for p in cmdline.split()):
            # An init= entry means systemd is not PID 1 on the first boot, so
            # systemd.run= would be ignored and the image would boot as a
            # stock Pi with none of LabLink's setup — and look fine doing it.
            # Fail loudly rather than ship that.
            raise PiImageError(
                "This base image boots via an init= hook, which the first-run "
                "mechanism cannot override. Use a Raspberry Pi OS Bookworm or "
                "later image."
            )
        cmdline = " ".join(
            part for part in cmdline.split()
            if not part.startswith(("systemd.run=", "systemd.run_success_action=",
                                    "systemd.unit="))
        )
        boot_dir = "/boot/firmware"
        cmdline += (f" systemd.run={boot_dir}/firstrun.sh"
                    f" systemd.run_success_action=reboot"
                    f" systemd.unit=kernel-command-line.target")
        _write_file(fs, "/cmdline.txt", cmdline.strip() + "\n")

        report(82, "Writing the first-run script...")
        firstrun = _render((scripts / "firstrun.sh").read_text(encoding="utf-8"), subs)
        _write_file(fs, "/firstrun.sh", firstrun)

        report(86, "Writing the LabLink installer...")
        firstboot = _render((scripts / "lablink-first-boot.sh").read_text(encoding="utf-8"), subs)
        _write_file(fs, "/lablink-first-boot.sh", firstboot)

        if config.admin_password:
            report(88, "Staging the admin password...")
            # Raw value, no trailing newline: firstrun.sh reads it verbatim so
            # any character is safe.
            _write_file(fs, "/lablink-admin-password", config.admin_password)

            report(90, "Writing userconf.txt...")
            hashed = hash_password_for_userconf(config.admin_password)
            _write_file(fs, "/userconf.txt", f"{config.admin_user}:{hashed}\n")

            if config.password_generated:
                # Tells firstrun.sh to put the credentials on the console
                # login banner. Only for a generated password: one the user
                # chose is theirs, and displaying it would be a disclosure
                # they never asked for.
                _write_file(fs, "/lablink-password-generated", "")

        if config.enable_ssh:
            report(92, "Enabling SSH...")
            _write_file(fs, "/ssh", "")

        for name, content in config.extra_files.items():
            _write_file(fs, f"/{name}", content)

        report(95, "Flushing the boot partition...")
    finally:
        fs.close()

    # Only valid once pyfatfs has written the FAT out, so it must follow close.
    _refresh_fsinfo(img_path, offset)


def build_image(config: ImageConfig, progress: Optional[ProgressFn] = None,
                work_dir: Optional[str] = None) -> str:
    """Download, decompress and customise an image. Returns its path."""

    def report(pct: int, msg: str) -> None:
        if progress:
            progress(pct, msg)

    out = Path(config.output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    work = Path(work_dir) if work_dir else out.parent
    xz_path = work / (out.name + ".xz")

    report(0, "Starting image build...")
    try:
        download_base_image(config.base_image_url, str(xz_path), progress)
        decompress_image(str(xz_path), str(out), progress)
        customize_image(str(out), config, progress)
    finally:
        try:
            if xz_path.exists():
                xz_path.unlink()
        except OSError:
            logger.warning("Could not remove the temporary download %s", xz_path)

    report(100, f"Image ready: {out}")
    return str(out)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def main(argv: Optional[list] = None) -> int:
    """Build an image without the GUI.

    Useful for scripted and headless builds, and for testing this module on a
    machine whose Python is too old for the desktop client -- the client needs
    3.12+ because of numpy and PyQt6, but nothing here does.

    Run from a LabLink checkout, since the scripts written into the image are
    read from scripts/pi/.
    """
    import argparse
    import getpass

    parser = argparse.ArgumentParser(
        prog="python -m client.utils.pi_image_native",
        description="Build a customised Raspberry Pi image for LabLink. "
                    "Needs no administrator privileges on any platform.",
    )
    parser.add_argument("-o", "--output", required=True,
                        help="path to write the .img file to")
    parser.add_argument("--hostname", default="lablink-pi")
    parser.add_argument("--user", default="admin", help="account to create")
    parser.add_argument("--password",
                        help="password for that account; prompted for if omitted")
    parser.add_argument("--wifi-ssid", default="",
                        help="leave unset for an ethernet-only Pi")
    parser.add_argument("--wifi-password", default="")
    parser.add_argument("--wifi-country", default="US",
                        help="two-letter regulatory domain (default: US)")
    parser.add_argument("--branch", default="main",
                        help="LabLink branch the Pi installs on first boot")
    parser.add_argument("--pi-model", default="5", choices=["3", "4", "5"])
    parser.add_argument("--os-variant", default="lite", choices=["lite", "full"])
    parser.add_argument("--no-ssh", action="store_true", help="do not enable SSH")
    parser.add_argument("--image", help="use this local .img instead of "
                                        "downloading (it is modified in place)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    password = args.password
    if password is None:
        password = getpass.getpass(
            f"Password for {args.user!r} on the Pi (blank to generate one): "
        )

    # An empty password used to mean no account at all: userconf.txt is only
    # written when one is set, so the image booted with sshd enabled and
    # nothing to log in as. Generate one instead, and say so.
    password_generated = not password
    if password_generated:
        password = generate_admin_password()
        print(f"\nGenerated password for {args.user!r}: {password}")
        print("Write it down; it is also shown on the Pi's console after first "
              "boot.\n")

    config = ImageConfig(
        output_path=args.output,
        base_image_url=base_image_url(args.pi_model, args.os_variant),
        hostname=args.hostname,
        admin_user=args.user,
        admin_password=password,
        password_generated=password_generated,
        wifi_ssid=args.wifi_ssid,
        wifi_password=args.wifi_password,
        wifi_country=args.wifi_country,
        enable_ssh=not args.no_ssh,
        branch=args.branch,
    )

    last = [-1]

    def report(pct: int, message: str) -> None:
        # One line per percent at most: this runs for minutes and the download
        # would otherwise scroll a terminal off its scrollback.
        if pct != last[0]:
            last[0] = pct
            print(f"[{pct:3d}%] {message}", flush=True)

    try:
        if args.image:
            from shutil import copyfile

            if args.image != args.output:
                copyfile(args.image, args.output)
            customize_image(args.output, config, report)
        else:
            build_image(config, report)
    except PiImageError as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        # A missing --image, an unwritable output path, a full disk, or a
        # failed download: urllib's errors subclass OSError too. All of these
        # are the user's environment rather than a bug, and a traceback makes
        # a working tool look broken.
        print(f"\nerror: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130

    print(f"\nWrite it to a card with Raspberry Pi Imager, balenaEtcher or dd:\n"
          f"  {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
