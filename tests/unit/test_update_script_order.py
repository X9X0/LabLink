"""The update script must not take the bench down before it can replace it.

On 2026-09-20 a server update failed on a Pi and left it with no server at
all: the script ran ``docker compose down`` first and ``docker compose
build`` second, so a build that failed had already stopped the working
version. The operator got a dialog saying "check logs above for errors"
and a dead bench.

The build failed because ``--no-cache`` made every update re-download the
whole Debian package set, and BuildKit had lost outbound network on that
Pi -- the host and ordinary containers could still reach the mirror, but
build containers could not, so apt reported every package as "Unable to
locate". Restarting the docker daemon repaired it.

Three properties are asserted here, because each one on its own would have
turned that incident into a non-event:

* build before stopping, so a failed build costs nothing;
* keep the layer cache, so an update is seconds rather than minutes and
  does not depend on re-downloading an OS;
* fall back to the classic builder, so a BuildKit fault does not stop a
  bench being updated at all.

Read as text rather than executed: running it would need Docker, a git
checkout at /opt/lablink and root. What went wrong was the *order* of the
steps, and the order is visible in the source.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

SCRIPT = os.path.join(os.path.dirname(__file__), "../..", "lablink-update.sh")


@pytest.fixture(scope="module")
def script():
    with open(SCRIPT, encoding="utf-8") as handle:
        return handle.read()


def position(script, pattern):
    """Where a step happens, by line number."""
    match = re.search(pattern, script, re.MULTILINE)
    assert match, f"no {pattern!r} in the update script"
    return script[:match.start()].count("\n") + 1


class TestNothingIsStoppedUntilTheNewImageExists:
    def test_the_build_comes_before_the_teardown(self, script):
        """The incident, in one assertion."""
        build = position(script, r"^if docker compose build")
        down = position(script, r"^docker compose down")
        assert build < down, (
            "the script stops the running server before it knows the new one "
            "can be built; a failed build then leaves the bench with nothing")

    def test_a_failed_build_exits_before_stopping_anything(self, script):
        """Not just ordered -- it has to leave on the failure path."""
        after_build = script[script.index("if docker compose build"):]
        failure = after_build[:after_build.index("docker compose down")]
        assert "exit 1" in failure, (
            "the failure branch falls through to the teardown")

    def test_the_failure_message_says_the_old_version_is_still_up(self, script):
        """An operator reading it should know the bench is still serving."""
        assert re.search(r"previous version is still running", script), (
            "nothing tells the operator whether their bench is down")


class TestAnUpdateIsFast:
    def test_the_cache_is_used_by_default(self, script):
        """--no-cache re-downloaded an entire OS on every update."""
        default_build = re.search(r"^if docker compose build (.*)$", script,
                                  re.MULTILINE)
        assert default_build, "no default build command"
        assert "--no-cache" not in default_build.group(1), (
            "every update throws the layer cache away and refetches apt and "
            "pip, which is both slow and a network failure waiting to happen")

    def test_a_clean_build_is_still_available(self, script):
        """Keeping the capability, just not as the default."""
        assert "--clean" in script
        assert re.search(r'--clean".*BUILD_ARGS="--no-cache"', script, re.S), (
            "--clean does not actually reach docker as --no-cache")

    def test_clean_is_not_mistaken_for_a_git_ref(self, script):
        """Every unrecognised argument is taken as the ref to check out."""
        assert re.search(r'--clean\)\s*;;', script), (
            "--clean falls through to the *) branch and becomes the ref, so "
            "the script would try to check out a branch called --clean")


class TestABuildKitFaultDoesNotBlockTheBench:
    def test_there_is_a_fallback_to_the_classic_builder(self, script):
        assert "DOCKER_BUILDKIT=0" in script, (
            "a BuildKit network fault stops the bench being updated at all, "
            "though the classic builder works fine")

    def test_the_fallback_runs_only_after_buildkit_fails(self, script):
        """As an elif, not as the first thing tried: BuildKit is the
        better builder when it works."""
        assert re.search(
            r"^if docker compose build.*\n(?:.*\n)*?^elif DOCKER_BUILDKIT=0 ",
            script, re.MULTILINE), "the fallback is not wired as a fallback"

    def test_it_says_which_builder_it_used(self, script):
        """Silently succeeding by a different route hides a real fault."""
        assert "classic builder" in script
        assert "systemctl restart" in script, (
            "the operator is not told how to repair BuildKit properly")


class TestTheScriptIsStillValidShell:
    def test_bash_parses_it(self, script):
        """Fed on stdin, not by path: a Windows path with backslashes is
        not something Git Bash will open."""
        import shutil
        import subprocess

        if shutil.which("bash") is None:
            pytest.skip("no bash on this machine")

        # Bytes, not text. Text mode would encode the box-drawing banner
        # with the Windows default codec (which cannot represent it) and
        # would translate every \n to \r\n, which bash then rejects as a
        # syntax error. The file itself is LF in git; only this pipe was
        # mangling it.
        done = subprocess.run(["bash", "-n"], input=script.encode("utf-8"),
                              capture_output=True)
        assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
