# LabLink 2.0.0 — Breaking Changes

LabLink 2.0.0 is a deliberate compatibility break. It exists to move the whole
dependency stack to current releases in one step, so the project has a base to
build on rather than absorbing a security-driven overhaul every few months.

**2.0.0 does not interoperate with 1.x.** Upgrade the server and the client
together; a 1.x client will not work against a 2.x server, and vice versa.

---

## 1. Python 3.12 is now the minimum

Previously 3.11 (and `setup.py` still claimed 3.8).

This is forced by the scientific stack, not chosen for its own sake:

| package | version | requires |
|---|---|---|
| numpy | 2.5.2 | Python >= 3.12 |
| scipy | 1.18.1 | Python >= 3.12 |
| pandas | 3.0.5 | Python >= 3.11 |
| websockets | 17.1 | Python >= 3.11 |

**Server:** no action for the normal deployment. The server runs in Docker and
the image moved to `python:3.13-slim`, so the Raspberry Pi host's own Python is
irrelevant. If you run the server *outside* Docker you must provide Python
3.12+ yourself.

The supported floor stays at 3.12 rather than 3.13 on purpose: Ubuntu 24.04
LTS ships 3.12 and the desktop client runs natively, so raising the floor
would cost users nothing to gain. The container takes 3.13 because it is
self-contained and the longer support window is free there.

**Client:** the desktop client runs natively, so the machine you run it on
needs Python 3.12 or newer.

CI now covers Python 3.12 and 3.13.

---

## 2. Existing auth tokens are rejected — everyone is logged out

Access tokens are now bound to a server-side session (`session_id` in the JWT
payload), which is what makes logout, password change and admin reset able to
revoke a token immediately instead of leaving it valid for up to 7 days.

Tokens issued by 1.x carry no `session_id` and are refused with HTTP 401.

**On upgrade every user must log in again.** There is no migration path for
in-flight tokens, and that is intentional — honouring them would defeat the
revocation guarantee.

---

## 3. SSH deployment drops `ssh-rsa` (RSA/SHA-1) host keys

`paramiko` moves 3.4.0 -> 5.0.0, which fixes PYSEC-2026-2858 by removing
SHA-1 RSA signatures. DSA (`ssh-dss`) is removed entirely.

Host key algorithms LabLink will now negotiate:

```
ssh-ed25519, ecdsa-sha2-nistp256/384/521, rsa-sha2-512, rsa-sha2-256
```

`ssh-rsa` and `ssh-dss` are gone.

**Verified against a real SSH server** (an OpenSSH container configured to
offer only an `ssh-rsa` host key, i.e. the old-Pi case):

| | result |
|---|---|
| paramiko 3.4.0 (LabLink 1.x) | connects, negotiating `ssh-rsa` |
| paramiko 5.0.0 (LabLink 2.0.0) | refuses |

The error you will see is:

```
paramiko.ssh_exception.IncompatiblePeer: Incompatible ssh peer (no acceptable host key)
```

**What this means in practice:**

- A device whose SSH server offers **only** an `ssh-rsa` host key can no longer
  be deployed to. OpenSSH has generated ed25519 host keys by default since 7.2
  (2016) and disabled `ssh-rsa` by default since 8.8 (2021), so any reasonably
  current Raspberry Pi OS is unaffected.
- Existing `ssh-rsa` entries in `known_hosts` still parse and load without
  error — they simply will not be negotiated. You do not need to clean the file
  out, but an old device trusted through such an entry will stop connecting.
- If you hit this, the fix is on the device: regenerate host keys
  (`sudo ssh-keygen -A` and restart sshd) or update its OS. Do not work around
  it by re-enabling SHA-1.

`scp` moves 0.14.5 -> 0.16.1 alongside paramiko.

---

## 4. Raspberry Pi images move to Debian Trixie

Images built by `build-pi-image.sh` now use Raspberry Pi OS **Trixie**
(Debian 13, 2026-06-19) instead of Bookworm (Debian 12, 2024-03-15). The
previous pin was over two years old, which meant a long apt catch-up and an
old kernel on every fresh install.

This changes the host OS major version under the deployment. It is low risk
in practice, and the following were checked before the switch:

