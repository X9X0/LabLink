"""An "update" must not quietly install an older client.

The update selectors offer tags and branches side by side. A branch moves with
the work; a tag does not. This repository's only tag, v2.0.0, sits well behind
main, so choosing it from the version list checked out a client 169 commits
older than the running one, said nothing, and came back as an older build. The
user had asked to update.

Going backwards on purpose is what Rollback is for. These cover the check that
makes the update path say what it is about to do first.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from client.utils.git_operations import compare_ref_to_head  # noqa: E402


def _git(stdout):
    """A completed subprocess carrying `stdout`."""
    result = MagicMock()
    result.stdout = stdout
    result.returncode = 0
    return result


class TestCompareRefToHead:
    """`git rev-list --left-right --count HEAD...ref` prints "behind ahead"."""

    def test_a_ref_behind_head_is_reported_as_behind(self):
        with patch("subprocess.run", side_effect=[_git(""), _git("169\t0\n")]):
            assert compare_ref_to_head("v2.0.0") == {
                "ahead": 0, "behind": 169, "same": False
            }

    def test_a_ref_ahead_of_head_is_reported_as_ahead(self):
        with patch("subprocess.run", side_effect=[_git(""), _git("0\t4\n")]):
            assert compare_ref_to_head("main") == {
                "ahead": 4, "behind": 0, "same": False
            }

    def test_the_same_commit_is_reported_as_same(self):
        with patch("subprocess.run", side_effect=[_git(""), _git("0\t0\n")]):
            assert compare_ref_to_head("main")["same"] is True

    def test_diverged_is_neither_purely_ahead_nor_behind(self):
        """A rebased branch: the guard must not call this a downgrade."""
        with patch("subprocess.run", side_effect=[_git(""), _git("3\t7\n")]):
            position = compare_ref_to_head("feature")
        assert position == {"ahead": 7, "behind": 3, "same": False}
        assert not (position["ahead"] == 0 and position["behind"] > 0)

    def test_it_fetches_before_comparing(self):
        """An unfetched tag cannot be compared, and a stale one lies."""
        with patch("subprocess.run", side_effect=[_git(""), _git("0\t0\n")]) as run:
            compare_ref_to_head("v2.0.0")

        first = run.call_args_list[0][0][0]
        assert first[:2] == ["git", "fetch"], f"did not fetch first: {first}"

    def test_an_unknown_ref_returns_none_rather_than_guessing(self):
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(
            128, "git", stderr="unknown revision"
        )):
            assert compare_ref_to_head("nope") is None

    def test_unparsable_output_returns_none(self):
        """None means "cannot tell", and the caller then asks nothing."""
        with patch("subprocess.run", side_effect=[_git(""), _git("garbage\n")]):
            assert compare_ref_to_head("main") is None

    def test_missing_git_returns_none(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            assert compare_ref_to_head("main") is None


class TestBranchHashes:
    """A branch name does not say which code it is.

    Two installs both "on main" can be a week apart, and when the picker sent
    one to a branch 30 commits behind, nothing on screen would have shown it.
    """

    def _for_each_ref(self, stdout):
        return patch("subprocess.run", return_value=_git(stdout))

    def test_a_remote_branch_is_listed_under_its_plain_name(self):
        from client.utils.git_operations import get_branch_hashes

        with self._for_each_ref("origin/main d2af428\n"):
            assert get_branch_hashes() == {"main": "d2af428"}

    def test_a_local_branch_wins_over_the_remote_of_the_same_name(self):
        """git checkout <name> resolves locally, which is what the updater
        does before it pulls."""
        from client.utils.git_operations import get_branch_hashes

        # refs/remotes/origin is asked for first, refs/heads second.
        with self._for_each_ref("origin/main aaaaaaa\nmain bbbbbbb\n"):
            assert get_branch_hashes()["main"] == "bbbbbbb"

    def test_head_pointers_are_not_branches(self):
        from client.utils.git_operations import get_branch_hashes

        with self._for_each_ref("origin/HEAD d2af428\nmain d2af428\n"):
            assert set(get_branch_hashes()) == {"main"}

    def test_a_bare_remote_ref_is_not_a_branch(self):
        """This repository carries a stray refs/remotes/origin."""
        from client.utils.git_operations import get_branch_hashes

        with self._for_each_ref("origin 231a4a3\nmain 231a4a3\n"):
            assert set(get_branch_hashes()) == {"main"}

    def test_malformed_lines_are_skipped_rather_than_crashing(self):
        from client.utils.git_operations import get_branch_hashes

        with self._for_each_ref("main d2af428\ngarbage\n\n"):
            assert get_branch_hashes() == {"main": "d2af428"}

    def test_it_asks_git_once_rather_than_once_per_branch(self):
        """This runs on the UI thread every time the list is refreshed."""
        from client.utils.git_operations import get_branch_hashes

        with patch("subprocess.run", return_value=_git("main d2af428\n")) as run:
            get_branch_hashes()

        assert run.call_count == 1
        assert "for-each-ref" in run.call_args[0][0]

    def test_git_being_unavailable_is_not_fatal(self):
        """Losing the hashes must not cost the branch list."""
        from client.utils.git_operations import get_branch_hashes

        with patch("subprocess.run", side_effect=FileNotFoundError()):
            assert get_branch_hashes() == {}


GUI = True
try:
    import pyqtgraph  # noqa: F401
    from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: F401
except ImportError:
    GUI = False


@pytest.mark.skipif(not GUI, reason="PyQt6 and pyqtgraph are required")
class TestTheUpdateButtonAsksFirst:
    """Read on the source: building SystemPanel to click through the dialogs
    would need a live server, and what matters here is that the branch exists
    and is reached before anything is marked for update."""

    @pytest.fixture
    def source(self):
        import inspect

        from client.ui.system_panel import SystemPanel

        return inspect.getsource(SystemPanel._update_client)

    def test_the_direction_is_checked(self, source):
        assert "compare_ref_to_head" in source

    def test_it_is_checked_before_marking_for_update(self, source):
        """Marking first would leave the flag set for a cancelled update."""
        assert source.index("compare_ref_to_head") < source.index("mark_for_update("), \
            "the downgrade check must come before anything is marked"

    def test_going_backwards_defaults_to_no(self, source):
        """The dangerous answer must not be one stray Enter away."""
        backwards = source.split('"This Is Older Than What You Are Running"', 1)[1]
        assert "QMessageBox.StandardButton.No," in backwards, \
            "no default button given, so Yes is one keypress away"

    def test_declining_returns_without_marking(self, source):
        after = source.split("if going_back != QMessageBox.StandardButton.Yes:", 1)[1]
        first_branch = after.split("# Confirm with user", 1)[0]
        assert "return" in first_branch
        assert "mark_for_update" not in first_branch

    def test_the_branch_picker_shows_the_hash(self):
        """Display only: the checkout is still given the bare branch name."""
        import inspect

        from client.ui.system_panel import SystemPanel

        picker = inspect.getsource(SystemPanel._refresh_branches)
        assert "get_branch_hashes" in picker
        assert "addItem(display_name, branch_name)" in picker, (
            "the hash must not leak into the value the checkout receives"
        )

    def test_an_unchanged_ref_is_reported_rather_than_reinstalled(self, source):
        assert "Already Up To Date" in source

    def test_an_undeterminable_position_does_not_block_the_update(self, source):
        """`compare_ref_to_head` returns None off a checkout or without git.

        The guard is an explanation, not a gate: it must not make the update
        button unusable where the comparison simply cannot be made.
        """
        assert "if position and" in source, \
            "the guard must be conditional on having a position at all"
