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
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def _server_subpackages() -> set:
    """Every directory under server/ that a bare import could name.

    Derived rather than listed. The hand-written version omitted `utils`, and
    `server/main.py` kept importing `utils.mdns` bare through the whole #197
    sweep -- invisible to this file, and skipped on the Pi because the import
    sits behind `not running_in_docker`. It crashed the native launch instead.

    No `__init__.py` requirement: `server/utils/` has none and imports anyway
    as a namespace package, which is precisely how it went unnoticed.
    """
    return {
        entry.name
        for entry in (REPO / "server").iterdir()
        if entry.is_dir()
        and not entry.name.startswith((".", "__"))
        and any(entry.glob("*.py"))
    }


def _client_subpackages() -> set:
    """The same, for client/ -- to know which names are ambiguous."""
    return {
        entry.name
        for entry in (REPO / "client").iterdir()
        if entry.is_dir()
        and not entry.name.startswith((".", "__"))
        and entry.name != "venv"
        and any(entry.glob("*.py"))
    }


LOCAL_PACKAGES = _server_subpackages()

# `api` and `utils` name a package in both trees, and `tests` names the suite
# itself as well as server/tests. Inside tests/, a bare `utils.data_buffer` is
# the client's, imported by client tests that put client/ on sys.path -- so the
# name alone cannot decide the spelling there. Server code has no such excuse,
# which is why only the tests/ scan narrows.
AMBIGUOUS_IN_TESTS = (LOCAL_PACKAGES & _client_subpackages()) | {"tests"}
TEST_TREE_PACKAGES = LOCAL_PACKAGES - AMBIGUOUS_IN_TESTS


class TestNoBareIntraServerImports:
    """Every import of the server's own modules must be spelled server.*."""

    def _offenders(self, root: Path, packages=None):
        packages = LOCAL_PACKAGES if packages is None else packages
        found = []
        for path in sorted(root.rglob("*.py")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if not stripped.startswith(("from ", "import ")):
                    continue
                for package in packages:
                    if stripped.startswith((f"from {package}.", f"from {package} ",
                                            f"import {package}.")):
                        found.append(f"{path.relative_to(REPO)}:{number}: {stripped}")
        return found

    def test_server_imports_itself_by_one_name(self):
        offenders = self._offenders(REPO / "server")

        assert not offenders, (
            "bare intra-server imports create a second module path:\n  "
            + "\n  ".join(offenders)
        )

    def test_tests_import_the_server_by_one_name(self):
        """A test importing bare re-creates the duplication inside the suite."""
        offenders = self._offenders(REPO / "tests", TEST_TREE_PACKAGES)

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
        # Narrowed like the import scan above: "utils.websocket_manager" in a
        # client test names the client's module, not the server's.
        pattern = re.compile(
            r"""['"](""" + "|".join(sorted(TEST_TREE_PACKAGES)) + r""")"""
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


# Every Dockerfile that builds the server, which is now one: the repo-root
# Dockerfile is gone and build_docker.sh builds this file, the same one
# docker-compose builds. It stays a list because the parametrised checks below
# are what caught the divergence when there were two, and a second Dockerfile
# arriving with nothing checking it is how #197 reached the Pi.
SERVER_DOCKERFILES = ["docker/Dockerfile.server"]


class TestLaunchTarget:
    """The container and the direct run must name the same module."""

    @pytest.mark.parametrize("dockerfile", SERVER_DOCKERFILES)
    def test_dockerfile_launches_server_main_from_the_repo_root(self, dockerfile):
        text = (REPO / dockerfile).read_text(encoding="utf-8")

        assert '"server.main:app"' in text, (
            f"{dockerfile}: launching `main:app` from inside server/ puts the "
            "package directory on sys.path and reintroduces the second import "
            "path"
        )
        launch = text.rsplit("CMD", 1)[0]
        assert launch.rstrip().endswith("WORKDIR /app"), (
            f"{dockerfile}: the working directory must be the repo root, not "
            "server/"
        )

    @pytest.mark.parametrize("dockerfile", SERVER_DOCKERFILES)
    def test_dockerfile_keeps_the_package_directory(self, dockerfile):
        """`COPY server/ .` flattens the package out of existence.

        The contents land in /app with no `server` directory above them, so
        `import server.main` cannot resolve at all and the container dies at
        startup -- before the guard in main.py ever runs.
        """
        text = (REPO / dockerfile).read_text(encoding="utf-8")

        for line in text.splitlines():
            stripped = line.strip()
            # The whole directory, not `COPY server/requirements.txt .`
            if not stripped.startswith("COPY server/ "):
                continue
            destination = stripped.split()[-1]
            assert destination.rstrip("/").endswith("/server"), (
                f"{dockerfile}: {stripped!r} copies the package's contents "
                f"into {destination}, leaving no `server` package to import"
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


# The shell scripts that start the server on a native (non-Docker) install.
# install-client.sh is deliberately absent: it launches client/main.py, which
# is a different entry point and not part of the server package.
SERVER_LAUNCH_SCRIPTS = ["start_server.sh", "install-server.sh"]


class TestShellLaunchersStartTheServerCorrectly:
    """The native install path must agree with the container.

    `cd server && python3 main.py` does not merely risk the duplicate shape --
    since every intra-server import is spelled server.*, running from inside
    the package means `import server.api` does not resolve at all and the
    server dies on its first import.
    """

    @pytest.mark.parametrize("script", SERVER_LAUNCH_SCRIPTS)
    def test_launches_the_module_not_the_file(self, script):
        text = (REPO / script).read_text(encoding="utf-8")

        assert "-m server.main" in text, (
            f"{script}: the server must be started as a module from the repo "
            "root, the way the container starts it"
        )

    @pytest.mark.parametrize("script", SERVER_LAUNCH_SCRIPTS)
    def test_does_not_run_main_py_directly(self, script):
        text = (REPO / script).read_text(encoding="utf-8")

        offenders = [
            line.strip() for line in text.splitlines()
            # Comments naming the old form are how the next reader learns why
            if not line.strip().startswith("#")
            and re.search(r"python3?\s+main\.py", line)
        ]

        assert not offenders, (
            f"{script}: {offenders} runs the file from inside the package; "
            "`import server.x` cannot resolve from there"
        )

    def test_systemd_unit_works_from_the_repo_root(self):
        """A unit file is the launcher that outlives the install script."""
        text = (REPO / "install-server.sh").read_text(encoding="utf-8")

        assert "WorkingDirectory=$LABLINK_DIR\n" in text, (
            "the unit must run from the repo root, not $LABLINK_DIR/server"
        )
        assert "ExecStart=$LABLINK_DIR/server/venv/bin/python -m server.main" in text
