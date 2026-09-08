"""File and console I/O must not depend on the process locale.

`open()` and `Path.read_text()` with no `encoding=` decode using the locale,
which is **cp1252 on a typical Windows install**. 43 markdown files in this
repository raise `UnicodeDecodeError` when read that way, `CHANGELOG.md` among
them -- and `scripts/bump_version.py` reads and rewrites that file.

The console side is the mirror image: a script printing non-ASCII to a cp1252
stdout raises `UnicodeEncodeError`. `bump_version.py --help` did, on a `→` in
its own help text.

Issue #192 records this being hit five separate times on one branch. These
checks make the sixth a failing test rather than a bug report.
"""

import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# tests/ and client/ were fixed earlier and are covered by their own suites;
# venv and node_modules are not ours.
SKIP_DIRS = {"venv", "node_modules", "__pycache__", ".git", "client", "tests",
             "build", "dist"}

# Binary handles have no encoding to declare.
BINARY_MARKERS = ("Image.open", "tarfile.open", "gzip.open", "zipfile",
                  '"rb"', "'rb'", '"wb"', "'wb'", '"ab"', "'ab'")

_READ_TEXT = re.compile(r"\.read_text\(\s*\)")
_OPEN_CALL = re.compile(r"(?<![.\w])open\(([^)]*)\)")


def _source_files():
    for path in sorted(REPO.rglob("*.py")):
        if set(path.relative_to(REPO).parts) & SKIP_DIRS:
            continue
        yield path


def test_no_locale_dependent_file_reads():
    offenders = []
    for path in _source_files():
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            stripped = line.strip()
            if stripped.startswith("#") or any(m in line for m in BINARY_MARKERS):
                continue
            if _READ_TEXT.search(stripped):
                offenders.append(f"{path.relative_to(REPO)}:{number}: {stripped[:70]}")
                continue
            match = _OPEN_CALL.search(stripped)
            if match and "encoding" not in match.group(1):
                offenders.append(f"{path.relative_to(REPO)}:{number}: {stripped[:70]}")

    assert not offenders, (
        "these decode with the process locale, which is cp1252 on Windows; "
        'pass encoding="utf-8":\n  ' + "\n  ".join(offenders)
    )


def _scripts_printing_non_ascii():
    """Runnable scripts with a non-ASCII literal in a print()."""
    for path in _source_files():
        source = path.read_text(encoding="utf-8")
        if "__main__" not in source and not path.name.startswith(
            ("verify_", "validate_")
        ):
            continue
        if any(
            line.strip().startswith("print(") and any(ord(c) > 127 for c in line)
            for line in source.splitlines()
        ):
            yield path


def test_scripts_printing_non_ascii_force_utf8_output():
    """Otherwise the first such print dies on a Windows console."""
    offenders = [
        str(path.relative_to(REPO))
        for path in _scripts_printing_non_ascii()
        if "reconfigure" not in path.read_text(encoding="utf-8")
    ]

    assert not offenders, (
        "these print non-ASCII but do not reconfigure stdout, so they raise "
        "UnicodeEncodeError on a cp1252 console:\n  " + "\n  ".join(offenders)
    )


class TestTheCheckItselfWorks:
    """A guard that cannot fail is decoration."""

    def test_it_flags_an_unencoded_read(self, tmp_path):
        sample = tmp_path / "bad.py"
        sample.write_text('data = open("x.txt").read()\n', encoding="utf-8")

        line = sample.read_text(encoding="utf-8").strip()
        match = _OPEN_CALL.search(line)

        assert match is not None
        assert "encoding" not in match.group(1)

    def test_it_accepts_an_encoded_read(self, tmp_path):
        sample = tmp_path / "good.py"
        sample.write_text(
            'data = open("x.txt", encoding="utf-8").read()\n', encoding="utf-8"
        )

        match = _OPEN_CALL.search(sample.read_text(encoding="utf-8").strip())

        assert "encoding" in match.group(1)

    def test_it_ignores_binary_handles(self):
        line = 'with tarfile.open(archive, "r") as tar:'

        assert any(marker in line for marker in BINARY_MARKERS)

    @pytest.mark.parametrize("path", ["CHANGELOG.md", "docs/BENCH_LOG.md"])
    def test_the_premise_holds(self, path):
        """These really are undecodable as cp1252 -- the reason for all this."""
        raw = (REPO / path).read_bytes()

        with pytest.raises(UnicodeDecodeError):
            raw.decode("cp1252")

        assert raw.decode("utf-8")
