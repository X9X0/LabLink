"""Importing a test module must not run a script.

Several files here are written to be run both as `python test_x.py` and under
pytest. Anything left at module level executes during *collection* — before
any test runs, and for every file pytest touches — which caused two problems
that looked nothing alike:

- A top-level `sys.exit()` in a dependency guard raised SystemExit during
  collection. pytest reports that as INTERNALERROR and aborts the entire
  session: `no tests ran`, not one file's worth. It also got *worse* with
  dependencies installed, because the module then executed further and
  reached a later exit.
- `create_default_profiles()` at module level wrote to the checked-in
  `profiles/` directory, so `pytest --collect-only` dirtied the working tree
  and those timestamps were committed by accident more than once.

Both are the same defect — a script body outside `if __name__ == "__main__":`
— so both are guarded here.
"""

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TEST_FILES = sorted(
    p for p in REPO.glob("tests/**/*.py")
    if p.name != "__init__.py"
)


def _is_main_guard(node):
    """`if __name__ == "__main__":` — pytest never enters this."""
    return (
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
    )


def _runs_on_import(tree):
    """Top-level nodes pytest executes when it imports the module.

    Function, async function and class bodies only run when called, and a
    __name__ guard is never entered — at any nesting depth, which is why this
    walks with an explicit stack rather than only checking the top level.
    """
    out = []
    stack = [(n, False) for n in reversed(tree.body)]
    while stack:
        node, guarded = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if _is_main_guard(node):
            guarded = True
        if not guarded:
            out.append(node)
        for child in ast.iter_child_nodes(node):
            stack.append((child, guarded))
    return out


@pytest.mark.parametrize("path", TEST_FILES, ids=lambda p: str(p.relative_to(REPO)))
class TestNoImportTimeSideEffects:
    def test_no_sys_exit_on_import(self, path):
        """A SystemExit during collection takes down the whole run."""
        tree = ast.parse(path.read_text(encoding="utf-8"))

        offenders = [
            node.lineno for node in _runs_on_import(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "exit"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "sys"
        ]

        assert not offenders, (
            f"sys.exit() runs at import on line(s) {offenders}. Move it inside "
            'if __name__ == "__main__": — under pytest this aborts the entire '
            "session with INTERNALERROR, not just this file."
        )

    def test_no_writes_to_the_repository_on_import(self, path):
        """Collection must not touch tracked files.

        Catches the known offender by name rather than trying to detect
        filesystem writes in general: create_default_profiles() rewrote
        profiles/*.json every time the suite was collected.
        """
        tree = ast.parse(path.read_text(encoding="utf-8"))

        offenders = []
        for node in _runs_on_import(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if name in {"create_default_profiles", "save_profile", "save_settings"}:
                    offenders.append(f"{name}() on line {node.lineno}")

        assert not offenders, (
            f"{'; '.join(offenders)} runs at import, which writes to the "
            "repository during collection. Move it inside "
            'if __name__ == "__main__":.'
        )
