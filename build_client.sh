#!/bin/bash
# Build script for LabLink GUI Client

set -e  # Exit on error

echo "=================================="
echo "LabLink Client Build Script"
echo "=================================="
echo

# Check if pyinstaller is installed
if ! command -v pyinstaller &> /dev/null; then
    echo "PyInstaller not found. Installing..."
    pip install pyinstaller
fi

# Change to client directory
cd client

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf build/ dist/

# Build the application
echo "Building LabLink client..."
pyinstaller lablink.spec

# Check if build was successful
if [ -f "dist/LabLink" ] || [ -f "dist/LabLink.exe" ] || [ -d "dist/LabLink.app" ]; then
    echo
    echo "✓ Build successful!"
    echo
    echo "Output location:"
    ls -lh dist/
    echo
    echo "To run:"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "  open dist/LabLink.app"
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
        echo "  dist\\LabLink.exe"
    else
        echo "  ./dist/LabLink"
    fi
else
    echo
    echo "✗ Build failed!"
    exit 1
fi

echo
echo "=================================="
echo "Build complete!"
echo "=================================="
