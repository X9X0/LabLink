"""
Encoding constraints on the Windows installer, which the README advertises as

    iwr -useb .../install-client.ps1 | iex

Piping the script to `iex` parses it as a string rather than loading it as a
file, and that route does not tolerate a UTF-8 BOM: the byte order mark fuses
with the leading '#' so PowerShell reads it as a command name, the param()
block stops being recognised, and the install dies on line 1 with

    The term '#' is not recognized as the name of a cmdlet...

Loading the identical bytes from disk works fine, so nothing here is visible
from running the installer normally -- the one-liner is the only thing that
breaks, and it breaks completely. The script therefore has to stay pure ASCII,
because the moment it needs a non-ASCII character it needs a BOM to survive
Windows PowerShell 5.1, which reads BOM-less UTF-8 as cp1252.

That is the whole reason install-client.ps1 draws its banners with '=' and '|'
rather than box-drawing characters.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Shipped PowerShell that a user may fetch and pipe straight to iex.
REMOTELY_EXECUTED = REPO_ROOT / "install-client.ps1"

#: Every PowerShell script in the repo. None of them need non-ASCII, and a BOM
#: is only ever needed to protect non-ASCII, so the pair travels together.
ALL_POWERSHELL = sorted(REPO_ROOT.glob("*.ps1")) + sorted(
    (REPO_ROOT / "scripts" / "windows").glob("*.ps1")
)

UTF8_BOM = b"\xef\xbb\xbf"


def test_installer_exists():
    assert REMOTELY_EXECUTED.is_file(), f"{REMOTELY_EXECUTED} is missing"


def test_installer_has_no_bom():
    """A BOM makes `iwr | iex` fail on line 1 while the file still runs."""
    head = REMOTELY_EXECUTED.read_bytes()[:3]
    assert head != UTF8_BOM, (
        "install-client.ps1 starts with a UTF-8 BOM. The file will still run, "
        "but the one-liner in the README dies immediately with \"The term '#' "
        "is not recognized\". Save it as ASCII or UTF-8 without BOM."
    )


def test_installer_is_pure_ascii():
    """Non-ASCII forces a BOM back, which breaks the one-liner again."""
    raw = REMOTELY_EXECUTED.read_bytes()
    offenders = {b for b in raw if b > 127}
    assert not offenders, (
        "install-client.ps1 contains non-ASCII bytes "
        f"({sorted(offenders)!r}). Windows PowerShell 5.1 reads BOM-less UTF-8 "
        "as cp1252, so non-ASCII here eventually forces a BOM back in, and the "
        "BOM breaks `iwr | iex`. Use ASCII for banners and box drawing."
    )


@pytest.mark.parametrize("script", ALL_POWERSHELL, ids=lambda p: p.name)
def test_no_powershell_script_has_a_bom(script):
    assert script.read_bytes()[:3] != UTF8_BOM, f"{script.name} has a UTF-8 BOM"


def test_readme_documents_the_one_liner():
    """The one-liner is the advertised path; keep the README and script in step."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "install-client.ps1 | iex" in readme, (
        "README no longer documents the one-liner install. If it was removed "
        "deliberately, these encoding constraints can be relaxed too."
    )
