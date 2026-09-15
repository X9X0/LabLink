"""Client self-update utilities."""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Project root (the git checkout) and the client entry point
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CLIENT_DIR = PROJECT_ROOT / "client"
CLIENT_MAIN = CLIENT_DIR / "main.py"

# Flag file location (in project root)
UPDATE_FLAG_FILE = PROJECT_ROOT / ".client_update"


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


def build_relaunch_command() -> list:
    """Command line that starts a fresh copy of the running client.

    A frozen (PyInstaller) build re-runs its own executable; a source checkout
    re-runs the same interpreter on ``client/main.py`` with the original
    arguments, so ``--debug`` and friends survive the restart.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable] + sys.argv[1:]
    return [sys.executable, str(CLIENT_MAIN)] + sys.argv[1:]


def relaunch_client() -> bool:
    """Start a detached copy of the client so the current one can exit.

    The new process sees the update flag on startup and applies the checkout
    before creating its window. Returns True if the new process was started.
    """
    cmd = build_relaunch_command()
    try:
        kwargs = {
            "cwd": str(CLIENT_DIR if CLIENT_DIR.is_dir() else PROJECT_ROOT),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if os.name == "nt":
            kwargs["creationflags"] = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(cmd, **kwargs)
        logger.info(f"Relaunched client: {' '.join(cmd)}")
        return True
    except Exception as e:
        logger.error(f"Failed to relaunch client: {e}")
        return False
