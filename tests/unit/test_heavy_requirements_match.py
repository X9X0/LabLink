"""server/requirements-heavy.txt is a subset of server/requirements.txt.

The heavy file exists so Docker can install numpy, scipy, pandas and
h5py in their own layer, and reuse it when anything else changes. That
only works while the two files agree: the full file is installed after
the heavy one, so a pin that disagrees would have pip replace what the
cached layer just installed -- silently undoing the saving, or worse,
running the server on a different version from the one the audit saw.

Keeping the full file whole is deliberate. pip-audit scans requirements
files by path (`-r server/requirements.txt` in the security job), so a
package moved *out* of that file would stop being audited. The heavy
file duplicates rather than removes, and this holds the duplicate
honest.
"""

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
FULL = ROOT / "server" / "requirements.txt"
HEAVY = ROOT / "server" / "requirements-heavy.txt"


def pins(path):
    """{name: pinned version} from a requirements file.

    Only exact `==` pins, which is all either of these files uses. A
    range in the heavy file would make "the same pin" meaningless.
    """
    found = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.match(r"^([A-Za-z0-9._-]+)\s*==\s*([A-Za-z0-9._+!-]+)$", line)
        if match:
            found[match.group(1).lower()] = match.group(2)
    return found


class TestTheTwoFilesAgree:
    def test_both_files_are_there(self):
        assert FULL.is_file(), FULL
        assert HEAVY.is_file(), HEAVY

    def test_the_heavy_file_is_not_empty(self):
        """An empty one would pass every other test here while quietly
        doing nothing for the build."""
        assert pins(HEAVY), "no pinned packages in requirements-heavy.txt"

    def test_every_heavy_package_is_in_the_full_file(self):
        missing = sorted(set(pins(HEAVY)) - set(pins(FULL)))
        assert not missing, (
            "these are installed by the heavy layer and then not named in "
            "requirements.txt, so pip-audit never sees them: %s" % missing)

    def test_the_pins_are_identical(self):
        heavy, full = pins(HEAVY), pins(FULL)
        disagree = {
            name: (heavy[name], full[name])
            for name in heavy
            if name in full and heavy[name] != full[name]
        }
        assert not disagree, (
            "the full file is installed after the heavy one, so these would "
            "be replaced right after the cached layer installed them "
            "(heavy, full): %s" % disagree)

    @pytest.mark.parametrize("package", ["numpy", "scipy", "pandas", "h5py"])
    def test_the_slow_ones_are_in_the_heavy_file(self, package):
        """The four that cost the build time. If one is dropped from
        here, a bump anywhere else goes back to reinstalling it."""
        assert package in pins(HEAVY), package

    def test_everything_pins_exactly(self):
        """A range in the heavy file cannot be checked against the full
        file, and would let the two drift apart."""
        loose = [
            line.split("#", 1)[0].strip()
            for line in HEAVY.read_text(encoding="utf-8").splitlines()
            if line.split("#", 1)[0].strip()
            and "==" not in line.split("#", 1)[0]
        ]
        assert not loose, "not an exact pin: %s" % loose


class TestTheDockerfileUsesIt:
    """A file nothing installs would pass everything above and save
    nothing."""

    def _dockerfile(self):
        return (ROOT / "docker" / "Dockerfile.server").read_text(
            encoding="utf-8")

    def test_the_heavy_file_is_installed(self):
        said = self._dockerfile()
        assert "requirements-heavy.txt" in said, (
            "the heavy file exists and the image never installs it")

    def test_it_is_installed_before_the_full_list(self):
        """The whole point: the heavy layer has to come first, or it is
        invalidated by the same changes it was meant to survive."""
        said = self._dockerfile()
        heavy = said.index("COPY server/requirements-heavy.txt")
        full = said.index("COPY server/requirements.txt")
        assert heavy < full, (
            "the heavy layer is copied after the full list, so any change "
            "to requirements.txt still invalidates it")

    def test_the_full_list_is_still_installed(self):
        """The heavy file is a subset. Installing only it would leave
        the server without most of its dependencies."""
        said = self._dockerfile()
        assert "-r requirements.txt" in said
