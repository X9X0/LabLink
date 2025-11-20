#!/bin/bash
# LabLink Update Script
# Updates code from git and rebuilds containers
#
# Usage: sudo ./lablink-update.sh [branch]
# Example: sudo ./lablink-update.sh main

BRANCH="${1:-main}"

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

echo "Step 2: Pulling latest code from git (branch: $BRANCH)..."
if git fetch origin "$BRANCH" && git checkout "$BRANCH" && git pull origin "$BRANCH"; then
    NEW_COMMIT=$(git rev-parse --short HEAD)
    echo "  ✓ Code updated to: $NEW_COMMIT"

    if [ "$CURRENT_COMMIT" = "$NEW_COMMIT" ]; then
        echo "  Already up to date!"
        read -p "Rebuild anyway? (y/N): " rebuild
        if [ "$rebuild" != "y" ] && [ "$rebuild" != "Y" ]; then
            echo "No rebuild needed. Exiting."
            exit 0
        fi
    fi
else
    echo "  ✗ Git pull failed"
    echo "  Continuing with rebuild anyway..."
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
