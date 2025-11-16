#!/bin/bash
# LabLink Raspberry Pi Image Builder
# Creates a bootable Raspberry Pi image with LabLink pre-installed
#
# Requirements: Linux host with root access, qemu-user-static, kpartx
# Usage: sudo ./build-pi-image.sh [output-image-name.img]

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
PI_OS_VERSION="${PI_OS_VERSION:-2024-03-15}"
PI_OS_URL="https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-${PI_OS_VERSION}/2024-03-15-raspios-bookworm-arm64-lite.img.xz"
OUTPUT_IMAGE="${1:-lablink-pi-$(date +%Y%m%d).img}"
WORK_DIR="/tmp/lablink-pi-build"
MOUNT_BOOT="$WORK_DIR/boot"
MOUNT_ROOT="$WORK_DIR/root"

# LabLink configuration
LABLINK_VERSION="${LABLINK_VERSION:-latest}"
LABLINK_HOSTNAME="${LABLINK_HOSTNAME:-lablink}"
ENABLE_SSH="${ENABLE_SSH:-yes}"
WIFI_SSID="${WIFI_SSID:-}"
WIFI_PASSWORD="${WIFI_PASSWORD:-}"
LABLINK_ADMIN_PASSWORD="${LABLINK_ADMIN_PASSWORD:-lablink}"

