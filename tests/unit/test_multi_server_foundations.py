"""The pieces that let one client hold several benches at once.

Three things have to hold before the Equipment and Control tabs can span more
than one server:

- the registry can hand back a live client per server, and losing one server
  does not disturb the others;
- an instrument knows which server listed it, and two servers that mint the
  same equipment id stay distinguishable;
- each server's tokens are stored separately, or the second login silently
  overwrites the first and the next start offers one server's token to the
  other.
"""

import pathlib
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from client.models.equipment import Equipment  # noqa: E402
from client.utils.server_manager import ServerManager  # noqa: E402


@pytest.fixture
def manager():
    path = pathlib.Path(tempfile.mkdtemp()) / "servers.json"
    manager = ServerManager(config_path=path)
    manager.add_server("Lab Server", "10.10.0.51", 8000, 8000)
    manager.add_server("Bench 2", "10.10.0.56", 8000, 8000)
    return manager


class TestTheRegistryHoldsSeveralConnections:
    def test_both_servers_can_be_connected_at_once(self, manager):
        first, second = object(), object()
        manager.mark_connected("Lab Server", first)
        manager.mark_connected("Bench 2", second)

        assert manager.connected_clients() == {
            "Lab Server": first, "Bench 2": second,
        }

    def test_losing_one_server_leaves_the_other_alone(self, manager):
        first, second = object(), object()
        manager.mark_connected("Lab Server", first)
        manager.mark_connected("Bench 2", second)

        manager.mark_disconnected("Lab Server")

        assert manager.get_client("Lab Server") is None
        assert manager.get_client("Bench 2") is second
        assert list(manager.connected_clients()) == ["Bench 2"]

    def test_a_configured_but_unconnected_server_offers_no_client(self, manager):
        assert manager.get_client("Lab Server") is None
        assert manager.connected_clients() == {}

    def test_an_unknown_server_is_not_an_error(self, manager):
        """Equipment can outlive the server entry it was listed through."""
        assert manager.get_client("gone") is None

    def test_the_order_follows_the_configuration(self, manager):
        """A list that reshuffles as servers reconnect is hard to use."""
        manager.mark_connected("Bench 2", object())
        manager.mark_connected("Lab Server", object())

        assert list(manager.connected_clients()) == ["Lab Server", "Bench 2"]


class TestEquipmentKnowsItsServer:
    def _equipment(self, server_name):
        return Equipment.from_api_dict(
            {"id": "ps_36509eb5", "model": "1685B", "type": "power_supply"},
            server_name,
        )

    def test_the_same_id_on_two_servers_stays_distinguishable(self):
        first, second = self._equipment("Lab Server"), self._equipment("Bench 2")

        assert first.equipment_id == second.equipment_id
        assert first.key != second.key

    def test_the_key_names_both_halves(self):
        assert self._equipment("Lab Server").key == "Lab Server::ps_36509eb5"

    def test_equipment_with_no_server_still_works(self):
        """Single-server callers predate this and must keep working."""
        equipment = Equipment.from_api_dict({"id": "ps_1", "type": "power_supply"})

        assert equipment.server_name is None
        assert equipment.key.endswith("ps_1")


class TestTokensAreKeptPerServer:
    @pytest.fixture
    def storage(self, monkeypatch):
        """A TokenStorage backed by a dict, with no keyring and no QSettings."""
        from client.utils import token_storage as module

        monkeypatch.setattr(module, "_KEYRING_AVAILABLE", False)

        class _Settings:
            def __init__(self):
                self.data = {}

            def setValue(self, key, value):
                self.data[key] = value

            def value(self, key, default=None, type=None):
                return self.data.get(key, default)

            def remove(self, key):
                self.data.pop(key, None)

            def sync(self):
                pass

        store = module.TokenStorage.__new__(module.TokenStorage)
        store.settings = _Settings()
        return store

    def test_two_servers_keep_separate_tokens(self, storage):
        storage.save_tokens("access-A", "refresh-A", server="10.10.0.51:8000")
        storage.save_tokens("access-B", "refresh-B", server="10.10.0.56:8000")

        assert storage.load_tokens("10.10.0.51:8000") == ("access-A", "refresh-A")
        assert storage.load_tokens("10.10.0.56:8000") == ("access-B", "refresh-B")

    def test_clearing_one_server_leaves_the_other_signed_in(self, storage):
        storage.save_tokens("access-A", "refresh-A", server="10.10.0.51:8000")
        storage.save_tokens("access-B", "refresh-B", server="10.10.0.56:8000")

        storage.clear_tokens("10.10.0.51:8000")

        assert storage.load_tokens("10.10.0.51:8000") == (None, None)
        assert storage.has_tokens("10.10.0.56:8000")

    def test_an_unknown_server_has_no_tokens(self, storage):
        storage.save_tokens("access-A", "refresh-A", server="10.10.0.51:8000")

        assert not storage.has_tokens("10.10.0.99:8000")

    def test_an_existing_login_survives_the_upgrade(self, storage):
        """The pre-multi-server install has one unkeyed pair.

        Whichever server asks first is the one it was saved for, so it is
        adopted rather than dropped -- upgrading should not read as a logout.
        """
        storage.save_tokens("access-old", "refresh-old")  # unkeyed, as before

        assert storage.load_tokens("10.10.0.51:8000") == ("access-old", "refresh-old")

    def test_the_adopted_tokens_are_rewritten_under_the_server(self, storage):
        storage.save_tokens("access-old", "refresh-old")
        storage.load_tokens("10.10.0.51:8000")

        # Keyed now, and the unkeyed copy is gone, so a second server cannot
        # pick up the first server's credentials by the same route.
        assert storage._read_tokens("10.10.0.51:8000") == (
            "access-old", "refresh-old",
        )
        assert storage._read_tokens(None) == (None, None)
        assert storage.load_tokens("10.10.0.56:8000") == (None, None)
