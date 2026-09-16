"""Live acceptance checks for the three DS1054Z fixes, against a real bench.

These replace hand-poking the bench after a deploy. They cover everything in
``docs/HANDOFF_INSTRUMENT_PANELS.md`` "Verification" that does not need a
mouse: the right code is deployed, the scope returns a trace, measurements come
back promptly, the supplies still read, the server log is clean, and the queue
bound refuses a burst instead of swallowing it.

What they cannot check, and still needs a human at the client: that the panel
*draws* the trace, that a hidden panel stops polling, and that switching
instruments feels instant. Those are Qt behaviours on a running client. What
these do is make sure the server side is right before you spend time looking,
and catch a bad deploy in the first second rather than after ten minutes of
wondering why nothing changed.

Configure the same way as ``test_live_pi.py`` (it reads the same variables,
and ``LABLINK_PI_CREDS`` if you keep them in a file):

    LABLINK_PI_HOST          hostname or IP of the Pi          (required)
    LABLINK_PI_USER          SSH username                      (default: admin)
    LABLINK_API_PORT         LabLink API port                  (default: 8000)
    LABLINK_REMOTE_DIR       the Pi's checkout                 (default: /opt/lablink)
    LABLINK_EXPECT_COMMIT    commit the Pi should be on        (default: local HEAD)
    LABLINK_SCOPE_RESOURCE   the scope's resource string, for a
                             LAN scope that discovery cannot see
    LABLINK_TRACE_BUDGET_S   slowest acceptable trace fetch    (default: 4.0)
    LABLINK_RUN_BURST        set to 1 to run the queue-bound burst

Run with:

    pytest tests/hardware/test_scope_lag_fixes.py -v

**Effect on the bench.** These connect the oscilloscope and read from it. They
send no command that changes a setting, and they never disconnect anything:
disconnecting closes a serial port, and on a port with termios ``hupcl`` set
that resets a legacy B&K supply and drops a live output (see the warning at the
top of ``test_live_pi.py``). The supplies here are only read, and only if the
server already has them open. The burst check is opt-in because it deliberately
loads one instrument for several seconds.
"""

import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import requests

REPO = Path(__file__).resolve().parents[2]


def _load_creds_file():
    """Load KEY=VALUE pairs from LABLINK_PI_CREDS, as test_live_pi.py does."""
    path = os.environ.get("LABLINK_PI_CREDS")
    if not path:
        return
    f = Path(path).expanduser()
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_creds_file()

PI_HOST = os.environ.get("LABLINK_PI_HOST", "")
PI_USER = os.environ.get("LABLINK_PI_USER", "admin")
API_PORT = int(os.environ.get("LABLINK_API_PORT", "8000"))
REMOTE_DIR = os.environ.get("LABLINK_REMOTE_DIR", "/opt/lablink")
CONTAINER = os.environ.get("LABLINK_CONTAINER", "lablink-server")
TRACE_BUDGET_S = float(os.environ.get("LABLINK_TRACE_BUDGET_S", "4.0"))
MEAS_BUDGET_S = float(os.environ.get("LABLINK_MEAS_BUDGET_S", "3.0"))
RUN_BURST = os.environ.get("LABLINK_RUN_BURST", "") not in ("", "0", "false", "no")
#: A resource string to use for the oscilloscope instead of whatever discovery
#: finds. Needed for a LAN scope: discovery enumerates VISA resources, which on
#: this server means USB, and this DS1054Z serves LAN for remote I/O only while
#: USB is physically unplugged -- so the link we now recommend is the one
#: discovery cannot see. e.g. TCPIP0::192.168.91.37::inst0::INSTR
SCOPE_RESOURCE = os.environ.get("LABLINK_SCOPE_RESOURCE", "")

BASE_URL = f"http://{PI_HOST}:{API_PORT}"
API = f"{BASE_URL}/api/equipment"

#: The log lines that each mean one of the three bugs is back. See
#: docs/HANDOFF_SCOPE_LAG.md "Log lines to look for".
BAD_LOG_SIGNATURES = (
    "VI_ERROR_TMO",          # a command the instrument did not answer
    "waited",                # an exchange queued behind others
    "took 10.0s",            # the full VISA timeout, spent on one command
    "refusing",              # the queue bound firing during ordinary use
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_hardware,
    pytest.mark.skipif(not PI_HOST, reason="set LABLINK_PI_HOST to run bench checks"),
]


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------


