"""Version management for LabLink."""

import logging
import re
import subprocess
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Read version from VERSION file
_version_file = Path(__file__).parent.parent.parent / "VERSION"
__version__ = _version_file.read_text().strip() if _version_file.exists() else "0.27.0"


def get_version() -> str:
    """Get the current version string.

    Returns:
        Version string (e.g., "0.28.0")
    """
    return __version__


def get_git_commit_info() -> Dict[str, Optional[str]]:
    """Get git commit information for the running server.

    Returns:
        Dictionary with git commit details:
        - commit_hash: Short commit hash (e.g., "a1b2c3d")
        - commit_hash_full: Full commit hash
        - branch: Current git branch
        - commit_date: Commit date
        - commit_message: First line of commit message
    """
    git_info = {
        "commit_hash": None,
        "commit_hash_full": None,
        "branch": None,
        "commit_date": None,
        "commit_message": None,
    }

    try:
        # Get repository root (go up from server/system/)
        repo_root = Path(__file__).parent.parent.parent

        # Get short commit hash
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            git_info["commit_hash"] = result.stdout.strip()

        # Get full commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            git_info["commit_hash_full"] = result.stdout.strip()

        # Get branch name
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            git_info["branch"] = result.stdout.strip()

        # Get commit date
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ci"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            git_info["commit_date"] = result.stdout.strip()

        # Get commit message (first line)
        result = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            git_info["commit_message"] = result.stdout.strip()

    except Exception as e:
        logger.debug(f"Unable to get git commit info: {e}")

    return git_info


def get_version_info() -> Dict[str, any]:
    """Get detailed version information.

    Returns:
        Dictionary with version details including major, minor, patch, and git info
    """
    # Parse version string (format: major.minor.patch)
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", __version__)
    if match:
        major, minor, patch = match.groups()
        version_info = {
            "version": __version__,
            "major": int(major),
            "minor": int(minor),
            "patch": int(patch),
        }
    else:
        # Fallback if version doesn't match expected format
        version_info = {
            "version": __version__,
            "major": 0,
            "minor": 0,
            "patch": 0,
        }

    # Add git commit information
    version_info["git"] = get_git_commit_info()

    return version_info


def compare_versions(version1: str, version2: str) -> int:
    """Compare two version strings.

    Args:
        version1: First version string
        version2: Second version string

    Returns:
        -1 if version1 < version2
        0 if version1 == version2
        1 if version1 > version2
    """
    def parse_version(v: str) -> tuple:
        match = re.match(r"(\d+)\.(\d+)\.(\d+)", v)
        if match:
            return tuple(int(x) for x in match.groups())
        return (0, 0, 0)

    v1 = parse_version(version1)
    v2 = parse_version(version2)

    if v1 < v2:
        return -1
    elif v1 > v2:
        return 1
    return 0
