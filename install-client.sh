#!/bin/bash
# LabLink GUI Client - Automated Installation Script
# Supports: macOS, Linux (Ubuntu, Debian, Fedora, etc.)
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/X9X0/LabLink/main/install-client.sh | bash
#   OR
#   ./install-client.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
LABLINK_DIR="${LABLINK_DIR:-$HOME/LabLink}"
CREATE_DESKTOP_SHORTCUT="${CREATE_DESKTOP_SHORTCUT:-yes}"

# Functions
print_header() {
    echo -e "${BLUE}"
    echo "╔═══════════════════════════════════════════════════════╗"
    echo "║                                                       ║"
    echo "║           LabLink Client Installation                 ║"
    echo "║            Desktop GUI Application                    ║"
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

    OS_TYPE=$(uname -s)
    case "$OS_TYPE" in
        Darwin*)
            OS="macos"
            print_step "Detected: macOS"
            ;;
        Linux*)
            OS="linux"
            if [ -f /etc/os-release ]; then
                . /etc/os-release
                print_step "Detected: $PRETTY_NAME"
            else
                print_step "Detected: Linux"
            fi
            ;;
        *)
            print_error "Unsupported OS: $OS_TYPE"
            exit 1
            ;;
    esac
}

check_requirements() {
    print_step "Checking requirements..."

    # Check Python version
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
        print_step "Python $PYTHON_VERSION found"

        if python3 -c 'import sys; exit(0 if sys.version_info >= (3, 8) else 1)'; then
            print_step "Python version OK (>= 3.8)"
        else
            print_error "Python 3.8 or higher is required"
            install_python
        fi
    else
        print_error "Python 3 not found"
        install_python
    fi

    # Check pip
    if ! command -v pip3 &> /dev/null; then
        print_step "Installing pip..."
        python3 -m ensurepip --upgrade || {
            print_error "Failed to install pip"
            exit 1
        }
    fi
}

install_python() {
    print_step "Installing Python 3..."

    if [ "$OS" = "macos" ]; then
        if command -v brew &> /dev/null; then
            brew install python@3.11
        else
            print_error "Homebrew not found. Please install Python 3.11 manually from python.org"
            exit 1
        fi
    elif [ "$OS" = "linux" ]; then
        if command -v apt &> /dev/null; then
            sudo apt update
            sudo apt install -y python3 python3-pip python3-venv python3-tk
        elif command -v yum &> /dev/null; then
            sudo yum install -y python3 python3-pip python3-tkinter
        elif command -v dnf &> /dev/null; then
            sudo dnf install -y python3 python3-pip python3-tkinter
        else
            print_error "Package manager not found. Please install Python 3.8+ manually"
            exit 1
        fi
    fi

    print_step "Python installed"
}

install_system_dependencies() {
    print_step "Installing system dependencies..."

    if [ "$OS" = "linux" ]; then
        # Install Qt dependencies and other required libraries
        if command -v apt &> /dev/null; then
            sudo apt update
            sudo apt install -y \
                libxcb-xinerama0 \
                libxcb-icccm4 \
                libxcb-image0 \
                libxcb-keysyms1 \
                libxcb-randr0 \
                libxcb-render-util0 \
                libxcb-shape0 \
                libxkbcommon-x11-0 \
                libdbus-1-3 \
                libgl1-mesa-glx \
                libglib2.0-0
        fi
    fi

    print_step "System dependencies installed"
}

download_lablink() {
    print_step "Downloading LabLink Client..."

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

install_client_dependencies() {
    print_step "Installing Python dependencies..."

    cd "$LABLINK_DIR/client"

    # Create virtual environment
    if [ ! -d "venv" ]; then
        python3 -m venv venv
        print_step "Created Python virtual environment"
    fi

    # Activate virtual environment
    source venv/bin/activate

    # Upgrade pip
    pip install --upgrade pip

    # Install requirements
    pip install -r requirements.txt

    print_step "Dependencies installed"
}

create_launcher_script() {
    print_step "Creating launcher script..."

    cd "$LABLINK_DIR"

    cat > lablink-client <<'EOF'
#!/bin/bash
# LabLink Client Launcher

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/client"

# Activate virtual environment
source venv/bin/activate

# Run client
python main.py "$@"
EOF

    chmod +x lablink-client

    print_step "Launcher script created: $LABLINK_DIR/lablink-client"
}

create_desktop_shortcut() {
    if [ "$CREATE_DESKTOP_SHORTCUT" != "yes" ]; then
        return
    fi

    print_step "Creating desktop shortcut..."

    if [ "$OS" = "linux" ]; then
        # Create .desktop file
        DESKTOP_FILE="$HOME/.local/share/applications/lablink.desktop"
        mkdir -p "$(dirname "$DESKTOP_FILE")"

        cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=LabLink
Comment=Laboratory Equipment Control
Exec=$LABLINK_DIR/lablink-client
Icon=$LABLINK_DIR/client/resources/icon.png
Terminal=false
Categories=Development;Science;
EOF

        chmod +x "$DESKTOP_FILE"

        # Try to copy to desktop
        if [ -d "$HOME/Desktop" ]; then
            cp "$DESKTOP_FILE" "$HOME/Desktop/"
            chmod +x "$HOME/Desktop/lablink.desktop"
        fi

        print_step "Desktop shortcut created"

    elif [ "$OS" = "macos" ]; then
        # Create .app bundle for macOS
        APP_DIR="$HOME/Applications/LabLink.app"
        mkdir -p "$APP_DIR/Contents/MacOS"
        mkdir -p "$APP_DIR/Contents/Resources"

        # Create launcher
        cat > "$APP_DIR/Contents/MacOS/LabLink" <<EOF
#!/bin/bash
cd "$LABLINK_DIR/client"
source venv/bin/activate
python main.py
EOF
        chmod +x "$APP_DIR/Contents/MacOS/LabLink"

        # Create Info.plist
        cat > "$APP_DIR/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>LabLink</string>
    <key>CFBundleName</key>
    <string>LabLink</string>
    <key>CFBundleIdentifier</key>
    <string>com.lablink.client</string>
    <key>CFBundleVersion</key>
    <string>0.27.0</string>
</dict>
</plist>
EOF

        print_step "macOS app bundle created: $APP_DIR"
    fi
}

print_success() {
    echo ""
    echo -e "${GREEN}"
    echo "╔═══════════════════════════════════════════════════════╗"
    echo "║                                                       ║"
    echo "║        LabLink Client Installed Successfully!        ║"
    echo "║                                                       ║"
    echo "╚═══════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    echo "Installation Directory: $LABLINK_DIR"
    echo ""
    echo "To start LabLink Client:"
    echo "  $LABLINK_DIR/lablink-client"
    echo ""

    if [ "$OS" = "linux" ]; then
        echo "Desktop shortcut created in Applications menu"
    elif [ "$OS" = "macos" ]; then
        echo "App bundle created in ~/Applications/LabLink.app"
    fi

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
        read -p "Create desktop shortcut? (yes/no) [yes]: " SHORTCUT_INPUT
        CREATE_DESKTOP_SHORTCUT="${SHORTCUT_INPUT:-yes}"

        read -p "Installation directory [$LABLINK_DIR]: " DIR_INPUT
        LABLINK_DIR="${DIR_INPUT:-$LABLINK_DIR}"
        echo ""
    fi

    detect_os
    check_requirements
    install_system_dependencies
    download_lablink
    install_client_dependencies
    create_launcher_script
    create_desktop_shortcut

    print_success
}

# Run main installation
main "$@"
