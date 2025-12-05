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


def get_git_branches(show_all: bool = False, sort_by_date: bool = True) -> List[str]:
    """Get list of git branches (local and remote).

    Args:
        show_all: If True, show all branches. If False, only show current and active branches (default: False)
        sort_by_date: If True, sort by most recent commit date (default: True)

    Returns:
        List of branch names, e.g., ["main", "feature/new-feature", ...]
    """
    try:
        # Get current branch first
        current_branch = get_current_git_branch()

        # Get all branches with commit date if sorting by date
        if sort_by_date:
            # Use --sort=-committerdate to sort by most recent first
            result = subprocess.run(
                ["git", "branch", "-a", "--sort=-committerdate"],
                capture_output=True,
                text=True,
                check=True
            )
        else:
            result = subprocess.run(
                ["git", "branch", "-a"],
                capture_output=True,
                text=True,
                check=True
            )

        branches = []
        seen_branches = set()

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
            original_line = line
            if line.startswith('remotes/origin/'):
                line = line.replace('remotes/origin/', '')

            # Skip if already seen (avoid duplicates)
            if line in seen_branches:
                continue

            # Filter for active branches if not showing all
            if not show_all and line != current_branch:
                # Skip dependabot branches
                if 'dependabot/' in line:
                    continue

                # Skip claude/* automated branches
                if line.startswith('claude/'):
                    continue

                # Check if branch has commits in last 3 months (active)
                try:
                    # Use original_line for the check to handle remote branches
                    check_line = original_line if original_line.startswith('remotes/') else line
                    commit_check = subprocess.run(
                        ["git", "log", "-1", "--since=3.months.ago", "--format=%ci", check_line],
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    # If no output, branch has no commits in last 3 months
                    if not commit_check.stdout.strip():
                        continue
                except:
                    # If check fails, include the branch anyway
                    pass

            if line:
                branches.append(line)
                seen_branches.add(line)

        logger.info(f"Found {len(branches)} git branches (show_all={show_all})")
        return branches
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
