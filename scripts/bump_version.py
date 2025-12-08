#!/usr/bin/env python3
"""
LabLink Version Bump Script
============================

Automatically increments version numbers following Semantic Versioning.
Updates VERSION file and creates git commit/tag.

Usage:
    python scripts/bump_version.py patch   # 1.2.0 → 1.2.1 (bug fixes)
    python scripts/bump_version.py minor   # 1.2.0 → 1.3.0 (new features)
    python scripts/bump_version.py major   # 1.2.0 → 2.0.0 (breaking changes)

    Options:
    --no-commit     Don't create git commit
    --no-tag        Don't create git tag
    --dry-run       Show what would be done without making changes
"""

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path


def get_current_version(version_file: Path) -> str:
    """Read current version from VERSION file."""
    if not version_file.exists():
        print(f"❌ VERSION file not found: {version_file}")
        sys.exit(1)

    version = version_file.read_text().strip()
    if not re.match(r'^\d+\.\d+\.\d+$', version):
        print(f"❌ Invalid version format in VERSION file: {version}")
        sys.exit(1)

    return version


def parse_version(version: str) -> tuple:
    """Parse version string into (major, minor, patch) tuple."""
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)$', version)
    if not match:
        raise ValueError(f"Invalid version format: {version}")

    return tuple(int(x) for x in match.groups())


def bump_version(current: str, bump_type: str) -> str:
    """Bump version number based on type."""
    major, minor, patch = parse_version(current)

    if bump_type == 'major':
        return f"{major + 1}.0.0"
    elif bump_type == 'minor':
        return f"{major}.{minor + 1}.0"
    elif bump_type == 'patch':
        return f"{major}.{minor}.{patch + 1}"
    else:
        raise ValueError(f"Invalid bump type: {bump_type}")


def update_version_file(version_file: Path, new_version: str, dry_run: bool = False) -> None:
    """Update VERSION file with new version."""
    if dry_run:
        print(f"  [DRY-RUN] Would update {version_file} to {new_version}")
        return

    version_file.write_text(f"{new_version}\n")
    print(f"✓ Updated {version_file} → {new_version}")


def update_readme(readme_file: Path, new_version: str, dry_run: bool = False) -> None:
    """Update version badge and current version in README.md."""
    if not readme_file.exists():
        print(f"⚠️  README.md not found, skipping")
        return

    content = readme_file.read_text()
    today = date.today().strftime("%B %d, %Y")

    # Update version badge
    content = re.sub(
        r'!\[Version\]\(https://img\.shields\.io/badge/version-[^-]+-blue\.svg\)',
        f'![Version](https://img.shields.io/badge/version-{new_version}-blue.svg)',
        content
    )

    # Update "Current Version" section
    content = re.sub(
        r'\*\*Current Version\*\*: v[0-9.]+',
        f'**Current Version**: v{new_version}',
        content
    )

    # Update release date
    content = re.sub(
        r'\*\*Release Date\*\*: [^\n]+',
        f'**Release Date**: {today}',
        content
    )

    if dry_run:
        print(f"  [DRY-RUN] Would update README.md to version {new_version}")
        return

    readme_file.write_text(content)
    print(f"✓ Updated README.md → {new_version}")


def update_changelog(changelog_file: Path, new_version: str, dry_run: bool = False) -> None:
    """Add new version section to CHANGELOG.md."""
    if not changelog_file.exists():
        print(f"⚠️  CHANGELOG.md not found, skipping")
        return

    content = changelog_file.read_text()
    today = date.today().strftime("%Y-%m-%d")

    # Find the position after the header
    header_end = content.find("---\n")
    if header_end == -1:
        print(f"⚠️  Could not find CHANGELOG header, skipping")
        return

    # Create new version entry
    new_entry = f"""
## [{new_version}] - {today}

### ✨ Added
-

### 🐛 Fixed
-

### 📝 Changed
-

---

"""

    # Insert new entry
    updated_content = content[:header_end + 4] + new_entry + content[header_end + 4:]

    if dry_run:
        print(f"  [DRY-RUN] Would add version {new_version} to CHANGELOG.md")
        return

    changelog_file.write_text(updated_content)
    print(f"✓ Added version {new_version} to CHANGELOG.md")
    print(f"  ⚠️  Please edit CHANGELOG.md to add release notes!")


