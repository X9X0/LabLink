# Testing the Windows image builder

Branch: `feat/native-pi-image-builder` (PR #190)

## ▶ Next task

**End-to-end through the GUI: build an image, write the card, boot the Pi.**
Every stage has now been done in isolation; none has been done as one chain,
and the card write in particular has never succeeded from the wizard.

1. `git pull`, then launch the client from the 3.12 venv.
2. Confirm the status bar reads `feat/native-pi-image-builder` **before doing
   anything else**. If it does not, old code is running and the run proves
   nothing.
3. **Tools → Build Raspberry Pi Image...**, and build one.
4. Write the card with the new writer — this is the step that has never
   worked from the wizard.
5. Boot the Pi from that card.

What to watch, and record either way:

- **The generated password**, if the field is left blank. It must be visible
  *before* the card is written; it exists nowhere else. If it is easy to miss
  on screen, that is a finding.
- **A UAC prompt at the card write, and only there.** The raw write needs
  elevation and cannot self-elevate. Building an image still must not prompt.
- **Whether the insert-the-card flow reads clearly** to someone who has not
  read the code. Two disks appearing at once should be reported as ambiguous
  rather than resolved by picking one — worth provoking with a spare USB
  stick if there is one.
- **On boot**: the console banner carrying the generated password, and that
  it disappears after `passwd`. Then `tests/hardware/test_live_pi.py` against
  it — 25+ passed from a wizard-built, wizard-written card is the end of the
  chain.

**Writing the card is the only destructive step in this document.** If the
insertion detection is at all unclear about which disk it chose, stop and
report rather than confirming through it.

Append findings here as before. Record it in the same detail if it all works:
"it worked" from a path nothing has ever exercised is a result, not a
non-event.

## Status

| | State |
|---|---|
| CLI builder on Windows | ✅ verified -- built an image, booted a Pi 5 end to end |
| Regression suite on Windows | ✅ full `tests/client/`: 130 collected, 129 passed, 1 skipped (no dosfstools) |
| `tests/unit/` on Windows | ⚠️ 609 collected, 597 passed, 4 failed (all one clock bug), 3 errors (no pyserial); 5 files must be `--ignore`d or the run aborts |
| CI on Linux (3.12 + 3.13) | ✅ 15/15 |
| Wizard environment on Windows (3.12 venv, deps, launch) | ✅ prepped and verified headlessly |
| `pkg_resources` shim | ✅ confirmed load-bearing on Windows (setuptools 84.0.0) |
| Live-Pi acceptance suite against a builder-made Pi | ✅ 25 passed, 4 skipped (no instruments attached) |
| **Qt wizard on Windows -- building an image** | ✅ **done -- built `lablink pi.img`, 2,908,160 KB, structurally correct** |
| Writing the card from the wizard | ✅ **two cards, two readers** -- both written from the wizard, both booted |
| SCPI / USB-TMC instrument path | ✅ B&K 9205B, self-identifying, session tests pass |
| Booting a wizard-built image | ✅ **full GUI chain done** -- build → card write → boot → LabLink healthy |
| Live-Pi suite against the GUI chain | ✅ **29 collected, 29 passed, 0 skipped, 0 failed** |
| Instrument discovery on a builder-made Pi | ✅ a B&K-protocol supply on a CP210x bridge, discovered through the container |
| Instrument session (connect, read, poll) | ✅ real readings, including under 10x polling, against a live supply |
| Password strength checked at entry | ✅ fixed -- wizard and CLI now enforce LabLink's own rules |
| Blank password producing an unloggable Pi | ✅ fixed -- a password is generated and published; 22501c8 |
| Client restart after a branch switch, on Windows | ❌ not run |

Full detail in [Still open](#still-open). Three bugs have already come out of
Windows testing (1290bee, 0da195b, and one below), so treat "it worked" as
worth recording in as much detail as a failure.

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

## Human-in-the-loop script for the wizard run

Everything automatable has been automated. What is left needs a person at the
machine, because it is a GUI. This is that script -- short on purpose, so it
actually gets followed.

**Before starting**, the agent on that machine should have the environment
ready (steps 1-3 above) and confirm to the human:

- the 3.12 venv exists and `pip install -r client\requirements.txt` succeeded
- `pip install -r requirements-test.txt` has been run too
- roughly 3 GB of free disk, and a network connection for the ~500 MB download

Then hand over the following. Each step has one thing to look at; write down
what you actually saw, including "as described", since that is the result.

| # | Do this | Look for | Saw? |
|---|---|---|---|
| 1 | `python client\main.py` | Window opens. **Status bar** bottom-left reads `LabLink 2.0.0  📍 feat/native-pi-image-builder (<hash>)` in green | |
| 2 | Menu: **Tools → Build Raspberry Pi Image...** | Wizard opens on its first page | |
| 3 | Pi Model: your board. Hostname: `lablink-wiz`. Output: **a path with a space in it**, e.g. `C:\Users\<you>\My Images\wiz.img` | The file dialog accepts it | |
| 4 | Admin password: anything. Wi-Fi: leave blank. Country: leave `US`. Branch: `main`. OS: Lite | Fields accept input; no validation complaints | |
| 5 | Click through to the build page and start it | **No UAC / "Do you want to allow this app to make changes" prompt at any point** | |
| 6 | Watch the first lines in the output pane | `Building with the native (pure Python) builder.` then `No administrator privileges are required.` | |
| 7 | While it downloads (a few minutes) | Progress bar moves; the window still responds to dragging and clicking -- not "(Not Responding)" | |
| 8 | Let it finish | Ends around 100% with a success message naming the .img path | |
| 9 | Check the output file | The `.img` exists and is roughly 2.8 GB | |

**Stop and report immediately if:**

- a UAC prompt appears -- the whole point of this change is that none should
- the output says `This tool requires bash to be installed` -- that means old
  code is running, not this branch
- the window greys out and stays unresponsive for more than a few seconds
- the status bar in step 1 shows no branch at all

**Optional but valuable**, on a run you do not need: click Cancel or close the
window mid-build, and note whether it stops cleanly or hangs. Nothing has ever
tested that path.

**To report:** the "Saw?" column filled in, the first two lines from step 6
verbatim, total elapsed time, and whether the window stayed responsive. If it
failed, the whole output pane rather than a summary of it.

Then write the image to a card and boot it -- a Pi from a wizard-built image
closes the last gap, since only CLI-built images have booted so far.

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
- `pip show pyfatfs passlib setuptools` (see the `pip show paramiko` note
  above if it throws a UnicodeEncodeError)
- the full traceback if it fails
- whether the produced `.img` boots a Pi
- **the collected total, not just the passed count** -- see below

## Expected test counts

Report what pytest *collected*, because a suite that quietly collects less
than it should looks identical to one that passes:

| Suite | Expected |
|---|---|
| `tests/client/` | **130 collected** |
| `tests/client/test_pi_image_native.py` | 79 |
| `tests/client/test_client_restart.py` | 18 |
| `tests/client/test_async_offload.py` | 20 |
| `tests/client/test_ssh_known_hosts.py` | 13 |
| `tests/hardware/test_live_pi.py` | 29 |

`pytest tests/client/ --collect-only -q` prints the total on its own.

Two files opt out rather than fail when a dependency is missing, so their
tests vanish from the run instead of erroring:

- `test_ssh_known_hosts.py` needs **paramiko** (`pytest.importorskip`) -- it
  covers the known_hosts/TOFU handling under paramiko 5, including the
  bracketed `[host]:port` form.
- `test_async_offload.py` imports `client.api.client`, so it needs the client
  dependency set.

`pip install -r requirements-test.txt` alongside `client\requirements.txt`
covers both. A run reporting **97** rather than 130 is those two files
missing, which is worth fixing before reading anything into the result.

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

## Findings from preparing the Windows wizard environment (2026-09-01)

Steps 1--3 of the wizard procedure, plus a headless launch check. The
interactive part (steps 4--7: clicking through the wizard itself) is
deliberately **not** covered here -- it needs a human at the machine. What
follows is everything that could be verified without one, including a bug
that would have stopped the wizard run at step 4.

### Environment

Python 3.12 was already installed alongside 3.10, so nothing was installed
system-wide:

```
-V:3.12 *  C:\Users\...\AppData\Local\Programs\Python\Python312\python.exe  (3.12.10)
-V:3.10     C:\Program Files\Python310\python.exe                            (3.10.4)
```

The existing `client/venv` was a stale **3.10.0** venv (`pyvenv.cfg` says so),
which cannot run the client at all -- numpy 2.5, pandas 3.0 and PyQt6 6.11 all
require 3.12+. It is gitignored and disposable, so it was removed and rebuilt
with `py -3.12`. `pip install -r client\requirements.txt` then succeeded with
no build steps: every dependency resolved to a `cp312` wheel, PyQt6 6.11.0
included.

### The `pkg_resources` shim is real, and it works -- confirmed on Windows

This is the gap the previous two runs could not close, and it closed exactly
as predicted:

```
pip show setuptools          ->  Version: 84.0.0
python -c "import pkg_resources"  ->  ModuleNotFoundError    (exit=1)
```

A fresh 3.12 venv ships no setuptools at all (`ensurepip` stopped including
it); `fs` declares it as a runtime dependency, so pip pulled in 84.0.0, and
84 no longer has `pkg_resources`. Then, directly:

```
python -c "import fs.base"
  -> ModuleNotFoundError: No module named 'pkg_resources'
     (raised from fs/__init__.py line 4: __import__("pkg_resources").declare_namespace)

python -c "...; _install_pkg_resources_shim(); import fs.base; print('OK')"
  -> OK
```

So `_install_pkg_resources_shim()` is now **load-bearing rather than
theoretical**, and it does its job on Windows. The failure it prevents is not
subtle -- without it the image builder cannot import its FAT library at all.

### Bug 3: `python client\main.py` could not start, at all

Step 4 of the wizard procedure says to run `python client\main.py`. That
command fails immediately, on any platform, in a checkout without the repo
root already on `sys.path`:

```
File "client\main.py", line 20, in <module>
    from client.ui.main_window import MainWindow
ModuleNotFoundError: No module named 'client'
```

The imports on lines 20--21 are absolute (`client.ui...`), which needs the
**repo root** on `sys.path`. What line 13 actually added was
`Path(__file__).parent` -- the `client/` directory itself, which makes
`ui`/`utils` importable as top-level names but never creates a package called
`client`. Running a file directly puts only that file's own directory on
`sys.path`, not its parent, so nothing else supplied the missing entry.

`python -m client.main` worked throughout, because the `-m` form resolves the
package from the current directory -- which is why this survived: anyone
launching it that way, or from an IDE that sets the working directory as the
source root, would never see it.

**Fix**: line 13 now inserts `Path(__file__).resolve().parent.parent`, the
repo root. Verified both ways afterwards -- `python client\main.py` and
`python -m client.main` each start cleanly and log
`Starting LabLink GUI Client v2.0.0`, with the Qt event loop live.

Note the shape of this one: the wizard procedure has been in this document
since ffd650e and its very first command could not have worked. Worth
remembering when a step "should obviously be fine".

### Bug 4: the same UTF-8 read bug as 1290bee, in the client test suite

`tests/client/test_client_restart.py` reads Python source back to assert on
its shape, and did it with a bare `Path(...).read_text()` -- the identical
mistake [Bug 1](#bug-1-pathread_text-decoded-with-the-wrong-codec-on-windows)
fixed in the builder. Four tests died on Windows before asserting anything:

```
UnicodeDecodeError: 'charmap' codec can't decode byte 0x9d in position 4351
UnicodeDecodeError: 'charmap' codec can't decode byte 0x8d in position 12738
```

`client/main.py` and `client/ui/main_window.py` both contain non-cp1252 UTF-8,
so the tests could only ever pass on a UTF-8 locale. **Fix**: all four
`read_text()` calls in that file now pass `encoding="utf-8"`. Suite goes from
**14 passed / 4 failed** to **18 passed**.

### Still worth doing: the rest of the codebase has the same pattern

A grep for `.read_text()` with no `encoding=` finds roughly twenty more
across `client/`, `server/`, `scripts/` and `lablink.py`. Most read `VERSION`
or `requirements.txt` and are ASCII in practice, but
`scripts/bump_version.py` reads `README.md`, `CHANGELOG.md` and the
`Dockerfile`, any of which can carry an em-dash or a curly quote -- the same
crash, in the release tooling, on a Windows machine.

Not fixed here: it is a separate sweep, unrelated to the image builder, and
it deserves its own change rather than being smuggled into this branch.

## The live-Pi acceptance suite, run against a builder-made Pi (2026-09-01)

`tests/hardware/test_live_pi.py` exists for exactly this situation and had
never been pointed at the Pi this branch produced. The Pi from the first-boot
run above was still up, so it was:

```
25 passed, 4 skipped in 10.95s
```

The four skips are all `LABLINK_EXPECT_EQUIPMENT` not being set -- no
instruments are attached to this Pi, so the instrument-session tests opt out
by design. Nothing failed.

What that covers, on a machine whose entire existence traces back to a
FAT32 partition written by `pi_image_native.py` on Windows:

- **Deployment** -- `/opt/lablink` present, version matches, the first-boot
  service is recorded as having succeeded, Docker running, both containers up,
  the container's Python version correct, and the scientific stack (numpy,
  pandas, scipy, h5py) importing *inside* the container.
- **SSH** -- host key algorithm supported, exec round-trip, SCP round-trip,
  and the trust-on-first-use policy correctly *rejecting* an unknown host.
- **API and the full auth lifecycle** -- login issues a token, a bad password
  is refused, the token grants access, a garbage token does not, logout
  actually revokes, and a refreshed token both works and stays revocable.
- **WebSocket** -- port open, authenticated connect succeeds, an unauthenticated
  one is rejected.
- **Resource hygiene** -- file descriptors stable across repeated API calls.

This is the end of the chain the branch set out to build: a Windows machine
with no root, no bash, no loop device and no qemu wrote an image; that image
booted; and the Pi it produced passes the project's own acceptance suite.

### Incidentally, a direct check of b1a6a1c

The suite reads its credentials through `_load_creds_file()`, the function
that commit changed, and it runs at module scope -- so a decode failure there
takes out collection, not just one test. The creds file used for this run
deliberately contains an em-dash and a `═`, making it undecodable as cp1252.
It loaded without complaint on Windows, which is the fix working rather than
the fix being untested.

Two notes for anyone repeating this:

- `pytest-asyncio` is needed, or the three `TestWebSocket` async tests report
  as failures with "async def functions are not natively supported" rather
  than as an environment problem. It is not in `client/requirements.txt`,
  since it is a test-only dependency -- it is declared in
  `requirements-test.txt`, along with `paramiko`, which this suite also needs.
  `pip install -r requirements-test.txt` covers both, and is the right way to
  run any of the test suites rather than installing packages one at a time.
- The LabLink *web* password is not the SSH password. First-boot reads it
  from `/etc/lablink-build-admin-password`, staged into the image from
  `--password`, so for a builder-made Pi the two happen to coincide.
- **`pip show paramiko` crashes on a legacy Windows console.** Not a LabLink
  problem, but this document tells you to run `pip show` twice, so it is
  worth knowing before the traceback alarms you. paramiko's metadata carries
  a non-ASCII author name, and pip renders through `rich`, which writes to a
  cp1252 console and dies with `UnicodeEncodeError: 'charmap' codec can't
  encode character 'ć'`. The package is installed fine -- only the
  display fails. `pip show setuptools`/`pyfatfs`/`passlib` are unaffected,
  being pure ASCII. To check a version without the theatrics:

  ```powershell
  python -c "from importlib.metadata import version; print(version('paramiko'))"
  ```

Verified after the change: `pip install -r requirements-test.txt` into the
3.12 venv brings in pytest 9.1.1, pytest-asyncio 1.4.0, paramiko 5.0.0 and
the rest in one step, and both suites still pass on Windows -- 96 passed /
1 skipped for `tests/client/`, 25 passed / 4 skipped against the live Pi.

## Bug 5, found by counting the tests (2026-09-01)

1e39c8e was right to check the arithmetic, and the correction was worth
making twice over.

First, plainly: the "96 passed / 1 skipped for `tests/client/`" above was
sloppy reporting on my part. That run named two files explicitly rather than
the directory, so it was never a `tests/client/` result at all. The number
was true; the label was not.

Second, running the directory properly did not simply add the missing tests.
It failed:

```
4 failed, 125 passed, 1 skipped   (130 collected)
```

All four in `test_async_offload.py`, all identical:

```
UnicodeDecodeError: 'charmap' codec can't decode byte 0x8f in position 17187
```

**The same cp1252 bug as 1290bee, ddd674b and b1a6a1c -- a fifth time.** The
reason it survived three separate audits is that it is not spelled
`read_text()`:

```python
source = open(os.path.join(root, rel_path)).read()
```

A bare `open()` takes the locale's codec exactly as `read_text()` does, and
`client/ui/equipment_panel.py` is not pure ASCII. Every sweep so far searched
for `.read_text()`, so this form was structurally invisible to all of them.
There were two such calls in that file; the second reads only ASCII-clean
paths today and was failing silently in waiting.

**Fix**: both now use `open(..., encoding="utf-8")`. The directory goes to
**129 passed, 1 skipped, 130 collected** -- fully green.

### What running the directory bought

`test_ssh_known_hosts.py` (13 tests) had never executed on Windows. It guards
on paramiko with `importorskip`, and paramiko only arrived here with
`requirements-test.txt`. It now runs and passes, including the part 1e39c8e
called out: the bracketed `[host]:port` known-hosts form, which is invisible
on the default port and wrong on any other. `test_async_offload.py` (20)
likewise.

Both had been opting out silently, which is the point worth keeping: a suite
that collects less than it should is indistinguishable, in the summary line,
from one that passes. Reporting the **collected** count alongside the passed
count is what makes the difference visible, and is why this bug surfaced at
all.

### Still open: the same pattern in product code

The bare-`open()` sweep that found this also turns up unencoded reads and
writes in the client itself, which are not test-only:

- `client/utils/server_manager.py` -- reads and writes the server config JSON
- `client/utils/settings.py` -- settings export/import
- `client/ui/theme.py` -- the theme settings file
- `client/ui/diagnostics_panel.py` -- writes a diagnostics report (the *write*
  side, so `UnicodeEncodeError`)
- `client/ui/ssh_deploy_wizard.py` -- known_hosts, ASCII by construction

A server name, a saved setting or a diagnostics line containing a non-ASCII
character would hit the same failure in front of a user rather than in a test
run. Left alone here for the same reason as the `read_text()` sweep: it is
unrelated to the image builder and deserves its own change, not a quiet
ride-along on this branch.

## Bug 6: `tests/unit/` on Windows, and a 15.6 ms clock (2026-09-01)

00fe94d's fix works: `tests/unit/demo_test.py` and `test_settings.py` give
**23 collected, 22 passed, 1 skipped** on Windows. Running the rest of that
directory, per the collected-count discipline, turned up two things.

### `tests/unit/` cannot be run as a directory at all

```
=========================== no tests ran in 12.88s ============================
INTERNALERROR>   File "tests\unit\test_enhancements.py", line 133, in <module>
INTERNALERROR>     sys.exit(1)
INTERNALERROR> SystemExit: 1
```

Seven files under `tests/` are script-style -- written to be run as
`python test_x.py`, with a top-level `try: import ... except: print(...);
sys.exit(1)`. Under pytest that `sys.exit` runs at **import** time, and
`SystemExit` during collection is an `INTERNALERROR` that aborts the whole
session. Not one file's worth of tests: all of them, with `no tests ran`.

They are `test_enhancements.py`, `test_new_drivers.py`,
`test_safety_system.py`, `test_settings_root.py`, `test_setup.py`, plus
`tests/gui/test_equipment_panels.py` and `test_visualization.py`.

This is not Windows-specific, and it gets *worse* with dependencies
installed rather than better: with `pyvisa` absent the module died early and
pytest still collected 41 tests from elsewhere; with it present the module
runs further, reaches a later `sys.exit(1)`, and takes the entire run with
it.

### The same files write to the repository on import

`git status` after that run was not clean:

```
 M profiles/Electronic_Load_-_Battery_Test.json
 M profiles/Oscilloscope_-_Debug_Quick.json
 M profiles/Power_Supply_-_5V_Logic.json
 ... 7 files, 14 insertions(+), 14 deletions(-)
```

Every change was a `created_at`/`modified_at` timestamp, rewritten to the
moment the suite ran. The cause is the same script-style shape:
`test_enhancements.py:92` calls `create_default_profiles()` at module scope,
so *importing* the file -- which is all pytest does during collection --
writes to the checked-in `profiles/` directory.

Worth noting what the previous values were: `2026-08-31 15:17:16`. Those are
not authored timestamps either, they are the moment somebody last ran this
suite, committed without being noticed. The working tree here was restored
with `git checkout -- profiles/`.

Running a test suite should not dirty the working tree, and a reviewer
should not have to tell a real profile change from a collection artefact.
Both problems -- aborting the session, and writing to the repo -- go away by
putting the script bodies behind `if __name__ == "__main__":`, which is what
they were written to be run as.

Excluding those five, `tests/unit/` is:

```
609 collected -- 597 passed, 5 skipped, 4 failed, 3 errors
```

The 3 errors are a missing `pyserial`; `tests/unit/` also needs
`server/requirements.txt` (`pyvisa`, `scipy`, `psutil`) on top of the client
and test ones. Installing those three into the 3.12 venv did not disturb it
-- numpy 2.5.2, pandas 3.0.5 and PyQt6 6.11.0 were unchanged, and
`tests/client/` stayed at 129 passed / 1 skipped.

### The 4 failures are one bug: Windows' wall clock

Measured on this machine:

| clock | resolution | instant ops measuring exactly `0.0` |
|---|---|---|
| `time.time()` | **0.015625 s** | **999 / 1000** |
| `time.perf_counter()` | 0.0000001 s | 400 / 1000 |

15.625 ms is the classic Windows timer tick. On Linux `time.time()` resolves
to about a nanosecond, which is why none of this is visible there.

**`test_diagnostics.py::test_check_connection_success`** asserts
`response_time_ms > 0`, and gets `0.0`. `server/diagnostics/manager.py:186`
measures with `(time.time() - start) * 1000`; a mocked call finishes inside
one tick, so the subtraction is exactly zero.

**`test_advanced_analysis.py::TestParameterTrending`** (3 failures) ends in
`numpy.linalg.LinAlgError: SVD did not converge in Linear Least Squares`.
The test adds five trend points in a tight loop with no delay.
`server/waveform/advanced_analysis.py:1255` fits a line against
`(timestamp - start_time).total_seconds()`, and five timestamps taken inside
one 15.6 ms tick are *identical* -- confirmed directly, five rapid
`time.time()` calls yield one distinct value here. An all-zero x-vector is
degenerate, and the fit collapses.

The fix in both places is `time.perf_counter()`, which is monotonic and
high-resolution everywhere. It is also simply the right API for a duration:
`time.time()` can step backwards under an NTP correction and produce a
negative elapsed time on any platform.

**Not fixed here.** This is server diagnostics and waveform analysis, with no
connection to the image builder, and folding it into this branch is exactly
the ride-along that has been declined twice already. Recording it with the
measurement so whoever picks it up does not have to rediscover the cause --
and noting it ranks above the deferred `open()`/`read_text()` items, because
those are latent whereas this is four tests failing today.

## The wizard run happened (2026-09-01)

A human ran the script from 0ab1706 on the same Windows machine. **The wizard
built an image.** That is the headline the branch existed for, and it is now
done rather than pending.

The output was `C:\Users\<user>\lablink pi.img`, 2,977,955,840 bytes
(2,908,160 KB) -- byte-for-byte the same size as the CLI-built image. Read
back with the independent FAT32 parser:

| file | present |
|---|---|
| `firstrun.sh` | yes |
| `lablink-first-boot.sh` | yes |
| `ssh` | yes |
| `cmdline.txt`, correctly patched | yes |

`cmdline.txt` carries `systemd.run=/boot/firmware/firstrun.sh`,
`systemd.run_success_action=reboot` and `systemd.unit=kernel-command-line.target`,
with the original `root=`/`rootfstype=`/`rootwait`/`resize` arguments intact and
no `init=`. Note the output path contains a space, which the wizard handled
without complaint -- that was chosen deliberately, since no CLI run had used one.

### The two things that did not go to plan

**1. Writing the card from the wizard failed** -- because that code does not
exist. From the run's own log:

```
ui.sd_card_writer - INFO - [15%] Starting write operation...
ui.sd_card_writer - INFO - [50%] Windows write not yet implemented
ui.sd_card_writer - INFO - Result: FAILED
ui.sd_card_writer - INFO - Windows SD card writing requires administrator
                           privileges.
```

`_write_windows()` in `client/ui/sd_card_writer.py` was a stub: it emitted
progress to 50%, then reported failure. Not a regression and nothing to do
with this branch -- the SD writer has never worked on Windows.

The message was the actual problem. It said only that administrator
privileges were required, which is true of raw device writing in general and
completely beside the point here: the code was never written, so running the
client elevated would have changed nothing. It sends people to fix something
that is not broken. It now says the feature is not implemented, says plainly
that running as administrator will not help, and points at Raspberry Pi
Imager -- which is what the human used, successfully, on the same file.

Worth keeping the two separate when reading this document: **the image
builder needs no privileges on any platform, and that is the point of this
branch.** Putting a finished image onto a card is a different operation that
does require elevation on Windows no matter who writes it -- Raspberry Pi
Imager triggers UAC too. A UAC prompt from the card writer does not
contradict the "no administrator privileges" claim the builder makes; a UAC
prompt during a *build* still would.

### The card writer was then implemented, and the enumeration was the danger

Implementing `_write_windows()` (4cf3104) meant first fixing how the target
disk is chosen, because the existing enumeration was worse than missing:

```python
f"\\\\.\\PhysicalDrive{ord(letter) - ord('A')}"   # D: -> PhysicalDrive3
```

Drive letters do not map to disk numbers. On the machine that produced the
log above, `C:` computes to `PhysicalDrive2` and the only disk is `0`. **The
stub was the only thing preventing that line from writing a 2.8 GB image
over an arbitrary disk.** A working writer bolted onto it would have been
genuinely destructive, and no test would have caught it, because the wrong
path was never opened.

Disks now come from `Get-Disk`, which reports the real number alongside
`IsSystem`, `IsBoot` and the bus type. The device path is derived from the
number and cannot be influenced by a drive letter; there is a test asserting
that a disk with letters `D:`, `Z:` and none at all yields the same path.

**The card is identified by appearance, not selection.** The dialog snapshots
the disks, asks the user to insert the card -- or remove and reinsert it if
it is already in -- and takes whichever one shows up. Picking from a list is
where this goes wrong: the entries look alike and a misclick costs somebody a
drive. It also sidesteps a real trap, that many USB card readers report
themselves as `Fixed hard disk media`, so filtering on removability both
misses real cards and cannot be trusted on its own. Appearing is a better
signal than self-description. Two disks appearing at once is reported as
ambiguous rather than resolved by guessing.

A manual chooser sits behind a button, for a reader that stays enumerated
with the card in it. It marks non-removable disks, confirms twice before
accepting one, and cannot select the system disk at all.

| rule | can the override reach it? |
|---|---|
| System or boot disk | **no, never** |
| Not removable media | yes |
| Image larger than the card | no |
| Disk reporting no size | no |

Verified through the helper's own CLI: `--disk 0 --override` against the
system disk is refused.

The write locks *and dismounts* the disk's volumes and holds them for the
duration. Skipping that leaves Windows caching a filesystem being overwritten
underneath it, and the card comes out looking written and quietly corrupt.
Then sector-aligned writes, a flush, and a read-back SHA-256 comparison.

**Not yet run against a real card.** There is no way to test raw device
writing without a raw device to lose, so the 36 new tests cover every
decision about *which* disk is written and none of the writing itself.
`tests/client/`: 149 -> **185 collected, 184 passed, 1 skipped**. Whoever
tries it first should use a card they do not mind losing.

**2. Blank passwords produce a Pi with no login account.** The password
fields were left empty. That is honoured exactly as designed --
`customize_image` writes `userconf.txt` and `lablink-admin-password` only
`if config.admin_password`, and `test_no_password_writes_no_credentials`
exists specifically to keep it that way ("must not create an empty-password
login"). Confirmed against the built image: both files are **absent**, while
the `ssh` flag file is **present**.

On current Pi OS, `userconf.txt` is what creates the account. So the result
is a Pi with **sshd enabled and no user to log in as** -- port 22 answers,
every credential fails, and it is not a password anyone can guess or reset
without re-imaging. Verified in practice: the previous image's password was
rejected, which incidentally also proved the card really did hold the new
wizard-built image rather than the old one.

`firstrun.sh` degrades gracefully rather than breaking -- it logs
`WARNING: admin does not exist; leaving userconf.txt`, skips the group and
sudoers setup, and still installs `lablink-first-boot.service` -- so the Pi
does complete setup and bring LabLink up. The application password falls back
to `LabLink@2025`, the default `lablink-first-boot.sh` uses when nothing was
staged.

**The builder is right; the wizard is what needs the guard.** Refusing to
create a passwordless login is correct. Letting someone reach the end of a
wizard, wait through a 500 MB download and a ~3 GB write, and receive an
unreachable Pi -- without a word -- is not. The field should either be
required, or warn plainly that leaving it blank means no SSH access and a
default application password.

A consequence for testing: the SSH half of
`tests/hardware/test_live_pi.py` cannot run against this image at all. The
API and auth halves still can.

### How it was fixed, and a note for whoever wrote 58d9de8

Two fixes for this landed within minutes of each other, in the same three
files: 58d9de8 added a warning, and 22501c8 generates a password instead.
That was not a race anyone lost -- 58d9de8 could not have known, because the
decision came from the repository owner in the meantime: **generate, rather
than warn.**

So a blank field now produces a strong unique password rather than either a
lockout or a known default. It is grouped in fours from an alphabet with no
`0`/`O` or `1`/`l`/`I`, since it gets read off a banner and typed by hand,
and it is guaranteed an upper-case letter and a digit for the LabLink
account rules. The wizard prints it above the build output before the card
is written; the CLI prints it after the prompt.

The Pi publishes it too, on the console login banner, because nobody typed
it and the only other copy is on the machine that built the image. That is
gated on a marker file written *only* for generated passwords -- a password
the user chose is theirs and is never displayed -- and `firstrun.sh` reads
the plaintext from the staged file rather than echoing it, because the
journal is world-readable. A timer restores the stock `/etc/issue` once the
password has been changed, so the notice does not sit on the login screen
forever.

**58d9de8's warning was removed rather than reworded**, and it is worth
being explicit about why, so it does not come back. With a password always
present, every claim it made became false: an account *is* created, the Pi
is *not* unreachable, and LabLink's login uses the generated password rather
than its default. There is no longer a bad outcome to warn about.

What was kept from it is `test_the_image_really_has_no_account`. That pins
`customize_image`'s own behaviour, which is unchanged and deliberately so --
and it is precisely what makes generating at the layer above load-bearing
rather than decorative. Its two CLI tests asserted the warning text and were
replaced by tests of the new behaviour: that the CLI generates, prints the
password it actually shipped, marks the image for the console banner,
honours `--no-ssh`, and leaves a chosen password verbatim and unprinted.

`tests/client/`: 130 collected before this, **144 collected, 143 passed,
1 skipped** after.

### The Pi from that image did not finish setting up

Recorded because it is unresolved rather than because it is understood.

The blank-password Pi booted and sshd came up -- port 22 answers -- but
after roughly 25 minutes ports 80 and 8000 were still closed and
`/health` never responded. The CLI-built image reached a healthy stack in
about eight.

The cause is not established. One candidate, unconfirmed: with no
`userconf.txt`, Raspberry Pi OS runs its own interactive account-creation
prompt on tty1, which can hold up a boot that `lablink-first-boot.service`
is queued behind. Checking would need a monitor on the Pi.

Which is the sharper point: **the failure cannot be diagnosed remotely,
because there is no account to log in as.** An unreachable Pi is not only
inconvenient, it is undebuggable, and that is the strongest argument for
the image never being built that way in the first place. Under the fix
above this state is no longer reachable from either entry point.

## The whole chain, through the GUI, on hardware (2026-09-01)

**Build → write the card → boot, entirely from the wizard, all of it
working.** This is what the branch set out to make possible and it had never
been done end to end. The card write in particular had never succeeded once.

The Pi came up at 10.10.0.51 and every link was verified rather than assumed:

- SSH as `admin` with the password typed into the wizard -- so `userconf.txt`
  was written and Raspberry Pi OS created the account from it
- hostname `lablink-pi`, the value entered in the wizard
- Debian 13 trixie, the intended base image
- `up 1 minute` at first contact -- `firstrun.sh` had run and rebooted, as
  designed
- `lablink-first-boot.service` **Finished** after apt upgrade, Docker install
  and a container build (pip install alone took 94.7 s)
- `http://10.10.0.51:8000/health` → `{"status":"healthy","connected_devices":0}`
- `http://10.10.0.51/` → `200`

For the record: **the password was typed, not left blank**, so the generated
password and its console banner were not exercised on this run. That path
still has only unit tests behind it.

### The live-Pi suite, and what it caught

```
29 collected -- 17 passed, 3 failed, 9 skipped
```

Deployment, SSH, the API and WebSocket checks passed. Every failure and every
non-instrument skip is one thing: **the LabLink admin account does not
exist.**

The password used was `password`. The Pi's own account took it happily --
that is why SSH works -- and it reached `/opt/lablink/.env` correctly as
`LABLINK_DEFAULT_ADMIN_PASSWORD`. Then, in the server's container log:

```
ERROR - main - Failed to create default admin user: 1 validation error for
UserCreate
password
  Value error, Password must contain at least one uppercase letter
  [type=value_error, input_value='password', input_type=str]
```

So the web UI came up with **no account able to log in**, and the only
evidence is a line in a Docker log on the Pi. `server/security/models.py`
requires 8 characters with an upper-case letter, a lower-case letter and a
digit; nothing checked that where the password was entered.

This is the blank-password bug in another costume: the wizard accepts input
that yields a half-working Pi and says nothing until much later, somewhere
much less visible.

**Fixed** by checking against LabLink's own rules at the point of entry, in
both the wizard and the CLI, naming the specific rule that failed rather than
saying "invalid". A test pins the rule strings to
`server/security/models.py`, so if the server's policy moves and this copy
does not, the suite fails and says which file to fix.

Two notes on the run itself:

- Running the suite against a rejected password locked the account:
  `Account temporarily locked. Try again in 1799 seconds`. That is the
  server's brute-force protection behaving correctly, but it is worth knowing
  before repeating the exercise -- a bad password costs half an hour.
- `LabLink@2025` is the fallback in `lablink-first-boot.sh`, used **only when
  no password is staged**. This run staged one, so that branch never ran and
  the default does not apply to this Pi.

`tests/client/`: 187 → **198 collected, 197 passed, 1 skipped**.

### Recovering the Pi, and a second bug found doing it

The Pi was repaired in place rather than re-imaged, which turned up another
problem worth knowing about.

Recovery is three steps: put a compliant password in
`/opt/lablink/.env`, clear the `login_attempts` rows, restart. The server
re-checks on every startup -- "Default admin user already exists", or else it
creates one -- so a valid password is picked up without re-imaging.

**`lablink-restart` does not apply an `.env` change.** It runs
`docker compose restart`, which restarts the existing containers with the
environment they already have. The password was updated in `.env`, the
restart reported success, and the container still had the old value:

```
$ sudo docker exec lablink-server printenv LABLINK_DEFAULT_ADMIN_PASSWORD
password
```

with the same validation error in the log as before. `docker compose up -d`
recreates the container and does pick it up:

```
User created: admin (ID: PyFdjP6KmjWiK9Ph9wXP4g)
⚠️  DEFAULT ADMIN CREATED - Username: admin
```

Anyone editing configuration and running `lablink-restart` will see it appear
to work and change nothing. `lablink-restart` should use `up -d`, or say that
it does not reload configuration. Not fixed here -- it is on the Pi side and
unrelated to the image builder -- but it costs a confusing half hour.

### Then the whole suite passed

With the account created, against the same wizard-built, wizard-written Pi:

```
29 collected -- 25 passed, 4 skipped, 0 failed
```

Deployment, SSH including the TOFU reject path and SCP, the full auth
lifecycle through revocation, WebSocket auth and descriptor hygiene all pass.

The four skips were `LABLINK_EXPECT_EQUIPMENT` being unset. **That was
recorded here as "no instruments attached", and that was wrong** -- there is
a B&K Precision supply on this Pi. Correcting it, because it turned four
skips from "nothing to test" into "a capability nobody has checked".

### Instruments are attached, and discovery finds them

```
lsusb:  Silicon Labs CP210x UART Bridge   →   /dev/ttyUSB0
```

Passed through to the container correctly, and LabLink's own discovery, run
against the wizard-built Pi:

```
POST /api/equipment/discover  →  200
  ASRL/dev/ttyUSB0::INSTR   B&K Precision   "Legacy fixed-width supply"
                            device_type: power_supply
```

So the serial path works end to end on an image built and written entirely
through the Windows GUI: udev, the container device passthrough, pyvisa 1.16
and the discovery layer. With `LABLINK_EXPECT_EQUIPMENT` and
`LABLINK_EQUIPMENT_RESOURCE` set, `test_expected_equipment_is_found` passes
rather than skipping -- **26 of 29 now, not 25**.

`/health` reporting `connected_devices: 0` is not a contradiction: that
counts open sessions, not discovered devices.

The remaining three need `LABLINK_EQUIPMENT_MODEL`. Discovery gets as far as
"Legacy fixed-width supply" because these instruments do not answer `*IDN?`,
so the driver is chosen from a model supplied at connect time. Given a wrong
one the server refuses cleanly --

```
connect → 500 {"detail":"Unsupported equipment model: B&K Precision"}
```

-- which is the right behaviour and worth having seen.

### Identifying the model by probing, and why it half works

The obvious question is whether the instrument can be identified rather than
asked about. It can be narrowed, but not named, and the distinction is the
protocol's own fault. Read-only queries, straight down the serial line:

```
GMAX -> b'605160\rOK\r'      rated 60.5 V / 16.0 A
GETS -> b'120020\rOK\r'      setpoints 12.0 V / 2.0 A
GETD -> b'001100000\rOK\r'   0.11 V, 0.0 A
GOUT -> b'1\rOK\r'           output off (this dialect inverts: "0" is on)
```

There is no identifier to read -- `bk_serial_probe.py` says so directly: *"the
protocol carries no model number"*. And the rated limits do not settle it
either: **60.5 V / 16.0 A matches nothing in the registry**, while the
1900B family is 16 V / 60 A, the same digits transposed. This is most likely
a third-party supply speaking the same protocol.

What *can* be established is the dialect, which is what the driver actually
needs. Connecting under each candidate and reading back -- all read-only --
separates them cleanly:

| model | `current_set` from the raw `GETS 120020` |
|---|---|
| 1902B / 1687B / 1696 | **2.0 A** -- one decimal |
| 1685B | **0.2 A** -- two decimals, wrong by 10x |
| 9103 | rejected: `Invalid GETS response` |

The one-decimal reading is corroborated by `GMAX`: at two decimals the same
digits would make it a 1.6 A supply, which no 60 V unit is. `GOUT` returning
`1` for an output that is visibly off confirms the inverted polarity too,
which rules out the 9103/9104 dialect independently.

So `1902B` is the correct *driver* for this instrument even though the
instrument is probably not a 1902B -- and the registry's warning is exactly
right: *"getting this wrong commands a tenfold different current"*. Picking
by guesswork had a one-in-three chance of being wrong by 10x.

### The session tests ran against a live supply

The output was on during the run -- 11.98 V against a 12.0 V setpoint --
so `test_readings_are_returned` and `test_repeated_readings_are_stable`
exercised the raw `GETD`/`GETS`/`GOUT` path against an energised instrument
under ten consecutive polls. That is the case the comment calls "the
timing-sensitive path that mocks cannot reproduce", and it is much stronger
evidence than polling a supply sitting at zero.

**Nothing here energises anything.** The session tests connect, query and
disconnect; `connect` sends only `GMAX`. The output being live was the
operator's doing, and the instrument was verified afterwards, by raw serial
rather than through LabLink, to be back at `GOUT 1` / 0.11 V -- byte for byte
what it read before any of this started.

**29 of 29, nothing skipped**, on a Pi whose image was built and written
entirely through the Windows GUI.

## Second bench: a second reader, and a self-identifying instrument (2026-09-02)

The first run proved the chain works once. This one was chosen to test what
was still a sample of one, and it moved three things off that number.

**The wizard's card writer wrote this card too, on a different reader**, and
the Pi booted from it. That was the highest-value unknown: the
insertion-detection flow had only ever been exercised against a single
reader, and a different one could plausibly enumerate differently or stay
enumerated across removal. It did not. Confirmed genuinely reimaged rather
than rebooted: the SSH host key changed from `956d1746…` to `476c1144…`.

Ethernet this time, so the Wi-Fi fields were untouched, and the password was
typed rather than generated -- so the generated-password console banner
*still* has only unit tests behind it.

### Two instruments, and only one of them needs guessing

```
POST /api/equipment/discover  ->  2 devices

  USB0::11975::37376::800886011797210043::0::INSTR
      B&K Precision 9205B      scpi       confidence 0.95
  ASRL/dev/ttyUSB0::INSTR
      B&K Precision "Legacy fixed-width supply"   fixed   confidence 0.6
```

The **9205B identifies itself**: USB `2ec7:9200` resolves through
`usb_hardware_db.py`, it answers `*IDN?` over USB-TMC, it carries a real
serial number, and it has a dedicated `BK9205B` SCPI driver. No dialect
derivation, no 10x scaling risk -- the opposite of the first bench's problem,
and a different code path from the raw fixed-width one. The session tests ran
against it: `voltage_set 12.0, current_set 20.0, voltage_actual 0.026,
output_enabled false`.

The legacy supply on this bench reports `gmax 605680` -- 60.5 V / **68.0 A**
-- against the first bench's `605160`, 60.5 V / 16.0 A. Same voltage field,
different current. So it is either a different unit or an unreliable read,
and it is exactly why `LABLINK_EQUIPMENT_MODEL=1902B` was **not** carried
over from the other bench. A model derived for one instrument is not evidence
about another.

### Reimaging at the same address blocks the SSH tests, correctly

Worth knowing before it wastes somebody's afternoon. The first run of the
suite here gave:

```
17 passed, 12 skipped
  SKIPPED: cannot SSH to 192.168.91.191:22 - BadHostKeyException:
  Host key for server '192.168.91.191' does not match
```

The Pi was reimaged at the address a previous Pi had used, so `known_hosts`
still held the old key. Every SSH-dependent test skipped. **That is the right
behaviour** -- silently accepting a changed host key is what trust-on-first-use
exists to prevent -- but twelve skips read as "not configured" rather than
"refused", which is the same vacuous-pass shape as the equipment skips
earlier in this document.

Clearing the stale entry (`ssh-keygen -R 192.168.91.191`) and rerunning gives
**29 collected, 29 passed, 0 skipped**. Do that after any reimage that reuses
an address, and check the fingerprint actually changed for the reason you
think it did before removing anything.

### Also worth noting

Both Pis are called `lablink-pi`, the default. They are on different subnets
today, so nothing collides, but `lablink-pi.local` cannot distinguish them
and would resolve to whichever answered first. A distinct hostname per build
costs nothing at image time and is unrecoverable afterwards without
re-imaging.

**That is the chain complete**: an image built in the wizard on Windows,
written to a card by the wizard, booted on a Pi, installing itself and
passing the project's own acceptance suite. No part of it had been done
through the GUI before today, and the card write had never worked at all.
