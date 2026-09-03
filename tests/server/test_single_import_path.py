"""The server package must be importable under exactly one name.

When both the repo root and server/ are on sys.path, the same file imports as
`equipment.locks` and `server.equipment.locks`. Python builds two module
objects, each running its own module-level `lock_manager = LockManager()`.

Nothing raises. The lifespan configures one set of singletons while every
request uses the other, so the lock reaper polls a dictionary nothing writes
to, the state directory is never set on the object that matters, and the
emergency stop is one import away from being checked on the wrong instance.

It went unnoticed for months precisely because it is silent -- no error, no
log line, no failing test. These are the tests that would have caught it.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

LOCAL_PACKAGES = {
    "acquisition", "alarm", "analysis", "api", "backup", "config", "database",
    "diagnostics", "discovery", "equipment", "firmware", "logging_config",
    "performance", "scheduler", "security", "system", "waveform", "web",
    "websocket",
}


class TestNoBareIntraServerImports:
    """Every import of the server's own modules must be spelled server.*."""

    def _offenders(self, root: Path, pattern: str):
        found = []
        for path in sorted(root.rglob("*.py")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if not stripped.startswith(("from ", "import ")):
                    continue
                for package in LOCAL_PACKAGES:
                    if stripped.startswith((f"from {package}.", f"from {package} ",
                                            f"import {package}.")):
                        found.append(f"{path.relative_to(REPO)}:{number}: {stripped}")
        return found

    def test_server_imports_itself_by_one_name(self):
        offenders = self._offenders(REPO / "server", "")

        assert not offenders, (
            "bare intra-server imports create a second module path:\n  "
            + "\n  ".join(offenders)
        )

    def test_tests_import_the_server_by_one_name(self):
        """A test importing bare re-creates the duplication inside the suite."""
        offenders = self._offenders(REPO / "tests", "")

        assert not offenders, (
            "tests importing the server bare load a second copy of it:\n  "
            + "\n  ".join(offenders)
        )

    def test_patch_targets_use_the_same_name(self):
        """mock.patch resolves a module path from a string, at runtime.

        Static import rewrites miss these, and a patch against the other
        spelling silently patches a different object than the one under test.
        """
        import re

        # A dotted path that is not a filename. "security.db" and
        # "scheduler.db" name files that happen to look like modules, and an
        # earlier version of this check flagged them -- the same false
        # positive the rewrite itself hit.
        extensions = ("py", "json", "yml", "yaml", "txt", "sh", "md", "db",
                      "log", "cfg", "ini", "csv", "html")
        pattern = re.compile(
            r"""['"](""" + "|".join(sorted(LOCAL_PACKAGES)) + r""")"""
            r"""((?:\.[A-Za-z_]\w*)+)['"]"""
        )
        offenders = []
        for path in sorted((REPO / "tests").rglob("*.py")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if line.strip().startswith("#"):
                    continue      # prose about this hazard is not the hazard
                for match in pattern.finditer(line):
                    if match.group(2).lstrip(".").split(".")[-1] in extensions:
                        continue          # a filename, not a module path
                    if f"server.{match.group(1)}" in line:
                        continue          # already prefixed
                    offenders.append(
                        f"{path.relative_to(REPO)}:{number}: {line.strip()}"
                    )

        assert not offenders, (
            "patch targets naming the server without the server. prefix:\n  "
            + "\n  ".join(offenders)
        )


class TestStartupGuard:
    """Starting in the broken shape must fail loudly rather than quietly work."""

    def test_guard_detects_the_duplicate(self):
        code = (
            "import sys\n"
            f"sys.path.insert(0, {str(REPO / 'server')!r})\n"
            "from server.main import _assert_single_import_path\n"
            "import server.equipment.locks, equipment.locks\n"
            "try:\n"
            "    _assert_single_import_path()\n"
            "    print('NOT DETECTED')\n"
            "except RuntimeError:\n"
            "    print('DETECTED')\n"
        )
        env = dict(os.environ, PYTHONPATH=str(REPO))
        result = subprocess.run([sys.executable, "-c", code], capture_output=True,
                                text=True, env=env, cwd=str(REPO))

        assert "DETECTED" in result.stdout, result.stderr[-400:]

    def test_guard_is_quiet_in_the_correct_shape(self):
        code = (
            "import sys\n"
            "sys.path = [p for p in sys.path if not p.rstrip('/').endswith('/server')]\n"
            "from server.main import _assert_single_import_path\n"
            "import server.equipment.locks, server.api.locks\n"
            "_assert_single_import_path()\n"
            "print('QUIET')\n"
        )
        env = dict(os.environ, PYTHONPATH=str(REPO))
        result = subprocess.run([sys.executable, "-c", code], capture_output=True,
                                text=True, env=env, cwd=str(REPO))

        assert "QUIET" in result.stdout, result.stderr[-400:]

    def test_the_lifespan_calls_it(self):
        """A guard nothing invokes is decoration."""
        source = (REPO / "server" / "main.py").read_text(encoding="utf-8")
        body = source.split("async def lifespan", 1)[1]

        assert "_assert_single_import_path()" in body.split("def ", 1)[0]


class TestLaunchTarget:
    """The container and the direct run must name the same module."""

    def test_dockerfile_launches_server_main_from_the_repo_root(self):
        text = (REPO / "docker" / "Dockerfile.server").read_text(encoding="utf-8")

        assert '"server.main:app"' in text, (
            "launching `main:app` from inside server/ puts the package "
            "directory on sys.path and reintroduces the second import path"
        )
        launch = text.rsplit("CMD", 1)[0]
        assert launch.rstrip().endswith("WORKDIR /app"), (
            "the working directory must be the repo root, not server/"
        )

    def test_direct_run_agrees_with_the_container(self):
        source = (REPO / "server" / "main.py").read_text(encoding="utf-8")

        assert '"server.main:app"' in source


class TestLauncherStartsTheServerCorrectly:
    """lablink.py must not recreate the shape the container no longer uses.

    It used to `cd server/` *and* put the repo root on PYTHONPATH, with a
    comment saying the server had mixed imports and needed both. Supplying
    both is precisely what let one file import under two names. The
    workaround was the defect, and it would now trip the startup guard.
    """

    def _launch_block(self) -> str:
        source = (REPO / "lablink.py").read_text(encoding="utf-8")
        return source.split("def launch_server", 1)[1].split("\n    def ", 1)[0]

    def test_runs_from_the_repo_root_as_a_module(self):
        block = self._launch_block()

        assert "-m server.main" in block, (
            "the launcher must start the server the way the container does"
        )

    def test_does_not_cd_into_the_package(self):
        block = self._launch_block()

        assert "cd {server_dir}" not in block, (
            "running from inside server/ puts the package directory on "
            "sys.path and reintroduces the second import path"
        )

    def test_does_not_set_pythonpath_alongside_it(self):
        """Both together are what create the duplication."""
        block = self._launch_block()

        assert "PYTHONPATH={lablink_root}" not in block
