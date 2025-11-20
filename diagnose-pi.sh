#!/bin/bash
# LabLink Pi Diagnostic Script
# Run this on the Raspberry Pi to diagnose connection issues

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════════════════╗"
echo "║                                                       ║"
echo "║       LabLink Raspberry Pi Diagnostics                ║"
echo "║                                                       ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""

# System Information
echo -e "${GREEN}=== System Information ===${NC}"
echo "Hostname: $(hostname)"
echo "Date/Time: $(date)"
echo "Uptime: $(uptime -p)"
echo "Raspberry Pi Model: $(cat /proc/device-tree/model 2>/dev/null || echo 'Unknown')"
echo ""

# Network Status
echo -e "${GREEN}=== Network Status ===${NC}"
echo "IP Addresses:"
ip -4 addr show | grep inet | grep -v 127.0.0.1 || echo "No IP addresses found"
echo ""

echo "Network Connectivity:"
if ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} Internet: OK"
else
    echo -e "  ${RED}✗${NC} Internet: No connectivity"
fi

if ping -c 1 -W 2 github.com >/dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} DNS: OK"
else
    echo -e "  ${RED}✗${NC} DNS: Not working"
fi
echo ""

# Docker Status
echo -e "${GREEN}=== Docker Status ===${NC}"
if command -v docker >/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Docker installed: $(docker --version)"

    if systemctl is-active --quiet docker; then
        echo -e "${GREEN}✓${NC} Docker service: Running"
    else
        echo -e "${RED}✗${NC} Docker service: Not running"
        echo "  Status:"
        systemctl status docker --no-pager 2>&1 | head -10 | sed 's/^/    /'
    fi

    # Docker info
    echo ""
    echo "Docker Info:"
    if docker info >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} Docker daemon responding"
        docker info 2>&1 | grep -E "(Server Version|Storage Driver|Cgroup Driver|Cgroup Version)" | sed 's/^/    /'
    else
        echo -e "  ${RED}✗${NC} Docker daemon not responding"
        echo "  Error:"
        docker info 2>&1 | head -5 | sed 's/^/    /'
    fi
else
    echo -e "${RED}✗${NC} Docker not installed"
fi
echo ""

# LabLink Installation
echo -e "${GREEN}=== LabLink Installation ===${NC}"
if [ -d /opt/lablink ]; then
    echo -e "${GREEN}✓${NC} LabLink directory exists: /opt/lablink"

    cd /opt/lablink

    # Check for docker-compose.yml
    if [ -f docker-compose.yml ]; then
        echo -e "${GREEN}✓${NC} docker-compose.yml found"
    else
        echo -e "${RED}✗${NC} docker-compose.yml not found"
    fi

    # Check for .env file
    if [ -f .env ]; then
        echo -e "${GREEN}✓${NC} .env file found"
        echo "  Environment variables (sensitive values hidden):"
        grep -E "^LABLINK_" .env 2>/dev/null | sed 's/=.*/=***/' | head -10 | sed 's/^/    /' || echo "    No LABLINK_ variables found"
    else
        echo -e "${YELLOW}⚠${NC} .env file not found"
    fi

    # Check file ownership
    echo ""
    echo "File ownership:"
    ls -la /opt/lablink | head -5 | sed 's/^/  /'
else
    echo -e "${RED}✗${NC} LabLink directory not found at /opt/lablink"
fi
echo ""

# LabLink Service Status
echo -e "${GREEN}=== LabLink Service Status ===${NC}"
if systemctl list-unit-files | grep -q lablink.service; then
    echo -e "${GREEN}✓${NC} lablink.service exists"

    if systemctl is-enabled --quiet lablink.service 2>/dev/null; then
        echo -e "${GREEN}✓${NC} Service is enabled"
    else
        echo -e "${YELLOW}⚠${NC} Service is not enabled"
    fi

    if systemctl is-active --quiet lablink.service; then
        echo -e "${GREEN}✓${NC} Service is active"
    else
        echo -e "${RED}✗${NC} Service is not active"
    fi

    echo ""
    echo "Service status:"
    systemctl status lablink.service --no-pager 2>&1 | sed 's/^/  /'

    echo ""
    echo "Service configuration:"
    cat /etc/systemd/system/lablink.service 2>/dev/null | sed 's/^/  /' || echo "  Could not read service file"
else
    echo -e "${RED}✗${NC} lablink.service not found"
fi
echo ""

# Docker Containers
echo -e "${GREEN}=== Docker Containers ===${NC}"
if [ -d /opt/lablink ]; then
    cd /opt/lablink

    if docker compose ps 2>/dev/null | grep -q .; then
        echo "Container status:"
        docker compose ps 2>/dev/null | sed 's/^/  /'

        # Check for running containers
        if docker compose ps 2>/dev/null | grep -q "Up"; then
            echo -e "${GREEN}✓${NC} Containers are running"
        else
            echo -e "${RED}✗${NC} No containers running"
        fi
    else
        echo -e "${RED}✗${NC} No docker compose containers found"
        echo "  This could mean docker compose was never run"
    fi

    # Show all Docker containers (not just compose)
    echo ""
    echo "All Docker containers on system:"
    docker ps -a 2>/dev/null | sed 's/^/  /' || echo "  Could not list containers"
else
    echo -e "${RED}✗${NC} Cannot check containers - /opt/lablink not found"
fi
echo ""

