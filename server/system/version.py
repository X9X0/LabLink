"""Version management for LabLink."""

import re
from pathlib import Path
from typing import Dict

# Read version from VERSION file
_version_file = Path(__file__).parent.parent.parent / "VERSION"
__version__ = _version_file.read_text().strip() if _version_file.exists() else "0.27.0"


def get_version() -> str:
    """Get the current version string.

    Returns:
        Version string (e.g., "0.28.0")
    """
    return __version__


def get_version_info() -> Dict[str, any]:
    """Get detailed version information.

    Returns:
        Dictionary with version details including major, minor, patch
    """
    # Parse version string (format: major.minor.patch)
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", __version__)
    if match:
        major, minor, patch = match.groups()
        return {
            "version": __version__,
            "major": int(major),
            "minor": int(minor),
            "patch": int(patch),
        }

    # Fallback if version doesn't match expected format
    return {
        "version": __version__,
        "major": 0,
        "minor": 0,
        "patch": 0,
    }


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
