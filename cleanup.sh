#!/bin/bash
# Don't exit on error - we want to see all results
# set -e

echo "========================================="
echo "LabLink Cleanup Script"
echo "========================================="
echo ""

# Create directories
echo "Creating directory structure..."
mkdir -p docs/history/sessions docs/planning tests/{hardware,gui}

# 1. Remove duplicate test file
echo ""
echo "[1/5] Removing duplicate test file..."
if [ -f "test_mock_equipment.py" ]; then
    rm -f test_mock_equipment.py
    echo "  ✓ Removed test_mock_equipment.py (duplicate)"
else
    echo "  ℹ test_mock_equipment.py not found (already removed?)"
fi

# 2. Archive session summaries
echo ""
echo "[2/5] Archiving session summaries..."
moved_count=0
for file in SESSION*.md COMPLETION_SUMMARY.md WEBSOCKET_COMPLETION_SUMMARY.md; do
    if [ -f "$file" ]; then
        mv "$file" docs/history/sessions/
        echo "  ✓ Archived $file"
        ((moved_count++))
    fi
done
echo "  → Archived $moved_count session summary files"

# 3. Archive conversation logs and planning docs
echo ""
echo "[3/5] Archiving development logs..."
moved_count=0
for file in DEVELOPMENT_CONVERSATION_VERBOSE.md CONVERSATION_LOG.md; do
    if [ -f "$file" ]; then
        mv "$file" docs/history/
        echo "  ✓ Archived $file"
        ((moved_count++))
    fi
done
for file in WEBSOCKET_INTEGRATION_PLAN.md NEXT_STEPS_ANALYSIS.md; do
    if [ -f "$file" ]; then
        mv "$file" docs/planning/
        echo "  ✓ Moved $file to planning"
        ((moved_count++))
    fi
done
echo "  → Archived/moved $moved_count files"

# 4. Move test files from root to tests/
echo ""
echo "[4/5] Organizing root-level test files..."
moved_count=0

# GUI tests
for file in test_equipment_panels.py test_gui_with_mock.py test_visualization.py; do
    if [ -f "$file" ]; then
        mv "$file" tests/gui/
        echo "  ✓ Moved $file → tests/gui/"
        ((moved_count++))
    fi
done

# Integration tests
for file in test_websocket_streaming.py test_client.py; do
    if [ -f "$file" ]; then
        mv "$file" tests/integration/
        echo "  ✓ Moved $file → tests/integration/"
        ((moved_count++))
    fi
done

# Unit tests
for file in test_mdns.py test_setup.py demo_test.py; do
    if [ -f "$file" ]; then
        mv "$file" tests/unit/
        echo "  ✓ Moved $file → tests/unit/"
        ((moved_count++))
    fi
done

# Handle test_settings.py (may conflict with existing)
if [ -f "test_settings.py" ]; then
    if [ -f "tests/unit/test_settings.py" ]; then
        echo "  ⚠ test_settings.py conflicts with tests/unit/test_settings.py"
        echo "    Renaming to test_settings_root.py"
        mv test_settings.py tests/unit/test_settings_root.py
    else
        mv test_settings.py tests/unit/
        echo "  ✓ Moved test_settings.py → tests/unit/"
    fi
    ((moved_count++))
fi

echo "  → Moved $moved_count test files"

# 5. Move server test files
echo ""
echo "[5/5] Organizing server test files..."
moved_count=0

# Move server/test_*.py to tests/unit/
for file in server/test_*.py; do
    if [ -f "$file" ]; then
        basename=$(basename "$file")
        mv "$file" "tests/unit/${basename}"
        echo "  ✓ Moved $basename → tests/unit/"
        ((moved_count++))
    fi
done

# Move server/tests/test_*.py to tests/hardware/
if [ -d "server/tests" ]; then
    for file in server/tests/test_*.py; do
        if [ -f "$file" ]; then
            basename=$(basename "$file")
            mv "$file" "tests/hardware/${basename}"
            echo "  ✓ Moved $basename → tests/hardware/"
            ((moved_count++))
        fi
    done
    # Remove empty server/tests directory if it only has __init__.py
    if [ -f "server/tests/__init__.py" ] && [ $(ls -A server/tests | wc -l) -eq 1 ]; then
        rm -rf server/tests
        echo "  ✓ Removed empty server/tests directory"
    fi
fi

echo "  → Moved $moved_count server test files"

echo ""
echo "========================================="
echo "✅ Cleanup Complete!"
echo "========================================="
echo ""
echo "Summary of changes:"
echo "  • Removed 1 duplicate test file"
echo "  • Archived session summaries to docs/history/sessions/"
echo "  • Archived dev logs to docs/history/"
echo "  • Moved planning docs to docs/planning/"
echo "  • Organized all test files into tests/ subdirectories"
echo ""
echo "Next steps:"
echo "  1. Review changes: git status"
echo "  2. Run tests: pytest tests/ -v"
echo "  3. Commit changes: git add -A && git commit -m 'chore: Reorganize tests and archive redundant docs'"
echo ""
