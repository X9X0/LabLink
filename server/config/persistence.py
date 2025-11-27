"""Configuration persistence for runtime settings."""

import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Path to persistent config file - use data directory instead of config directory
# to avoid permission issues and ensure it's in a writable location
DATA_DIR = Path("./data")
RUNTIME_CONFIG_FILE = DATA_DIR / "runtime_settings.json"


def save_discovery_settings(settings: Dict[str, Any]) -> None:
    """Save discovery settings to persistent configuration file.

    Args:
        settings: Dictionary of discovery settings to persist
    """
    try:
        # Ensure data directory exists
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        # Load existing config or create new one
        if RUNTIME_CONFIG_FILE.exists():
            with open(RUNTIME_CONFIG_FILE, "r") as f:
                config = json.load(f)
        else:
            config = {}

        # Update discovery settings
        if "discovery" not in config:
            config["discovery"] = {}

        config["discovery"].update(settings)

        # Write back to file
        with open(RUNTIME_CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)

        logger.info(f"Saved discovery settings to {RUNTIME_CONFIG_FILE}")

    except Exception as e:
        logger.error(f"Failed to save discovery settings: {e}")
        raise


def load_discovery_settings() -> Dict[str, Any]:
    """Load persisted discovery settings from configuration file.

    Returns:
        Dictionary of persisted discovery settings, or empty dict if none exist
    """
    try:
        if not RUNTIME_CONFIG_FILE.exists():
            logger.debug("No runtime config file found, using defaults")
            return {}

        with open(RUNTIME_CONFIG_FILE, "r") as f:
            config = json.load(f)

        discovery_settings = config.get("discovery", {})
        logger.info(f"Loaded {len(discovery_settings)} discovery settings from {RUNTIME_CONFIG_FILE}")
        return discovery_settings

    except Exception as e:
        logger.error(f"Failed to load discovery settings: {e}")
        return {}


def apply_persisted_settings(settings_obj) -> None:
    """Apply persisted settings to the global settings object.

    Args:
        settings_obj: The Settings object to update
    """
    try:
        discovery_settings = load_discovery_settings()

        if not discovery_settings:
            return

        # Apply discovery settings
        for key, value in discovery_settings.items():
            if hasattr(settings_obj, key):
                setattr(settings_obj, key, value)
                logger.debug(f"Applied persisted setting: {key} = {value}")

        logger.info("Applied persisted settings successfully")

    except Exception as e:
        logger.error(f"Failed to apply persisted settings: {e}")