def _ssh(command, timeout=90):
    """Run a command on the Pi over ssh, returning (status, stdout)."""
    if not shutil.which("ssh"):
        pytest.skip("no ssh client on PATH")
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
         f"{PI_USER}@{PI_HOST}", command],
        capture_output=True, text=True, timeout=timeout,
    )
    return result.returncode, result.stdout


@pytest.fixture(scope="module")
def ssh_ready():
    """Skip the whole module rather than fail every check if ssh is not set up.

    Retried, because this fixture is module-scoped: one blip on a bench LAN
    would otherwise skip all eleven checks and read as "nothing to report",
    which is the worst possible answer from a check you are trusting to tell
    you whether a deploy worked. Seen once on this bench mid-session, with the
    Pi up and its API answering throughout.
    """
    for attempt in range(3):
        status, out = _ssh("echo ok", timeout=40)
        if status == 0 and "ok" in out:
            return True
        if attempt < 2:
            time.sleep(2)
    pytest.skip(f"cannot ssh to {PI_USER}@{PI_HOST} with a key (BatchMode) "
                f"after 3 attempts")


@pytest.fixture(scope="module")
def api():
    """The API must answer, or there is nothing to check."""
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=15)
    except requests.exceptions.RequestException as e:
        pytest.skip(f"API unreachable at {BASE_URL} - {e}")
    if r.status_code != 200:
        pytest.skip(f"{BASE_URL}/health returned {r.status_code}")
    return BASE_URL


@pytest.fixture(scope="module")
def inventory(api):
    """What is on the bench, normalised.

    Two different questions, and they have different answers. ``/list`` reports
    the equipment the server has registered, which on a server with a fresh
    database is nothing at all -- the fixtest container used while validating
    these checks answered ``[]`` while discovery found all three instruments.
    ``/discover`` reports what is actually plugged in. So prefer the register,
    and fall back to a scan, normalising both to the same keys.
    """
    listed = requests.get(f"{API}/list", timeout=30).json()
    if listed:
        return listed

    found = requests.post(f"{API}/discover", timeout=180).json().get("devices", [])
    if not found:
        pytest.skip("neither the register nor a discovery scan found any instrument")
    return [
        {
            "id": None,                       # not registered yet; filled in on connect
            "type": device.get("device_type"),
            "model": device.get("model"),
            "resource_string": device.get("resource_name"),
            "connected": bool(device.get("is_connected")),
        }
        for device in found
    ]


@pytest.fixture(scope="module")
def scope(inventory):
    """The oscilloscope, open and ready.

    Never disconnected -- see the module docstring. Opening it is necessary
    and harmless: a scope has no output to drop.
    """
    if SCOPE_RESOURCE:
        # Named explicitly, because a LAN scope is invisible to discovery.
        already = [d for d in inventory
                   if d.get("resource_string") == SCOPE_RESOURCE]
        found = dict(already[0]) if already else {
            "id": None, "type": "oscilloscope", "model": "",
            "resource_string": SCOPE_RESOURCE, "connected": False,
        }
    else:
        scopes = [d for d in inventory if d.get("type") == "oscilloscope"]
        if not scopes:
            pytest.skip("no oscilloscope on this bench (set "
                        "LABLINK_SCOPE_RESOURCE for one on LAN)")
        found = dict(scopes[0])

    # A server that has just restarted -- which is to say, one that has just
    # been deployed to -- has the instrument registered but not open, and
    # answers 404 to every command until something connects it.
    if found["id"] and found["connected"]:
        return found

    response = requests.post(
        f"{API}/connect",
        json={"resource_string": found["resource_string"],
              "equipment_type": "oscilloscope",
              "model": found.get("model") or ""},
        timeout=120,
    )
    if response.status_code != 200:
        pytest.skip(f"could not open the scope: "
                    f"{response.status_code} {response.text[:200]}")
    found["id"] = response.json()["equipment_id"]
    found["connected"] = True
    return found


#: Long enough for a healthy multi-window trace read (~1 s on the bench) and
#: for one server-side VISA timeout (10 s), short enough that a broken build
#: does not cost minutes per check.
REQUEST_TIMEOUT_S = float(os.environ.get("LABLINK_REQUEST_TIMEOUT_S", "30"))


