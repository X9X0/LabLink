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


class TestRestartIsWiredUp:
    """The helper is useless if nothing calls it."""

    def _source(self):
        from pathlib import Path
        import client.main as m

        return Path(m.__file__).read_text()

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
