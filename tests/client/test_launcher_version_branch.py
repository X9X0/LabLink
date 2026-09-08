"""The launcher must say which LabLink it is about to start (issue #191).

It showed nothing: the window was titled "LabLink Launcher", and `__version__`
was read from the VERSION file at import and then used by nothing at all.

The issue came out of a real debugging session -- a branch was checked out
through developer mode, the client was launched, and it still failed with an
error from the code path that branch replaces. Nothing on screen said which
code was running, so the only way to find out was to read the source.

These cover the launcher half. The client half landed with #190 and is what
this mirrors.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

pytest.importorskip("PyQt6")


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def launcher(qapp):
    """A launcher instance without running its startup checks."""
    import lablink

    window = lablink.LabLinkLauncher.__new__(lablink.LabLinkLauncher)
    return window


class TestVersionIsShown:
    def test_version_text_uses_the_version_file(self, launcher):
        import lablink

        text = lablink.LabLinkLauncher._version_text(launcher)

        assert lablink.__version__ in text
        assert text == f"LabLink {lablink.__version__}"

    def test_the_version_matches_the_version_file(self):
        import lablink

        assert lablink.__version__ == (REPO / "VERSION").read_text(
            encoding="utf-8"
        ).strip()

    def test_the_window_title_carries_it(self):
        """`__version__` was dead code before this; the title is one use."""
        source = (REPO / "lablink.py").read_text(encoding="utf-8")

        assert 'setWindowTitle(f"LabLink Launcher {__version__}")' in source


class TestBranchIsShown:
    """Delivered by signal, and shown for main as well."""

    def _label(self, launcher, branch_info):
        from PyQt6.QtWidgets import QLabel
        import lablink

        launcher.version_label = QLabel()
        lablink.LabLinkLauncher._show_branch(launcher, branch_info)
        return launcher.version_label

    def test_branch_and_commit_are_appended(self, launcher):
        label = self._label(launcher, "feat/thing (abc1234)")

        assert "feat/thing (abc1234)" in label.text()
        assert "LabLink" in label.text()

    def test_a_branch_off_main_is_highlighted(self, launcher):
        label = self._label(launcher, "feat/thing (abc1234)")

        assert "27ae60" in label.styleSheet()
        assert "bold" in label.styleSheet()

    def test_main_is_shown_too_just_greyed(self, launcher):
        """Hiding it on main is what the client used to do, so the common
        case said nothing at all about what was running."""
        label = self._label(launcher, "main (147f38d)")

        assert "main (147f38d)" in label.text()
        assert "gray" in label.styleSheet()

    def test_the_tooltip_says_what_it_means(self, launcher):
        label = self._label(launcher, "feat/thing (abc1234)")

        assert "feat/thing" in label.toolTip()
        assert "launcher" in label.toolTip().lower()


class TestTheLookupIsSafe:
    """It runs off the GUI thread and must not raise on the way."""

    def test_it_emits_branch_and_commit(self, qapp):
        import lablink

        worker = lablink.GitBranchWorker()
        seen = []
        worker.detected.connect(seen.append)

        with patch("client.utils.git_operations.is_git_checkout", return_value=True), \
             patch("client.utils.git_operations.get_current_git_branch", return_value="feat/x"), \
             patch("client.utils.git_operations.get_current_commit_hash", return_value="deadbee"):
            worker.run()

        assert seen == ["feat/x (deadbee)"]

    def test_it_says_nothing_without_a_checkout(self, qapp):
        """A ZIP download or packaged install has no .git; version still shows."""
        import lablink

        worker = lablink.GitBranchWorker()
        seen = []
        worker.detected.connect(seen.append)

        with patch("client.utils.git_operations.is_git_checkout", return_value=False):
            worker.run()

        assert seen == []

    def test_a_detached_head_is_not_reported_as_a_branch(self, qapp):
        import lablink

        worker = lablink.GitBranchWorker()
        seen = []
        worker.detected.connect(seen.append)

        with patch("client.utils.git_operations.is_git_checkout", return_value=True), \
             patch("client.utils.git_operations.get_current_git_branch", return_value=None):
            worker.run()

        assert seen == []

    def test_the_branch_alone_is_enough_without_a_hash(self, qapp):
        import lablink

        worker = lablink.GitBranchWorker()
        seen = []
        worker.detected.connect(seen.append)

        with patch("client.utils.git_operations.is_git_checkout", return_value=True), \
             patch("client.utils.git_operations.get_current_git_branch", return_value="feat/x"), \
             patch("client.utils.git_operations.get_current_commit_hash", return_value=None):
            worker.run()

        assert seen == ["feat/x"]

    def test_delivery_is_by_signal_not_timer(self):
        """A QTimer created off the GUI thread never fires -- issue #191 notes
        that as the reason the client's indicator never appeared."""
        source = (REPO / "lablink.py").read_text(encoding="utf-8")
        worker = source.split("class GitBranchWorker", 1)[1].split("\nclass ", 1)[0]

        assert "pyqtSignal" in worker
        assert "singleShot" not in worker


class TestCommitHashHelper:
    """The helper added for this, in git_operations rather than shelled out."""

    def test_it_reports_this_checkout(self):
        from client.utils.git_operations import get_current_commit_hash

        short = get_current_commit_hash()

        assert short and len(short) >= 7
        assert all(c in "0123456789abcdef" for c in short)

    def test_full_and_short_agree(self):
        from client.utils.git_operations import get_current_commit_hash

        short = get_current_commit_hash(short=True)
        full = get_current_commit_hash(short=False)

        assert full.startswith(short)
        assert len(full) == 40

    def test_it_runs_in_the_repo_not_the_working_directory(self):
        """Every git call here used to use the process cwd; see repo_dir()."""
        source = (REPO / "client" / "utils" / "git_operations.py").read_text(
            encoding="utf-8"
        )
        body = source.split("def get_current_commit_hash", 1)[1].split("\ndef ", 1)[0]

        assert "cwd=repo_dir()" in body