def _command(equipment_id, action, parameters=None, timeout=None):
    """POST one command, returning (elapsed_seconds, response)."""
    started = time.monotonic()
    try:
        response = requests.post(
            f"{API}/{equipment_id}/command",
            json={"command_id": f"bench-{action}-{int(started * 1000)}",
                  "equipment_id": equipment_id,
                  "action": action,
                  "parameters": parameters or {}},
            timeout=timeout or REQUEST_TIMEOUT_S,
        )
    except requests.exceptions.Timeout:
        raise AssertionError(
            f"{action} did not answer within {timeout or REQUEST_TIMEOUT_S:.0f}s. "
            f"The server does not cancel a request the client abandons, so check "
            f"the container log for 'waited' before retrying -- a backlog takes "
            f"as long to drain as it took to build."
        ) from None
    return time.monotonic() - started, response


def _data_or_fail(elapsed, response, what):
    assert response.status_code == 200, (
        f"{what}: HTTP {response.status_code} in {elapsed:.2f}s -- {response.text[:200]}"
    )
    body = response.json()
    assert body.get("success"), f"{what} failed in {elapsed:.2f}s: {body.get('error')}"
    return body["data"]


def _expected_commit():
    """The commit the bench is supposed to be running."""
    from_env = os.environ.get("LABLINK_EXPECT_COMMIT", "")
    if from_env:
        return from_env
    local = subprocess.run(["git", "rev-parse", "HEAD"],
                           capture_output=True, text=True, cwd=REPO)
    return local.stdout.strip() if local.returncode == 0 else ""


def _deployed_commit():
    """What the Pi's checkout is actually on, as (commit, where).

    Reads the refs directly: git itself refuses the root-owned checkout with
    "detected dubious ownership" unless it runs as root.
    """
    status, head = _ssh(f"cat {REMOTE_DIR}/.git/HEAD")
    if status != 0 or not head.strip():
        return "", ""
    head = head.strip()
    if not head.startswith("ref: "):
        return head, "a detached commit or tag"
    ref = head[len("ref: "):].strip()
    _, out = _ssh(f"cat {REMOTE_DIR}/.git/{ref} 2>/dev/null || "
                  f"grep ' {ref}$' {REMOTE_DIR}/.git/packed-refs")
    commit = out.strip().split()[0] if out.strip() else ""
    return commit, ref.replace("refs/heads/", "")


def _same_commit(deployed, expected):
    if not deployed or not expected:
        return False
    return deployed.startswith(expected[:12]) or expected.startswith(deployed[:12])


@pytest.fixture(scope="module")
def right_code(ssh_ready):
    """Gate every behaviour check on the deploy having worked.

    Without this, a Pi still on the old build spends the full VISA timeout on
    every request and the run takes minutes to tell you what the first check
    already knew. The deploy check itself still fails loudly; these skip.
    """
    expected = _expected_commit()
    if not expected:
        pytest.skip("cannot determine the commit under test")
    deployed, _where = _deployed_commit()
    if not _same_commit(deployed, expected):
        pytest.skip(
            f"the Pi is on {deployed[:12] or 'an unreadable ref'}, not "
            f"{expected[:12]} -- see the failure in TestTheRightCodeIsDeployed"
        )
    return expected


def _log_since(seconds, grep=""):
    """The container's log for the last `seconds`, ANSI colour stripped.

    A relative window rather than a timestamp: the Pi's clock and the machine
    running these checks need not agree.
    """
    pipeline = (
        f"docker logs --since {int(seconds)}s {CONTAINER} 2>&1 "
        r"| sed 's/\x1b\[[0-9;]*m//g'"
    )
    if grep:
        pipeline += f" | grep -E {grep!r}"
    status, out = _ssh(pipeline)
    return out


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------


