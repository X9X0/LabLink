"""Client self-update utilities."""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Flag file location (in project root)
UPDATE_FLAG_FILE = Path(__file__).parent.parent.parent / ".client_update"


def mark_for_update(ref: str, mode: str = "stable") -> bool:
    """Mark the client for update on next restart.

    Creates a flag file with the target branch/tag. On next startup,
    the launcher will detect this and perform the update.

    Args:
        ref: Git reference (tag or branch) to update to
        mode: Update mode ("stable" or "development")

    Returns:
        True if flag file was created successfully
    """
    try:
        flag_data = {
            "ref": ref,
            "mode": mode
        }

        with open(UPDATE_FLAG_FILE, "w") as f:
            json.dump(flag_data, f, indent=2)

        logger.info(f"Marked client for update to {ref} ({mode} mode)")
        return True

    except Exception as e:
        logger.error(f"Failed to create update flag file: {e}")
        return False


def check_update_flag() -> Optional[dict]:
    """Check if client is marked for update.

    Returns:
        Dict with 'ref' and 'mode' if update is pending, None otherwise
    """
    try:
        if UPDATE_FLAG_FILE.exists():
            with open(UPDATE_FLAG_FILE, "r") as f:
                data = json.load(f)

            logger.info(f"Found update flag: {data}")
            return data

        return None

    except Exception as e:
        logger.error(f"Failed to read update flag file: {e}")
        return None


def clear_update_flag() -> bool:
    """Clear the update flag after update is complete.

    Returns:
        True if flag was cleared successfully
    """
    try:
        if UPDATE_FLAG_FILE.exists():
            UPDATE_FLAG_FILE.unlink()
            logger.info("Cleared update flag")
            return True

        return True  # Already cleared

    except Exception as e:
        logger.error(f"Failed to clear update flag: {e}")
        return False


def perform_client_update(ref: str) -> bool:
    """Perform the actual client update.

    This should be called by the launcher on startup if an update is pending.

    Args:
        ref: Git reference to checkout

    Returns:
        True if update was successful
    """
    from client.utils.git_operations import checkout_git_ref

    try:
        logger.info(f"Performing client update to {ref}...")

        # Checkout the specified ref
        if not checkout_git_ref(ref):
            logger.error(f"Failed to checkout {ref}")
            return False

        logger.info(f"Successfully updated client to {ref}")
        return True

    except Exception as e:
        logger.error(f"Error during client update: {e}")
        return False