def update_dockerfile(dockerfile: Path, new_version: str, dry_run: bool = False) -> None:
    """Update LABEL version in Dockerfile."""
    if not dockerfile.exists():
        print(f"⚠️  {dockerfile.name} not found, skipping")
        return

    content = dockerfile.read_text()

    # Update LABEL version line
    updated_content = re.sub(
        r'LABEL version="[^"]+"',
        f'LABEL version="{new_version}"',
        content
    )

    if dry_run:
        print(f"  [DRY-RUN] Would update {dockerfile.name} to version {new_version}")
        return

    dockerfile.write_text(updated_content)
    print(f"✓ Updated {dockerfile.name} → {new_version}")


def git_commit_and_tag(new_version: str, no_commit: bool = False, no_tag: bool = False, dry_run: bool = False) -> None:
    """Create git commit and tag for version bump."""
    if no_commit and no_tag:
        return

    # Check if git repo
    try:
        subprocess.run(["git", "rev-parse", "--git-dir"], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        print("⚠️  Not a git repository, skipping git operations")
        return

    # Check for uncommitted changes
    result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if result.stdout.strip() and not dry_run:
        # Stage VERSION, README, CHANGELOG, and Dockerfile
        print("📝 Staging VERSION, README.md, CHANGELOG.md, and Dockerfile.server...")
        subprocess.run(["git", "add", "VERSION", "README.md", "CHANGELOG.md", "docker/Dockerfile.server"], check=False)

    if not no_commit:
        commit_msg = f"chore: Bump version to {new_version}"

        if dry_run:
            print(f"  [DRY-RUN] Would create commit: {commit_msg}")
        else:
            try:
                subprocess.run(["git", "commit", "-m", commit_msg], check=True)
                print(f"✓ Created git commit: {commit_msg}")
            except subprocess.CalledProcessError as e:
                print(f"⚠️  Failed to create commit: {e}")

    if not no_tag:
        tag_name = f"v{new_version}"

        if dry_run:
            print(f"  [DRY-RUN] Would create tag: {tag_name}")
        else:
            try:
                subprocess.run(["git", "tag", "-a", tag_name, "-m", f"Release {new_version}"], check=True)
                print(f"✓ Created git tag: {tag_name}")
                print(f"\n💡 To push the tag, run: git push origin {tag_name}")
            except subprocess.CalledProcessError as e:
                print(f"⚠️  Failed to create tag: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Bump LabLink version number",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        'bump_type',
        choices=['major', 'minor', 'patch'],
        help='Type of version bump'
    )
    parser.add_argument(
        '--no-commit',
        action='store_true',
        help="Don't create git commit"
    )
    parser.add_argument(
        '--no-tag',
        action='store_true',
        help="Don't create git tag"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Show what would be done without making changes"
    )

    args = parser.parse_args()

    # Get repository root
    repo_root = Path(__file__).parent.parent
    version_file = repo_root / "VERSION"
    readme_file = repo_root / "README.md"
    changelog_file = repo_root / "CHANGELOG.md"
    dockerfile_server = repo_root / "docker" / "Dockerfile.server"

    print("=" * 70)
    print("LabLink Version Bump Tool")
    print("=" * 70)

    # Get current version
    current_version = get_current_version(version_file)
    print(f"\n📌 Current version: {current_version}")

    # Calculate new version
    new_version = bump_version(current_version, args.bump_type)
    print(f"🎯 New version:     {new_version}")

    if args.dry_run:
        print("\n🔍 DRY-RUN MODE - No changes will be made\n")

    # Confirm
    if not args.dry_run:
        print(f"\n❓ Bump version from {current_version} → {new_version}?")
        response = input("   Continue? [y/N]: ").strip().lower()
        if response not in ['y', 'yes']:
            print("❌ Aborted")
            sys.exit(0)

    print("\n📝 Updating files...\n")

    # Update VERSION file
    update_version_file(version_file, new_version, args.dry_run)

    # Update README
    update_readme(readme_file, new_version, args.dry_run)

    # Update CHANGELOG
    update_changelog(changelog_file, new_version, args.dry_run)

    # Update Dockerfile
    update_dockerfile(dockerfile_server, new_version, args.dry_run)

    # Git operations
    if not args.dry_run:
        print("\n📦 Git operations...\n")
        git_commit_and_tag(new_version, args.no_commit, args.no_tag, args.dry_run)

    print("\n" + "=" * 70)
    if args.dry_run:
        print("✅ Dry-run complete!")
    else:
        print("✅ Version bump complete!")
        print(f"\n📝 Next steps:")
        print(f"   1. Edit CHANGELOG.md to add release notes")
        print(f"   2. Review changes: git diff")
        print(f"   3. Push changes: git push")
        print(f"   4. Push tag: git push origin v{new_version}")
    print("=" * 70)


if __name__ == "__main__":
    main()