# Functions
print_header() {
    echo -e "${BLUE}"
    echo "╔═══════════════════════════════════════════════════════╗"
    echo "║                                                       ║"
    echo "║       LabLink Raspberry Pi Image Builder             ║"
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

check_root() {
    if [ "$EUID" -ne 0 ]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

check_dependencies() {
    print_step "Checking dependencies..."

    local missing=()

    for cmd in wget xz kpartx qemu-arm-static losetup parted; do
        if ! command -v $cmd &> /dev/null; then
            missing+=($cmd)
        fi
    done

    if [ ${#missing[@]} -gt 0 ]; then
        print_error "Missing dependencies: ${missing[*]}"
        echo ""
        echo "Install with:"
        echo "  Ubuntu/Debian: sudo apt install wget xz-utils kpartx qemu-user-static parted"
        echo "  Fedora: sudo dnf install wget xz kpartx qemu-user-static parted"
        exit 1
    fi

    print_step "All dependencies found"
}

download_pi_os() {
    print_step "Downloading Raspberry Pi OS..."

    local pi_os_file="$WORK_DIR/raspios.img.xz"

    if [ -f "$pi_os_file" ]; then
        print_step "Using cached Raspberry Pi OS image"
    else
        wget -O "$pi_os_file" "$PI_OS_URL" || {
            print_error "Failed to download Raspberry Pi OS"
            exit 1
        }
    fi

    print_step "Extracting image..."
    xz -d -k -f "$pi_os_file" || {
        print_error "Failed to extract Raspberry Pi OS image"
        exit 1
    }

    local extracted_img="${pi_os_file%.xz}"

    # Verify extraction succeeded
    if [ ! -f "$extracted_img" ]; then
        print_error "Extracted image not found at: $extracted_img"
        ls -lh "$WORK_DIR/" || true
        exit 1
    fi

    print_step "Image extracted successfully: $extracted_img"

    echo "$extracted_img"
}

expand_image() {
    local img_file="$1"
    local extra_space_mb="$2"

    print_step "Expanding image by ${extra_space_mb}MB..."

    # Debug: verify file exists before dd
    if [ ! -f "$img_file" ]; then
        print_error "Image file not found before expand: $img_file"
        ls -lh "$(dirname "$img_file")/" || true
        exit 1
    fi

    print_step "Image file verified: $(ls -lh "$img_file")"

    # Add extra space for LabLink installation
    dd if=/dev/zero bs=1M count=$extra_space_mb >> "$img_file" 2>&1 || {
        print_error "Failed to expand image with dd"
        exit 1
    }

    # Resize partition
    parted "$img_file" resizepart 2 100% || true

    print_step "Image expanded"
}

mount_image() {
    local img_file="$1"

    print_step "Mounting image..."

    # Set up loop device
    LOOP_DEVICE=$(losetup -f --show -P "$img_file")
    print_step "Loop device: $LOOP_DEVICE"

    # Wait for partitions
    sleep 2

    # Mount partitions
    mkdir -p "$MOUNT_BOOT" "$MOUNT_ROOT"

    mount "${LOOP_DEVICE}p1" "$MOUNT_BOOT"
    mount "${LOOP_DEVICE}p2" "$MOUNT_ROOT"

    # Resize root filesystem
    resize2fs "${LOOP_DEVICE}p2" || true

    print_step "Image mounted at $MOUNT_ROOT"
}

unmount_image() {
    print_step "Unmounting image..."

    sync

    umount "$MOUNT_BOOT" || true
    umount "$MOUNT_ROOT" || true

    if [ -n "$LOOP_DEVICE" ]; then
        losetup -d "$LOOP_DEVICE" || true
    fi

    print_step "Image unmounted"
}

configure_first_boot() {
    print_step "Configuring first boot..."

    # Enable SSH
    if [ "$ENABLE_SSH" = "yes" ]; then
        touch "$MOUNT_BOOT/ssh"
        print_step "SSH enabled"
    fi

    # Configure Wi-Fi
    if [ -n "$WIFI_SSID" ]; then
        cat > "$MOUNT_BOOT/wpa_supplicant.conf" <<EOF
country=US
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="$WIFI_SSID"
    psk="$WIFI_PASSWORD"
}
EOF
        print_step "Wi-Fi configured"
    fi

    # Set hostname
    echo "$LABLINK_HOSTNAME" > "$MOUNT_ROOT/etc/hostname"

    # Update /etc/hosts
    sed -i "s/raspberrypi/$LABLINK_HOSTNAME/g" "$MOUNT_ROOT/etc/hosts"

    print_step "Hostname set to: $LABLINK_HOSTNAME"
}

install_lablink() {
    print_step "Installing LabLink server..."

    # Copy qemu-arm-static for chroot
    cp /usr/bin/qemu-arm-static "$MOUNT_ROOT/usr/bin/" || \
    cp /usr/bin/qemu-aarch64-static "$MOUNT_ROOT/usr/bin/qemu-arm-static" || {
        print_warning "Could not copy qemu-arm-static, chroot may not work"
    }

    # Create first-boot script
    cat > "$MOUNT_ROOT/usr/local/bin/lablink-first-boot.sh" <<'FIRSTBOOT'
#!/bin/bash
# LabLink First Boot Setup

set -e

echo "[LabLink] Starting first boot setup..."

# Update system
apt-get update
apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
usermod -aG docker pi

# Install LabLink
mkdir -p /opt/lablink
cd /opt/lablink

# Download LabLink
curl -L https://github.com/X9X0/LabLink/archive/refs/heads/main.tar.gz -o lablink.tar.gz
tar -xzf lablink.tar.gz --strip-components=1
rm lablink.tar.gz

# Configure environment
cp .env.example .env

# Generate JWT secret
JWT_SECRET=$(openssl rand -hex 32)
sed -i "s/your-secret-key-change-this-in-production/$JWT_SECRET/" .env

# Set default admin password
sed -i "s/LABLINK_ADMIN_PASSWORD=.*/LABLINK_ADMIN_PASSWORD=${LABLINK_ADMIN_PASSWORD}/" .env

# Start LabLink
docker compose up -d

# Enable LabLink on boot
cat > /etc/systemd/system/lablink.service <<EOF
[Unit]
Description=LabLink Server
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/lablink
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down

[Install]
WantedBy=multi-user.target
EOF

systemctl enable lablink.service

echo "[LabLink] First boot setup complete!"
echo "[LabLink] Access at http://$(hostname).local"

# Disable this script from running again
systemctl disable lablink-first-boot.service

FIRSTBOOT

    chmod +x "$MOUNT_ROOT/usr/local/bin/lablink-first-boot.sh"

    # Create systemd service for first boot
    cat > "$MOUNT_ROOT/etc/systemd/system/lablink-first-boot.service" <<EOF
[Unit]
Description=LabLink First Boot Setup
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/lablink-first-boot.sh
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    # Enable first-boot service
    ln -sf /etc/systemd/system/lablink-first-boot.service \
        "$MOUNT_ROOT/etc/systemd/system/multi-user.target.wants/lablink-first-boot.service"

    print_step "LabLink installation configured"
}

create_welcome_message() {
    print_step "Creating welcome message..."

    cat > "$MOUNT_ROOT/etc/motd" <<'EOF'

╔═══════════════════════════════════════════════════════╗
║                                                       ║
║                LabLink Server - Ready!                ║
║                                                       ║
╚═══════════════════════════════════════════════════════╝

Access LabLink:
  Web Dashboard: http://$(hostname).local
  API:           http://$(hostname).local:8000
  API Docs:      http://$(hostname).local:8000/docs

Default Credentials:
  Username: admin
  Password: lablink (CHANGE THIS!)

Commands:
  sudo docker compose logs -f  # View logs
  sudo docker compose restart  # Restart LabLink
  sudo systemctl status lablink  # Check status

For help: https://github.com/X9X0/LabLink

EOF

    print_step "Welcome message created"
}

finalize_image() {
    local source_img="$1"
    local output_img="$2"

    print_step "Finalizing image..."

    # Copy to output location
    cp "$source_img" "$output_img"

    # Compress (optional)
    if command -v xz &> /dev/null; then
        print_step "Compressing image..."
        xz -z -9 -T0 "$output_img"
        output_img="${output_img}.xz"
    fi

    # Calculate checksum
    sha256sum "$output_img" > "${output_img}.sha256"

    print_step "Image created: $output_img"
    print_step "SHA256: ${output_img}.sha256"
}

print_success() {
    local img_file="$1"

    echo ""
    echo -e "${GREEN}"
    echo "╔═══════════════════════════════════════════════════════╗"
    echo "║                                                       ║"
    echo "║     Raspberry Pi Image Created Successfully!         ║"
    echo "║                                                       ║"
    echo "╚═══════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    echo "Image: $img_file"
    echo "Size: $(du -h "$img_file" | cut -f1)"
    echo ""
    echo "Next Steps:"
    echo "  1. Write image to SD card:"
    echo "     - Use LabLink GUI SD card writer"
    echo "     - Or: sudo dd if=$img_file of=/dev/sdX bs=4M status=progress"
    echo "     - Or: Use Raspberry Pi Imager or balenaEtcher"
    echo ""
    echo "  2. Insert SD card into Raspberry Pi and power on"
    echo ""
    echo "  3. Wait ~5-10 minutes for first boot setup"
    echo ""
    echo "  4. Access LabLink at:"
    echo "     http://$LABLINK_HOSTNAME.local"
    echo ""
    echo "  5. Login with:"
    echo "     Username: admin"
    echo "     Password: $LABLINK_ADMIN_PASSWORD"
    echo ""
    echo "⚠️  IMPORTANT: Change the default password after first login!"
    echo ""
}

cleanup() {
    print_step "Cleaning up..."

    unmount_image

    if [ -d "$WORK_DIR" ]; then
        rm -rf "$WORK_DIR"
    fi
}

# Main build process
main() {
    print_header

    # Parse arguments
    if [ -t 0 ] && [ $# -eq 0 ]; then
        echo "Configuration Options:"
        read -p "Output image name [lablink-pi-$(date +%Y%m%d).img]: " output_input
        OUTPUT_IMAGE="${output_input:-$OUTPUT_IMAGE}"

        read -p "Raspberry Pi hostname [lablink]: " hostname_input
        LABLINK_HOSTNAME="${hostname_input:-lablink}"

        read -p "Enable SSH? (yes/no) [yes]: " ssh_input
        ENABLE_SSH="${ssh_input:-yes}"

        read -p "Wi-Fi SSID (leave empty to skip): " WIFI_SSID
        if [ -n "$WIFI_SSID" ]; then
            read -sp "Wi-Fi Password: " WIFI_PASSWORD
            echo ""
        fi

        read -sp "Default admin password [lablink]: " password_input
        echo ""
        LABLINK_ADMIN_PASSWORD="${password_input:-lablink}"

        echo ""
    fi

    # Trap cleanup on exit
    trap cleanup EXIT

    check_root
    check_dependencies

    # Create work directory
    mkdir -p "$WORK_DIR"

    # Download base image
    BASE_IMAGE=$(download_pi_os)

    # Expand image for LabLink
    expand_image "$BASE_IMAGE" 2048  # Add 2GB

    # Mount image
    mount_image "$BASE_IMAGE"

    # Configure system
    configure_first_boot
    install_lablink
    create_welcome_message

    # Unmount
    unmount_image

    # Finalize
    finalize_image "$BASE_IMAGE" "$OUTPUT_IMAGE"

    print_success "$OUTPUT_IMAGE"
}

# Run main build
main "$@"
