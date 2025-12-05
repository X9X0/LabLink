"""Git operations utility for client-side update management."""

import logging
import subprocess
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


def get_git_root() -> Optional[str]:
    """Get git repository root directory.

    Returns:
        Path to git root, or None if not in a git repository
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to get git root: {e.stderr}")
        return None
    except FileNotFoundError:
        logger.error("git command not found")
        return None


def get_git_tags() -> List[str]:
    """Get list of git tags sorted by version (newest first).

    Returns:
        List of tag names, e.g., ["v0.28.0", "v0.27.0", ...]
    """
    try:
        result = subprocess.run(
            ["git", "tag", "--sort=-version:refname"],
            capture_output=True,
            text=True,
            check=True
        )
        tags = [tag.strip() for tag in result.stdout.split('\n') if tag.strip()]
        logger.info(f"Found {len(tags)} git tags")
        return tags
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to get git tags: {e.stderr}")
        return []
    except FileNotFoundError:
        logger.error("git command not found")
        return []


def get_git_branches() -> List[str]:
    """Get list of git branches (local and remote).

    Returns:
        List of branch names, e.g., ["main", "feature/new-feature", ...]
    """
    try:
        # Get all branches (local and remote)
        result = subprocess.run(
            ["git", "branch", "-a"],
            capture_output=True,
            text=True,
            check=True
        )

        branches = []
        for line in result.stdout.split('\n'):
            line = line.strip()
            if not line:
                continue

            # Remove '* ' prefix from current branch
            if line.startswith('* '):
                line = line[2:]

            # Skip HEAD pointers
            if 'HEAD' in line:
                continue

            # Clean up remote branch names (remotes/origin/branch -> branch)
            if line.startswith('remotes/origin/'):
                line = line.replace('remotes/origin/', '')

            if line and line not in branches:
                branches.append(line)

        logger.info(f"Found {len(branches)} git branches")
        return sorted(branches)
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to get git branches: {e.stderr}")
        return []
    except FileNotFoundError:
        logger.error("git command not found")
        return []


def get_current_git_branch() -> Optional[str]:
    """Get currently checked out branch.

    Returns:
        Current branch name, or None if not on a branch
    """
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=True
        )
        branch = result.stdout.strip()
        return branch if branch else None
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to get current branch: {e.stderr}")
        return None
    except FileNotFoundError:
        logger.error("git command not found")
        return None


def checkout_git_ref(ref: str) -> bool:
    """Checkout a git tag or branch.

    Args:
        ref: Tag name (v0.29.0) or branch name (main)

    Returns:
        True if successful, False otherwise
    """
    try:
        # First, fetch latest changes
        logger.info(f"Fetching latest changes from origin...")
        subprocess.run(
            ["git", "fetch", "--all", "--tags"],
            capture_output=True,
            text=True,
            check=True
        )

        # Then checkout the ref
        logger.info(f"Checking out {ref}...")
        result = subprocess.run(
            ["git", "checkout", ref],
            capture_output=True,
            text=True,
            check=True
        )

        # If it's a branch, pull latest changes
        if ref in get_git_branches():
            logger.info(f"Pulling latest changes for branch {ref}...")
            subprocess.run(
                ["git", "pull", "origin", ref],
                capture_output=True,
                text=True,
                check=True
            )

        logger.info(f"Successfully checked out {ref}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to checkout {ref}: {e.stderr}")
        return False
    except FileNotFoundError:
        logger.error("git command not found")
        return False


def get_git_version_from_tag(tag: str) -> Optional[str]:
    """Extract version number from a git tag.

    Args:
        tag: Git tag name (e.g., "v0.28.0" or "0.28.0")

    Returns:
        Version string without 'v' prefix, or None if invalid
    """
    if not tag:
        return None

    # Remove 'v' prefix if present
    version = tag.lstrip('v')
    return version if version else None