class TestTheRightCodeIsDeployed:
    """First, because everything below is meaningless against the old build.

    The in-app *Update Remote Server* takes its ref from the version selector
    when the update mode is "Stable (VERSION releases)", and from the branch
    combo only in "Development (all commits)" mode
    (``client/ui/system_panel.py``, ``_update_remote_server``). A bench Pi left
    on the stable channel therefore gets a release tag, silently moving it off
    the feature branch and deploying none of the work under test.
    """

    def test_the_pi_is_on_the_commit_under_test(self, ssh_ready):
        expected = _expected_commit()
        if not expected:
            pytest.skip("cannot read the local HEAD to compare against")
        deployed, where = _deployed_commit()
        if not deployed:
            pytest.skip(f"{REMOTE_DIR} is not a readable git checkout on {PI_HOST}")

        assert _same_commit(deployed, expected), (
            f"The Pi is on {where or '?'} at {deployed[:12]}, not the commit "
            f"under test {expected[:12]}.\n\n"
            "If you just pressed Update Remote Server, it almost certainly used "
            "the stable channel: the ref comes from the version selector unless "
            "the update mode is 'Development (all commits)'. Set that mode, pick "
            "the branch, update again. Every other check here skips until this "
            "one passes, because against the old build they only measure the "
            "old bugs."
        )

    def test_the_container_is_healthy_with_its_instruments(self, api, ssh_ready):
        r = requests.get(f"{BASE_URL}/health", timeout=15)
        body = r.json()
        assert body.get("status") == "healthy", body
        _, status = _ssh(f"docker inspect -f '{{{{.State.Status}}}}' {CONTAINER}")
        assert "running" in status, f"{CONTAINER} is not running: {status.strip()}"


class TestTheScopeReturnsATrace:
    """Cause 2: a 1212-byte reply never arrived over this scope's USB link.

    The panel showed nothing at all, 62 attempts out of 62. The trace is now
    read in windows under the measured 492-byte ceiling.
    """

    def test_a_full_trace_comes_back(self, right_code, scope):
        elapsed, response = _command(
            scope["id"], "get_waveform_data", {"channel": 1, "points": 600})
        data = _data_or_fail(elapsed, response, "get_waveform_data")

        assert data["num_samples"] == 600, data["num_samples"]
        assert len(data["voltage"]) == 600 and len(data["time"]) == 600
        assert elapsed < TRACE_BUDGET_S, (
            f"the trace took {elapsed:.2f}s, over the {TRACE_BUDGET_S}s budget "
            f"(about 1.0s on the bench for three windowed reads)"
        )

    def test_the_trace_carries_a_real_signal(self, right_code, scope):
        """A flat line of zeros would pass a length check and mean nothing."""
        elapsed, response = _command(
            scope["id"], "get_waveform_data", {"channel": 1, "points": 600})
        data = _data_or_fail(elapsed, response, "get_waveform_data")
        volts = data["voltage"]
        assert len(set(volts)) > 1, "every sample is identical -- not a trace"
        assert data["x_increment"] > 0, data["x_increment"]
        assert data["sample_rate"] > 0, data["sample_rate"]

    def test_it_keeps_working_when_asked_repeatedly(self, right_code, scope):
        """The old failure was total, but an intermittent one would be worse.

        A single read succeeded 1 time in 13 while this was being diagnosed,
        so one passing fetch is not evidence. The panel asks once a second.
        """
        times = []
        for _ in range(3):
            elapsed, response = _command(
                scope["id"], "get_waveform_data", {"channel": 1, "points": 600})
            data = _data_or_fail(elapsed, response, "repeated get_waveform_data")
            assert data["num_samples"] == 600
            times.append(elapsed)
        assert max(times) < TRACE_BUDGET_S, (
            f"slowest of three fetches was {max(times):.2f}s: {[round(t, 2) for t in times]}"
        )


class TestTheMeasurementsAnswer:
    """Cause 1: :MEAS:VAV? is not a DS1000Z command and never answered.

    Every measurement poll paid a full 10 s VISA timeout for it, 100 times in
    the container's first 27 minutes, and lost the rest of the set with it.
    """

    def test_the_panels_basic_set_comes_back_promptly(self, right_code, scope):
        elapsed, response = _command(
            scope["id"], "get_measurements",
            {"channel": 1, "items": ["vpp", "vavg", "freq"]})
        data = _data_or_fail(elapsed, response, "get_measurements")

        assert set(data) == {"vpp", "vavg", "freq"}, data
        # vavg is the one that never used to arrive.
        assert "vavg" in data and data["vavg"] is not None
        assert elapsed < MEAS_BUDGET_S, (
            f"three measurements took {elapsed:.2f}s; a single unanswered "
            f"command costs 10s, and the bench does this in 0.01s"
        )

    def test_every_item_the_driver_offers_answers(self, right_code, scope):
        elapsed, response = _command(scope["id"], "get_measurements", {"channel": 1})
        data = _data_or_fail(elapsed, response, "get_measurements (all items)")
        assert set(data) == {"vpp", "vmax", "vmin", "vavg", "vrms", "freq", "period"}, (
            f"missing items: {{'vpp','vmax','vmin','vavg','vrms','freq','period'}} - {set(data)}"
        )
        assert elapsed < MEAS_BUDGET_S, f"seven measurements took {elapsed:.2f}s"


