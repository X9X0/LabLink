#!/bin/bash
# Script to verify what code version is running on the Pi

echo "===== LabLink Pi Code Verification ====="
echo ""

echo "1. Git repository status:"
if [ -d /opt/lablink/.git ]; then
    cd /opt/lablink
    echo "  Current branch: $(git branch --show-current)"
    echo "  Latest commit: $(git log -1 --oneline)"
    echo "  Latest commit date: $(git log -1 --format=%cd)"
    echo ""
else
    echo "  WARNING: Not a git repository (tarball installation)"
    echo ""
fi

echo "2. Check if Pi diagnostics endpoint exists in server code:"
if [ -f /opt/lablink/server/api/diagnostics.py ]; then
    if grep -q "pi-diagnostics" /opt/lablink/server/api/diagnostics.py; then
        echo "  ✓ Pi diagnostics endpoint found in code"
        echo "  Endpoint definition:"
        grep -A 2 "pi-diagnostics" /opt/lablink/server/api/diagnostics.py | head -5
    else
        echo "  ✗ Pi diagnostics endpoint NOT found in code"
    fi
else
    echo "  ✗ diagnostics.py file not found"
fi
echo ""

echo "3. Check if diagnose-pi.sh script exists:"
if [ -f /opt/lablink/diagnose-pi.sh ]; then
    echo "  ✓ diagnose-pi.sh exists"
    ls -lh /opt/lablink/diagnose-pi.sh
else
    echo "  ✗ diagnose-pi.sh not found"
fi
echo ""

echo "4. Check requests dependency version:"
if [ -f /opt/lablink/server/requirements.txt ]; then
    echo "  requests version in requirements.txt:"
    grep "^requests" /opt/lablink/server/requirements.txt || echo "  ✗ requests not found in requirements"
else
    echo "  ✗ requirements.txt not found"
fi
echo ""

echo "5. Check Docker container Python environment:"
if docker compose ps | grep -q "Up"; then
    echo "  Checking installed packages in container..."
    docker compose exec -T lablink-server pip show requests 2>/dev/null || echo "  ✗ requests not installed in container"
else
    echo "  ✗ Containers not running"
fi
echo ""

echo "6. Check server logs for startup errors:"
echo "  Recent server logs:"
docker compose logs --tail=30 lablink-server 2>/dev/null | grep -i "error\|warning\|diagnostics" || echo "  No errors found in recent logs"
echo ""

echo "7. Check API routes registered:"
echo "  Testing health endpoint:"
curl -s http://localhost:8000/health | head -3 || echo "  ✗ Server not responding"
echo ""
echo "  Testing diagnostics endpoint:"
curl -s -o /dev/null -w "HTTP %{http_code}" http://localhost:8000/api/diagnostics/pi-diagnostics -X POST
echo ""
echo ""

echo "8. Check when LabLink was last updated:"
if [ -d /opt/lablink ]; then
    echo "  Last modified: $(stat -c %y /opt/lablink | cut -d. -f1)"
    echo "  LabLink directory contents modified:"
    ls -lt /opt/lablink | head -10
fi
echo ""

echo "===== Verification Complete ====="
