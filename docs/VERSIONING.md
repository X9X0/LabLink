# LabLink Versioning System

## Overview

LabLink uses **single-source versioning** where all components (server, client, launcher, Docker) read from a central `VERSION` file. This ensures version consistency across the entire system.

## Current Version: 1.2.0

## Version File Location

```
LabLink/
└── VERSION  (single source of truth)
```

## Components Using VERSION File

| Component | File | How It Reads |
|-----------|------|-------------|
| **Server** | `server/system/version.py` | Reads VERSION file, fallback to hardcoded |
| **Client** | `client/main.py` | Reads VERSION file at startup |
| **Launcher** | `lablink.py` | Reads VERSION file, sets `__version__` |
| **Docker Server** | `docker/Dockerfile.server` | Label updated to match VERSION |
| **Docker Web** | `docker/Dockerfile.web` | Label updated to match VERSION |
| **README** | `README.md` | Badge manually updated |

## Semantic Versioning

LabLink follows [Semantic Versioning 2.0.0](https://semver.org/):

```
MAJOR.MINOR.PATCH

Example: 1.2.0
         │ │ │
         │ │ └─ Patch: Bug fixes (backward compatible)
         │ └─── Minor: New features (backward compatible)
         └───── Major: Breaking changes
```

### When to Bump Versions

**PATCH** (1.2.0 → 1.2.1):
- Bug fixes
- Security patches
- Documentation updates
- Performance improvements (no API changes)

**MINOR** (1.2.0 → 1.3.0):
- New features (backward compatible)
- New API endpoints
- Deprecations (with backward compatibility)
- Significant UI improvements

**MAJOR** (1.2.0 → 2.0.0):
- Breaking API changes
- Removed deprecated features
- Major architectural changes
- Incompatible upgrades

## Automated Version Bumping

Use the `scripts/bump_version.py` script to automate version updates:

### Basic Usage

```bash
# Bug fixes
python scripts/bump_version.py patch   # 1.2.0 → 1.2.1

# New features
python scripts/bump_version.py minor   # 1.2.0 → 1.3.0

# Breaking changes
python scripts/bump_version.py major   # 1.2.0 → 2.0.0
```

### Advanced Options

```bash
# Dry-run (see what would happen)
python scripts/bump_version.py minor --dry-run

# Skip git commit
python scripts/bump_version.py patch --no-commit

# Skip git tag
python scripts/bump_version.py minor --no-tag

# Both
python scripts/bump_version.py major --no-commit --no-tag
```

### What the Script Does

1. ✅ Reads current version from `VERSION` file
2. ✅ Calculates new version based on bump type
3. ✅ Updates `VERSION` file
4. ✅ Adds new version section to `CHANGELOG.md`
5. ✅ Creates git commit: `chore: Bump version to X.Y.Z`
6. ✅ Creates git tag: `vX.Y.Z`
7. ✅ Provides push instructions

## Manual Version Update Process

If you need to update versions manually:

### 1. Update VERSION File

```bash
echo "1.3.0" > VERSION
```

### 2. Update CHANGELOG.md

Add a new section at the top (after the header):

```markdown
## [1.3.0] - 2025-12-06

### ✨ Added
- New feature description

### 🐛 Fixed
- Bug fix description

### 📝 Changed
- Change description

---
```

### 3. Verify All Components

```bash
# Check server
python3 -c "from server.system.version import get_version; print(get_version())"

# Check VERSION file
cat VERSION

# Check client (would read from VERSION at startup)
# Check launcher (would read from VERSION at startup)
```

### 4. Commit and Tag

```bash
git add VERSION CHANGELOG.md
git commit -m "chore: Bump version to 1.3.0"
git tag -a v1.3.0 -m "Release 1.3.0"
git push
git push origin v1.3.0
```

## Version History

| Version | Date | Description |
|---------|------|-------------|
| **1.2.0** | 2025-12-06 | Server update system, UI consolidation, smart branch filtering |
| **1.0.1** | 2025-11-28 | Equipment control panel, GUI launcher, diagnostics |
| **1.0.0** | 2025-11-14 | First production release |

## Checking Current Version

### From Command Line

```bash
# Quick check
cat VERSION

# Server version
python3 -c "from server.system.version import get_version; print(get_version())"

# Launcher version
python3 -c "import lablink; print(lablink.__version__)"
```

### From Python

```python
# Server
from server.system.version import get_version
print(f"Server version: {get_version()}")

# From VERSION file directly
from pathlib import Path
version = Path("VERSION").read_text().strip()
print(f"Version: {version}")
```

### From Client GUI

The version is displayed in:
- Help → About dialog
- Application title bar (set via `QApplication.setApplicationVersion()`)

## Git Tags

All releases are tagged with `vX.Y.Z` format:

```bash
# List all version tags
git tag -l "v*" | sort -V

# Show tag details
git show v1.2.0

# Checkout specific version
git checkout v1.2.0
```

## Best Practices

### DO ✅
- Use `scripts/bump_version.py` for version changes
- Update CHANGELOG.md with meaningful release notes
- Test the version after bumping (`cat VERSION`)
- Create git tags for all releases
- Follow semantic versioning strictly

### DON'T ❌
- Hardcode versions in multiple files
- Skip CHANGELOG updates
- Forget to push tags (`git push origin vX.Y.Z`)
- Use inconsistent version formats
- Bump major version without breaking changes

## Migration from Old System

**Before (inconsistent):**
- VERSION: 0.28.0
- README: 1.0.1
- client/main.py: 0.10.0 (hardcoded)
- Dockerfiles: 0.27.0 (hardcoded)
- CHANGELOG: 1.0.0 only

**After (unified to 1.2.0):**
- ✅ Single VERSION file: 1.2.0
- ✅ All components read from VERSION
- ✅ CHANGELOG updated with 1.0.1 and 1.2.0
- ✅ README badge: 1.2.0
- ✅ Copyright: © 2025

## Troubleshooting

### Version Mismatch Detected

If components show different versions:

```bash
# 1. Check VERSION file
cat VERSION

# 2. Verify server reads it correctly
python3 -c "from server.system.version import get_version; print(get_version())"

# 3. Restart application to pick up new version
```

### Bump Script Fails

```bash
# Check you're in repo root
cd /path/to/LabLink

# Check VERSION file exists
ls -la VERSION

# Try dry-run first
python scripts/bump_version.py patch --dry-run
```

### Git Tag Already Exists

```bash
# Delete local tag
git tag -d v1.2.0

# Delete remote tag
git push origin :refs/tags/v1.2.0

# Recreate tag
git tag -a v1.2.0 -m "Release 1.2.0"
git push origin v1.2.0
```

## Future Enhancements

Potential improvements to the versioning system:

- [ ] CI/CD integration for automatic version bumps
- [ ] Pre-commit hook to verify version consistency
- [ ] Docker build args to inject VERSION at build time
- [ ] Version validation tests in CI pipeline
- [ ] Automatic CHANGELOG generation from git commits
- [ ] Version comparison utilities

## References

- [Semantic Versioning 2.0.0](https://semver.org/)
- [Keep a Changelog](https://keepachangelog.com/)
- [LabLink CHANGELOG.md](../CHANGELOG.md)
- [Version Bump Script](../scripts/bump_version.py)

---

**Last Updated:** 2025-12-06
**Version:** 1.2.0
**Copyright:** © 2025 LabLink Project
