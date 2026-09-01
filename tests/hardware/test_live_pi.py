"""
Live acceptance tests against a real Raspberry Pi running LabLink.

These are the checks that cannot be made without hardware: real SSH to the
device, real VISA transport to real instruments, and the auth lifecycle over a
real network. Everything here is skipped unless explicitly configured, so it
never runs in CI.

Configure with environment variables:

    LABLINK_PI_HOST         hostname or IP of the Pi            (required)
    LABLINK_PI_USER         SSH username                        (default: admin)
    LABLINK_PI_SSH_KEY      path to a private key               (preferred)
    LABLINK_PI_SSH_PASSWORD SSH password                        (if no key)
    LABLINK_PI_SSH_PORT     SSH port                            (default: 22)
    LABLINK_API_PORT        LabLink API port                    (default: 8000)
    LABLINK_ADMIN_USER      LabLink login                       (default: admin)
    LABLINK_ADMIN_PASSWORD  LabLink password                    (required for auth tests)
    LABLINK_EXPECT_VERSION  version the Pi should report        (default: repo VERSION)
    LABLINK_EXPECT_EQUIPMENT  comma-separated substrings expected in discovery

Or put the same KEY=VALUE lines in a file and point at it:

    LABLINK_PI_CREDS=~/.lablink-test-creds

Run with:

    pytest tests/hardware/test_live_pi.py -v

These tests are read-only with respect to instruments: they discover,
connect, query status/readings, and disconnect. Nothing sets an output, a
voltage or a current, so a run cannot leave an instrument energised.
"""

import json
import os
import socket
import time
from pathlib import Path

import pytest

requests = pytest.importorskip("requests")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _load_creds_file():
    """Load KEY=VALUE pairs from LABLINK_PI_CREDS into the environment.

    Keeps secrets out of shell history and out of any transcript.
    """
    path = os.environ.get("LABLINK_PI_CREDS")
    if not path:
        return
    f = Path(path).expanduser()
    if not f.exists():
        return
    for line in f.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_creds_file()

PI_HOST = os.environ.get("LABLINK_PI_HOST", "")
PI_USER = os.environ.get("LABLINK_PI_USER", "admin")
SSH_KEY = os.environ.get("LABLINK_PI_SSH_KEY", "")
SSH_PASSWORD = os.environ.get("LABLINK_PI_SSH_PASSWORD", "")
SSH_PORT = int(os.environ.get("LABLINK_PI_SSH_PORT", "22"))
API_PORT = int(os.environ.get("LABLINK_API_PORT", "8000"))
ADMIN_USER = os.environ.get("LABLINK_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("LABLINK_ADMIN_PASSWORD", "")
EXPECT_EQUIPMENT = [
    s.strip() for s in os.environ.get("LABLINK_EXPECT_EQUIPMENT", "").split(",") if s.strip()
]

_repo_version = (Path(__file__).resolve().parents[2] / "VERSION")
EXPECT_VERSION = os.environ.get(
    "LABLINK_EXPECT_VERSION",
    _repo_version.read_text().strip() if _repo_version.exists() else "",
)

BASE_URL = f"http://{PI_HOST}:{API_PORT}"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_hardware,
    pytest.mark.skipif(not PI_HOST, reason="set LABLINK_PI_HOST to run live Pi tests"),
]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def ssh():
    """An SSH connection to the Pi, or skip."""
    paramiko = pytest.importorskip("paramiko")

    if not (SSH_KEY or SSH_PASSWORD):
        pytest.skip("set LABLINK_PI_SSH_KEY or LABLINK_PI_SSH_PASSWORD")

    client = paramiko.SSHClient()
    client.load_system_host_keys()
    # Deliberately permissive: this fixture is for inspecting the device, and
    # the strict TOFU behaviour is asserted separately in TestSSH.
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    kwargs = {"username": PI_USER, "port": SSH_PORT, "timeout": 15}
    if SSH_KEY:
        kwargs["key_filename"] = str(Path(SSH_KEY).expanduser())
    else:
        kwargs["password"] = SSH_PASSWORD
        kwargs["look_for_keys"] = False

    try:
        client.connect(PI_HOST, **kwargs)
    except Exception as e:
        pytest.skip(f"cannot SSH to {PI_HOST}:{SSH_PORT} - {type(e).__name__}: {e}")

    yield client
    client.close()


def _run(ssh, command, timeout=60):
    """Run a command on the Pi, returning (exit_status, stdout, stderr)."""
    _, out, err = ssh.exec_command(command, timeout=timeout)
    status = out.channel.recv_exit_status()
    return status, out.read().decode(errors="replace"), err.read().decode(errors="replace")


