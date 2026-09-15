"""A minimal, independent FAT32 reader used to verify built Pi images.

This deliberately shares no code with pyfatfs, which is what writes the images.
Verifying a writer with its own reader proves only self-consistency; if both
agree on a wrong interpretation of the on-disk format, the Pi still refuses to
boot and the tests still pass. So this parses the BPB, the FAT and the
directory entries directly from bytes.

It is read-only and only supports what a Raspberry Pi boot partition needs:
FAT32, the root directory, long filenames, and following a cluster chain.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

ATTR_LONG_NAME = 0x0F
ATTR_VOLUME_ID = 0x08


@dataclass
class Bpb:
    """The BIOS Parameter Block: the geometry needed to find anything."""

    bytes_per_sector: int
    sectors_per_cluster: int
    reserved_sectors: int
    num_fats: int
    sectors_per_fat: int
    root_cluster: int

    @property
    def cluster_size(self) -> int:
        return self.bytes_per_sector * self.sectors_per_cluster

    @property
    def fat_start(self) -> int:
        return self.reserved_sectors * self.bytes_per_sector

    @property
    def data_start(self) -> int:
        return self.fat_start + self.num_fats * self.sectors_per_fat * self.bytes_per_sector


def find_fat_partition_offset(img_path: str) -> int:
    """Locate the first FAT partition by reading the MBR by hand."""
    with open(img_path, "rb") as fh:
        mbr = fh.read(512)
    assert mbr[510:512] == b"\x55\xaa", "missing MBR signature"
    for i in range(4):
        entry = mbr[446 + i * 16: 446 + (i + 1) * 16]
        if entry[4] in (0x01, 0x04, 0x06, 0x0B, 0x0C, 0x0E) and entry[12:16] != b"\0\0\0\0":
            return struct.unpack_from("<I", entry, 8)[0] * 512
    raise AssertionError("no FAT partition in the MBR")


class Fat32Reader:
    """Reads files out of a FAT32 partition inside a disk image."""

    def __init__(self, img_path: str, offset: int):
        self._fh = open(img_path, "rb")
        self._offset = offset
        self._bpb = self._read_bpb()
        self._fat = self._read_fat()

    def close(self) -> None:
        self._fh.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- structures ---------------------------------------------------------
    def _at(self, pos: int, size: int) -> bytes:
        self._fh.seek(self._offset + pos)
        return self._fh.read(size)

    def _read_bpb(self) -> Bpb:
        b = self._at(0, 512)
        bpb = Bpb(
            bytes_per_sector=struct.unpack_from("<H", b, 11)[0],
            sectors_per_cluster=b[13],
            reserved_sectors=struct.unpack_from("<H", b, 14)[0],
            num_fats=b[16],
            sectors_per_fat=struct.unpack_from("<I", b, 36)[0],
            root_cluster=struct.unpack_from("<I", b, 44)[0],
        )
        assert bpb.bytes_per_sector in (512, 1024, 2048, 4096), "implausible sector size"
        assert bpb.sectors_per_fat, "not FAT32 (16-bit FAT size is in use)"
        return bpb

    def _read_fat(self) -> bytes:
        return self._at(self._bpb.fat_start,
                        self._bpb.sectors_per_fat * self._bpb.bytes_per_sector)

    def _chain(self, start: int) -> list[int]:
        """Follow a cluster chain to its end marker."""
        clusters, cluster = [], start
        while 2 <= cluster < 0x0FFFFFF8 and len(clusters) < 1_000_000:
            clusters.append(cluster)
            cluster = struct.unpack_from("<I", self._fat, cluster * 4)[0] & 0x0FFFFFFF
        return clusters

    def _cluster_bytes(self, cluster: int) -> bytes:
        pos = self._bpb.data_start + (cluster - 2) * self._bpb.cluster_size
        return self._at(pos, self._bpb.cluster_size)

    def _read_chain(self, start: int) -> bytes:
        return b"".join(self._cluster_bytes(c) for c in self._chain(start))

    # -- directory ----------------------------------------------------------
    def list_root(self) -> dict[str, tuple[int, int]]:
        """Map filename -> (first cluster, size in bytes) for the root dir."""
        data = self._read_chain(self._bpb.root_cluster)
        entries: dict[str, tuple[int, int]] = {}
        lfn_parts: dict[int, str] = {}

        for i in range(0, len(data), 32):
            entry = data[i:i + 32]
            if len(entry) < 32 or entry[0] == 0x00:
                break
            if entry[0] == 0xE5:  # deleted
                lfn_parts.clear()
                continue

            attrs = entry[11]
            if attrs == ATTR_LONG_NAME:
                seq = entry[0] & 0x1F
                raw = entry[1:11] + entry[14:26] + entry[28:32]
                text = raw.decode("utf-16-le", errors="ignore")
                lfn_parts[seq] = text.split("￿")[0].split("\x00")[0]
                continue
            if attrs & ATTR_VOLUME_ID:
                lfn_parts.clear()
                continue

            if lfn_parts:
                name = "".join(lfn_parts[k] for k in sorted(lfn_parts))
                lfn_parts.clear()
            else:
                stem = entry[0:8].decode("ascii", "ignore").rstrip()
                ext = entry[8:11].decode("ascii", "ignore").rstrip()
                name = f"{stem}.{ext}" if ext else stem

            cluster = (struct.unpack_from("<H", entry, 20)[0] << 16) | \
                struct.unpack_from("<H", entry, 26)[0]
            size = struct.unpack_from("<I", entry, 28)[0]
            entries[name] = (cluster, size)

        return entries

    def read_file(self, name: str) -> bytes:
        """Read one root-directory file, matched case-insensitively."""
        entries = self.list_root()
        for key, (cluster, size) in entries.items():
            if key.lower() == name.lower():
                if size == 0:
                    return b""
                return self._read_chain(cluster)[:size]
        raise FileNotFoundError(f"{name} not in {sorted(entries)}")
