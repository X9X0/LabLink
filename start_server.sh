#!/bin/bash
# LabLink Server Launcher
# Automatically activates virtual environment and starts the server

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

# Start the server
#
# From the repo root, naming the module -- not `cd server && python3 main.py`.
# Running it from inside the package puts server/ on sys.path, so `import
# server.x` cannot resolve at all, and the arrangement that used to make it
# work imported the same file under two names (issue #197). The server now
# refuses to start in that shape.
echo "Starting LabLink server..."
python3 -m server.main "$@"