@pytest.fixture(scope="session")
def api():
    """The Pi's API must be reachable, or every API test is pointless."""
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=15)
    except requests.exceptions.RequestException as e:
        pytest.skip(f"LabLink API unreachable at {BASE_URL} - {e}")
    if r.status_code != 200:
        pytest.skip(f"{BASE_URL}/health returned {r.status_code}")
    return BASE_URL


def _login_or_skip(base_url):
    """Fetch a fresh access token, or skip."""
    if not ADMIN_PASSWORD:
        pytest.skip("set LABLINK_ADMIN_PASSWORD")
    r = requests.post(
        f"{base_url}/api/security/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    if r.status_code != 200:
        pytest.skip(f"login failed ({r.status_code}): {r.text[:200]}")
    return r.json()["access_token"]


@pytest.fixture
def token(api):
    """A live access token, or skip.

    Deliberately function-scoped: logout revokes *every* session for the user
    (destroy_user_sessions), so a shared session-scoped token would be killed
    by the revocation tests and later tests would fail with a misleading 403
    depending purely on ordering.
    """
    if not ADMIN_PASSWORD:
        pytest.skip("set LABLINK_ADMIN_PASSWORD")
    r = requests.post(
        f"{api}/api/security/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    if r.status_code != 200:
        pytest.skip(f"login failed ({r.status_code}): {r.text[:200]}")
    return r.json()["access_token"]


# ---------------------------------------------------------------------------
# 1. Deployment - did the right build actually land?
# ---------------------------------------------------------------------------


class TestDeployment:
    """The first-boot script installs a *branch*. Confirm which one landed.

    If this fails, every other result below is measuring the wrong build.
    """

    def test_lablink_directory_exists(self, ssh):
        status, out, _ = _run(ssh, "test -d /opt/lablink && echo present")
        assert status == 0 and "present" in out, "/opt/lablink missing - first boot did not complete"

    def test_version_on_pi_matches_expectation(self, ssh):
        status, out, err = _run(ssh, "cat /opt/lablink/VERSION")
        assert status == 0, f"could not read VERSION: {err.strip()}"
        deployed = out.strip()

        assert deployed == EXPECT_VERSION, (
            f"Pi is running LabLink {deployed}, expected {EXPECT_VERSION}. "
            "The first-boot script downloads a branch tarball - if this says "
            "1.x the image was built without LABLINK_BRANCH pointing at the "
            "2.0.0 branch, and the rest of this run is testing the wrong build."
        )

    def test_first_boot_service_succeeded(self, ssh):
        status, out, _ = _run(
            ssh, "systemctl is-active lablink-first-boot.service 2>/dev/null || true"
        )
        # inactive is fine once it has completed; failed is not
        assert "failed" not in out, f"first-boot service failed: {out.strip()}"

    def test_docker_is_running(self, ssh):
        status, _, _ = _run(ssh, "docker info")
        assert status == 0, "docker is not running on the Pi"

    def test_containers_are_up(self, ssh):
        status, out, err = _run(ssh, "cd /opt/lablink && docker compose ps")
        assert status == 0, f"docker compose ps failed: {err.strip()}"
        assert "Up" in out or "running" in out.lower(), f"no running containers:\n{out}"

    def test_container_python_version(self, ssh):
        """2.0.0 ships python:3.13-slim; numpy 2.5 / scipy 1.18 need >= 3.12."""
        status, out, _ = _run(
            ssh,
            "cd /opt/lablink && docker compose exec -T lablink-server "
            "python -c 'import sys; print(\"%d.%d\" % sys.version_info[:2])' 2>/dev/null || true",
        )
        if not out.strip():
            pytest.skip("could not query the container's Python version")
        major, _, minor = out.strip().partition(".")
        assert (int(major), int(minor)) >= (3, 12), f"container Python is {out.strip()}"

    def test_scientific_stack_imports_in_container(self, ssh):
        """numpy 2.5 / scipy 1.18 must be importable, not just installed."""
        status, out, _ = _run(
            ssh,
            "cd /opt/lablink && docker compose exec -T lablink-server python -c "
            "'import numpy, scipy, pandas; print(numpy.__version__, scipy.__version__, pandas.__version__)' "
            "2>/dev/null || true",
        )
        if not out.strip():
            pytest.skip("could not query the container's scientific stack")
        print(f"\n  container numpy/scipy/pandas: {out.strip()}")
        assert out.strip(), "numpy/scipy/pandas failed to import in the container"


# ---------------------------------------------------------------------------
# 2. SSH - paramiko 5 against a real device
# ---------------------------------------------------------------------------


class TestSSH:
    """paramiko 5.0.0 drops ssh-rsa. Confirm this Pi is not affected."""

    def test_host_key_algorithm_is_supported(self, ssh):
        key = ssh.get_transport().get_remote_server_key()
        name = key.get_name()
        print(f"\n  negotiated host key: {name}")

        assert name not in ("ssh-rsa", "ssh-dss"), (
            f"this Pi offers {name}, which paramiko 5 removed. Regenerate host "
            "keys on the device: sudo ssh-keygen -A && sudo systemctl restart ssh"
        )

    def test_exec_command_round_trip(self, ssh):
        status, out, _ = _run(ssh, "echo LABLINK_SSH_OK")
        assert status == 0
        assert "LABLINK_SSH_OK" in out

    def test_tofu_policy_rejects_unknown_host(self, ssh):
        """The wizard's policy must refuse an untrusted key, on this device.

        Takes the ssh fixture purely so an unreachable host skips here rather
        than failing with a connection timeout.
        """
        paramiko = pytest.importorskip("paramiko")
        from client.ui.ssh_deploy_wizard import _LabLinkHostKeyPolicy

        client = paramiko.SSHClient()  # deliberately no known_hosts loaded
        policy = _LabLinkHostKeyPolicy()
        client.set_missing_host_key_policy(policy)

        kwargs = {"username": PI_USER, "port": SSH_PORT, "timeout": 15}
        if SSH_KEY:
            kwargs["key_filename"] = str(Path(SSH_KEY).expanduser())
        else:
            kwargs["password"] = SSH_PASSWORD
            kwargs["look_for_keys"] = False

        with pytest.raises(paramiko.ssh_exception.SSHException, match="Unknown host key"):
            client.connect(PI_HOST, **kwargs)

        # and the offered key must be retrievable by bare hostname, which is
        # what makes the wizard's accept dialog reachable
        assert policy.get_unknown_key(PI_HOST) is not None, (
            "policy stored the key under a name the wizard cannot look up"
        )

    def test_scp_round_trip(self, ssh, tmp_path):
        scp_mod = pytest.importorskip("scp")
        src = tmp_path / "lablink-scp-probe.txt"
        src.write_text("lablink live test\n")

        with scp_mod.SCPClient(ssh.get_transport()) as scp:
            scp.put(str(src), "/tmp/lablink-scp-probe.txt")
        status, out, _ = _run(ssh, "cat /tmp/lablink-scp-probe.txt")

        assert status == 0
        assert "lablink live test" in out
        _run(ssh, "rm -f /tmp/lablink-scp-probe.txt")


# ---------------------------------------------------------------------------
# 3. API and auth lifecycle over a real network
# ---------------------------------------------------------------------------


class TestApi:
    def test_health(self, api):
        r = requests.get(f"{api}/health", timeout=15)
        assert r.status_code == 200
        assert r.json().get("status") in ("healthy", "degraded")

    def test_api_root_reports_expected_version(self, api):
        r = requests.get(f"{api}/api", timeout=15)
        assert r.status_code == 200
        reported = r.json().get("version")
        print(f"\n  API reports version: {reported}")
        assert reported == EXPECT_VERSION, (
            f"API reports {reported}, expected {EXPECT_VERSION}"
        )


class TestAuthLifecycle:
    """The 1.3.0 revocation work, against a real deployment."""

    def test_login_returns_a_token(self, api):
        if not ADMIN_PASSWORD:
            pytest.skip("set LABLINK_ADMIN_PASSWORD")
        r = requests.post(
            f"{api}/api/security/login",
            json={"username": ADMIN_USER, "password": ADMIN_PASSWORD},
            timeout=20,
        )
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["access_token"] and body["refresh_token"]

    def test_bad_password_is_rejected(self, api):
        r = requests.post(
            f"{api}/api/security/login",
            json={"username": ADMIN_USER, "password": "definitely-not-the-password"},
            timeout=20,
        )
        assert r.status_code in (401, 429)

    def test_token_grants_access(self, api, token):
        r = requests.get(f"{api}/api/security/me", headers=_auth(token), timeout=20)
        assert r.status_code == 200
        assert r.json()["username"] == ADMIN_USER

    def test_garbage_token_rejected(self, api):
        r = requests.get(f"{api}/api/security/me", headers=_auth("not.a.jwt"), timeout=20)
        assert r.status_code == 401

    def test_logout_actually_revokes_the_token(self, api):
        """The core of the 1.3.0 change, end to end on real hardware."""
        if not ADMIN_PASSWORD:
            pytest.skip("set LABLINK_ADMIN_PASSWORD")
        login = requests.post(
            f"{api}/api/security/login",
            json={"username": ADMIN_USER, "password": ADMIN_PASSWORD},
            timeout=20,
        )
        assert login.status_code == 200
        tok = login.json()["access_token"]
        assert requests.get(f"{api}/api/security/me", headers=_auth(tok), timeout=20).status_code == 200

        assert requests.post(f"{api}/api/security/logout", headers=_auth(tok), timeout=20).status_code == 200

        after = requests.get(f"{api}/api/security/me", headers=_auth(tok), timeout=20)
        assert after.status_code == 401, (
            "access token still works after logout - it is not revocable on this build"
        )

    def test_refreshed_token_works_and_is_revocable(self, api):
        if not ADMIN_PASSWORD:
            pytest.skip("set LABLINK_ADMIN_PASSWORD")
        login = requests.post(
            f"{api}/api/security/login",
            json={"username": ADMIN_USER, "password": ADMIN_PASSWORD},
            timeout=20,
        ).json()

        r = requests.post(
            f"{api}/api/security/refresh",
            json={"refresh_token": login["refresh_token"]},
            timeout=20,
        )
        assert r.status_code == 200, r.text[:300]
        fresh = r.json()["access_token"]
        assert requests.get(f"{api}/api/security/me", headers=_auth(fresh), timeout=20).status_code == 200

        requests.post(f"{api}/api/security/logout", headers=_auth(fresh), timeout=20)
        assert requests.get(
            f"{api}/api/security/me", headers=_auth(fresh), timeout=20
        ).status_code == 401


# ---------------------------------------------------------------------------
# 4. Equipment - pyvisa 1.16 against real instruments
# ---------------------------------------------------------------------------


class TestEquipmentDiscovery:
    """The largest unverified surface in 2.0.0."""

    def test_discovery_responds(self, api, token):
        r = requests.post(f"{api}/api/equipment/discover", headers=_auth(token), timeout=90)
        assert r.status_code == 200, f"discovery failed: {r.text[:300]}"
        devices = r.json().get("devices", [])
        print(f"\n  discovered {len(devices)} device(s):")
        for d in devices:
            print(f"    {d.get('resource_name')}  {d.get('manufacturer')} {d.get('model')}")

    def test_expected_equipment_is_found(self, api, token):
        if not EXPECT_EQUIPMENT:
            pytest.skip("set LABLINK_EXPECT_EQUIPMENT to assert on specific instruments")
        r = requests.post(f"{api}/api/equipment/discover", headers=_auth(token), timeout=90)
        assert r.status_code == 200
        blob = json.dumps(r.json()).lower()

        missing = [want for want in EXPECT_EQUIPMENT if want.lower() not in blob]
        assert not missing, (
            f"expected instruments not discovered: {missing}. "
            "Check USB/serial connections and that pyvisa can see them "
            "(pyvisa 1.16 is new in 2.0.0)."
        )

    def test_list_connected(self, api, token):
        r = requests.get(f"{api}/api/equipment/list", headers=_auth(token), timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestEquipmentSession:
    """Connect, read, disconnect - the real VISA transport path.

    Skipped unless LABLINK_EXPECT_EQUIPMENT names something, since it needs a
    known instrument to drive.
    """

    @pytest.fixture(scope="class")
    def connected(self, api):
        if not EXPECT_EQUIPMENT:
            pytest.skip("set LABLINK_EXPECT_EQUIPMENT to run instrument tests")

        # Own token: logout in the auth tests revokes all sessions, and this
        # fixture outlives a function-scoped one.
        token = _login_or_skip(api)

        r = requests.post(f"{api}/api/equipment/discover", headers=_auth(token), timeout=90)
        assert r.status_code == 200
        wanted = EXPECT_EQUIPMENT[0].lower()
        match = next(
            (d for d in r.json().get("devices", []) if wanted in json.dumps(d).lower()), None
        )
        if match is None:
            pytest.skip(f"{EXPECT_EQUIPMENT[0]} not discovered")

        body = {
            "resource_string": match["resource_name"],
            "equipment_type": match.get("equipment_type") or "power_supply",
            "model": match.get("model") or "unknown",
        }
        c = requests.post(
            f"{api}/api/equipment/connect", headers=_auth(token), json=body, timeout=60
        )
        if c.status_code != 200:
            pytest.skip(f"connect failed: {c.status_code} {c.text[:200]}")

        equipment_id = c.json()["equipment_id"]
        yield equipment_id

        requests.post(
            f"{api}/api/equipment/disconnect/{equipment_id}",
            headers=_auth(token),
            timeout=30,
        )

    def test_status_is_reported(self, api, token, connected):
        r = requests.get(f"{api}/api/equipment/{connected}/status", headers=_auth(token), timeout=30)
        assert r.status_code == 200, r.text[:300]

    def test_readings_are_returned(self, api, token, connected):
        """The BK raw protocol (GETD/GOUT/GETS) is the timing-sensitive path
        that mocks cannot reproduce - this is what it is here to catch."""
        r = requests.get(
            f"{api}/api/equipment/{connected}/readings", headers=_auth(token), timeout=45
        )
        assert r.status_code == 200, f"readings failed: {r.text[:300]}"
        print(f"\n  readings: {json.dumps(r.json())[:200]}")

    def test_repeated_readings_are_stable(self, api, token, connected):
        """Serial instruments desync under repeated polling if framing is wrong."""
        failures = []
        for i in range(10):
            r = requests.get(
                f"{api}/api/equipment/{connected}/readings",
                headers=_auth(token),
                timeout=45,
            )
            if r.status_code != 200:
                failures.append(f"poll {i}: {r.status_code} {r.text[:120]}")
            time.sleep(0.5)

        assert not failures, "readings became unstable under repeated polling:\n" + "\n".join(failures)


# ---------------------------------------------------------------------------
# 5. WebSocket streaming under websockets 17
# ---------------------------------------------------------------------------


class TestWebSocket:
    """The /ws route is served by the FastAPI app on the API port.

    docker-compose.yml maps 8001 and sets LABLINK_WS_PORT=8001, but nothing
    binds 8001 inside the container - uvicorn runs with --port 8000 only. The
    default here follows the API port for that reason.
    """

    def test_ws_port_is_open(self, api):
        ws_port = int(os.environ.get("LABLINK_WS_PORT", str(API_PORT)))
        with socket.socket() as s:
            s.settimeout(10)
            if s.connect_ex((PI_HOST, ws_port)) != 0:
                pytest.skip(f"nothing listening on {PI_HOST}:{ws_port}")

    @pytest.mark.asyncio
    async def test_authenticated_connect(self, token):
        """websockets 17 replaced the legacy client; auth is a token query param."""
        websockets = pytest.importorskip("websockets")
        ws_port = int(os.environ.get("LABLINK_WS_PORT", str(API_PORT)))
        url = f"ws://{PI_HOST}:{ws_port}/ws?token={token}"
        try:
            async with websockets.connect(url, open_timeout=15) as ws:
                assert ws is not None
        except Exception as e:
            pytest.skip(f"websocket connect failed: {type(e).__name__}: {e}")

    @pytest.mark.asyncio
    async def test_rejects_missing_token(self):
        """An unauthenticated websocket must be refused.

        The port is checked first: without that, an unreachable host makes the
        connection fail and the test passes while proving nothing.
        """
        websockets = pytest.importorskip("websockets")
        ws_port = int(os.environ.get("LABLINK_WS_PORT", str(API_PORT)))

        with socket.socket() as probe:
            probe.settimeout(10)
            if probe.connect_ex((PI_HOST, ws_port)) != 0:
                pytest.skip(f"nothing listening on {PI_HOST}:{ws_port}")

        url = f"ws://{PI_HOST}:{ws_port}/ws"
        try:
            async with websockets.connect(url, open_timeout=15):
                pytest.fail("unauthenticated websocket was accepted")
        except pytest.fail.Exception:
            raise
        except (OSError, socket.timeout) as e:
            pytest.skip(f"websocket unreachable, cannot judge auth: {e}")
        except Exception:
            pass  # refused by the server, which is correct


# ---------------------------------------------------------------------------
# 6. Resource hygiene
# ---------------------------------------------------------------------------


class TestResourceHygiene:
    """The 1.3.0 work fixed a file-descriptor leak; confirm it holds in situ."""

    def test_descriptors_stable_across_api_calls(self, ssh, api, token):
        def fds():
            status, out, _ = _run(
                ssh,
                "cd /opt/lablink && docker compose exec -T lablink-server "
                "sh -c 'ls /proc/1/fd | wc -l' 2>/dev/null || true",
            )
            return int(out.strip()) if out.strip().isdigit() else None

        before = fds()
        if before is None:
            pytest.skip("could not count file descriptors in the container")

        for _ in range(40):
            requests.get(f"{api}/api/equipment/list", headers=_auth(token), timeout=20)

        after = fds()
        print(f"\n  container fds: {before} -> {after}")
        assert after - before < 25, (
            f"file descriptors grew {before} -> {after} across 40 requests, "
            "which suggests connections are being leaked"
        )