- Docker publishes `trixie` packages for arm64 (129 of them), so the
  `get.docker.com` install used on first boot works.
- Raspberry Pi OS ships Trixie for both arm64 and armhf, so Pi 3 remains
  supported.
- The build script installs no packages of its own and never touches
  `raspi-config`, `config.txt` or `cmdline.txt`, so there is little
  version-specific surface to break.
- Wi-Fi is configured through both `wpa_supplicant.conf` and a NetworkManager
  connection file; Trixie uses NetworkManager.
- LabLink itself runs in Docker, so the host OS does not constrain the
  application stack.

The base image is a deliberate pin, not tracked automatically. To go back:

```
PI_OS_DIR_DATE=2024-03-15 PI_OS_FILE_DATE=2024-03-15 PI_OS_CODENAME=bookworm
```

`PI_OS_VARIANT` selects `lite` (default) or `full`. Lite is correct for a
headless lab appliance: LabLink runs in Docker and needs no desktop. Full is
only worth it if the LabLink desktop client will run on the Pi itself.

---

## 5. Dependency baseline

Everything is now pinned to a current release. The notable majors:

| package | 1.x | 2.0.0 |
|---|---|---|
| numpy | 1.26.3 | 2.5.2 |
| pandas | 2.2.0 | 3.0.5 |
| scipy | 1.11.4 | 1.18.1 |
| paramiko | 3.4.0 | 5.0.0 |
| websockets | 12.0 | 17.1 |
| bcrypt | 4.1.3 | 5.0.0 |
| psutil | 5.9.8 | 7.2.2 |
| PyQt6 | 6.6.1 | 6.11.0 |
| pytest | 7.4.4 | 9.1.1 |
| fastapi | >=0.115 | 0.141.1 |
| pyvisa | 1.14.1 | 1.16.2 |

Existing password hashes are unaffected by the bcrypt major: the stored format
is unchanged and `bcrypt.checkpw` still verifies them.

`websockets` 14 replaced the legacy client. `WebSocketClientProtocol` still
resolves in 17.x but is deprecated, so the client now imports
`websockets.asyncio.client.ClientConnection` with a fallback for older installs.

---

## 6. Not included

`paramiko` is the only dependency whose CVE required a judgement call; it is
fixed here. Nothing else is knowingly left vulnerable — `pip-audit` over the
server and shared requirements reports no known vulnerabilities.

---

## Verification

This release was validated before merge:

- all four requirements files resolve and install together on Python 3.12
- every one of the 192 server/client/shared modules imports cleanly
- full test suite: 968 passed
- `pip-audit` over `shared/` + `server/`, and over the full stack including
  the client: no known vulnerabilities
- **against a real OpenSSH server in Docker**, under paramiko 5.0.0: the TOFU
  policy rejects an unknown host, the offered key is retrievable, saving it to
  known_hosts lets a subsequent `RejectPolicy` connect without re-prompting,
  and `exec_command` plus SCP upload/download round-trip correctly — on both
  the default port and a non-standard one

**On real hardware** (Raspberry Pi 5, `tests/hardware/test_live_pi.py`,
29 passing):

- the image deployed 2.0.0, the container runs Python >= 3.12, and numpy,
  scipy and pandas import there — installed from aarch64 wheels, not compiled
- the Pi negotiates a modern SSH host key, and the deploy wizard's TOFU flow,
  `exec_command` and SCP all work under paramiko 5
- login, logout and refresh behave correctly over the network, and logout
  genuinely revokes the token
- **pyvisa 1.16 drives a real BK Precision 1902B** over its proprietary serial
  protocol: connect, status, readings, and ten sequential polls without the
  framing desynchronising
- WebSocket streaming connects when authenticated and is refused with 403
  when not
- the container's file descriptor count is stable across repeated requests

**Still not covered:** no test drives a real Qt event loop. The PyQt6
6.6 -> 6.11 and pyqtgraph 0.13 -> 0.14 bumps rest on import checks and unit
tests, so exercise the GUI against hardware before relying on it in a lab.

One instrument caveat, not a regression: an instrument using a proprietary
serial protocol answers no `*IDN?`, so discovery reports it as "Unknown Serial
Device" and the model must be selected manually when connecting.
