#!/bin/bash
# LabLink Demo Launcher
# Automatically activates virtual environment and runs the demo

set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Error: Virtual environment not found."
    echo "Please run: python3 setup.py --venv"
    exit 1
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Run the demo
echo "Starting LabLink demo application..."
python3 demo_acquisition_full.py
