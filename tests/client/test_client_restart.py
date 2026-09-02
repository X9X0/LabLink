"""The client must restart after it rewrites its own code.

Both the easter-egg branch selector and the client self-update check out
different code and then carry on in the same process. Python caches imported
modules in sys.modules, and MainWindow -- with the whole UI behind it -- is
imported at the top of client/main.py, before main() runs. So the files on
disk change and the running process does not notice.

The failure mode is nasty because it looks like success: the client reports
"Successfully checked out <branch>" and then keeps executing the old code.
That is exactly how a Windows user ended up hitting the bash-only image
builder while believing they were running the branch that replaced it.
"""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

pytest.importorskip("PyQt6")
pytest.importorskip("qasync")

from client.main import _restart_client  # noqa: E402


class TestRestartClient:
    def test_replaces_the_process_on_posix(self):
        """execv, so the restarted client keeps the same terminal and exit code."""
        argv = ["client/main.py", "--debug"]

        with patch.object(sys, "argv", argv), \
                patch.object(os, "name", "posix"), \
                patch.object(os, "execv") as execv:
            _restart_client()

        execv.assert_called_once()
        exe, passed = execv.call_args[0]
        assert exe == sys.executable
        assert passed == [sys.executable, "client/main.py", "--debug"]

    def test_spawns_and_exits_on_windows(self):
        """os.execv on Windows loses the console, so spawn a replacement."""
        with patch.object(sys, "argv", ["client/main.py"]), \
                patch.object(os, "name", "nt"), \
                patch("subprocess.Popen") as popen, \
                pytest.raises(SystemExit) as exit_info:
            _restart_client()

        popen.assert_called_once_with([sys.executable, "client/main.py"])
        assert exit_info.value.code == 0

    def test_easter_egg_flag_is_dropped(self):
        """Otherwise the branch dialog reappears on every single launch."""
        with patch.object(sys, "argv", ["client/main.py", "--easter-egg", "--debug"]), \
                patch.object(os, "name", "posix"), \
                patch.object(os, "execv") as execv:
            _restart_client(drop_easter_egg=True)

        _, passed = execv.call_args[0]
        assert "--easter-egg" not in passed
        assert "--debug" in passed, "unrelated flags must survive the restart"

    def test_flag_is_kept_when_not_asked_to_drop_it(self):
        """The self-update path has no dialog to suppress."""
        with patch.object(sys, "argv", ["client/main.py", "--easter-egg"]), \
                patch.object(os, "name", "posix"), \
                patch.object(os, "execv") as execv:
            _restart_client()

        _, passed = execv.call_args[0]
        assert "--easter-egg" in passed

    def test_does_not_return(self):
        """A restart that falls through would run the stale code anyway."""
        with patch.object(sys, "argv", ["client/main.py"]), \
                patch.object(os, "name", "nt"), \
                patch("subprocess.Popen"):
            with pytest.raises(SystemExit):
                _restart_client()


class TestBothInvocationsCanImportEverything:
    """`python client/main.py` and `python -m client.main` must both work.

    The tree is imported two ways -- `client.ui.*` in most places, but bare
    `ui.*` and `utils.*` in a few (pi_image_builder reaches the SD writer with
    `from ui.sd_card_writer import SDCardWriter`, and api/client.py imports
    `utils.websocket_manager`). Neither invocation puts both roots on sys.path
    by itself: running the file adds only client/, and `-m` adds only the cwd.

    main.py adds both. Getting it wrong breaks one invocation on the *lazily*
    imported paths only, so the client still starts and the damage shows up
    later, when someone opens a dialog.
    """

    BARE_IMPORTS = ["ui.sd_card_writer", "utils.websocket_manager"]
    PACKAGE_IMPORTS = ["client.ui.main_window", "client.ui.theme"]

    def _run(self, extra_paths, module):
        import subprocess
        import sys as _sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        code = (
            "import sys\n"
            + "".join(f"sys.path.insert(0, r'{p}')\n" for p in extra_paths)
            + f"import {module}\n"
            "print('OK')\n"
        )
        return subprocess.run([_sys.executable, "-c", code], cwd=str(root),
                              capture_output=True, text=True)

    @pytest.mark.parametrize("module", BARE_IMPORTS + PACKAGE_IMPORTS)
    def test_importable_with_the_paths_main_sets_up(self, module):
        """main.py puts both roots on sys.path, so every form resolves."""
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        result = self._run([str(root), str(root / "client")], module)

        assert "OK" in result.stdout, (
            f"{module} does not import with both roots on sys.path:\n"
            f"{result.stderr}"
        )

    def test_main_adds_both_roots(self):
        """The guard: main.py must not go back to adding only one."""
        from pathlib import Path

        source = (Path(__file__).resolve().parents[2]
                  / "client" / "main.py").read_text(encoding="utf-8")

        assert "_CLIENT_DIR.parent, _CLIENT_DIR" in source, (
            "main.py no longer adds both the repo root and client/ to sys.path; "
            "one of the two invocations will break on a lazily-imported module"
        )


class TestRestartIsWiredUp:
    """The helper is useless if nothing calls it."""

    def _source(self):
        from pathlib import Path
        import client.main as m

        return Path(m.__file__).read_text(encoding="utf-8")

    def test_easter_egg_checkout_restarts(self):
        source = self._source()
        after_checkout = source.split("if checkout_git_ref(selected_ref):", 1)[1]
        # ...before the else branch that reports failure
        success_branch = after_checkout.split("else:", 1)[0]

        assert "_restart_client(drop_easter_egg=True)" in success_branch

    def test_self_update_restarts(self):
        source = self._source()
        after_update = source.split("if perform_client_update(ref):", 1)[1]
        success_branch = after_update.split("else:", 1)[0]

        assert "_restart_client()" in success_branch
        assert success_branch.index("clear_update_flag()") < \
            success_branch.index("_restart_client()"), \
            "the update flag must be cleared first, or the restart loops"

    def test_main_window_is_imported_before_main_runs(self):
        """The reason a restart is needed at all.

        If this ever stops being true -- if the UI is imported lazily inside
        main() after the checkout -- the restart could be dropped. Until then
        it is load-bearing, and this records why.
        """
        source = self._source()

        assert source.index("from client.ui.main_window import MainWindow") < \
            source.index("def main():")


