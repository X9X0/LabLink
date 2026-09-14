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


def _git(stdout, returncode=0):
    """A completed subprocess carrying `stdout`."""
    result = MagicMock()
    result.stdout = stdout
    result.returncode = returncode
    return result


def _compare_calls(counts, remote_exists=True):
    """The three calls compare_ref_to_head makes, in order.

    fetch, then a rev-parse probing for origin/<ref>, then the rev-list. The
    probe is what decides whether the comparison targets origin's tip or the
    ref as given.
    """
    probe = _git("abc123\n") if remote_exists else _git("", returncode=1)
    return [_git(""), probe, _git(counts)]


class TestCompareRefToHead:
    """`git rev-list --left-right --count HEAD...ref` prints "behind ahead"."""

    def test_a_ref_behind_head_is_reported_as_behind(self):
        with patch("subprocess.run", side_effect=_compare_calls("169\t0\n")):
            assert compare_ref_to_head("v2.0.0") == {
                "ahead": 0, "behind": 169, "same": False
            }

    def test_a_ref_ahead_of_head_is_reported_as_ahead(self):
        with patch("subprocess.run", side_effect=_compare_calls("0\t4\n")):
            assert compare_ref_to_head("main") == {
                "ahead": 4, "behind": 0, "same": False
            }

    def test_the_same_commit_is_reported_as_same(self):
        with patch("subprocess.run", side_effect=_compare_calls("0\t0\n")):
            assert compare_ref_to_head("main")["same"] is True

    def test_diverged_is_neither_purely_ahead_nor_behind(self):
        """A rebased branch: the guard must not call this a downgrade."""
        with patch("subprocess.run", side_effect=_compare_calls("3\t7\n")):
            position = compare_ref_to_head("feature")
        assert position == {"ahead": 7, "behind": 3, "same": False}
        assert not (position["ahead"] == 0 and position["behind"] > 0)

    def test_it_fetches_before_comparing(self):
        """An unfetched tag cannot be compared, and a stale one lies."""
        with patch("subprocess.run", side_effect=_compare_calls("0\t0\n")) as run:
            compare_ref_to_head("v2.0.0")

        first = run.call_args_list[0][0][0]
        assert first[:2] == ["git", "fetch"], f"did not fetch first: {first}"

    def test_a_branch_is_compared_against_the_remote_not_the_local_ref(self):
        """The regression that blocked a real update.

        Fetching moves origin/<branch>; it never moves the local branch
        ref. Comparing against the local one therefore reported "already
        up to date" while origin was a commit ahead, and the guard then
        refused the update it exists to explain.
        """
        from client.utils.git_operations import compare_ref_to_head

        with patch("subprocess.run", side_effect=_compare_calls("0\t1\n")) as run:
            assert compare_ref_to_head("main")["ahead"] == 1

        rev_list = run.call_args_list[-1][0][0]
        assert "HEAD...origin/main" in rev_list, rev_list

    def test_a_tag_is_compared_against_itself(self):
        """A tag has no remote-tracking ref to fall back to."""
        from client.utils.git_operations import compare_ref_to_head

        with patch("subprocess.run",
                   side_effect=_compare_calls("177\t0\n", remote_exists=False)) as run:
            assert compare_ref_to_head("v2.0.0")["behind"] == 177

        rev_list = run.call_args_list[-1][0][0]
        assert "HEAD...v2.0.0" in rev_list, rev_list

    def test_an_unknown_ref_returns_none_rather_than_guessing(self):
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(
            128, "git", stderr="unknown revision"
        )):
            assert compare_ref_to_head("nope") is None

    def test_unparsable_output_returns_none(self):
        """None means "cannot tell", and the caller then asks nothing."""
        with patch("subprocess.run", side_effect=_compare_calls("garbage\n")):
            assert compare_ref_to_head("main") is None

    def test_missing_git_returns_none(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            assert compare_ref_to_head("main") is None


class TestTheVersionListCanSeeNewReleases:
    """"git tag" lists only what this clone already knows.

    Nothing in the version picker fetched, so a release cut five minutes ago
    could never appear however many times Refresh Versions was pressed -- and
    the log line said "Fetching git tags" while it did no such thing.
    """

    def test_it_does_not_fetch_by_default(self):
        """It is called on a timer as well as by the button."""
        from client.utils.git_operations import get_git_tags

        with patch("subprocess.run", return_value=_git("v2.1.2" + chr(10))) as run:
            get_git_tags()

        assert run.call_count == 1
        assert "fetch" not in run.call_args[0][0]

    def test_it_fetches_when_asked(self):
        from client.utils.git_operations import get_git_tags

        with patch("subprocess.run", side_effect=[_git(""), _git("v2.1.2" + chr(10))]) as run:
            tags = get_git_tags(fetch=True)

        first = run.call_args_list[0][0][0]
        assert first[:2] == ["git", "fetch"], first
        assert "--tags" in first
        assert tags == ["v2.1.2"]

    def test_the_refresh_button_asks_for_a_fetch(self):
        """Otherwise pressing it can only ever redisplay the same list."""
        import inspect

        from client.ui.system_panel import SystemPanel

        body = inspect.getsource(SystemPanel._populate_versions)
        assert "get_git_tags(fetch=True)" in body


class TestTheSshHostComesFromTheConnection:
    """The client already knows which machine it is talking to.

    Retyping the address invites a typo that points a rebuild at the wrong
    Pi. Only the SSH user is unknown, so that is remembered per server.
    """

    def test_the_source_reads_the_connection(self):
        import inspect

        from client.ui.system_panel import SystemPanel

        body = inspect.getsource(SystemPanel._prefill_ssh_from_connection)
        assert 'getattr(self.client, "host", None)' in body

    def test_it_never_overwrites_what_was_typed(self):
        """Whatever the user put there wins."""
        import inspect

        from client.ui.system_panel import SystemPanel

        body = inspect.getsource(SystemPanel._prefill_ssh_from_connection)
        guard = body.index("if self.ssh_host_input.text().strip():")
        setter = body.index("self.ssh_host_input.setText")
        assert guard < setter, "it must bail out before writing"

    def test_the_user_is_remembered_only_on_success(self):
        """Storing a user that failed to connect would be worse than blank."""
        import inspect

        from client.ui.system_panel import SystemPanel

        body = inspect.getsource(SystemPanel._update_remote_server)
        remembered = body.index("_remember_ssh_user")
        failed = body.index("Remote Update Failed")
        assert remembered < failed, "it is being remembered on the failure path"

    def test_remembering_cannot_fail_the_update(self):
        import inspect

        from client.ui.system_panel import SystemPanel

        body = inspect.getsource(SystemPanel._remember_ssh_user)
        assert "except Exception" in body


class TestPasswordlessSshIsSetUpForYou:
    """A user who has never made an SSH key must still be able to update a Pi.

    The update runs with output captured, so a password prompt can never be
    answered and would hang -- which made key access mandatory. Leaving the
    user to arrange that works only for people who already know how; everyone
    else met "Permission denied" with nothing to do about it.
    """

    def test_a_bare_host_is_rejected_with_an_explanation(self):
        """The remote username cannot be guessed from the API connection."""
        from client.utils.ssh_access import split_host

        assert split_host("192.168.91.191") == (None, "192.168.91.191")
        assert split_host("admin@192.168.91.191") == ("admin", "192.168.91.191")

    def test_the_key_is_ed25519(self):
        """A Pi on current OpenSSH refuses SHA-1 ssh-rsa outright, which is a
        common reason key auth fails for no visible reason."""
        from client.utils.ssh_access import KEY_PATH

        assert KEY_PATH.name == "id_ed25519"

    def test_the_password_is_never_stored(self):
        """It installs a key; it does not save a credential."""
        import inspect

        from client.utils import ssh_access

        source = inspect.getsource(ssh_access)
        for leak in ("json.dump", "keyring", "QSettings", "write_text(password"):
            assert leak not in source, f"{leak} suggests the password is kept"

    def test_installing_is_idempotent(self):
        """Running it twice must not append the key twice."""
        import inspect

        from client.utils.ssh_access import install_public_key

        assert "grep -qxF" in inspect.getsource(install_public_key)

    def test_the_update_checks_access_before_running(self):
        import inspect

        from client.ui.system_panel import SystemPanel

        body = inspect.getsource(SystemPanel._update_remote_server)
        checked = body.index("_ensure_passwordless_ssh")
        ran = body.index("update_remote_server(ssh_host")
        assert checked < ran, "it runs the update before checking it can connect"

    def test_the_deploy_wizard_leaves_a_reachable_server(self):
        """It has the password at that moment, so the key costs nothing then."""
        import inspect

        from client.ui import ssh_deploy_wizard

        assert "public_key_text" in inspect.getsource(ssh_deploy_wizard)


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

    def test_the_remote_wins_over_a_local_branch_of_the_same_name(self):
        """The hash shown is the destination, not where you are.

        Selecting an entry checks the branch out and pulls, so origin's
        tip is what you land on, and the status bar already says where
        you are. This was first documented the other way round, and the
        test passed only because it fed the mock in the order that suited
        the claim: git sorts for-each-ref by refname, so refs/heads always
        comes first and the remote always won regardless.
        """
        from client.utils.git_operations import get_branch_hashes

        # As git actually prints it: refs/heads sorts before refs/remotes.
        with self._for_each_ref("main bbbbbbb\norigin/main aaaaaaa\n"):
            assert get_branch_hashes()["main"] == "aaaaaaa"

    def test_the_preference_does_not_depend_on_the_order_git_prints(self):
        """Whichever way the lines arrive, the remote is the answer."""
        from client.utils.git_operations import get_branch_hashes

        with self._for_each_ref("origin/main aaaaaaa\nmain bbbbbbb\n"):
            assert get_branch_hashes()["main"] == "aaaaaaa"

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


class TestDescribeHead:
    """Checking out a tag detaches HEAD and `git branch --show-current`
    then prints nothing.

    Both server updates check a ref out in this very clone, so that is
    exactly when the status bar and the picker went blank -- at the moment
    "which code is this?" was most worth asking.
    """

    def test_a_branch_is_reported_by_name(self):
        from client.utils.git_operations import describe_head

        with patch("subprocess.run", return_value=_git("main" + chr(10))):
            assert describe_head() == "main"

    def test_a_detached_head_names_the_tag(self):
        from client.utils.git_operations import describe_head

        with patch("subprocess.run", side_effect=[
            _git(""), _git("v2.1.0" + chr(10)),
        ]):
            assert describe_head() == "detached at v2.1.0"

    def test_a_detached_head_with_no_tag_names_the_commit(self):
        from client.utils.git_operations import describe_head

        with patch("subprocess.run", side_effect=[
            _git(""), _git(""), _git("156bf31" + chr(10)),
        ]):
            assert describe_head() == "detached at 156bf31"

    def test_it_never_returns_an_empty_answer(self):
        """Blank is what the old code produced, and it said nothing."""
        from client.utils.git_operations import describe_head

        with patch("subprocess.run", side_effect=FileNotFoundError()):
            assert describe_head() is None


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

    def test_the_local_server_update_checks_the_direction(self):
        """It checks a ref out in the clone the client runs from, so an older
        ref would downgrade the running client as a side effect."""
        import inspect

        from client.ui.system_panel import SystemPanel

        body = inspect.getsource(SystemPanel._update_local_server)
        assert "compare_ref_to_head" in body
        assert "StandardButton.No," in body, "no default button on the warning"
        assert "this clone" in body, "it must say the checkout is shared"

    def test_the_remote_server_update_leaves_the_local_clone_alone(self):
        """Updating a Pi has no business moving this machine's checkout.

        It used to check the ref out locally and then run docker compose on
        the remote in a directory named by the *local* git root -- so it
        moved this machine's code and then told a Pi to "cd C:/LabLinkTest".
        Nothing ever updated the remote's own code.
        """
        import inspect

        from client.ui.system_panel import SystemPanel

        body = inspect.getsource(SystemPanel._update_remote_server)
        assert "checkout_git_ref" not in body, (
            "the remote update is checking something out locally again"
        )
        assert "get_git_root" not in body, (
            "the local git root is being sent to the remote again"
        )
        assert "update_remote_server" in body, (
            "it should drive the remote's own lablink-update.sh"
        )

    def test_the_remote_update_names_a_remote_path(self):
        """A path on the Pi, not whatever this machine calls its checkout."""
        import inspect

        from client.ui.system_panel import SystemPanel

        body = inspect.getsource(SystemPanel._update_remote_server)
        assert "remote_path_input" in body
        assert "/opt/lablink" in body, "there should be a sensible default"

    def test_an_unchanged_ref_is_reported_rather_than_reinstalled(self, source):
        assert "Already Up To Date" in source

    def test_an_undeterminable_position_does_not_block_the_update(self, source):
        """`compare_ref_to_head` returns None off a checkout or without git.

        The guard is an explanation, not a gate: it must not make the update
        button unusable where the comparison simply cannot be made.
        """
        assert "if position and" in source, \
            "the guard must be conditional on having a position at all"
