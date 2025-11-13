# LabLink Deployment Guide

Complete guide for deploying LabLink Server and Client with maximum simplicity.

## 📋 Table of Contents

- [Quick Start](#-quick-start)
- [Server Deployment](#️-server-deployment)
- [Client Installation](#-client-installation)
- [Raspberry Pi Imaging](#-raspberry-pi-imaging-gui-based-deployment)
- [Docker Deployment](#-docker-deployment)
- [Network Configuration](#-network-configuration)
- [Production Best Practices](#-production-best-practices)
- [Troubleshooting](#-troubleshooting)

---

## 🚀 Quick Start

### Server (One Command)

```bash
# Linux / Raspberry Pi / macOS
curl -fsSL https://raw.githubusercontent.com/X9X0/LabLink/main/install-server.sh | bash
```

### Client (One Command)

```bash
# Linux / macOS
curl -fsSL https://raw.githubusercontent.com/X9X0/LabLink/main/install-client.sh | bash

# Windows (PowerShell as Administrator)
iwr -useb https://raw.githubusercontent.com/X9X0/LabLink/main/install-client.ps1 | iex
```

That's it! The automated installers handle everything.

---

## 🖥️ Server Deployment

### Option 1: Automated Installer (Recommended)

The installer detects your OS, installs dependencies (including Docker), and deploys LabLink automatically.

**Interactive Mode:**
```bash
wget https://raw.githubusercontent.com/X9X0/LabLink/main/install-server.sh
chmod +x install-server.sh
./install-server.sh
```

**Non-Interactive Mode:**
```bash
export LABLINK_DIR=$HOME/lablink
export USE_DOCKER=yes
export START_ON_BOOT=yes
./install-server.sh
```

**What it does:**
1. ✅ Detects OS (Raspberry Pi OS, Ubuntu, Debian, Fedora, etc.)
2. ✅ Checks Python 3.8+ is installed
3. ✅ Installs Docker and Docker Compose (if USE_DOCKER=yes)
4. ✅ Downloads LabLink from GitHub
5. ✅ Configures environment with secure JWT secret
6. ✅ Deploys with Docker Compose or native Python
7. ✅ Sets up systemd service for auto-start on boot

### Option 2: Manual Docker Compose

```bash
# Clone repository
git clone https://github.com/X9X0/LabLink.git
cd LabLink

# Configure environment
cp .env.example .env
nano .env  # Edit settings

# Generate secure JWT secret
openssl rand -hex 32  # Copy to .env

# Start services
docker compose up -d

# View logs
docker compose logs -f lablink-server
```

### Option 3: Native Python Installation

```bash
# Clone repository
git clone https://github.com/X9X0/LabLink.git
cd LabLink/server

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run server
python main.py
```

**Access:**
- **API:** http://localhost:8000
- **Web Dashboard:** http://localhost:80
- **API Docs:** http://localhost:8000/docs

---

## 💻 Client Installation

### Windows

**Automated Installer (Recommended):**
```powershell
# Run PowerShell as Administrator
iwr -useb https://raw.githubusercontent.com/X9X0/LabLink/main/install-client.ps1 | iex
```

**What it does:**
- ✅ Checks/installs Python 3.8+
- ✅ Optionally installs Git
- ✅ Downloads LabLink
- ✅ Creates Python virtual environment
- ✅ Installs all dependencies
- ✅ Creates desktop and Start Menu shortcuts
- ✅ Creates launch script

**Manual Installation:**
1. Install Python 3.8+ from [python.org](https://python.org)
2. Download: `git clone https://github.com/X9X0/LabLink.git`
3. Install:
   ```cmd
   cd LabLink\client
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   python main.py
   ```

### macOS

**Automated Installer:**
```bash
curl -fsSL https://raw.githubusercontent.com/X9X0/LabLink/main/install-client.sh | bash
```

**What it does:**
- ✅ Checks/installs Python via Homebrew
- ✅ Downloads LabLink
- ✅ Installs dependencies
- ✅ Creates .app bundle in ~/Applications
- ✅ Creates launch script

### Linux

**Automated Installer:**
```bash
curl -fsSL https://raw.githubusercontent.com/X9X0/LabLink/main/install-client.sh | bash
```

**What it does:**
- ✅ Installs system dependencies (Qt libraries)
- ✅ Downloads LabLink
- ✅ Installs Python dependencies
- ✅ Creates .desktop file and menu entry
- ✅ Creates launch script

---

## 🥧 Raspberry Pi Imaging (GUI-Based Deployment)

LabLink provides a complete GUI-based workflow for deploying to Raspberry Pi devices with zero command-line knowledge required.

### Overview

1. **Build Image** - Create a custom Raspberry Pi image with LabLink pre-installed
2. **Write to SD Card** - Write the image to an SD card
3. **Boot Raspberry Pi** - Insert SD card and power on
4. **Auto-Configuration** - LabLink starts automatically on first boot

### Building a Raspberry Pi Image

**From the Client GUI:**

1. Open LabLink Client
2. Go to **Tools → Build Raspberry Pi Image...**
3. Configure settings:
   - **Hostname**: `lablink-pi` (default)
   - **Admin Password**: Set a secure password (optional, default is `raspberry`)
   - **Wi-Fi SSID**: Your network name (optional)
   - **Wi-Fi Password**: Your network password (optional)
   - **Enable SSH**: ✅ (recommended)
   - **Auto-expand filesystem**: ✅ (recommended)
4. Choose output location
5. Click **Next** and wait for build to complete (10-30 minutes)

**From Command Line (Linux only):**

```bash
# Run the build script
./build-pi-image.sh

# Or with custom settings
OUTPUT_IMAGE=~/lablink-pi.img \
PI_HOSTNAME=my-lablink \
WIFI_SSID="MyNetwork" \
WIFI_PASSWORD="MyPassword" \
ADMIN_PASSWORD="secure123" \
./build-pi-image.sh
```

**What the image includes:**
- ✅ Raspberry Pi OS Lite (latest)
- ✅ Docker and Docker Compose
- ✅ LabLink Server (latest from GitHub)
- ✅ Automatic first-boot configuration
- ✅ systemd service for auto-start
- ✅ Pre-configured networking (if Wi-Fi provided)
- ✅ SSH enabled (if selected)
- ✅ Filesystem auto-expansion

### Writing Image to SD Card

**From the Client GUI:**

1. Insert SD card into your computer
2. Open LabLink Client
3. Go to **Tools → Write Raspberry Pi Image to SD Card...**
4. Select the image file you built
5. Select the target SD card device
6. ⚠️ **WARNING**: Double-check the device - all data will be erased!
7. Enable **Verify after writing** (recommended)
8. Click **Write Image**
9. Wait for write and verification to complete
10. Safely eject the SD card

**Platform-Specific Notes:**

- **Linux**: Requires `sudo` privileges for writing to block devices
- **macOS**: Requires admin password, uses `dd` command
- **Windows**: Currently provides manual instructions (use [Etcher](https://www.balena.io/etcher/) or [Rufus](https://rufus.ie/))

**Manual Write (Linux/macOS):**

```bash
# Linux
sudo dd if=lablink-pi.img of=/dev/sdX bs=4M status=progress
sudo sync

# macOS
sudo dd if=lablink-pi.img of=/dev/diskX bs=4m
sudo diskutil eject /dev/diskX
```

Replace `/dev/sdX` (Linux) or `/dev/diskX` (macOS) with your actual SD card device.

### First Boot

1. **Insert SD card** into Raspberry Pi
2. **Power on** Raspberry Pi
3. **Wait for configuration** (2-5 minutes on first boot)
   - Filesystem expansion
   - Network connection (if Wi-Fi configured)
   - Docker installation
   - LabLink download and startup
4. **Connect from Client**:
   - Find Pi IP address: `sudo nmap -sn 192.168.1.0/24` or check your router
   - In LabLink Client: **File → Connect to Server**
   - Enter: `<raspberry-pi-ip>:8000` (API port)
   - Enter: `<raspberry-pi-ip>:8001` (WebSocket port)

### Accessing the Raspberry Pi

**SSH Access (if enabled):**

```bash
ssh pi@<raspberry-pi-ip>
# Default password: raspberry (or your custom password)
```

**LabLink Service Management:**

```bash
# View logs
sudo journalctl -u lablink.service -f

# Restart service
sudo systemctl restart lablink.service

# Stop service
sudo systemctl stop lablink.service

# Check status
sudo systemctl status lablink.service
```

**Docker Management:**

```bash
cd /opt/lablink
docker compose logs -f        # View logs
docker compose restart        # Restart services
docker compose down           # Stop services
docker compose up -d          # Start services
```

### Updating LabLink on Raspberry Pi

```bash
ssh pi@<raspberry-pi-ip>
cd /opt/lablink
git pull
docker compose down
docker compose up -d --build
```

### Troubleshooting Pi Imaging

**Build Issues:**

- **Script not found**: Ensure `build-pi-image.sh` is in LabLink root directory
- **Permission denied**: Script may need execute permission: `chmod +x build-pi-image.sh`
- **Download failed**: Check internet connection
- **Insufficient space**: Need at least 8 GB free disk space

**Write Issues:**

- **No drives detected**: Try refreshing drive list or use manual method
- **Permission denied (Linux)**: Run client with sudo or add user to `disk` group
- **Write failed**: Check SD card isn't write-protected
- **Verification failed**: Try a different SD card, may be faulty

**Boot Issues:**

- **Pi doesn't boot**: Re-write image, ensure SD card is properly seated
- **Can't find Pi on network**: Connect monitor and keyboard to check IP address
- **LabLink not starting**: SSH in and check logs: `sudo journalctl -u lablink.service -f`
- **Wi-Fi not connecting**: Re-configure with correct credentials or use Ethernet

---

## 🐳 Docker Deployment

### Basic Setup (Server + Web)

```bash
docker compose up -d
```

Services started:
- `lablink-server` - FastAPI backend (ports 8000, 8001)
- `lablink-web` - nginx serving web dashboard (port 80)

### Full Setup (All Services)

```bash
docker compose --profile full up -d
```

Additional services:
- `redis` - Caching and rate limiting
- `postgres` - Production database
- `grafana` - Monitoring dashboards (port 3000)
- `prometheus` - Metrics collection

### Available Profiles

| Profile | Services | Use Case |
|---------|----------|----------|
| `default` | server, web | Basic deployment |
| `caching` | + redis | Better performance |
| `postgres` | + postgres | Production database |
| `monitoring` | + grafana, prometheus | Monitoring |
| `full` | All services | Complete stack |

**Examples:**
```bash
# With caching
docker compose --profile caching up -d

# With monitoring
docker compose --profile monitoring up -d

# Everything
docker compose --profile full up -d
```

### Environment Configuration

Edit `.env` file:
```bash
# Ports
LABLINK_API_PORT=8000
LABLINK_WEB_PORT=80

# Security (REQUIRED in production)
LABLINK_JWT_SECRET_KEY=your-secret-here  # Generate with: openssl rand -hex 32

# OAuth2 (optional)
LABLINK_OAUTH_GOOGLE_CLIENT_ID=...
LABLINK_OAUTH_GITHUB_CLIENT_ID=...

# Database (for postgres profile)
POSTGRES_PASSWORD=secure-password-here

# Monitoring (for monitoring profile)
GRAFANA_ADMIN_PASSWORD=secure-password-here
```

### Docker Commands

```bash
# Start services
docker compose up -d

# Stop services
docker compose down

# View logs
docker compose logs -f

# View specific service logs
docker compose logs -f lablink-server

# Restart services
docker compose restart

# Update and restart
git pull
docker compose build
docker compose up -d

# Clean up everything
docker compose down -v  # WARNING: Deletes data volumes
```

---

## 🌐 Network Configuration

### Firewall Rules

**Ubuntu/Debian:**
```bash
sudo ufw allow 8000/tcp  # API
sudo ufw allow 8001/tcp  # WebSocket
sudo ufw allow 80/tcp    # Web Dashboard
sudo ufw allow 443/tcp   # HTTPS (if configured)
sudo ufw enable
```

**Raspberry Pi OS:**
```bash
sudo iptables -A INPUT -p tcp --dport 8000 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 8001 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables-save | sudo tee /etc/iptables/rules.v4
```

### Finding Your Server

```bash
# Get server IP
hostname -I | awk '{print $1}'

# Or
ip addr show | grep 'inet ' | grep -v 127.0.0.1
```

**Local Network Access:**
- Server available at `hostname.local` (mDNS/Bonjour)
- Example: `raspberrypi.local` or `ubuntu.local`
- Works on macOS, Linux, and Windows 10+

### Port Forwarding (Remote Access)

1. Configure router to forward ports to server IP:
   - 8000 → Server API
   - 8001 → WebSocket
   - 80 → Web Dashboard
   - 443 → HTTPS (recommended)

2. Use dynamic DNS for stable hostname:
   - DuckDNS, No-IP, DynDNS, etc.

3. **Security:** Use HTTPS and strong authentication for internet-facing servers

---

## 🔒 Production Best Practices

### Security Checklist

- [ ] **Generate Strong JWT Secret**
  ```bash
  openssl rand -hex 32
  # Add to .env: LABLINK_JWT_SECRET_KEY=<secret>
  ```

- [ ] **Enable HTTPS**
  ```bash
  # Install certbot
  sudo apt install certbot python3-certbot-nginx

  # Get free SSL certificate
  sudo certbot --nginx -d yourdomain.com
  ```

- [ ] **Configure OAuth2** (optional but recommended)
  - Create OAuth2 apps for Google/GitHub/Microsoft
  - Add credentials to .env
  - Users can login with social accounts

- [ ] **Enable Multi-Factor Authentication**
  - Require 2FA for all users
  - Users set up in Settings page

- [ ] **Set Strong Passwords**
  - Postgres: Change `POSTGRES_PASSWORD` in .env
  - Grafana: Change `GRAFANA_ADMIN_PASSWORD` in .env

- [ ] **Configure Backups**
  - Enable automatic backups in server settings
  - Store backups off-site (cloud, NAS)

- [ ] **Enable Monitoring**
  ```bash
  docker compose --profile monitoring up -d
  # Access Grafana at http://server:3000
  ```

- [ ] **Restrict Network Access**
  - Use firewall rules
  - Consider VPN for remote access
  - Enable IP whitelisting in security settings

### Resource Limits

Adjust in `docker-compose.yml` or `.env`:
```bash
# For Raspberry Pi (limited resources)
LABLINK_CPU_LIMIT=1
LABLINK_MEM_LIMIT=512M

# For powerful servers
LABLINK_CPU_LIMIT=4
LABLINK_MEM_LIMIT=2G
```

### Database Selection

**SQLite (Default):**
- ✅ Simple, no configuration
- ✅ Perfect for single-user or small teams
- ❌ Limited concurrent writes

**PostgreSQL (Production):**
- ✅ Better performance
- ✅ Better concurrent access
- ✅ Better for multiple users
- ❌ Requires configuration

```bash
# Enable PostgreSQL
docker compose --profile postgres up -d

# Configure connection in .env
LABLINK_DATABASE_URL=postgresql://lablink:password@postgres:5432/lablink
```

---

## 🛠️ Troubleshooting

### Server Won't Start

**Check logs:**
```bash
# Docker
docker compose logs lablink-server

# Native
tail -f server/logs/lablink.log

# Systemd
journalctl -u lablink.service -f
```

**Common Issues:**

1. **Port in use:**
   ```bash
   sudo lsof -i :8000
   # Change LABLINK_API_PORT in .env if needed
   ```

2. **Permission denied (USB):**
   ```bash
   sudo usermod -aG dialout $USER
   # Log out and back in
   ```

3. **Docker permission:**
   ```bash
   sudo usermod -aG docker $USER
   # Log out and back in
   ```

### Client Can't Connect

1. **Verify server is running:**
   ```bash
   curl http://server-ip:8000/health
   ```

2. **Check firewall:**
   ```bash
   sudo ufw status
   sudo ufw allow 8000/tcp
   ```

3. **Test connectivity:**
   ```bash
   ping server-ip
   telnet server-ip 8000
   ```

### Equipment Not Detected

1. **Check USB:**
   ```bash
   lsusb  # Should show equipment
   ```

2. **Check permissions:**
   ```bash
   ls -l /dev/ttyUSB*  # Or /dev/ttyACM*
   sudo usermod -aG dialout $USER
   ```

3. **Verify VISA backend:**
   ```bash
   # In .env
   LABLINK_VISA_BACKEND=@py  # Pure Python (default)
   ```

### Performance Issues

1. **Check resources:**
   ```bash
   docker stats
   htop
   ```

2. **Enable caching:**
   ```bash
   docker compose --profile caching up -d
   ```

3. **Increase limits:**
   Edit .env:
   ```bash
   LABLINK_CPU_LIMIT=4
   LABLINK_MEM_LIMIT=2G
   ```

---

## 📚 Additional Resources

- **API Docs:** `http://your-server:8000/docs`
- **GitHub:** [https://github.com/X9X0/LabLink](https://github.com/X9X0/LabLink)
- **Issues:** [https://github.com/X9X0/LabLink/issues](https://github.com/X9X0/LabLink/issues)

---

## 🆘 Getting Help

1. Check [Troubleshooting](#-troubleshooting)
2. Search [existing issues](https://github.com/X9X0/LabLink/issues)
3. Create [new issue](https://github.com/X9X0/LabLink/issues/new) with:
   - LabLink version
   - OS and version
   - Error messages
   - Steps to reproduce

---

**Last Updated:** 2025-11-13
**Version:** 0.27.0
