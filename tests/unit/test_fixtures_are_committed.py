"""A data fixture the repository does not have is not a fixture.

tests/unit/data/rigol_documented_keywords.json is generated from the
Rigol programming manuals and read at import by
test_rigol_keywords_against_manuals. It passed locally all day and
failed the moment CI ran:

    ERROR tests/unit/test_rigol_keywords_against_manuals.py
      FileNotFoundError: .../tests/unit/data/rigol_documented_keywords.json

.gitignore has a blanket ``data/`` rule, meant for captured
measurements and scratch output. It matches a directory of that name
at any depth, so tests/unit/data/ fell under it. ``git add -A`` skipped
the file without a word, the commit looked clean, and 562 tests went
on reading a file that existed on one machine.

Existing on disk is not the same as being in the repository, and the
difference is invisible to every test that just opens the file. So
this asks git.
"""

import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

#: Files a test reads that must therefore be in the repository.
REQUIRED = [
    "tests/unit/data/rigol_documented_keywords.json",
]


def tracked(path):
    """Ask git whether it has this file, not whether the disk does."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "--error-unmatch", path],
            cwd=REPO, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("git is not available to ask")
    return out.returncode == 0


@pytest.mark.parametrize("path", REQUIRED)
def test_the_fixture_is_on_disk(path):
    assert os.path.exists(os.path.join(REPO, path)), (
        f"{path} is missing; regenerate it with "
        f"tools/regenerate_rigol_keyword_table.py")


@pytest.mark.parametrize("path", REQUIRED)
def test_the_fixture_is_in_the_repository(path):
    """The check that would have caught it.

    A fixture present on disk and absent from git passes every test
    that opens it, and fails the first time anybody else -- or CI --
    checks the branch out.
    """
    assert tracked(path), (
        f"{path} exists here but git does not have it. Check .gitignore: "
        f"a blanket rule like 'data/' matches directories at any depth, "
        f"and 'git add -A' skips ignored files without saying so.")


@pytest.mark.parametrize("path", REQUIRED)
def test_it_is_not_ignored(path):
    """Belt and braces: a file can be tracked and still ignored, which
    means the next person to regenerate it finds their change invisible
    to git add."""
    try:
        out = subprocess.run(
            ["git", "check-ignore", "-q", path],
            cwd=REPO, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("git is not available to ask")
    # check-ignore exits 0 when the path IS ignored.
    assert out.returncode != 0, (
        f"{path} is matched by a .gitignore rule, so a regenerated copy "
        f"would not be picked up by 'git add -A'")
