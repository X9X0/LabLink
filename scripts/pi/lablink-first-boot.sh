#!/bin/bash
# LabLink first boot - network-dependent stage.
#
# Installed by firstrun.sh and run by lablink-first-boot.service once the
# network is up. This is the logic that has been proven on hardware; it is kept
# here as a standalone file so both the bash image builder and the native
# (pure-Python, cross-platform) builder use exactly the same script rather than
# maintaining two copies.
#
# __LABLINK_BRANCH__ is substituted at image build time.
# LabLink First Boot Setup

# Log to both journal and file
exec 1> >(tee -a /var/log/lablink-first-boot.log)
exec 2>&1

echo "[LabLink] Starting first boot setup..."
echo "[LabLink] $(date)"

# Check if setup already completed
if [ -f /var/lib/lablink-setup-complete ]; then
    echo "[LabLink] Setup already completed, exiting"
    systemctl disable lablink-first-boot.service
    exit 0
fi

# Function to wait for network
wait_for_network() {
    local max_attempts=30
    local attempt=1

    echo "[LabLink] Waiting for network connectivity..."

    while [ $attempt -le $max_attempts ]; do
        if ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1; then
            echo "[LabLink] Network is ready (attempt $attempt)"
            return 0
        fi
        echo "[LabLink] Network not ready, attempt $attempt/$max_attempts..."
        sleep 2
        attempt=$((attempt + 1))
    done

    echo "[LabLink] WARNING: Network not available after $max_attempts attempts"
    return 1
}

# Function to sync time
sync_time() {
    echo "[LabLink] Synchronizing system time via NTP..."

    # Enable NTP
    timedatectl set-ntp true

    # Restart timesyncd to force sync
    systemctl restart systemd-timesyncd

    # Wait for time sync with timeout
    local max_wait=30
    local waited=0
    while [ $waited -lt $max_wait ]; do
        if timedatectl status | grep -q "System clock synchronized: yes"; then
            echo "[LabLink] Time synchronized successfully"
            echo "[LabLink] Current time: $(date)"
            return 0
        fi
        sleep 1
        waited=$((waited + 1))
    done

    echo "[LabLink] WARNING: Time sync timeout, but continuing anyway"
    echo "[LabLink] Current time: $(date)"
    return 0
}

# Function to wait for DNS resolution
wait_for_dns() {
    local max_attempts=20
    local attempt=1

    echo "[LabLink] Waiting for DNS resolution..."

    while [ $attempt -le $max_attempts ]; do
        if ping -c 1 -W 2 github.com >/dev/null 2>&1; then
            echo "[LabLink] DNS is ready (attempt $attempt)"
            return 0
        fi
        echo "[LabLink] DNS not ready, attempt $attempt/$max_attempts..."
        sleep 3
        attempt=$((attempt + 1))
    done

    echo "[LabLink] WARNING: DNS not available after $max_attempts attempts"
    echo "[LabLink] Service will retry on next boot"
    return 1
}

# Wait for network
if ! wait_for_network; then
    echo "[LabLink] Skipping setup due to network unavailability"
    echo "[LabLink] Service will retry on next boot"
    echo "[LabLink] You can manually run this script: sudo /usr/local/bin/lablink-first-boot.sh"
    exit 0
fi

# Sync time BEFORE doing any SSL operations
sync_time

# Wait for DNS to be ready BEFORE downloading anything
if ! wait_for_dns; then
    echo "[LabLink] Skipping setup due to DNS unavailability"
    echo "[LabLink] Service will retry on next boot"
    echo "[LabLink] You can manually run this script: sudo /usr/local/bin/lablink-first-boot.sh"
    exit 0
fi

# Update system
echo "[LabLink] Updating system packages..."
if apt-get update && apt-get upgrade -y; then
    echo "[LabLink] System updated successfully"
else
    echo "[LabLink] WARNING: System update failed, continuing anyway..."
fi

# Install Docker
echo "[LabLink] Installing Docker..."
if curl -fsSL https://get.docker.com | sh; then
    echo "[LabLink] Docker installed successfully"
    usermod -aG docker admin
    echo "[LabLink] Added admin user to docker group"
