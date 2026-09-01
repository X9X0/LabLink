"""
Tests for the SSH deploy wizard's known_hosts / TOFU handling.

paramiko brackets the host and appends the port for anything other than 22
("[host]:2222"), and looks entries up that way on reconnect. Getting this
wrong is invisible on the default port and breaks completely on any other:
the "accept this host key" dialog becomes unreachable, and an accepted key is
never matched again.

These tests need no network - they exercise the naming and lookup logic
directly.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

paramiko = pytest.importorskip("paramiko")

from client.ui.ssh_deploy_wizard import (  # noqa: E402
    _LabLinkHostKeyPolicy,
    _known_hosts_name,
    _save_host_key,
)


@pytest.fixture(scope="module")
def host_key():
    return paramiko.RSAKey.generate(2048)


class TestKnownHostsName:
    """The entry name must match what paramiko looks up."""

    def test_default_port_is_bare_hostname(self):
        assert _known_hosts_name("pi.local", 22) == "pi.local"

    def test_non_standard_port_is_bracketed(self):
        assert _known_hosts_name("pi.local", 2222) == "[pi.local]:2222"

    def test_port_defaults_to_22(self):
        assert _known_hosts_name("pi.local") == "pi.local"

    def test_ip_addresses_are_handled(self):
        assert _known_hosts_name("192.168.1.50", 22) == "192.168.1.50"
        assert _known_hosts_name("192.168.1.50", 2222) == "[192.168.1.50]:2222"


class TestSaveHostKey:
    def test_saves_bare_name_on_default_port(self, tmp_path, host_key):
        kh = tmp_path / "known_hosts"

        _save_host_key("pi.local", host_key, str(kh), port=22)

        assert kh.read_text().split()[0] == "pi.local"

    def test_saves_bracketed_name_on_other_port(self, tmp_path, host_key):
        kh = tmp_path / "known_hosts"

        _save_host_key("pi.local", host_key, str(kh), port=2222)

        assert kh.read_text().split()[0] == "[pi.local]:2222"

    def test_entry_is_loadable_by_paramiko(self, tmp_path, host_key):
        """The regression that matters: paramiko must find what we wrote."""
        kh = tmp_path / "known_hosts"
        _save_host_key("pi.local", host_key, str(kh), port=2222)

        client = paramiko.SSHClient()
        client.load_host_keys(str(kh))

        # paramiko looks up the bracketed form for a non-standard port
        assert client.get_host_keys().lookup("[pi.local]:2222") is not None

    def test_does_not_duplicate_entries(self, tmp_path, host_key):
        kh = tmp_path / "known_hosts"

        _save_host_key("pi.local", host_key, str(kh), port=2222)
        _save_host_key("pi.local", host_key, str(kh), port=2222)

        assert len(kh.read_text().strip().splitlines()) == 1


class TestTofuPolicyLookup:
    """get_unknown_key must resolve whichever form the caller has."""

    def test_rejects_unknown_host(self, host_key):
        policy = _LabLinkHostKeyPolicy()

        with pytest.raises(paramiko.ssh_exception.SSHException, match="Unknown host key"):
            policy.missing_host_key(None, "pi.local", host_key)

    def test_lookup_by_bare_host_after_bracketed_store(self, host_key):
        """The wizard stores what paramiko passed but looks up the bare host.

        On a non-standard port those differ, and the accept-host-key dialog
        was unreachable because this returned None.
        """
        policy = _LabLinkHostKeyPolicy()
        with pytest.raises(paramiko.ssh_exception.SSHException):
            policy.missing_host_key(None, "[pi.local]:2222", host_key)

        assert policy.get_unknown_key("pi.local") is host_key

    def test_lookup_by_bracketed_form_also_works(self, host_key):
        policy = _LabLinkHostKeyPolicy()
        with pytest.raises(paramiko.ssh_exception.SSHException):
            policy.missing_host_key(None, "[pi.local]:2222", host_key)

        assert policy.get_unknown_key("[pi.local]:2222") is host_key

    def test_default_port_lookup_unaffected(self, host_key):
        policy = _LabLinkHostKeyPolicy()
        with pytest.raises(paramiko.ssh_exception.SSHException):
            policy.missing_host_key(None, "pi.local", host_key)

        assert policy.get_unknown_key("pi.local") is host_key

    def test_unknown_hostname_returns_none(self, host_key):
        policy = _LabLinkHostKeyPolicy()

        assert policy.get_unknown_key("never-seen.local") is None
