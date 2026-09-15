"""A Qt signal must never be wired to an undecorated coroutine function.

``clicked.connect(self.some_async_method)`` looks right and type-checks fine,
but calling a coroutine function only builds a coroutine object. Qt discards
the return value, so the body never runs: no request, no dialog, no error, no
log line. The button simply does nothing, which is the hardest kind of failure
to notice -- Disconnect shipped broken this way from v1.3.0, when the method
was made ``async`` and the decorator was not added.

This is checked across the whole client package rather than on one widget,
because the mistake is invisible at the call site and costs nothing to make
again.
"""

import ast
import pathlib

import pytest

CLIENT = pathlib.Path(__file__).resolve().parents[2] / "client"
SKIP = {"venv", ".venv", "site-packages", "__pycache__", "build", "dist"}


def _source_files():
    return [p for p in sorted(CLIENT.rglob("*.py")) if not SKIP & set(p.parts)]


def _is_async_decorator(node):
    source = ast.unparse(node)
    return "asyncSlot" in source or "asyncClose" in source


def _offenders(path):
    """Signal connections in `path` that point at a bare coroutine method."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    found = []
    for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
        coroutines, decorated = {}, set()
        for fn in cls.body:
            if isinstance(fn, ast.AsyncFunctionDef):
                coroutines[fn.name] = fn.lineno
                if any(_is_async_decorator(d) for d in fn.decorator_list):
                    decorated.add(fn.name)

        for node in ast.walk(cls):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "connect" and node.args):
                continue
            target = node.args[0]
            if (isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                    and target.attr in coroutines
                    and target.attr not in decorated):
                found.append(
                    f"{path.name}:{node.lineno} connects {cls.name}."
                    f"{target.attr}, an async def at line "
                    f"{coroutines[target.attr]} with no @qasync.asyncSlot()"
                )
    return found


@pytest.mark.parametrize(
    "path", _source_files(), ids=lambda p: str(p.relative_to(CLIENT))
)
def test_no_signal_connects_a_bare_coroutine(path):
    offenders = _offenders(path)
    assert not offenders, "\n".join(offenders)


def test_the_audit_can_actually_see_the_bug():
    """Guard the guard: a checker that cannot fail proves nothing."""
    import tempfile

    source = '''
import qasync

class Panel:
    def __init__(self):
        self.button.clicked.connect(self.do_thing)

    async def do_thing(self):
        pass
'''
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "panel.py"
        path.write_text(source, encoding="utf-8")
        assert len(_offenders(path)) == 1

        path.write_text(
            source.replace("    async def do_thing",
                           "    @qasync.asyncSlot()\n    async def do_thing"),
            encoding="utf-8",
        )
        assert _offenders(path) == []
