#!/bin/bash
# Test runner script for LabLink equipment drivers

echo "LabLink Equipment Driver Test Suite"
echo "===================================="
echo ""

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Warning: No virtual environment detected."
    echo "Attempting to activate venv..."
    if [ -d "venv" ]; then
        source venv/bin/activate
    else
        echo "Error: venv directory not found. Please create it first:"
        echo "  python3 -m venv venv"
        echo "  source venv/bin/activate"
        echo "  pip install -r requirements.txt"
        exit 1
    fi
fi

# Install test dependencies if needed
echo "Checking test dependencies..."
pip install -q pytest pytest-asyncio 2>/dev/null

echo ""
echo "Running tests..."
echo ""

# Run pytest with verbose output
cd /home/x9x0/LabLink/server
python3 -m pytest tests/ -v --tb=short

# Check exit code
if [ $? -eq 0 ]; then
    echo ""
    echo "✓ All tests passed!"
else
    echo ""
    echo "✗ Some tests failed. See output above for details."
    exit 1
fi
