# Testing the Windows image builder

Branch: `feat/native-pi-image-builder` (PR #190)

## ▶ Next task

**Run the Qt wizard on Windows under Python 3.12+.** Procedure:
[Testing the wizard on Windows](#testing-the-wizard-on-windows-python-312).

It is not a repeat of the CLI run. It is the only route that reaches three
things nothing has touched yet:

- **the `pkg_resources` shim** -- a fresh 3.12 venv has no setuptools at all,
  so pip installs the current one (84) and `fs` cannot import without the
  shim. The machine used so far had setuptools 58.1.0, which still provides
  the module, so the shim has never actually run.
- **the Qt layer** -- the build on a `QThread`, progress signals reaching the
  GUI, the window staying responsive, cancelling mid-build.
- **the status bar branch indicator**, which was dead code until this branch
  and has never been seen working on Windows.

Report findings by appending a section to this file, as the previous runs did.

## Status

| | State |
|---|---|
| CLI builder on Windows | ✅ verified -- built an image, booted a Pi 5 end to end |
| Regression suite on Windows | ✅ 78 passed, 1 skipped (no dosfstools) |
| CI on Linux (3.12 + 3.13) | ✅ 15/15 |
| **Qt wizard on Windows** | ❌ **not run -- this is the next task** |
| `pkg_resources` shim | ❌ never exercised anywhere |
| Client restart after a branch switch, on Windows | ❌ not run |

Full detail in [Still open](#still-open). Two bugs have already come out of
Windows testing (1290bee, 0da195b), so treat "it worked" as worth recording
in as much detail as a failure.

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
python client\utils\pi_image_native.py -o lablink-test.img --hostname lablink-pi
```

Run the **file**, not `python -m client.utils.pi_image_native`. The `-m` form
imports the `client.utils` package, whose `__init__.py` pulls in numpy and
websockets, so it needs the full client dependency set rather than these two
packages. Running the file directly skips the package import entirely. (The
first Windows run used the `-m` form and worked only because numpy happened
to be installed already; the instruction was wrong, not the code.)

It prompts for the Pi account password. Add
`--wifi-ssid "Network" --wifi-password "..." --wifi-country US` for Wi-Fi;
leave them out for an ethernet-only Pi.

Budget ~500 MB of download, ~2.8 GB of output and about 90 seconds of work
once the download finishes.

`--image existing.img` skips the download and customises a local image, which
turns a smoke test into seconds.

## Option B: the wizard (needs Python 3.12+)

Step by step in
[Testing the wizard on Windows](#testing-the-wizard-on-windows-python-312)
below, which is the current procedure.

Whichever route you take, run it **from the checkout**. The builder reads
`scripts/pi/firstrun.sh` and `lablink-first-boot.sh` out of the tree; a
packaged install has neither, and it raises a clear error rather than
producing a broken image.

## Testing the wizard on Windows (Python 3.12+)

The CLI has been run on Windows and a Pi booted from its output. **The Qt
wizard has not.** This is the procedure for that run.

### 1. Install Python 3.12 alongside 3.10

Do not replace 3.10 -- installing side by side is supported and safer. Get
3.12 or newer from <https://www.python.org/downloads/> and tick **"Add Python
to PATH"**. The `py` launcher then selects between them:

```powershell
py -0p                 # lists every installed Python and its path
py -3.12 --version     # must report 3.12.x or newer
```

### 2. Get the branch

```powershell
cd $env:USERPROFILE
git clone -b feat/native-pi-image-builder https://github.com/X9X0/LabLink.git LabLink-wizard
cd LabLink-wizard
```

No git? Use the ZIP from Option A above; just note the folder name differs.

Pull first if the clone already exists -- the branch has moved since the CLI
run, and the two fixes that run produced (1290bee, 0da195b) plus their
regression tests are on it now.

### 3. Create the environment

```powershell
py -3.12 -m venv client\venv
client\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r client\requirements.txt
```

If `Activate.ps1` is blocked by execution policy, skip activation and use
`client\venv\Scripts\python.exe` in place of `python` throughout.

**This run finally exercises the `pkg_resources` shim.** Python 3.12's
`ensurepip` stopped installing setuptools, so a fresh venv has pip and
nothing else. `fs` (pyfatfs's dependency) declares setuptools as a runtime
requirement, so pip installs the current one -- 84 at the time of writing --
and setuptools removed `pkg_resources` in 81. `fs` cannot import without the
shim in that environment.

Confirmed on Linux in a fresh 3.12 venv: setuptools 84.0.0, `import
pkg_resources` raises ModuleNotFoundError, `import fs.base` fails without the
shim and succeeds with it, and a full build then completes. The first Windows
run could not test this because that machine had setuptools 58.1.0, which
still ships the module.

Record the result either way:

```powershell
pip show setuptools | Select-String "^Version"
python -c "import pkg_resources" ; echo "exit=$LASTEXITCODE"
```

An exit code of 1 means the shim is load-bearing for this run. An exit code
of 0 means setuptools still provides it and the shim is *again* untested --
worth saying so rather than assuming coverage.

### 4. Launch

```powershell
python client\main.py
```

Before touching the wizard, check the **status bar**. It should read
`LabLink 2.0.0  📍 feat/native-pi-image-builder (<hash>)`, in green and bold
because the branch is not main.

This indicator is itself new and unverified on Windows. It was previously
dead code everywhere: the git lookup ran on a worker thread and posted its
result with `QTimer.singleShot`, which creates a timer owned by a thread with
no event loop, so it never fired. It is a `pyqtSignal` now. If the branch
never appears, that is a bug worth reporting, not a cosmetic detail -- it is
the only on-screen answer to "which code is running".

If it shows only `LabLink 2.0.0` with no branch, check that the folder is a
git clone rather than a ZIP extract. A ZIP has no `.git` and the version
still shows, correctly, on its own.

### 5. Build an image

**Tools -> Build Raspberry Pi Image...**

| Field | Value |
|---|---|
| Pi Model | whatever the target board is (4 and 5 both use arm64) |
| Hostname | something distinct, e.g. `lablink-wiz`, so it does not collide on the network |
| Output path | anywhere with ~3 GB free |
| Admin password | your choice; it becomes the Pi login |
| Wi-Fi SSID / Password | leave blank for an ethernet Pi |
| Wi-Fi Country | two-letter code; only read when an SSID is set |
| LabLink Branch | `main` for a normal image, or this branch to test it end to end |
| Base OS | Lite |

The first two lines in the output pane must be:

```
Building with the native (pure Python) builder.
No administrator privileges are required.
```

If instead you see **"This tool requires bash to be installed"**, the wizard
took the shell path, which should be unreachable on Windows -- report it with
the full output.

**No UAC prompt should appear at any point.** The whole purpose of this
change is that no elevation is required.

### 6. What the wizard exercises that the CLI did not

- The build runs on a `QThread`, with progress delivered to the GUI by
  signals. Watch that the progress bar and output pane keep updating and the
  window stays responsive rather than greying out.
- Cancelling or closing mid-build -- worth trying once deliberately, on a run
  you do not need.
- The Wi-Fi country field, which the CLI run left at its default.
- The output-path file dialog, and paths containing spaces
  (`C:\Users\Your Name\...`) -- worth choosing one deliberately, since
  quoting bugs hide there.

### 7. Verify the image

Same as the CLI: the independent FAT32 reader, described under "Verifying an
image without a Pi" below. Then write it to a card and boot it.

### What to report

- `py -3.12 --version`, and `pip show pyfatfs passlib setuptools`
- whether `import pkg_resources` succeeded or failed (step 3)
- whether the status bar showed the branch (step 4)
- the first two lines of the build output (step 5)
- whether any UAC prompt appeared
- total build time, and whether the UI stayed responsive
- the full traceback if it fails

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

- ~~No image built by this code has been booted on a Pi.~~ Done -- see
  [Findings from the first Windows test](#findings-from-the-first-windows-test-2026-09-01)
  below. A CLI-built image booted, ran first-run setup end to end, and served
  its web UI and API.
- `fsck.vfat` itself was never run against a built image -- see that section
  for why, and what stood in for it. It runs in CI on Linux against a
  synthetic image, so the check is not absent overall, only from the
  Windows-built one.
- The `pkg_resources` shim is still unexercised: the test machine had
  setuptools 58.1.0, which still provides the module. It needs a run against
  setuptools >= 81, where `fs` cannot import without it.
- **The Qt wizard has still not run on Windows** -- only the CLI. This is the
  current next task; see
  [Testing the wizard on Windows](#testing-the-wizard-on-windows-python-312)
  for the procedure. It also covers the shim gap above, because a fresh 3.12
  venv has no setuptools at all.
- The client restart after an in-app branch switch is unverified on Windows.
  It takes a different path there -- `subprocess.Popen` then exit, rather than
  `os.execv`, which detaches the console on Windows and loses output.

## Findings from the first Windows test (2026-09-01)

First real run of this branch on Windows, both the CLI builder and a boot on
actual Pi hardware. Recorded here because both a build-time bug and a
first-boot bug turned up, and neither was visible from Linux-only testing.

### Environment

- Windows 11, Python 3.10.4 (meets the CLI's 3.8+ floor; the Qt wizard was not
  tested -- that needs 3.12+)
- `pip show`: pyfatfs 1.1.0, passlib 1.7.4, setuptools 58.1.0
- setuptools 58.1.0 still has `pkg_resources`, so the shim in
  `_install_pkg_resources_shim()` was never exercised this round. It remains
  untested against setuptools >= 81.
- No `fsck.vfat`/`mtools` on native Windows, and WSL's Ubuntu had neither
  installed with no passwordless `sudo` available to add them. Skipped rather
  than prompt for a password; verification relied on the independent FAT32
  reader only, described below.

### Bug 1: `Path.read_text()` decoded with the wrong codec on Windows

The first build attempt failed at 86%:

```
UnicodeDecodeError: 'charmap' codec can't decode byte 0x90 in position 9698:
character maps to <undefined>
```

`scripts/pi/lablink-first-boot.sh` is UTF-8 and contains a box-drawing banner
(`═` x14, U+2550) in its status output. `pi_image_native.py` read both
`firstrun.sh` and `lablink-first-boot.sh` with plain `Path.read_text()`,
which has no `encoding=` argument and so falls back to the process's locale
encoding -- cp1252 on this machine, not UTF-8. Byte 0x90 is invalid cp1252.

This is a Windows-only failure: the same call on Linux/macOS defaults to
UTF-8 and never notices. It sat outside the four risks the top of this doc
called out (setuptools, CRLF, big-file I/O, passlib) -- a fifth risk in the
same "Windows reads text differently" family.

The write side was checked too, since a similar bug there would corrupt the
banner rather than crash: `fs.open()` in the `fs` library (pyfatfs's
dependency) hardcodes `encoding=encoding or "utf-8"` regardless of locale, so
writing back into the FAT filesystem was never at risk.

**Fix**: added `encoding="utf-8"` to both `.read_text()` calls in
`pi_image_native.py` (`customize_image`, around lines 424 and 428).
Re-running the build against the already-decompressed image (via `--image`)
confirmed the fix -- build completed, and the FAT32 reader confirmed both
scripts round-tripped with Unix-only line endings and the banner intact.
Shipped as 1290bee; regression tests in `TestWindowsTextHandling`, which
reproduce the failure on Linux under a forced ASCII locale.

### Independent FAT32 reader check: passed

Against the successfully-built image:

- Expected files present: `firstrun.sh`, `lablink-first-boot.sh`,
  `lablink-admin-password`, `userconf.txt`, `ssh`
- `cmdline.txt` correctly patched (`systemd.run=/boot/firmware/firstrun.sh`,
  no leftover or duplicate directives, no `init=`)
- `userconf.txt` held a valid `$6$...` SHA-512 crypt hash from passlib
- Hostname and Wi-Fi SSID substitutions landed correctly
- Both scripts had Unix line endings only, no stray `\r`
- The UTF-8 banner decoded cleanly after the fix

### First real Pi boot: succeeded

A Pi 5 was imaged from the CLI-built `.img` via a card writer (not this
machine) and booted. Full chain worked on the first attempt:

FAT32 write &rarr; Pi OS first boot &rarr; `firstrun.sh` &rarr;
`lablink-first-boot.service` &rarr; apt upgrade &rarr; Docker install &rarr;
LabLink container build (`fastapi`, `pandas`, `numpy`, `scipy`, `pyvisa`,
...) &rarr; healthy running stack.

Verified over SSH (`admin` / the password passed to `--password`) and from
the host machine:

- `http://<pi-ip>/` &rarr; `200`
- `http://<pi-ip>:8000/health` &rarr; `{"status":"healthy","connected_devices":0}`

`sshpass` was not available locally; the SSH checks used Python's
`paramiko` instead (password auth, no interactive terminal needed).

### Bug 2: broken container-health wait loop in `lablink-first-boot.sh`

`lablink-first-boot.sh:224-226` used `local max_wait=60`, `local waited=0`
and `local containers_up=false` at the top level of the script -- not inside
a function. Confirmed with an isolated `bash -c` test that `local` outside a
function fails ("local: can only be used in a function") *without*
performing the assignment, leaving all three variables unset.

That turns the bounded wait `while [ $waited -lt $max_wait ]` into
`[ -lt ]` after empty-variable expansion, which `test` evaluates as a single
non-empty string -- always true. The intended 60-second timeout became an
unbounded busy loop.

It didn't show up on this boot only by luck: `docker compose ps` already
reported "Up" on the very first check, so the loop's `break` fired on
iteration one, before the bug's failure mode (an infinite spin with no
timeout, no diagnostic dump) could matter. A slower container start --
weaker network, more services, a Pi 3 -- would have hung
`lablink-first-boot.service` indefinitely instead of falling through to the
existing timeout/diagnostic branch.

This file is new to this branch in its entirety (extracted so the bash and
native builders share one copy), so the bug is in scope here even though it
has nothing to do with Windows specifically.

**Fix**: dropped `local` from those three assignments -- they're script-level
globals, not function-local, so the keyword was never valid. Shipped as
0da195b; regression tests in `TestFirstBootScriptShell`.

### Noted, not fixed: `lablink.service` shows inactive right after first boot

Immediately after first-boot setup, `systemctl status lablink.service`
reports `inactive (dead)` even though the containers are up and healthy.
`lablink-first-boot.sh` starts them directly with `docker compose up -d`
rather than through `systemctl start lablink.service`, so the unit's
`RemainAfterExit=yes` state is never set until systemd itself runs
`ExecStart` -- which only happens on the *next* reboot, since the unit is
merely `enable`d here, not started. `lablink-status`'s "LabLink service: Not
active" line is misleading in this narrow first-boot window even though
LabLink itself is fine.

This is pre-existing behaviour carried into the new shared script (the old
bash builder's inline copy did the same thing), not something the
Windows-native-builder work introduced, and it resolves itself on the next
real reboot. Left as-is rather than fixed, since it's outside the scope of
this branch's purpose.

## Findings from running the new regression suite on Windows (2026-09-01)

`tests/client/test_pi_image_native.py` (added after the findings above,
covering both bugs plus a lot more) was run on the same Windows 11 / Python
3.10.4 machine: 72 passed, 1 skipped (`test_fsck_reports_a_clean_filesystem`
-- no `dosfstools` on this machine, exactly as expected from the earlier
section), 6 failed.

All six failures were one parametrized test,
`TestShellInjection::test_hostile_values_stay_inside_their_quotes`. Every one
failed the same way:

```
/bin/bash: C:\Users\...\check.sh: No such file or directory
```

**Not a code bug.** This machine has WSL installed, and a bare `bash` on
`PATH`, invoked the way `subprocess.run(["bash", str(harness)])` does,
resolved to the WSL interop launcher rather than Git Bash's own
`bash.exe` -- confirmed with `bash --version`, which reported
`x86_64-pc-linux-gnu` (WSL) rather than the `x86_64-pc-msys` Git Bash
reports, even though `where bash` lists Git's copy first. That launcher
mangles a Windows-style absolute path passed as an argument -- it silently
drops every backslash, so `C:\Users\...\check.sh` becomes
`C:Users...check.sh`, which naturally does not exist.

Confirmed by calling Git Bash's `bash.exe` directly by its full path with the
identical script: exits 0, output correct. The sibling test in the same
class, `test_hostile_values_do_not_execute`, uses `bash -c "<line>"` instead
of a script *path* and passes cleanly, which is consistent with the theory --
there is no path argument for the WSL launcher to mangle.

The diagnosis is right, but the conclusion has been revised: **the tests
were changed rather than the machine.**

Passing a path was an incidental choice, not something either test needed.
Both now feed the script to bash on **stdin** and read the result back on
**stdout**, so no filesystem path crosses the boundary in either direction
and it no longer matters which bash answers:

- `test_hostile_values_stay_inside_their_quotes` returns the values
  NUL-separated on stdout. NUL is the one byte a shell variable cannot
  contain, so it is a safe separator for deliberately hostile values.
- `test_hostile_values_do_not_execute` had a second, quieter problem. It
  detected an injection by `touch`ing a marker file, which the WSL launcher
  would create in *its* filesystem rather than the one Python inspects -- so
  the assertion would have held whether or not the injection fired, passing
  for the wrong reason on precisely the platform this branch exists to
  support. It now has the injected command echo a marker to stdout.

Both were re-verified by disabling the quote escaping in `_sq()`: each fails,
and passes again once restored.

The WSL detail is still worth knowing when debugging anything else that
shells out: a bare `bash` can resolve to the WSL interop launcher even when
`where bash` lists Git Bash first, and it strips backslashes from Windows
paths given as arguments. `bash --version` reporting `x86_64-pc-linux-gnu`
rather than `x86_64-pc-msys` is the tell.

### Re-verified on the same Windows machine: the WSL fix holds

Pulled `07519e7` and re-ran the full suite on the same Windows 11 / Python
3.10.4 machine that produced the six failures above:

```
78 passed, 1 skipped, 2 warnings
```

The skip is `test_fsck_reports_a_clean_filesystem` -- still no `dosfstools`
on this machine, exactly as expected. Every previously-failing test now
passes, including both rewritten ones. No other regressions.
