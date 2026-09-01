# Testing the Windows image builder

Branch: `feat/native-pi-image-builder` (PR #190)

Everything here is verified on Linux and **unverified on Windows**, which is
the entire point of the change. This is the handoff for whoever runs it there.

## What changed and why it needs Windows testing

The Pi image builder used to loop-mount the image, map its partitions with
`kpartx`, chroot into the ext4 root under ARM emulation and need root for all
of it. None of that exists on Windows, so the wizard failed part-way through
with an error about `bash`.

The replacement writes **only the FAT32 boot partition**, which is reachable
in pure Python at a byte offset inside the `.img`, and defers everything else
to Raspberry Pi OS's own first-run hook (`systemd.run=` in `cmdline.txt`) --
the mechanism Raspberry Pi Imager uses. No root, no loop device, no bash, no
qemu.

Since the whole purpose is the Windows path, Linux results prove nothing about
the thing being changed. What is genuinely unexercised there:

- the `pkg_resources` shim, against whatever setuptools the venv resolves
  (`fs`, a pyfatfs dependency, still imports a module setuptools 81 removed)
- path handling and line endings -- the scripts are written on Windows and run
  by bash on the Pi, where a stray `\r` gives a confusing "bad interpreter"
- writing and seeking inside a ~2.8 GB file
- `passlib` producing the SHA-512 crypt hash, since Windows has no `openssl`
  and Python 3.13 removed `crypt`

## Requirements

The **desktop client** needs Python **3.12+**: numpy 2.5, pandas 3.0 and
PyQt6 6.11 all dropped 3.11 and below. On an older Python, `pip install`
fails with a dependency-resolution error rather than saying so.

The **builder itself** has no such floor -- pyfatfs declares 3.8+, passlib has
none, the rest is standard library. So the CLI can be tested on an older
Python without upgrading anything, and it exercises every Windows-specific
risk listed above. Only the Qt wizard on top is untested that way, and Qt is
already known to work on Windows.

## Option A: the CLI (works on Python 3.8+)

```powershell
cd $env:USERPROFILE
Invoke-WebRequest -Uri "https://github.com/X9X0/LabLink/archive/refs/heads/feat/native-pi-image-builder.zip" -OutFile lablink.zip
Expand-Archive lablink.zip -DestinationPath .
cd LabLink-feat-native-pi-image-builder
python -m pip install pyfatfs passlib
python -m client.utils.pi_image_native -o lablink-test.img --hostname lablink-pi
```

It prompts for the Pi account password. Add
`--wifi-ssid "Network" --wifi-password "..." --wifi-country US` for Wi-Fi;
leave them out for an ethernet-only Pi.

Budget ~500 MB of download, ~2.8 GB of output and about 90 seconds of work
once the download finishes.

`--image existing.img` skips the download and customises a local image, which
turns a smoke test into seconds.

## Option B: the wizard (needs Python 3.12+)

```powershell
git clone -b feat/native-pi-image-builder https://github.com/X9X0/LabLink.git
cd LabLink
py -3.12 -m venv client\venv
client\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r client\requirements.txt
python client\main.py
```

Then **Tools -> Build Raspberry Pi Image...**

Run it from the checkout. The builder reads `scripts/pi/firstrun.sh` and
`lablink-first-boot.sh` from the tree; a packaged install has neither, and it
raises a clear error rather than producing a broken image.

## Confirming you are on the right code

The status bar shows `LabLink <version>  📍 <branch> (<hash>)`, highlighted
when the branch is not main.

The build log's first two lines must be:

```
Building with the native (pure Python) builder.
No administrator privileges are required.
```

If you see **"This tool requires bash to be installed"**, you are running
older code, not this branch. That message exists only on the shell path,
which this branch never takes on Windows.

Note that the in-app branch selector (developer mode) restarts the client
after switching branches. It has to: `client/main.py` imports the whole UI at
module scope, so a checkout that does not restart leaves the old code running
in memory while reporting success. That restart is part of this branch -- a
2.0 client cannot switch onto this branch and load it, because the fix for
that is *on* the branch.

## What to report back

- `python --version`
- `pip show pyfatfs passlib setuptools`
- the full traceback if it fails
- whether the produced `.img` boots a Pi

## Verifying an image without a Pi

`fsck` should be clean and the boot partition should hold the expected files.
On Linux:

```bash
dd if=lablink-test.img of=boot.vfat bs=1M skip=8 count=512
fsck.vfat -n boot.vfat        # must exit 0
```

The repository ships an independent FAT32 reader used by the tests, which
shares no code with the library that writes the image:

```bash
python -c "
from tests.client.fat_reader import Fat32Reader, find_fat_partition_offset
img = 'lablink-test.img'
with Fat32Reader(img, find_fat_partition_offset(img)) as fs:
    print(sorted(n for n in fs.list_root() if 'lablink' in n.lower() or n in ('ssh','userconf.txt','firstrun.sh')))
    print(fs.read_file('cmdline.txt').decode())
"
```

Reading an image back through the library that wrote it proves the two agree,
not that the bytes are right. That distinction caught two real defects here,
so keep the check independent.

## Still open

- **No image built by this code has been booted on a Pi.** `fsck` passes and
  the files parse correctly, which is not the same thing.
- The Windows path itself, per everything above.
