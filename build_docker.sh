#!/bin/bash
# Build script for LabLink Docker image

set -e

echo "=================================="
echo "LabLink Docker Build Script"
echo "=================================="
echo

# Version
VERSION="0.10.0"

# Build image
echo "Building Docker image..."
docker build -t lablink-server:$VERSION .
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
