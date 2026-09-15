#!/bin/bash
# Build script for LabLink Docker image

set -e

echo "=================================="
echo "LabLink Docker Build Script"
echo "=================================="
echo

# Version, from the single source of truth rather than a copy of it. This said
# 0.10.0 while VERSION said 2.0.0, so the script tagged images with a number
# nothing else in the repo recognised.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VERSION="$(tr -d '[:space:]' < "$SCRIPT_DIR/VERSION")"

# Build image
#
# docker/Dockerfile.server, the same file docker-compose builds and the one
# running on the bench Pi. This used to build a second Dockerfile in the repo
# root that nothing deployed, and the two drifted until the root one could not
# import the server package at all (#197/#202).
echo "Building Docker image..."
docker build -f "$SCRIPT_DIR/docker/Dockerfile.server" -t lablink-server:$VERSION "$SCRIPT_DIR"
docker tag lablink-server:$VERSION lablink-server:latest

echo
echo "✓ Build successful!"
echo
echo "Image: lablink-server:$VERSION"
echo "Size: $(docker images lablink-server:$VERSION --format "{{.Size}}")"
echo
echo "To run:"
echo "  docker run -p 8000:8000 -p 8001:8001 lablink-server:$VERSION"
echo
echo "Or with docker-compose:"
echo "  docker-compose up -d"
echo
echo "To save image:"
echo "  docker save lablink-server:$VERSION | gzip > lablink-server-$VERSION.tar.gz"
echo
echo "=================================="