else
    echo "[LabLink] ERROR: Docker installation failed"
    echo "[LabLink] Service will retry on next boot"
    echo "[LabLink] Or manually run: sudo /usr/local/bin/lablink-first-boot.sh"
    exit 1
fi

# Install LabLink
echo "[LabLink] Downloading LabLink..."
mkdir -p /opt/lablink
cd /opt/lablink

if curl -fL "https://github.com/X9X0/LabLink/archive/refs/heads/__LABLINK_BRANCH__.tar.gz" -o lablink.tar.gz; then
    echo "[LabLink] Download successful, extracting..."
    tar -xzf lablink.tar.gz --strip-components=1
    rm lablink.tar.gz
else
    echo "[LabLink] ERROR: Failed to download LabLink"
    echo "[LabLink] Service will retry on next boot"
    echo "[LabLink] Or manually run: sudo /usr/local/bin/lablink-first-boot.sh"
    exit 1
fi

# Configure environment
if [ -f .env.example ]; then
    cp .env.example .env

    # Generate JWT secret
    JWT_SECRET=$(openssl rand -hex 32)
    sed -i "s/your-secret-key-change-this-in-production/$JWT_SECRET/" .env

    # Set default admin password for web UI
    # Password must meet requirements: 8+ chars, uppercase letter
    #
    # This runs on the Pi, where the build-time environment does not exist, so
    # the password is read from the file the build wrote into the image. It
    # is deliberately not echoed: the journal is world-readable.
    STAGED_PASSWORD_FILE=/etc/lablink-build-admin-password
    if [ -r "$STAGED_PASSWORD_FILE" ]; then
        WEB_ADMIN_PASSWORD=$(cat "$STAGED_PASSWORD_FILE")
    else
        WEB_ADMIN_PASSWORD=""
    fi
    if [ -z "$WEB_ADMIN_PASSWORD" ]; then
        WEB_ADMIN_PASSWORD="LabLink@2025"
        USED_DEFAULT_PASSWORD=yes
    fi

    # Rewrite the line rather than sed it, so no character in the password can
    # be interpreted as a delimiter or backreference.
    grep -v '^LABLINK_DEFAULT_ADMIN_PASSWORD=' .env > .env.tmp || true
    printf 'LABLINK_DEFAULT_ADMIN_PASSWORD=%s\n' "$WEB_ADMIN_PASSWORD" >> .env.tmp
    mv .env.tmp .env
    sed -i "s|LABLINK_DEFAULT_ADMIN_EMAIL=.*|LABLINK_DEFAULT_ADMIN_EMAIL=admin@example.com|" .env

    if [ -z "${USED_DEFAULT_PASSWORD:-}" ]; then
        echo "[LabLink] Environment configured with the admin password set at build time"
        # Consumed: do not leave the plaintext password on the filesystem.
        rm -f "$STAGED_PASSWORD_FILE"
    else
        echo "[LabLink] WARNING: no build-time admin password; using the built-in default."
        echo "[LabLink] Change it immediately: this default is public."
    fi
else
    echo "[LabLink] WARNING: .env.example not found"
fi

# Ensure Docker daemon is fully ready
echo "[LabLink] Ensuring Docker daemon is ready..."
for i in {1..30}; do
    if docker info >/dev/null 2>&1; then
        echo "[LabLink] Docker daemon is ready"
        break
    fi
    echo "[LabLink] Waiting for Docker daemon (attempt $i/30)..."
    sleep 2
done

# Verify Docker is working
if ! docker info >/dev/null 2>&1; then
    echo "[LabLink] ✗ ERROR: Docker daemon is not responding"
    echo "[LabLink] Service will retry on next boot"
    echo "[LabLink] Or manually run: sudo /usr/local/bin/lablink-first-boot.sh"
    exit 1
fi

