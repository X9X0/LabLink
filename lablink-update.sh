#!/bin/bash
# LabLink Update Script
# Updates code from git and rebuilds containers
#
# Usage: sudo ./lablink-update.sh [ref] [--yes] [--clean]
# Example: sudo ./lablink-update.sh main
#          sudo ./lablink-update.sh v2.1.1
#          sudo ./lablink-update.sh v2.1.1 --yes    # never prompt
#          sudo ./lablink-update.sh main --clean    # ignore the layer cache
#
# The ref may be a branch or a tag. A tag is a fixed point and is checked out
# detached, which is what pinning a bench Pi to a release means; only a branch
# is pulled, because pulling a tag is not a thing.
#
# --yes, or any non-interactive shell, rebuilds without asking. The client
# drives this over SSH, where a prompt would simply hang forever.

REF="main"
ASSUME_YES=0
REEXECED=0
for arg in "$@"; do
    case "$arg" in
        --yes|-y) ASSUME_YES=1 ;;
        --clean) ;;                 # handled at the build step
        --reexeced) REEXECED=1 ;;   # set by the restart below, not by hand
        *) REF="$arg" ;;
    esac
done

# What this script looked like before it updated itself. Bash executes a
# script by reading it as it goes, keeping a byte offset into the file, so
# a checkout that rewrites this file underneath a running copy leaves bash
# reading from the old offset into new contents -- and it runs whatever
# fragment happens to land there. On 2026-09-20 that made the first of two
# consecutive updates fail; the second, running the already-updated script,
# worked. See the restart after the checkout.
SELF="$(readlink -f "$0" 2>/dev/null || echo "$0")"
SELF_BEFORE=""
[ -r "$SELF" ] && SELF_BEFORE="$(sha256sum "$SELF" 2>/dev/null | cut -d' ' -f1)"

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

# One update at a time. Two runs overlapping -- an operator pressing the
# button while another is still going, or a person on the box at the same
# time -- have each other's containers half torn down, and docker compose
# reports "No such container: <id>" as one removes what the other just made.
exec 9>/var/lock/lablink-update.lock
if ! flock -n 9; then
    echo "Another LabLink update is already running. Nothing to do."
    exit 0
fi

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

# If the checkout replaced this script, start again with the new one before
# doing anything else. Carrying on would run the remains of the old script
# read at a byte offset into a file that is no longer the same length.
#
# The lock on fd 9 survives exec -- same process, same open file -- so the
# restart cannot deadlock against itself. --reexeced stops it looping if a
# checkout somehow keeps producing a different file.
if [ "$REEXECED" -eq 0 ] && [ -n "$SELF_BEFORE" ] && [ -r "$SELF" ]; then
    SELF_AFTER="$(sha256sum "$SELF" 2>/dev/null | cut -d' ' -f1)"
    if [ -n "$SELF_AFTER" ] && [ "$SELF_AFTER" != "$SELF_BEFORE" ]; then
        echo "The update script changed; restarting with the new one."
        echo ""
        exec "$SELF" "$@" --reexeced
    fi
fi

# Build before stopping anything. The old containers keep serving while the
# new image is made, so a build that fails costs nothing: the bench carries
# on running the version it already had. Stopping first, as this did, meant
# a failed build left the Pi with no server at all -- which is exactly what
# happened on 2026-09-20, and the operator was left with a dead bench and a
# dialog saying "check logs above".
echo "Step 3: Building containers..."

# The layer cache is the difference between an update that takes seconds and
# one that takes minutes. --no-cache threw it away every time, so every
# update re-downloaded the whole Debian package set and the whole of pip --
# slow, and one lost packet away from failing. Docker already rebuilds from
# the first layer whose inputs changed, so a change to the Python source
# reuses the apt and pip layers, and a change to requirements.txt does not.
# Pass --clean when you actually want to distrust the cache.
BUILD_ARGS=""
for arg in "$@"; do
    [ "$arg" = "--clean" ] && BUILD_ARGS="--no-cache"
done

if docker compose build $BUILD_ARGS; then
    echo "  ✓ Build successful"
elif DOCKER_BUILDKIT=0 docker compose build $BUILD_ARGS; then
    # BuildKit runs builds in its own network namespace, and on this Pi it
    # has twice lost outbound access while the host and ordinary containers
    # kept theirs -- apt then cannot reach deb.debian.org and every package
    # is "Unable to locate". The classic builder uses the plain docker
    # bridge and works. Restarting the docker daemon rebuilds the NAT
    # chains and fixes BuildKit properly; this is so that a bench update
    # does not have to wait for someone to do that.
    echo "  ✓ Build successful (BuildKit failed; used the classic builder)"
    echo "    BuildKit could not reach the network. 'sudo systemctl restart"
    echo "    docker' usually repairs that; the build itself was fine."
else
    echo "  ✗ Build failed"
    echo "  Check logs above for errors."
    echo "  Nothing was stopped: the previous version is still running."
    exit 1
fi
echo ""

echo "Step 4: Stopping containers..."
docker compose down
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