class TestGitOperationsUseTheCheckout:
    """git must run in the LabLink checkout, not the current directory.

    Launched from a desktop shortcut, a Start Menu entry, or as
    `python C:\\LabLink\\client\\main.py` from a home directory, every git
    command ran wherever the process happened to start. That silently
    targeted an unrelated repository or none at all: the branch list came
    back empty and checkouts failed, with nothing on screen to say why.
    """

    def test_repo_dir_is_the_checkout(self):
        from pathlib import Path

        from client.utils.git_operations import repo_dir

        root = Path(repo_dir())
        assert (root / "client").is_dir()
        assert (root / "VERSION").exists()

    def test_every_git_call_passes_cwd(self):
        """A missed one reintroduces the bug for that command alone."""
        import re
        from pathlib import Path

        import client.utils.git_operations as git_ops

        source = Path(git_ops.__file__).read_text(encoding="utf-8")
        calls = re.findall(r"subprocess\.run\((?:[^()]|\([^()]*\))*\)", source, re.S)

        assert calls, "no subprocess calls found - did the module change shape?"
        without_cwd = [c for c in calls if "cwd=" not in c]
        assert not without_cwd, f"git calls not pinned to the checkout: {without_cwd}"

    def test_git_resolves_the_checkout_from_an_unrelated_directory(
            self, tmp_path, monkeypatch):
        """The actual regression, exercised the way the bug happened.

        Deliberately not asserting on the current branch: CI checks out a
        detached HEAD, so `git branch --show-current` is legitimately empty
        there and the test would fail for a reason unrelated to the bug.
        The repository root answers the real question -- which repository did
        git operate on -- and is well defined whether or not a branch is
        checked out.
        """
        from pathlib import Path

        from client.utils.git_operations import get_git_root, repo_dir

        monkeypatch.chdir(tmp_path)  # somewhere that is not a git repo

        root = get_git_root()
        assert root, "git found no repository outside the checkout"
        assert Path(root).resolve() == Path(repo_dir()).resolve()

    def test_is_git_checkout_detects_the_clone(self):
        from client.utils.git_operations import is_git_checkout

        assert is_git_checkout() is True


class TestVersionInStatusBar:
    """The status bar must identify the client code that is running.

    It previously showed the connection and the *server* version, and nothing
    at all about the client -- so after switching branches there was no way to
    tell which code was executing. That is precisely the question the branch
    selector creates.
    """

    @pytest.fixture
    def window(self):
        app_mod = pytest.importorskip("PyQt6.QtWidgets")
        app = app_mod.QApplication.instance() or app_mod.QApplication([])

        from client.ui.main_window import MainWindow

        # Silence the background git lookup for the duration. It runs on a
        # worker thread started in __init__ and emits the *real* branch, which
        # lands during a later processEvents() and overwrites whatever the test
        # just set. That made these tests depend on which branch the checkout
        # happened to be on: they passed on a feature branch, where the real
        # branch is styled like the test's own non-main value, and failed the
        # moment they ran on main.
        with patch.object(MainWindow, "_get_git_branch", return_value=None):
            win = MainWindow()
        yield win, app
        win.close()

    def test_client_version_is_shown_immediately(self, window):
        """Without waiting on git, which can be slow or absent."""
        win, _ = window

        assert "LabLink" in win.version_label.text()
        assert win._client_version in win.version_label.text()

    def test_version_is_the_client_not_the_server(self, window):
        from pathlib import Path

        win, _ = window
        expected = (Path(__file__).parent.parent.parent / "VERSION").read_text(encoding="utf-8").strip()

        assert win._client_version == expected

    def test_branch_is_appended_when_the_lookup_returns(self, window):
        """The regression: this used to be posted with QTimer.singleShot from a
        worker thread, where it never fired, so the indicator never appeared."""
        win, app = window

        win.branch_detected.emit("some-branch (abc1234)")
        app.processEvents()

        assert "some-branch (abc1234)" in win.version_label.text()
        assert win._client_version in win.version_label.text()

    def test_main_is_shown_too(self, window):
        """It used to be hidden on main, leaving the common case blank."""
        win, app = window

        win.branch_detected.emit("main (abc1234)")
        app.processEvents()

        assert "main (abc1234)" in win.version_label.text()

    def test_a_feature_branch_is_highlighted(self, window):
        win, app = window

        win.branch_detected.emit("main (abc1234)")
        app.processEvents()
        on_main = win.version_label.styleSheet()

        win.branch_detected.emit("feature/x (abc1234)")
        app.processEvents()
        off_main = win.version_label.styleSheet()

        assert on_main != off_main, "a non-main branch should stand out"
        assert "bold" in off_main

    def test_the_signal_is_connected_before_the_thread_starts(self):
        """Connect after start and the emit can be missed entirely."""
        from pathlib import Path

        import client.ui.main_window as mw

        source = Path(mw.__file__).read_text(encoding="utf-8")
        setup = source.split("def _setup_status_bar", 1)[1].split("def ", 1)[0]

        assert setup.index("branch_detected.connect") < setup.index("threading.Thread")