# Start LabLink
echo "[LabLink] Starting LabLink with Docker Compose..."
if docker compose up -d; then
    echo "[LabLink] LabLink containers starting..."

    # Wait for containers to be healthy
    echo "[LabLink] Waiting for services to be ready..."
    local max_wait=60
    local waited=0
    local containers_up=false

    while [ $waited -lt $max_wait ]; do
        if docker compose ps 2>/dev/null | grep -q "Up"; then
            containers_up=true
            break
        fi
        sleep 2
        waited=$((waited + 2))
        echo "[LabLink] Waiting for containers... ($waited/${max_wait}s)"
    done

    # Check container status
    if [ "$containers_up" = true ]; then
        echo "[LabLink] ✓ LabLink started successfully"

        # Show container status
        echo "[LabLink] Container status:"
        docker compose ps
    else
        echo "[LabLink] ⚠ WARNING: Containers started but may not be healthy"
        echo "[LabLink] Container status:"
        docker compose ps
        echo "[LabLink] Logs:"
        docker compose logs --tail=20
    fi
else
    echo "[LabLink] ✗ ERROR: Failed to start LabLink"
    echo "[LabLink] Docker Compose logs:"
    docker compose logs --tail=50
    echo "[LabLink] Service will retry on next boot"
    echo "[LabLink] Or manually run: sudo /usr/local/bin/lablink-first-boot.sh"
    exit 1
fi

# Enable LabLink on boot
cat > /etc/systemd/system/lablink.service <<EOF
[Unit]
Description=LabLink Server
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=forking
RemainAfterExit=yes
WorkingDirectory=/opt/lablink
# Ensure Docker is fully ready before starting
ExecStartPre=/bin/sleep 2
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
# Wait for containers to be healthy
ExecStartPost=/bin/bash -c 'for i in {1..30}; do if /usr/bin/docker compose ps 2>/dev/null | grep -q "Up"; then exit 0; fi; sleep 1; done; exit 0'
# Restart on failure with backoff
Restart=on-failure
RestartSec=10s
# Give Docker Compose enough time to start containers
TimeoutStartSec=120
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

systemctl enable lablink.service

# Create status check script
cat > /usr/local/bin/lablink-status <<'STATUSSCRIPT'
#!/bin/bash
# LabLink Status Checker

echo "════════════════════════════════════════════════════════"
echo "           LabLink Server Status"
echo "════════════════════════════════════════════════════════"
echo ""

# Check network
echo "Network Status:"
if ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1; then
    echo "  ✓ Internet connectivity: OK"
else
    echo "  ✗ Internet connectivity: OFFLINE"
fi

# Show IP addresses
echo "  IP Addresses:"
ip -4 addr show | grep inet | grep -v 127.0.0.1 | awk '{print "    - " $2}' || echo "    No IP addresses"
echo ""

# Check Docker
echo "Docker Status:"
if systemctl is-active --quiet docker; then
    echo "  ✓ Docker service: Running"
else
    echo "  ✗ Docker service: Not running"
fi
echo ""

# Check LabLink service
echo "LabLink Service Status:"
if systemctl is-active --quiet lablink; then
    echo "  ✓ LabLink service: Enabled and active"
else
    echo "  ⚠ LabLink service: Not active"
    systemctl status lablink --no-pager 2>&1 | head -5 | sed 's/^/    /'
fi
echo ""

# Check LabLink containers
if [ -d /opt/lablink ]; then
    echo "LabLink Containers:"
    cd /opt/lablink
    if docker compose ps 2>/dev/null | grep -q "Up"; then
        docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" | sed 's/^/  /'
        echo ""
        echo "  ✓ LabLink is running"
        echo ""
        echo "Access Points:"
        echo "  Web UI:  http://$(hostname).local"
        echo "  API:     http://$(hostname).local:8000"
        echo "  API Docs: http://$(hostname).local:8000/docs"
    else
        echo "  ✗ No containers running"
        echo ""
        echo "To start LabLink:"
        echo "  cd /opt/lablink && sudo docker compose up -d"
        echo ""
        echo "To view logs:"
        echo "  cd /opt/lablink && sudo docker compose logs -f"
    fi
else
    echo "  ✗ LabLink not installed at /opt/lablink"
fi