# Port Listeners
echo -e "${GREEN}=== Port Listeners ===${NC}"
echo "Checking if anything is listening on LabLink ports..."
if command -v ss >/dev/null 2>&1; then
    if ss -tlnp 2>/dev/null | grep -q ":8000"; then
        echo -e "${GREEN}✓${NC} Port 8000 (API) is listening:"
        ss -tlnp 2>/dev/null | grep ":8000" | sed 's/^/    /'
    else
        echo -e "${RED}✗${NC} Port 8000 (API) is NOT listening"
    fi

    if ss -tlnp 2>/dev/null | grep -q ":8001"; then
        echo -e "${GREEN}✓${NC} Port 8001 (WebSocket) is listening:"
        ss -tlnp 2>/dev/null | grep ":8001" | sed 's/^/    /'
    else
        echo -e "${YELLOW}⚠${NC} Port 8001 (WebSocket) is NOT listening"
    fi

    if ss -tlnp 2>/dev/null | grep -q ":80"; then
        echo -e "${GREEN}✓${NC} Port 80 (Web) is listening:"
        ss -tlnp 2>/dev/null | grep ":80" | sed 's/^/    /'
    else
        echo -e "${YELLOW}⚠${NC} Port 80 (Web) is NOT listening"
    fi
else
    echo "ss command not available, trying netstat..."
    netstat -tlnp 2>/dev/null | grep -E ":(8000|8001|80)" || echo "No listeners on LabLink ports"
fi
echo ""

# Recent Logs
echo -e "${GREEN}=== Recent System Logs ===${NC}"

# First boot log
if [ -f /var/log/lablink-first-boot.log ]; then
    echo "First boot log (last 30 lines):"
    tail -30 /var/log/lablink-first-boot.log | sed 's/^/  /'
    echo ""
else
    echo "No first boot log found at /var/log/lablink-first-boot.log"
fi

# Systemd journal for lablink service
if systemctl list-unit-files | grep -q lablink.service; then
    echo "LabLink service journal (last 20 lines):"
    journalctl -u lablink.service --no-pager -n 20 2>/dev/null | sed 's/^/  /' || echo "  Could not read journal"
    echo ""
fi

# First boot service
if systemctl list-unit-files | grep -q lablink-first-boot.service; then
    echo "First boot service journal (last 20 lines):"
    journalctl -u lablink-first-boot.service --no-pager -n 20 2>/dev/null | sed 's/^/  /' || echo "  Could not read journal"
    echo ""
fi

# Docker compose logs
if [ -d /opt/lablink ]; then
    cd /opt/lablink
    echo "Docker Compose logs (last 30 lines):"
    docker compose logs --tail=30 2>/dev/null | sed 's/^/  /' || echo "  Could not read docker logs"
fi
echo ""

# Setup completion marker
echo -e "${GREEN}=== Setup Status ===${NC}"
if [ -f /var/lib/lablink-setup-complete ]; then
    echo -e "${GREEN}✓${NC} First boot setup marked as complete"
    echo "  Completed: $(stat -c %y /var/lib/lablink-setup-complete)"
else
    echo -e "${YELLOW}⚠${NC} First boot setup not marked as complete"
    echo "  This suggests the first-boot script may still be running or failed"
fi
echo ""

# Health check
echo -e "${GREEN}=== Health Check ===${NC}"
echo "Testing local HTTP connectivity..."
if command -v curl >/dev/null 2>&1; then
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health --connect-timeout 2 | grep -q "200"; then
        echo -e "${GREEN}✓${NC} LabLink API responding on localhost:8000"
    else
        echo -e "${RED}✗${NC} LabLink API not responding on localhost:8000"
        echo "  Response: $(curl -s http://localhost:8000/health --connect-timeout 2 2>&1 | head -3)"
    fi
else
    if wget -q -O - http://localhost:8000/health --timeout=2 >/dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} LabLink API responding on localhost:8000"
    else
        echo -e "${RED}✗${NC} LabLink API not responding on localhost:8000"
    fi
fi
echo ""

# Recommendations
echo -e "${BLUE}=== Recommendations ===${NC}"
echo ""

# Analyze and provide recommendations
has_issues=false

if ! systemctl is-active --quiet docker 2>/dev/null; then
    echo -e "${RED}•${NC} Docker service is not running. Try: ${YELLOW}sudo systemctl start docker${NC}"
    has_issues=true
fi

if ! systemctl is-active --quiet lablink.service 2>/dev/null; then
    echo -e "${RED}•${NC} LabLink service is not running. Try: ${YELLOW}sudo systemctl start lablink${NC}"
    has_issues=true
fi

if [ ! -f /var/lib/lablink-setup-complete ]; then
    echo -e "${YELLOW}•${NC} First boot setup not complete. Check logs: ${YELLOW}sudo journalctl -u lablink-first-boot -f${NC}"
    has_issues=true
fi

if [ -d /opt/lablink ] && ! docker compose ps 2>/dev/null | grep -q "Up"; then
    echo -e "${RED}•${NC} No containers running. Try: ${YELLOW}cd /opt/lablink && sudo docker compose up -d${NC}"
    has_issues=true
fi

if [ ! -d /opt/lablink ]; then
    echo -e "${RED}•${NC} LabLink not installed. First boot script may have failed."
    echo -e "    Check: ${YELLOW}sudo journalctl -u lablink-first-boot${NC}"
    has_issues=true
fi

if ! $has_issues; then
    echo -e "${GREEN}✓${NC} No obvious issues detected!"
    echo ""
    echo "If you're still having connection issues from a client:"
    echo "  1. Verify client can reach Pi: ${YELLOW}ping lablink-pi.local${NC}"
    echo "  2. Check firewall: ${YELLOW}sudo ufw status${NC}"
    echo "  3. Test from Pi browser: ${YELLOW}curl http://localhost:8000/health${NC}"
fi

echo ""
echo -e "${BLUE}╔═══════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Diagnostics complete. Share this output for help.   ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════╝${NC}"
