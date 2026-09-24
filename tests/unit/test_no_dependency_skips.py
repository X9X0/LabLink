"""A missing dependency must fail, not quietly delete its own tests.

104 test files in this suite guard themselves on an import -- ``pytest.
importorskip``, a ``try: import ... except ImportError`` setting a
GUI_AVAILABLE flag, a ``skipif``. That is the right shape for a test
that genuinely cannot run somewhere, and the wrong shape for a
dependency that was simply never installed: the tests disappear and the
run is still green.

It is not hypothetical. Every entry in requirements-test.txt below the
"Optional" block was added after exactly this -- pyfatfs, passlib,
paramiko, pydantic[email], pyserial, pytest-benchmark -- each one a
suite that had been passing vacuously for some unknown stretch. The
file's own comments say it plainly: "Without these the image-builder
tests importorskip themselves and pass vacuously, which is worse than
not having them."

And it was still happening. On 2026-09-24 this environment was missing
pytest-benchmark, pandas and h5py, and running pytest 7.4.4 against a
declared floor of 9.1.1 -- so tests/performance had been skipping
silently and nobody could have known from the output.

So the rule is inverted here: importability is asserted up front, by a
test that fails loudly and names both the module and the file that
declares it. Somewhere that genuinely cannot have these -- a headless
box with no Qt -- sets LABLINK_ALLOW_MISSING_DEPS=1 and takes the
consequence knowingly, which is the entire difference from today.
"""

import importlib
import os

import pytest

#: module -> the requirements file that declares it.
REQUIRED = {
    # Server runtime; the API and driver suites import these transitively.
    "fastapi": "server/requirements.txt",
    "pydantic": "shared/requirements.txt",
    "pydantic_settings": "server/requirements.txt",
    "email_validator": "server/requirements.txt",
    "pyvisa": "server/requirements.txt",
    "serial": "server/requirements.txt",
    "scipy": "server/requirements.txt",
    "numpy": "server/requirements.txt",
    "pandas": "server/requirements.txt",
    "h5py": "server/requirements.txt",
    "apscheduler": "server/requirements.txt",
    "psutil": "server/requirements.txt",
    "zeroconf": "server/requirements.txt",
    "websockets": "server/requirements.txt",
    "jwt": "server/requirements.txt",
    "bcrypt": "server/requirements.txt",
    "pyotp": "server/requirements.txt",
    "multipart": "server/requirements.txt",
    "httpx": "server/requirements.txt",
    # Client. CI installed these ad-hoc for a long time rather than from
    # the file, which is how pyqtgraph came to be present in one job and
    # absent in two others.
    "PyQt6": "client/requirements.txt",
    "PyQt6.QtCharts": "client/requirements.txt",
    "pyqtgraph": "client/requirements.txt",
    "qasync": "client/requirements.txt",
    "paramiko": "client/requirements.txt",
    "scp": "client/requirements.txt",
    "keyring": "client/requirements.txt",
    "pyfatfs": "client/requirements.txt",
    "passlib": "client/requirements.txt",
    # Test tooling.
    "pytest_asyncio": "requirements-test.txt",
    "pytest_benchmark": "requirements-test.txt",
    "pytest_mock": "requirements-test.txt",
    "requests": "requirements-test.txt",
}

#: (module, minimum) for the few where an old version is as bad as none.
#: pytest-asyncio 0.23 and pytest 9 are mutually incompatible, so an
#: environment can satisfy "installed" and still collect nothing.
MINIMUMS = {
    "pytest": (9, 1),
    "pytest_asyncio": (1, 4),
}

OPT_OUT = "LABLINK_ALLOW_MISSING_DEPS"

pytestmark = pytest.mark.skipif(
    os.environ.get(OPT_OUT) == "1",
    reason=f"{OPT_OUT}=1: missing dependencies accepted deliberately",
)


def _version(module):
    raw = getattr(module, "__version__", None)
    if not raw:
        return None
    parts = []
    for piece in str(raw).split(".")[:2]:
        digits = "".join(c for c in piece if c.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) if len(parts) == 2 else None


class TestEveryGatedDependencyIsInstalled:
    @pytest.mark.parametrize("module,declared_in", sorted(REQUIRED.items()))
    def test_it_imports(self, module, declared_in):
        try:
            importlib.import_module(module)
        except ImportError as missing:
            pytest.fail(
                f"{module} is not installed, so every test guarded on it "
                f"skips and the run still passes.\n"
                f"  declared in: {declared_in}\n"
                f"  install it, or set {OPT_OUT}=1 to accept the gap "
                f"knowingly.\n"
                f"  ({missing})"
            )

    def test_the_whole_set_is_reported_at_once(self):
        """One failure naming everything beats fixing them one run at a time."""
        missing = {}
        for module, declared_in in REQUIRED.items():
            try:
                importlib.import_module(module)
            except ImportError:
                missing.setdefault(declared_in, []).append(module)

        assert not missing, "missing dependencies:\n" + "\n".join(
            f"  pip install -r {where}   # {', '.join(sorted(mods))}"
            for where, mods in sorted(missing.items())
        )


class TestTheToolchainMeetsItsDeclaredFloor:
    """Installed-but-too-old collects nothing and still reads as green."""

    @pytest.mark.parametrize("module,minimum", sorted(MINIMUMS.items()))
    def test_it_is_new_enough(self, module, minimum):
        try:
            loaded = importlib.import_module(module)
        except ImportError:
            pytest.fail(f"{module} is not installed")

        found = _version(loaded)
        if found is None:
            pytest.skip(f"{module} reports no parseable __version__")

        assert found >= minimum, (
            f"{module} {'.'.join(map(str, found))} is below the declared "
            f"floor {'.'.join(map(str, minimum))} in requirements-test.txt. "
            f"pytest 9 with pytest-asyncio 0.23 collects no async tests at "
            f"all, which looks identical to having none."
        )
