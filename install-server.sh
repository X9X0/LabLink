#!/bin/bash
# LabLink Server - Automated Installation Script
# Supports: Raspberry Pi OS, Ubuntu, Debian, and similar distributions
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/X9X0/LabLink/main/install-server.sh | bash
#   OR
#   ./install-server.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
LABLINK_DIR="${LABLINK_DIR:-$HOME/lablink}"
LABLINK_VERSION="${LABLINK_VERSION:-latest}"
INSTALL_DOCKER="${INSTALL_DOCKER:-yes}"
START_ON_BOOT="${START_ON_BOOT:-yes}"
USE_DOCKER="${USE_DOCKER:-yes}"

# Functions
print_header() {
    echo -e "${BLUE}"
    echo "╔═══════════════════════════════════════════════════════╗"
    echo "║                                                       ║"
    echo "║            LabLink Server Installation                ║"
    echo "║         Laboratory Equipment Control System           ║"
    echo "║                                                       ║"
    echo "╚═══════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

detect_os() {
    print_step "Detecting operating system..."

    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        OS_VERSION=$VERSION_ID
    else
        print_error "Cannot detect OS. /etc/os-release not found."
        exit 1
    fi

    print_step "Detected: $PRETTY_NAME"

    case "$OS" in
        raspbian|debian|ubuntu)
            PKG_MANAGER="apt"
            ;;
        centos|rhel|fedora)
            PKG_MANAGER="yum"
            ;;
        *)
            print_warning "Unsupported OS: $OS. Attempting to continue..."
            PKG_MANAGER="apt"
            ;;
    esac
}

check_requirements() {
    print_step "Checking requirements..."

    # Check if running as root
    if [ "$EUID" -eq 0 ]; then
        print_warning "Running as root. This is not recommended."
        SUDO=""
    else
        SUDO="sudo"
    fi

    # Check Python version
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
        print_step "Python $PYTHON_VERSION found"

        if python3 -c 'import sys; exit(0 if sys.version_info >= (3, 8) else 1)'; then
            print_step "Python version OK (>= 3.8)"
        else
            print_error "Python 3.8 or higher is required"
            exit 1
        fi
    else
        print_error "Python 3 not found. Please install Python 3.8+"
        exit 1
    fi

    # Check available disk space (need at least 1GB)
    AVAILABLE_SPACE=$(df -BG . | tail -1 | awk '{print $4}' | sed 's/G//')
    if [ "$AVAILABLE_SPACE" -lt 1 ]; then
        print_error "Insufficient disk space. Need at least 1GB free."
        exit 1
    fi

    print_step "Disk space OK (${AVAILABLE_SPACE}GB available)"
}

install_docker() {
    if [ "$INSTALL_DOCKER" != "yes" ]; then
        print_step "Skipping Docker installation (disabled)"
        return
    fi

    if command -v docker &> /dev/null; then
        print_step "Docker already installed ($(docker --version))"

        # Check Docker Compose
        if docker compose version &> /dev/null; then
            print_step "Docker Compose already installed"
            return
        fi
    fi

    print_step "Installing Docker..."

    # Install Docker using official script
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    $SUDO sh /tmp/get-docker.sh
    rm /tmp/get-docker.sh

    # Add current user to docker group
    if [ -n "$SUDO" ]; then
        $SUDO usermod -aG docker "$USER"
        print_warning "User added to docker group. You may need to log out and back in."
    fi

    # Start Docker service
    $SUDO systemctl enable docker
    $SUDO systemctl start docker

    print_step "Docker installed successfully"
}

download_lablink() {
    print_step "Downloading LabLink..."

    # Create installation directory
    mkdir -p "$LABLINK_DIR"
    cd "$LABLINK_DIR"

    # Check if git is available
    if command -v git &> /dev/null; then
        print_step "Cloning LabLink repository..."
        if [ -d ".git" ]; then
            git pull
        else
            git clone https://github.com/X9X0/LabLink.git .
        fi
    else
        print_step "Git not found. Downloading archive..."
        curl -L https://github.com/X9X0/LabLink/archive/refs/heads/main.tar.gz -o /tmp/lablink.tar.gz
        tar -xzf /tmp/lablink.tar.gz --strip-components=1 -C "$LABLINK_DIR"
        rm /tmp/lablink.tar.gz
    fi

    print_step "LabLink downloaded to $LABLINK_DIR"
}