echo ""
echo "════════════════════════════════════════════════════════"
echo ""
echo "Useful Commands:"
echo "  lablink-status         - Show this status"
echo "  lablink-start          - Start LabLink"
echo "  lablink-stop           - Stop LabLink"
echo "  lablink-restart        - Restart LabLink"
echo "  lablink-logs           - View LabLink logs"
echo "  lablink-update         - Update code and rebuild containers"
echo ""
STATUSSCRIPT

chmod +x /usr/local/bin/lablink-status

# Create convenience commands
cat > /usr/local/bin/lablink-start <<'STARTSCRIPT'
#!/bin/bash
echo "Starting LabLink..."
cd /opt/lablink && sudo docker compose up -d
sleep 3
lablink-status
STARTSCRIPT
chmod +x /usr/local/bin/lablink-start

cat > /usr/local/bin/lablink-stop <<'STOPSCRIPT'
#!/bin/bash
echo "Stopping LabLink..."
cd /opt/lablink && sudo docker compose down
echo "LabLink stopped."
STOPSCRIPT
chmod +x /usr/local/bin/lablink-stop

cat > /usr/local/bin/lablink-restart <<'RESTARTSCRIPT'
#!/bin/bash
echo "Restarting LabLink..."
cd /opt/lablink && sudo docker compose restart
sleep 3
lablink-status
RESTARTSCRIPT
chmod +x /usr/local/bin/lablink-restart

cat > /usr/local/bin/lablink-logs <<'LOGSSCRIPT'
#!/bin/bash
cd /opt/lablink && sudo docker compose logs -f --tail=100
LOGSSCRIPT
chmod +x /usr/local/bin/lablink-logs

cat > /usr/local/bin/lablink-update <<'UPDATESCRIPT'
#!/bin/bash
# LabLink Update Script
# Updates code from git and rebuilds containers

echo "╔═══════════════════════════════════════════════════════╗"
echo "║                                                       ║"
echo "║            LabLink Update & Rebuild                   ║"
echo "║                                                       ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

cd /opt/lablink || exit 1

echo "Step 1: Checking current version..."
CURRENT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
echo "  Current commit: $CURRENT_COMMIT"
echo ""

echo "Step 2: Pulling latest code from git..."
if git pull; then
    NEW_COMMIT=$(git rev-parse --short HEAD)
    echo "  ✓ Code updated to: $NEW_COMMIT"

    if [ "$CURRENT_COMMIT" = "$NEW_COMMIT" ]; then
        echo "  Already up to date!"
        read -p "Rebuild anyway? (y/N): " rebuild
        if [ "$rebuild" != "y" ] && [ "$rebuild" != "Y" ]; then
            echo "No rebuild needed. Exiting."
            exit 0
        fi
    fi
else
    echo "  ✗ Git pull failed"
    echo "  Continuing with rebuild anyway..."
fi
echo ""

echo "Step 3: Stopping containers..."
docker compose down
echo ""

echo "Step 4: Rebuilding containers (this may take 2-3 minutes)..."
if docker compose build --no-cache; then
    echo "  ✓ Rebuild successful"
else
    echo "  ✗ Rebuild failed"
    echo "  Check logs above for errors"
    exit 1
fi
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

# Show final status
lablink-status
UPDATESCRIPT
chmod +x /usr/local/bin/lablink-update

echo "[LabLink] First boot setup complete!"
echo "[LabLink] ════════════════════════════════════════════════════════"
echo "[LabLink] "
echo "[LabLink] ✓ Setup completed successfully!"
echo "[LabLink] "
echo "[LabLink] Access LabLink at: http://$(hostname).local"
echo "[LabLink] "
echo "[LabLink] Useful commands:"
echo "[LabLink]   lablink-status  - Check LabLink status"
echo "[LabLink]   lablink-logs    - View logs"
echo "[LabLink]   lablink-update  - Update to latest code"
echo "[LabLink] "
echo "[LabLink] ════════════════════════════════════════════════════════"
echo "[LabLink] Completed at: $(date)"

# Run status check to show final state
echo ""
/usr/local/bin/lablink-status

# Mark setup as complete
touch /var/lib/lablink-setup-complete
echo "[LabLink] Setup marked as complete"

# Disable this script from running again
systemctl disable lablink-first-boot.service
