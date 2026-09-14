"""What instruments this server has seen, remembered across restarts.

The equipment list lived only in memory, so every container restart emptied
it -- and an upgrade restarts containers. The operator was then asked to
rediscover a bench they had already identified once.

That is worse than tedious. A 1685B does not answer ``*IDN?`` at all, so
discovery infers it from a USB serial bridge; two such bridges look alike, and
picking the wrong one means commanding a supply believing it is another.
Remembering what was already identified avoids repeating that guess.

Only identity is stored, never a connection. The ports stay shut until
somebody asks to connect, which is what makes this safe to load at boot on a
shared bench.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

#: Under /app/data, which is a named docker volume and therefore survives
#: "docker compose down", a rebuild, and an upgrade. Anything written outside
#: it goes away with the container, which is how the list was lost.
DEFAULT_PATH = Path("data") / "equipment_inventory.json"

#: Bump when the stored shape changes, so an old file is ignored rather than
#: half-read.
SCHEMA = 1


class EquipmentInventory:
    """A record of instruments this server has identified before."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else DEFAULT_PATH
        self._entries: Dict[str, dict] = {}
        self.load()

    # -- persistence ------------------------------------------------------

    def load(self) -> int:
        """Read the remembered instruments. Never raises: a missing or corrupt
        file means an empty bench, not a server that will not start."""
        self._entries = {}
        try:
            if not self.path.exists():
                return 0
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Could not read {self.path}: {e}")
            return 0

        if not isinstance(data, dict) or data.get("schema") != SCHEMA:
            logger.warning(f"Ignoring {self.path}: unrecognised schema")
            return 0

        for entry in data.get("equipment", []):
            equipment_id = entry.get("id")
            if equipment_id:
                self._entries[equipment_id] = entry

        logger.info(f"Remembered {len(self._entries)} instrument(s) from {self.path}")
        return len(self._entries)

    def save(self) -> bool:
        """Write the inventory out. Best effort: failing to remember must not
        take down a server that is otherwise working."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema": SCHEMA,
                "equipment": list(self._entries.values()),
            }
            # Via a temporary file, so a crash mid-write cannot leave a
            # half-written inventory that the next boot would discard.
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )
            temporary.replace(self.path)
            return True
        except OSError as e:
            logger.warning(f"Could not write {self.path}: {e}")
            return False

    # -- contents ---------------------------------------------------------

    def remember(self, info) -> None:
        """Record an instrument that has been identified.

        Args:
            info: an EquipmentInfo, or anything with the same attributes.
        """
        entry = {
            "id": getattr(info, "id", None),
            "type": _plain(getattr(info, "type", None)),
            "manufacturer": getattr(info, "manufacturer", "") or "",
            "model": getattr(info, "model", "") or "",
            "serial_number": getattr(info, "serial_number", None),
            "connection_type": _plain(getattr(info, "connection_type", None)),
            "resource_string": getattr(info, "resource_string", "") or "",
            "nickname": getattr(info, "nickname", None),
        }
        if not entry["id"]:
            return

        if self._entries.get(entry["id"]) == entry:
            return  # nothing changed, so nothing to write

        self._entries[entry["id"]] = entry
        self.save()

    def forget(self, equipment_id: str) -> None:
        """Drop an instrument, for when it is deliberately removed."""
        if self._entries.pop(equipment_id, None) is not None:
            self.save()

    def entries(self) -> List[dict]:
        return list(self._entries.values())

    def __contains__(self, equipment_id: str) -> bool:
        return equipment_id in self._entries

    def __len__(self) -> int:
        return len(self._entries)


def _plain(value):
    """Enum to its value, so the file stays readable and version-independent."""
    return getattr(value, "value", value)
