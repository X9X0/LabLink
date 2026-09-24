"""A dependency guard must not hide a broken project import.

The pattern across this suite is::

    try:
        from PyQt6.QtWidgets import QApplication
        GUI_AVAILABLE = True
    except ImportError:
        GUI_AVAILABLE = False

    pytestmark = pytest.mark.skipif(not GUI_AVAILABLE,
                                    reason="PyQt6 is required")

which is right, and was wrong in thirty files because the project's own
imports sat inside the same try. Then any mistake in them -- a moved
class, a renamed module, a typo -- was caught by ``except ImportError``
and reported as "PyQt6 is required". The file skipped, and the run was
green.

That is not hypothetical. While writing tests/gui/test_connect_all.py,
ConnectionStatus was imported from shared.models.equipment; it lives in
client.models.equipment. All fourteen tests skipped, the suite passed,
and it was only noticed because fourteen skips looked odd in the
output.

The dependency belongs in the guard. Everything else belongs after it,
under ``if <FLAG>:``, where a mistake is a collection error.
"""

import ast
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
PROJECT_ROOTS = {"client", "server", "shared"}


def _is_project_import(node):
    if isinstance(node, ast.ImportFrom):
        return bool(node.module) and node.module.split(".")[0] in PROJECT_ROOTS
    if isinstance(node, ast.Import):
        return any(a.name.split(".")[0] in PROJECT_ROOTS for a in node.names)
    return False


def _offenders(path):
    """Project imports sitting inside a module-level ImportError guard."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return []                       # a broken file is another test's job

    found = []
    for node in tree.body:
        if not isinstance(node, ast.Try):
            continue
        if not any(isinstance(h.type, ast.Name) and h.type.id == "ImportError"
                   for h in node.handlers):
            continue
        for stmt in node.body:
            if _is_project_import(stmt):
                found.append(f"line {stmt.lineno}: "
                             f"{getattr(stmt, 'module', None) or 'import'}")
    return found


def test_files():
    return sorted((REPO / "tests").rglob("test_*.py"))


@pytest.mark.parametrize("path", test_files(), ids=lambda p: p.name)
def test_no_project_import_hides_inside_a_dependency_guard(path):
    offenders = _offenders(path)
    assert not offenders, (
        f"{path.relative_to(REPO)} imports the project inside its "
        f"try/except ImportError, so a mistake in one of these is "
        f"reported as a missing dependency and the whole file skips "
        f"green:\n  " + "\n  ".join(offenders) +
        "\n\nMove them below the pytestmark, under `if <FLAG>:`.")


def test_the_check_would_notice_the_original_mistake():
    """Guarding the guard: a rule that matches nothing proves nothing."""
    import tempfile

    sample = (
        "import pytest\n"
        "try:\n"
        "    from PyQt6.QtWidgets import QApplication\n"
        "    from client.models.equipment import ConnectionStatus\n"
        "    GUI_AVAILABLE = True\n"
        "except ImportError:\n"
        "    GUI_AVAILABLE = False\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "test_sample.py"
        path.write_text(sample, encoding="utf-8")
        assert _offenders(path), "the check does not catch the real shape"


def test_the_check_accepts_the_corrected_shape():
    import tempfile

    sample = (
        "import pytest\n"
        "try:\n"
        "    from PyQt6.QtWidgets import QApplication\n"
        "    GUI_AVAILABLE = True\n"
        "except ImportError:\n"
        "    GUI_AVAILABLE = False\n"
        "\n"
        "if GUI_AVAILABLE:\n"
        "    from client.models.equipment import ConnectionStatus\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "test_sample.py"
        path.write_text(sample, encoding="utf-8")
        assert not _offenders(path), "the check rejects the correct shape"
