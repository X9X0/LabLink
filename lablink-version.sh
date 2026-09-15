#!/bin/bash
# LabLink Version Check Script
# Run this on the Raspberry Pi to check what version/commit is running

set -e

echo "======================================"
echo "    LabLink Version Information"
echo "======================================"
echo ""

# Get the LabLink directory - try multiple locations
LABLINK_DIR=""

# Method 1: Check common deployment locations
for dir in "/opt/lablink" "$HOME/lablink" "$HOME/LabLink"; do
    if [ -d "$dir" ] && [ -f "$dir/VERSION" ]; then
        LABLINK_DIR="$dir"
        break
    fi
done

# Method 2: If not found, try to find it relative to script location (for symlinked command)
if [ -z "$LABLINK_DIR" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [ -f "$SCRIPT_DIR/VERSION" ]; then
        LABLINK_DIR="$SCRIPT_DIR"
    fi
fi

# Method 3: Check current directory as last resort
if [ -z "$LABLINK_DIR" ] && [ -f "$(pwd)/VERSION" ]; then
    LABLINK_DIR="$(pwd)"
fi

# Exit if LabLink directory not found
if [ -z "$LABLINK_DIR" ]; then
    echo "Error: LabLink directory not found"
    echo ""
    echo "Searched locations:"
    echo "  - /opt/lablink (Pi image deployment)"
    echo "  - $HOME/lablink (SSH deployment)"
    echo "  - Script directory"
    echo "  - Current directory"
    echo ""
    echo "Please ensure you are running this on a system with LabLink installed."
    exit 1
fi

cd "$LABLINK_DIR"
echo "LabLink Directory: $LABLINK_DIR"
echo ""

# Get version from VERSION file
if [ -f "VERSION" ]; then
    VERSION=$(cat VERSION)
    echo "Version: $VERSION"
else
    echo "Version: Unknown (VERSION file not found)"
fi

echo ""

# Get git information
if [ -d ".git" ]; then
    echo "Git Information:"
    echo "  Branch:  $(git rev-parse --abbrev-ref HEAD)"
    echo "  Commit:  $(git rev-parse --short HEAD)"
    echo "  Date:    $(git log -1 --format=%ci)"
    echo ""
    echo "Latest Commit:"
    echo "  $(git log -1 --oneline)"
    echo ""

    # Check if there are uncommitted changes
    if ! git diff-index --quiet HEAD --; then
        echo "⚠️  WARNING: Uncommitted changes detected!"
        git status --short
    else
        echo "✓ Working directory is clean"
    fi
else
    echo "Git Information: Not available (not a git repository)"
fi

echo ""

# Check if server is running
echo "Server Status:"
if command -v docker &> /dev/null; then
    if docker ps --format '{{.Names}}' | grep -q 'lablink-server'; then
        echo "  ✓ Docker container 'lablink-server' is running"

        # Try to get version from API
        if command -v curl &> /dev/null; then
            echo ""
            echo "Running Server Version (from API):"
            RESPONSE=$(curl -s http://localhost:8000/api/system/version 2>/dev/null || echo "")
            if [ -n "$RESPONSE" ]; then
                # Extract version and git info using basic parsing
                echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
            else
                echo "  Unable to query API (server may not be responding)"
            fi
        fi
    else
        echo "  ✗ Docker container 'lablink-server' is not running"
    fi
elif systemctl is-active --quiet lablink-server 2>/dev/null; then
    echo "  ✓ LabLink server service is running"
else
    echo "  ✗ LabLink server is not running"
fi

echo ""
echo "======================================"