class TestTheSuppliesAreUnchanged:
    """Verification item 2: the supplies must behave exactly as before.

    Read only, and only if the server already has them open. Nothing here
    connects or disconnects a supply: closing a serial port drops DTR and a
    legacy B&K treats that as a reset, which switches a live output off.
    """

    def test_every_open_supply_still_reads_quickly(self, right_code, inventory):
        supplies = [d for d in inventory
                    if d.get("type") == "power_supply" and d.get("connected")]
        if not supplies:
            pytest.skip("no power supply is currently open on the server")
        for supply in supplies:
            started = time.monotonic()
            r = requests.get(f"{API}/{supply['id']}/readings", timeout=30)
            elapsed = time.monotonic() - started
            assert r.status_code == 200, (
                f"{supply['model']}: HTTP {r.status_code} -- {r.text[:200]}")
            assert elapsed < 2.0, (
                f"{supply['model']} readings took {elapsed:.2f}s; the bench "
                f"answers in 0.03-0.07s"
            )


class TestTheLogIsClean:
    """Verification item 4, and the sharpest single signal on this bench.

    The whole diagnosis was done from these four strings. A run of ordinary
    panel traffic must produce none of them.
    """

    def test_ordinary_traffic_leaves_no_bad_signature(self, right_code, scope, ssh_ready):
        started = time.monotonic()
        for _ in range(3):
            _, response = _command(
                scope["id"], "get_waveform_data", {"channel": 1, "points": 600})
            assert response.status_code == 200
            _, response = _command(
                scope["id"], "get_measurements",
                {"channel": 1, "items": ["vpp", "vavg", "freq"]})
            assert response.status_code == 200
        requests.get(f"{API}/{scope['id']}/readings", timeout=30)

        window = int(time.monotonic() - started) + 5
        log = _log_since(window)
        if not log.strip():
            pytest.skip("could not read the container log to check it")

        offenders = {
            signature: [line for line in log.splitlines() if signature in line]
            for signature in BAD_LOG_SIGNATURES
        }
        offenders = {k: v for k, v in offenders.items() if v}
        assert not offenders, (
            "the log shows the bugs are back:\n"
            + "\n".join(f"  {sig} x{len(lines)}: {lines[0][:140]}"
                        for sig, lines in offenders.items())
        )


@pytest.mark.skipif(not RUN_BURST, reason="set LABLINK_RUN_BURST=1 to load an instrument")
class TestTheQueueIsBounded:
    """Cause 3: an abandoned request kept running and the queue grew to 205 s.

    Opt-in: this deliberately points twenty concurrent trace fetches at one
    instrument for several seconds. It is the only check here that makes the
    bench briefly unresponsive, and the only one that expects 503s in the log.
    """

    def test_a_burst_is_refused_rather_than_queued(self, right_code, scope, ssh_ready):
        def fetch(_):
            return _command(scope["id"], "get_waveform_data",
                            {"channel": 1, "points": 600}, timeout=180)

        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=20) as pool:
            results = list(pool.map(fetch, range(20)))
        window = int(time.monotonic() - started) + 5

        codes = [r.status_code for _, r in results]
        worst = max(elapsed for elapsed, _ in results)
        refused = codes.count(503)
        served = codes.count(200)

        assert refused, (
            f"nothing was refused, so the queue absorbed all 20 requests "
            f"(codes: {sorted(set(codes))}). The bound is not working, and one "
            f"slow command can still build a backlog minutes deep."
        )
        assert served, f"everything was refused (codes: {sorted(set(codes))})"
        assert worst < 60, (
            f"the slowest request waited {worst:.1f}s. Twenty fetches at ~1s "
            f"each should cap out around 8s with the bound in place."
        )
        assert "refusing" in _log_since(window), (
            "the server refused requests without saying so in the log"
        )

    def test_the_instrument_recovers_immediately_afterwards(self, right_code, scope):
        """A refusal is about right now; the queue must drain and reopen."""
        elapsed, response = _command(
            scope["id"], "get_waveform_data", {"channel": 1, "points": 600})
        data = _data_or_fail(elapsed, response, "trace after the burst")
        assert data["num_samples"] == 600
        assert elapsed < TRACE_BUDGET_S, (
            f"{elapsed:.2f}s after the burst -- the queue did not drain")