setup_environment() {
    print_step "Setting up environment..."

    cd "$LABLINK_DIR"

    # Copy .env.example to .env if it doesn't exist
    if [ ! -f .env ]; then
        cp .env.example .env

        # Generate random JWT secret
        JWT_SECRET=$(openssl rand -hex 32)
        sed -i "s/your-secret-key-change-this-in-production/$JWT_SECRET/" .env

        print_step "Created .env file with generated JWT secret"
    else
        print_step ".env file already exists"
    fi

    # Make version check script executable
    if [ -f "lablink-version.sh" ]; then
        chmod +x lablink-version.sh

        # Create symlink in /usr/local/bin for easy access
        if [ -w /usr/local/bin ] || [ -n "$SUDO" ]; then
            $SUDO ln -sf "$LABLINK_DIR/lablink-version.sh" /usr/local/bin/lablink-version
            print_step "Installed 'lablink-version' command"
        fi
    fi
}

deploy_with_docker() {
    print_step "Deploying with Docker Compose..."

    cd "$LABLINK_DIR"

    # Pull images
    docker compose pull

    # Build custom images
    docker compose build

    # Start services
    docker compose up -d

    print_step "Docker containers started"

    # Wait for services to be healthy
    print_step "Waiting for services to start..."
    sleep 10

    # Check container status
    docker compose ps
}

deploy_native() {
    print_step "Deploying natively (without Docker)..."

    cd "$LABLINK_DIR/server"

    # Create virtual environment
    if [ ! -d "venv" ]; then
        python3 -m venv venv
        print_step "Created Python virtual environment"
    fi

    # Activate virtual environment
    source venv/bin/activate

    # Install dependencies
    print_step "Installing Python dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt

    print_step "Dependencies installed"

    # Create systemd service if requested
    if [ "$START_ON_BOOT" = "yes" ]; then
        setup_systemd_service
    fi

    # Start server
    print_step "Starting LabLink server..."
    nohup python main.py > ../logs/lablink.log 2>&1 &
    echo $! > ../lablink.pid

    print_step "Server started (PID: $(cat ../lablink.pid))"
}

setup_systemd_service() {
    print_step "Setting up systemd service..."

    SERVICE_FILE="/etc/systemd/system/lablink.service"

    $SUDO tee $SERVICE_FILE > /dev/null <<EOF
[Unit]
Description=LabLink Server
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$LABLINK_DIR/server
Environment="PATH=$LABLINK_DIR/server/venv/bin"
ExecStart=$LABLINK_DIR/server/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    $SUDO systemctl daemon-reload
    $SUDO systemctl enable lablink.service
    $SUDO systemctl start lablink.service

    print_step "Systemd service created and started"
}

print_success() {
    echo ""
    echo -e "${GREEN}"
    echo "╔═══════════════════════════════════════════════════════╗"
    echo "║                                                       ║"
    echo "║          LabLink Server Installed Successfully!      ║"
    echo "║                                                       ║"
    echo "╚═══════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    echo "Installation Directory: $LABLINK_DIR"
    echo ""
    echo "Next Steps:"
    echo "  1. Access the web dashboard: http://$(hostname -I | awk '{print $1}'):80"
    echo "  2. API documentation: http://$(hostname -I | awk '{print $1}'):8000/docs"
    echo "  3. Connect to server:"
    echo "     - Host: $(hostname -I | awk '{print $1}')"
    echo "     - API Port: 8000"
    echo "     - WebSocket Port: 8001"
    echo ""

    if [ "$USE_DOCKER" = "yes" ]; then
        echo "Docker Commands:"
        echo "  View logs:     docker compose logs -f"
        echo "  Stop services: docker compose down"
        echo "  Restart:       docker compose restart"
    else
        echo "Service Commands:"
        echo "  View logs:     journalctl -u lablink.service -f"
        echo "  Stop service:  sudo systemctl stop lablink.service"
        echo "  Restart:       sudo systemctl restart lablink.service"
    fi

    echo ""
    echo "Utility Commands:"
    echo "  Check version: lablink-version"
    echo ""
    echo "For help and documentation: https://docs.lablink.io"
    echo ""
}

# Main installation flow
main() {
    print_header

    # Prompt for installation options (if running interactively)
    if [ -t 0 ]; then
        echo "Installation Options:"
        read -p "Install with Docker? (yes/no) [yes]: " USE_DOCKER_INPUT
        USE_DOCKER="${USE_DOCKER_INPUT:-yes}"

        read -p "Start on boot? (yes/no) [yes]: " START_ON_BOOT_INPUT
        START_ON_BOOT="${START_ON_BOOT_INPUT:-yes}"

        read -p "Installation directory [$LABLINK_DIR]: " LABLINK_DIR_INPUT
        LABLINK_DIR="${LABLINK_DIR_INPUT:-$LABLINK_DIR}"
        echo ""
    fi

    detect_os
    check_requirements

    if [ "$USE_DOCKER" = "yes" ]; then
        install_docker
    fi

    download_lablink
    setup_environment

    if [ "$USE_DOCKER" = "yes" ]; then
        deploy_with_docker
    else
        deploy_native
    fi

    print_success
}

# Run main installation
main "$@"
