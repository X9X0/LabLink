#!/bin/bash
# LabLink Update Script
# Updates code from git and rebuilds containers
#
# Usage: sudo ./lablink-update.sh [ref] [--yes]
# Example: sudo ./lablink-update.sh main
#          sudo ./lablink-update.sh v2.1.1
#          sudo ./lablink-update.sh v2.1.1 --yes    # never prompt
#
# The ref may be a branch or a tag. A tag is a fixed point and is checked out
# detached, which is what pinning a bench Pi to a release means; only a branch
# is pulled, because pulling a tag is not a thing.
#
# --yes, or any non-interactive shell, rebuilds without asking. The client
# drives this over SSH, where a prompt would simply hang forever.

REF="main"
ASSUME_YES=0
for arg in "$@"; do
    case "$arg" in
        --yes|-y) ASSUME_YES=1 ;;
        *) REF="$arg" ;;
    esac
done

# No tty means nobody can answer a question.
[ -t 0 ] || ASSUME_YES=1

echo "╔═══════════════════════════════════════════════════════╗"
echo "║                                                       ║"
echo "║            LabLink Update & Rebuild                   ║"
echo "║                                                       ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root (use sudo)"
    exit 1
fi

cd /opt/lablink || exit 1

echo "Step 1: Checking current version..."
CURRENT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
echo "  Current branch: $CURRENT_BRANCH"
echo "  Current commit: $CURRENT_COMMIT"
echo ""

echo "Step 2: Updating code from git (ref: $REF)..."
if ! git rev-parse --git-dir >/dev/null 2>&1; then
    echo "  ✗ /opt/lablink is not a git checkout, so there is nothing to update."
    echo "    Deploy it with the client's SSH wizard, or clone it:"
    echo "      sudo git clone https://github.com/X9X0/LabLink.git /opt/lablink"
    echo "    (keep the existing .env — it is not in git)"
    exit 1
fi

# --tags as well as branches: the version list offers releases.
if git fetch --all --tags --prune && git checkout "$REF"; then
    # Only a branch can be pulled. A tag is already the exact commit, and
    # "git pull origin <tag>" would try to merge it into a detached HEAD.
    if git symbolic-ref -q HEAD >/dev/null; then
        git pull --ff-only origin "$REF" || echo "  (no fast-forward available)"
    fi

    NEW_COMMIT=$(git rev-parse --short HEAD)
    echo "  ✓ Code now at: $NEW_COMMIT"

    if [ "$CURRENT_COMMIT" = "$NEW_COMMIT" ]; then
        echo "  Already up to date!"
        if [ "$ASSUME_YES" -eq 1 ]; then
            echo "  Rebuilding anyway."
        else
            read -p "Rebuild anyway? (y/N): " rebuild
            if [ "$rebuild" != "y" ] && [ "$rebuild" != "Y" ]; then
                echo "No rebuild needed. Exiting."
                exit 0
            fi
        fi
    fi
else
    echo "  ✗ Could not check out $REF"
    exit 1
fi
echo ""

echo "Step 3: Stopping containers..."
docker compose down
echo ""

echo "Step 4: Rebuilding containers (this may take 2-3 minutes)..."
if docker compose build --no-cache; then
    echo "  ✓ Rebuild successful"
else
    echo "  ✗ Rebuild failed"
    echo "  Check logs above for errors"
    exit 1
fi
echo ""

echo "Step 5: Starting containers..."
if docker compose up -d; then
    echo "  ✓ Containers started"
else
    echo "  ✗ Failed to start containers"
    exit 1
fi
echo ""

echo "Step 6: Waiting for services to be ready..."
sleep 5

# Wait for containers to be healthy
MAX_WAIT=30
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if docker compose ps 2>/dev/null | grep -q "Up"; then
        echo "  ✓ Services are ready"
        break
    fi
    sleep 2
    WAITED=$((WAITED + 2))
done
echo ""

echo "╔═══════════════════════════════════════════════════════╗"
echo "║            Update Complete!                           ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

# Show final status if lablink-status exists
if command -v lablink-status &> /dev/null; then
    lablink-status
else
    echo "Container Status:"
    docker compose ps
fi
