"""SSH Deployment Wizard for deploying LabLink server to remote machines."""

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional

try:
    from PyQt6.QtCore import Qt, QThread, pyqtSignal
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox,
                                 QFileDialog, QFormLayout, QGroupBox,
                                 QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                                 QProgressBar, QPushButton, QRadioButton,
                                 QSpinBox, QTextEdit, QVBoxLayout, QWizard,
                                 QWizardPage)

    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

logger = logging.getLogger(__name__)


class DeploymentThread(QThread):
    """Thread for handling SSH deployment operations."""

    progress = pyqtSignal(int, str)  # progress percentage, message
    finished = pyqtSignal(bool, str)  # success, message

    def __init__(self, deployment_config: Dict):
        """Initialize deployment thread.

        Args:
            deployment_config: Configuration for deployment
        """
        super().__init__()
        self.config = deployment_config
        self._stop_requested = False

    def run(self):
        """Run deployment process."""
        try:
            import paramiko
            from scp import SCPClient

            # Extract configuration
            host = self.config["host"]
            port = self.config["port"]
            username = self.config["username"]
            auth_method = self.config["auth_method"]
            password = self.config.get("password")
            key_file = self.config.get("key_file")
            server_path = self.config["server_path"]
            source_path = self.config["source_path"]
            deployment_mode = self.config.get("deployment_mode", "python")
            install_docker = self.config.get("install_docker", False)
            install_deps = self.config["install_deps"]
            setup_service = self.config["setup_service"]

            self.progress.emit(5, "Connecting to remote host...")

            # Create SSH client
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # Connect
            try:
                if auth_method == "password":
                    ssh.connect(
                        host,
                        port=port,
                        username=username,
                        password=password,
                        timeout=15,
                    )
                elif auth_method == "key":
                    key_path = Path(key_file).expanduser()
                    ssh.connect(
                        host,
                        port=port,
                        username=username,
                        key_filename=str(key_path),
                        timeout=15,
                    )
                else:
                    raise ValueError(f"Unknown auth method: {auth_method}")
            except Exception as e:
                self.finished.emit(False, f"Connection failed: {e}")
                return

            if self._stop_requested:
                ssh.close()
                return

            self.progress.emit(10, "Connected successfully")

            # Create remote directory
            self.progress.emit(15, f"Creating remote directory: {server_path}")
            stdin, stdout, stderr = ssh.exec_command(f"mkdir -p {server_path}")
            exit_code = stdout.channel.recv_exit_status()
            if exit_code != 0:
                error = stderr.read().decode()
                self.finished.emit(False, f"Failed to create directory: {error}")
                ssh.close()
                return

            if self._stop_requested:
                ssh.close()
                return

            # Copy server files using tar+ssh (much faster than SCP)
            self.progress.emit(20, "Copying server files...")

            try:
                source = Path(source_path)
                if source.is_dir():
                    # Use tar+ssh for fast transfer (10-20x faster than SCP)
                    self._copy_files_tar(ssh, source, server_path, deployment_mode)
            except Exception as e:
                self.finished.emit(False, f"Failed to copy files: {e}")
                ssh.close()
                return

            if self._stop_requested:
                ssh.close()
                return

            self.progress.emit(60, "Files copied successfully")

            # Deploy based on mode
            if deployment_mode == "docker":
                # Docker deployment
                if install_docker and self._check_docker_needed(ssh):
                    self._install_docker(ssh)

                self._deploy_docker(ssh, server_path, username)
            else:
                # Python deployment (legacy)
                if install_deps:
                    self._install_python_deps(ssh, server_path)

                if setup_service:
                    self._setup_systemd_service(ssh, username, server_path)

            self.progress.emit(100, "Deployment completed successfully!")
            ssh.close()

            self.finished.emit(True, "LabLink server deployed successfully!")

        except ImportError as e:
            self.finished.emit(
                False, f"Missing required package: {e}\nPlease install paramiko and scp"
            )
        except Exception as e:
            logger.exception("Deployment failed")
            self.finished.emit(False, f"Deployment failed: {e}")

    def _copy_files_tar(self, ssh, source, server_path, deployment_mode):
        """Copy files using tar+ssh for fast transfer.

        This is 10-20x faster than SCP for multiple files.
        """
        import subprocess
        import tempfile

        self.progress.emit(25, "Preparing files for transfer...")

        # Create exclusion patterns
        exclude_patterns = [
            "--exclude=__pycache__",
            "--exclude=*.pyc",
            "--exclude=.git",
            "--exclude=venv",
            "--exclude=.env",
            "--exclude=*.log",
        ]

        # Create tar archive locally
        with tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False) as tmp_file:
            tar_path = tmp_file.name

        try:
            # Create compressed tar archive
            tar_cmd = ["tar", "czf", tar_path, "-C", str(source)] + exclude_patterns + ["."]
            subprocess.run(tar_cmd, check=True, capture_output=True)

            # Get file size for progress
            import os
            file_size = os.path.getsize(tar_path)
            file_size_mb = file_size / (1024 * 1024)

            self.progress.emit(35, f"Transferring {file_size_mb:.1f} MB...")

            # Transfer via SCP (single file is much faster)
            from scp import SCPClient
            with SCPClient(ssh.get_transport()) as scp:
                remote_tar = f"{server_path}.tar.gz"
                scp.put(tar_path, remote_tar)

            self.progress.emit(50, "Extracting files on remote...")

            # Extract on remote (extract TO server_path)
            extract_cmd = f"mkdir -p {server_path} && tar xzf {remote_tar} -C {server_path} && rm {remote_tar}"
            stdin, stdout, stderr = ssh.exec_command(extract_cmd, get_pty=True)
            exit_code = stdout.channel.recv_exit_status()

            if exit_code != 0:
                error = stderr.read().decode()
                raise Exception(f"Failed to extract files: {error}")

            self.progress.emit(60, "Files transferred successfully")

        finally:
            # Clean up local tar file
            import os
            if os.path.exists(tar_path):
                os.remove(tar_path)

    def _check_docker_needed(self, ssh):
        """Check if Docker needs to be installed."""
        stdin, stdout, stderr = ssh.exec_command("which docker && which docker-compose")
        exit_code = stdout.channel.recv_exit_status()
        return exit_code != 0  # True if Docker not found

    def _install_docker(self, ssh):
        """Install Docker and Docker Compose."""
        self.progress.emit(65, "Installing Docker...")
        commands = [
            # Install Docker
            "curl -fsSL https://get.docker.com -o get-docker.sh",
            "sudo sh get-docker.sh",
            "sudo usermod -aG docker $USER",
            # Install Docker Compose
            "sudo apt-get update",
            "sudo apt-get install -y docker-compose-plugin",
        ]

        for i, cmd in enumerate(commands):
            if self._stop_requested:
                return

            self.progress.emit(65 + i * 3, f"Running: {cmd[:40]}...")
            stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)
            exit_code = stdout.channel.recv_exit_status()

            if exit_code != 0:
                error = stderr.read().decode()
                logger.warning(f"Docker install warning: {error}")

        self.progress.emit(80, "Docker installed")

    def _deploy_docker(self, ssh, server_path, username):
        """Deploy using Docker Compose."""
        self.progress.emit(82, "Generating .env file...")

        # Generate JWT secret
        import secrets
        jwt_secret = secrets.token_urlsafe(32)

        env_content = self._generate_env_file(jwt_secret)

        # Write .env file
        env_path = f"{server_path}/.env"
        # Escape single quotes in env content
        env_content_escaped = env_content.replace("'", "'\\''")
        ssh.exec_command(f"cat > {env_path} << 'EOF'\n{env_content}\nEOF", get_pty=True)

        self.progress.emit(85, "Building and starting Docker containers...")

        # Run docker compose with progress monitoring
        docker_cmd = f"cd {server_path} && docker compose up -d --build"
        stdin, stdout, stderr = ssh.exec_command(docker_cmd, get_pty=True)

        # Stream and monitor Docker build output
        progress_value = 85
        last_message = ""
        for line in stdout:
            line_str = line.strip()
            if line_str:
                logger.info(f"Docker: {line_str}")

                # Update progress based on Docker output
                if "Pulling" in line_str or "Downloading" in line_str:
                    progress_value = min(90, progress_value + 0.5)
                    self.progress.emit(int(progress_value), "Pulling Docker images...")
                elif "Building" in line_str or "Step" in line_str:
                    progress_value = min(95, progress_value + 0.3)
                    self.progress.emit(int(progress_value), "Building containers...")
                elif "Creating" in line_str or "Starting" in line_str:
                    progress_value = min(98, progress_value + 1)
                    self.progress.emit(int(progress_value), "Starting containers...")

                last_message = line_str[:60]  # Keep last message for error reporting

        exit_code = stdout.channel.recv_exit_status()

        if exit_code != 0:
            # Read any error output
            error_lines = []
            for line in stderr:
                error_lines.append(line.strip())
            error = "\n".join(error_lines) if error_lines else last_message
            raise Exception(f"Docker deployment failed: {error}")

        self.progress.emit(99, "Docker containers started successfully!")

        # Install convenience commands
        self._install_convenience_commands(ssh, server_path, username)

    def _install_convenience_commands(self, ssh, server_path, username):
        """Install convenience shell commands for LabLink management."""
        commands_script = f"""#!/bin/bash
# LabLink convenience commands
# Source this file in .bashrc: source ~/.lablink_commands

alias lablink-status='cd {server_path} && docker compose ps'
alias lablink-logs='cd {server_path} && docker compose logs -f'
alias lablink-logs-server='cd {server_path} && docker compose logs -f lablink-server'
alias lablink-logs-web='cd {server_path} && docker compose logs -f lablink-web'
alias lablink-restart='cd {server_path} && docker compose restart'
alias lablink-stop='cd {server_path} && docker compose stop'
alias lablink-start='cd {server_path} && docker compose start'
alias lablink-update='cd {server_path} && git pull && docker compose up -d --build'
alias lablink-shell='cd {server_path} && docker compose exec lablink-server /bin/bash'
alias lablink-stats='docker stats --no-stream lablink-server lablink-web'
alias lablink-ip='hostname -I | awk "{{print \\$1}}"'

# Functions
lablink-url() {{
    echo "LabLink Server running at:"
    echo "  Web Dashboard: http://$(hostname -I | awk '{{print $1}}'):80"
    echo "  API: http://$(hostname -I | awk '{{print $1}}'):8000"
    echo "  WebSocket: ws://$(hostname -I | awk '{{print $1}}'):8001"
}}

lablink-help() {{
    echo "LabLink Docker Management Commands:"
    echo ""
    echo "Status & Monitoring:"
    echo "  lablink-status      - Show container status"
    echo "  lablink-logs        - View all logs (follow mode)"
    echo "  lablink-logs-server - View server logs only"
    echo "  lablink-logs-web    - View web dashboard logs only"
    echo "  lablink-stats       - Show container resource usage"
    echo "  lablink-url         - Show access URLs"
    echo "  lablink-ip          - Show Pi IP address"
    echo ""
    echo "Control:"
    echo "  lablink-restart     - Restart all containers"
    echo "  lablink-stop        - Stop all containers"
    echo "  lablink-start       - Start all containers"
    echo "  lablink-update      - Pull latest code and rebuild"
    echo "  lablink-shell       - Open shell in server container"
    echo ""
}}
"""

        # Write commands script
        ssh.exec_command(f"cat > ~/.lablink_commands << 'EOF'\n{commands_script}\nEOF")

        # Add to .bashrc if not already there
        bashrc_line = "\\n# LabLink commands\\n[ -f ~/.lablink_commands ] && source ~/.lablink_commands"
        check_cmd = "grep -q 'lablink_commands' ~/.bashrc"
        stdin, stdout, stderr = ssh.exec_command(check_cmd)
        exit_code = stdout.channel.recv_exit_status()

        if exit_code != 0:  # Not found, add it
            ssh.exec_command(f"echo -e '{bashrc_line}' >> ~/.bashrc")

        logger.info("Installed LabLink convenience commands")

    def _install_python_deps(self, ssh, server_path):
        """Install Python dependencies (Direct Python mode)."""
        self.progress.emit(65, "Installing Python dependencies...")
        commands = [
            f"cd {server_path}",
            "python3 -m venv venv",
            "source venv/bin/activate && pip install --upgrade pip",
            f"source venv/bin/activate && pip install -r requirements.txt",
        ]

        for i, cmd in enumerate(commands):
            if self._stop_requested:
                return

            self.progress.emit(65 + i * 5, f"Running: {cmd[:50]}...")
            stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)
            exit_code = stdout.channel.recv_exit_status()

            if exit_code != 0:
                error = stderr.read().decode()
                logger.warning(f"Command warning: {error}")

        self.progress.emit(85, "Dependencies installed")

    def _setup_systemd_service(self, ssh, username, server_path):
        """Set up systemd service (Direct Python mode)."""
        self.progress.emit(90, "Setting up systemd service...")
        service_content = self._generate_service_file(username, server_path)

        # Write service file
        service_path = "/tmp/lablink.service"
        ssh.exec_command(f"echo '{service_content}' > {service_path}")

        # Install service
        commands = [
            f"sudo mv {service_path} /etc/systemd/system/lablink.service",
            "sudo systemctl daemon-reload",
            "sudo systemctl enable lablink.service",
            "sudo systemctl start lablink.service",
        ]

        for cmd in commands:
            if self._stop_requested:
                return

            stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)
            exit_code = stdout.channel.recv_exit_status()

            if exit_code != 0:
                error = stderr.read().decode()
                logger.warning(f"Service setup warning: {error}")

        self.progress.emit(95, "Systemd service configured")

    def _scp_progress(self, filename, size, sent):
        """Track SCP progress."""
        if size > 0:
            percent = int((sent / size) * 100)
            # Map to 20-60% of overall progress
            overall_percent = 20 + int(percent * 0.4)
            # Convert filename from bytes to string if needed
            filename_str = filename.decode('utf-8') if isinstance(filename, bytes) else filename
            self.progress.emit(overall_percent, f"Copying: {Path(filename_str).name}")

    def _generate_env_file(self, jwt_secret: str) -> str:
        """Generate .env file content for Docker deployment.

        Args:
            jwt_secret: Generated JWT secret key

        Returns:
            .env file content
        """
        return f"""# LabLink Server Configuration
# Generated by SSH Deployment Wizard

# Server
LABLINK_VERSION=latest
LABLINK_API_PORT=8000
LABLINK_WS_PORT=8001
LABLINK_WEB_PORT=80
LABLINK_DEBUG=false
LABLINK_LOG_LEVEL=INFO

# Security
LABLINK_JWT_SECRET_KEY={jwt_secret}
LABLINK_JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
LABLINK_ENABLE_CORS=true

# Advanced Security
LABLINK_ENABLE_ADVANCED_SECURITY=true
LABLINK_CREATE_DEFAULT_ADMIN=true
LABLINK_DEFAULT_ADMIN_USERNAME=admin
LABLINK_DEFAULT_ADMIN_PASSWORD=LabLink@2025
LABLINK_DEFAULT_ADMIN_EMAIL=admin@example.com

# Equipment
LABLINK_VISA_BACKEND=@py
LABLINK_PRIVILEGED=true

# Resource Limits
LABLINK_CPU_LIMIT=2
LABLINK_MEM_LIMIT=1G
"""

    def _generate_service_file(self, username: str, server_path: str) -> str:
        """Generate systemd service file content.

        Args:
            username: User to run service as
            server_path: Path to server files

        Returns:
            Service file content
        """
        return f"""[Unit]
Description=LabLink Server
After=network.target

[Service]
Type=simple
User={username}
WorkingDirectory={server_path}
Environment="PATH={server_path}/venv/bin"
ExecStart={server_path}/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""

    def request_stop(self):
        """Request thread to stop."""
        self._stop_requested = True


class ConnectionPage(QWizardPage):
    """Wizard page for SSH connection details."""

    def __init__(self):
        """Initialize connection page."""
        super().__init__()

        self.setTitle("SSH Connection")
        self.setSubTitle("Enter the SSH connection details for the remote server.")

        layout = QFormLayout(self)

        # Hostname
        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("lablink-pi.local or 192.168.1.100")
        self.registerField("host*", self.host_edit)
        layout.addRow("Hostname/IP:", self.host_edit)

        # Port
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(22)
        self.registerField("port", self.port_spin)
        layout.addRow("Port:", self.port_spin)

        # Username
        self.username_edit = QLineEdit()
        self.username_edit.setText("pi")
        self.registerField("username*", self.username_edit)
        layout.addRow("Username:", self.username_edit)

        # Authentication method
        auth_group = QGroupBox("Authentication Method")
        auth_layout = QVBoxLayout()

        self.auth_group = QButtonGroup()

        self.password_radio = QRadioButton("Password")
        self.password_radio.setChecked(True)
        self.password_radio.toggled.connect(self._on_auth_method_changed)
        self.auth_group.addButton(self.password_radio, 0)
        auth_layout.addWidget(self.password_radio)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Enter password")
        self.registerField("password", self.password_edit)
        auth_layout.addWidget(self.password_edit)

        self.key_radio = QRadioButton("SSH Key")
        self.key_radio.toggled.connect(self._on_auth_method_changed)
        self.auth_group.addButton(self.key_radio, 1)
        auth_layout.addWidget(self.key_radio)

        key_layout = QHBoxLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("~/.ssh/id_rsa")
        self.key_edit.setEnabled(False)
        self.registerField("key_file", self.key_edit)
        key_layout.addWidget(self.key_edit)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_key_file)
        browse_btn.setEnabled(False)
        self.browse_btn = browse_btn
        key_layout.addWidget(browse_btn)

        auth_layout.addLayout(key_layout)

        auth_group.setLayout(auth_layout)
        layout.addRow(auth_group)

        # Test connection button
        test_layout = QHBoxLayout()
        test_btn = QPushButton("Test Connection")
        test_btn.clicked.connect(self._test_connection)
        test_layout.addWidget(test_btn)
        test_layout.addStretch()

        self.test_result_label = QLabel("")
        test_layout.addWidget(self.test_result_label)

        layout.addRow("", test_layout)

        # Connect signals to notify wizard of field changes
        self.host_edit.textChanged.connect(self.completeChanged)
        self.username_edit.textChanged.connect(self.completeChanged)
        self.password_edit.textChanged.connect(self.completeChanged)
        self.key_edit.textChanged.connect(self.completeChanged)

    def isComplete(self):
        """Check if page has all required fields filled."""
        has_host = bool(self.host_edit.text().strip())
        has_username = bool(self.username_edit.text().strip())

        # Check authentication fields based on selected method
        if self.password_radio.isChecked():
            has_auth = bool(self.password_edit.text())
        else:
            has_auth = bool(self.key_edit.text().strip())

        return has_host and has_username and has_auth

    def _on_auth_method_changed(self):
        """Handle authentication method change."""
        use_key = self.key_radio.isChecked()
        self.password_edit.setEnabled(not use_key)
        self.key_edit.setEnabled(use_key)
        self.browse_btn.setEnabled(use_key)
        self.completeChanged.emit()

    def _browse_key_file(self):
        """Browse for SSH key file."""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select SSH Private Key", str(Path.home() / ".ssh"), "All Files (*)"
        )
        if filename:
            self.key_edit.setText(filename)
            self.completeChanged.emit()

    def _test_connection(self):
        """Test SSH connection."""
        try:
            import paramiko

            host = self.host_edit.text()
            port = self.port_spin.value()
            username = self.username_edit.text()

            if not host or not username:
                self.test_result_label.setText("❌ Please fill in required fields")
                return

            self.test_result_label.setText("Testing...")

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            try:
                if self.password_radio.isChecked():
                    password = self.password_edit.text()
                    ssh.connect(
                        host,
                        port=port,
                        username=username,
                        password=password,
                        timeout=10,
                    )
                else:
                    key_file = self.key_edit.text()
                    key_path = Path(key_file).expanduser()
                    ssh.connect(
                        host,
                        port=port,
                        username=username,
                        key_filename=str(key_path),
                        timeout=10,
                    )

                ssh.close()
                self.test_result_label.setText("✅ Connection successful!")
            except Exception as e:
                self.test_result_label.setText(f"❌ Connection failed: {e}")

        except ImportError:
            self.test_result_label.setText("❌ paramiko not installed")


class DeploymentOptionsPage(QWizardPage):
    """Wizard page for deployment options."""

    def __init__(self):
        """Initialize deployment options page."""
        super().__init__()

        self.setTitle("Deployment Options")
        self.setSubTitle("Configure how the server will be deployed.")

        layout = QFormLayout(self)

        # Source path (local server directory)
        source_layout = QHBoxLayout()
        self.source_edit = QLineEdit()
        # Try to find project root (for Docker) or server directory (for Python mode)
        # Default to project root since Docker mode is recommended
        default_source = Path(__file__).parent.parent.parent
        if default_source.exists():
            self.source_edit.setText(str(default_source))
        self.registerField("source_path*", self.source_edit)
        source_layout.addWidget(self.source_edit)

        browse_source_btn = QPushButton("Browse...")
        browse_source_btn.clicked.connect(self._browse_source)
        source_layout.addWidget(browse_source_btn)

        layout.addRow("Local Server Path:", source_layout)

        # Remote server path
        self.server_path_edit = QLineEdit()
        self.server_path_edit.setPlaceholderText("/home/<username>/lablink")
        self.registerField("server_path*", self.server_path_edit)
        layout.addRow("Remote Server Path:", self.server_path_edit)

        # Deployment Mode
        mode_group = QGroupBox("Deployment Mode")
        mode_layout = QVBoxLayout()

        self.mode_button_group = QButtonGroup()

        self.docker_radio = QRadioButton("Docker Compose (Recommended)")
        self.docker_radio.setChecked(True)
        self.docker_radio.toggled.connect(self._on_mode_changed)
        self.mode_button_group.addButton(self.docker_radio, 0)
        mode_layout.addWidget(self.docker_radio)

        docker_desc = QLabel("  • Containerized deployment with Docker\n  • Automatic service management\n  • Includes web dashboard and optional monitoring")
        docker_desc.setStyleSheet("color: gray; margin-left: 20px;")
        mode_layout.addWidget(docker_desc)

        self.python_radio = QRadioButton("Direct Python (Legacy)")
        self.python_radio.toggled.connect(self._on_mode_changed)
        self.mode_button_group.addButton(self.python_radio, 1)
        mode_layout.addWidget(self.python_radio)

        python_desc = QLabel("  • Run server directly with Python\n  • Manual systemd service setup\n  • Server only (no web dashboard)")
        python_desc.setStyleSheet("color: gray; margin-left: 20px;")
        mode_layout.addWidget(python_desc)

        mode_group.setLayout(mode_layout)
        layout.addRow(mode_group)

        # Options
        options_group = QGroupBox("Installation Options")
        options_layout = QVBoxLayout()

        self.install_docker_check = QCheckBox(
            "Install Docker and Docker Compose (if not present)"
        )
        self.install_docker_check.setChecked(True)
        self.registerField("install_docker", self.install_docker_check)
        options_layout.addWidget(self.install_docker_check)

        self.install_deps_check = QCheckBox(
            "Install Python dependencies (Direct Python mode only)"
        )
        self.install_deps_check.setChecked(True)
        self.install_deps_check.setEnabled(False)  # Disabled by default (Docker mode)
        self.registerField("install_deps", self.install_deps_check)
        options_layout.addWidget(self.install_deps_check)

        self.setup_service_check = QCheckBox(
            "Set up as systemd service (Direct Python mode only)"
        )
        self.setup_service_check.setChecked(True)
        self.setup_service_check.setEnabled(False)  # Disabled by default (Docker mode)
        self.registerField("setup_service", self.setup_service_check)
        options_layout.addWidget(self.setup_service_check)

        options_group.setLayout(options_layout)
        layout.addRow(options_group)

        # Connect signals to notify wizard of field changes
        self.source_edit.textChanged.connect(self.completeChanged)
        self.server_path_edit.textChanged.connect(self.completeChanged)

    def isComplete(self):
        """Check if page has all required fields filled."""
        has_source = bool(self.source_edit.text().strip())
        has_server_path = bool(self.server_path_edit.text().strip())
        return has_source and has_server_path

    def initializePage(self):
        """Initialize page when shown - set default remote path based on username."""
        wizard = self.wizard()
        username = wizard.field("username")

        # Set default remote path based on username if field is empty
        if not self.server_path_edit.text():
            self.server_path_edit.setText(f"/home/{username}/lablink")

    def _on_mode_changed(self):
        """Handle deployment mode change."""
        use_docker = self.docker_radio.isChecked()

        # Enable/disable options based on mode
        self.install_docker_check.setEnabled(use_docker)
        self.install_deps_check.setEnabled(not use_docker)
        self.setup_service_check.setEnabled(not use_docker)

    def _browse_source(self):
        """Browse for source directory."""
        dirname = QFileDialog.getExistingDirectory(
            self, "Select Server Directory", self.source_edit.text() or str(Path.home())
        )
        if dirname:
            self.source_edit.setText(dirname)
            self.completeChanged.emit()


class DeploymentProgressPage(QWizardPage):
    """Wizard page showing deployment progress."""

    def __init__(self):
        """Initialize deployment progress page."""
        super().__init__()

        self.setTitle("Deploying Server")
        self.setSubTitle("Please wait while the server is deployed...")

        self.deployment_thread: Optional[DeploymentThread] = None
        self.deployment_successful = False

        layout = QVBoxLayout(self)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Preparing deployment...")
        layout.addWidget(self.status_label)

        # Log output
        log_label = QLabel("Deployment Log:")
        layout.addWidget(log_label)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFont(QFont("Monospace", 9))
        layout.addWidget(self.log_output)

        layout.addStretch()

    def initializePage(self):
        """Initialize page when shown."""
        # Get configuration from wizard
        wizard = self.wizard()

        config = {
            "host": str(wizard.field("host")),
            "port": wizard.field("port"),
            "username": str(wizard.field("username")),
            "auth_method": (
                "password" if wizard.page(0).password_radio.isChecked() else "key"
            ),
            "password": (
                str(wizard.field("password"))
                if wizard.page(0).password_radio.isChecked()
                else None
            ),
            "key_file": (
                str(wizard.field("key_file"))
                if wizard.page(0).key_radio.isChecked()
                else None
            ),
            "source_path": str(wizard.field("source_path")),
            "server_path": str(wizard.field("server_path")),
            "deployment_mode": "docker" if wizard.page(1).docker_radio.isChecked() else "python",
            "install_docker": wizard.field("install_docker"),
            "install_deps": wizard.field("install_deps"),
            "setup_service": wizard.field("setup_service"),
        }

        # Start deployment
        self._start_deployment(config)

    def _start_deployment(self, config: Dict):
        """Start deployment process.

        Args:
            config: Deployment configuration
        """
        self.deployment_thread = DeploymentThread(config)
        self.deployment_thread.progress.connect(self._on_progress)
        self.deployment_thread.finished.connect(self._on_finished)
        self.deployment_thread.start()

        self.log_output.append("=== Deployment Started ===")
        self.log_output.append(f"Host: {config['host']}:{config['port']}")
        self.log_output.append(f"User: {config['username']}")
        self.log_output.append(f"Remote Path: {config['server_path']}")
        self.log_output.append("")

    def _on_progress(self, percent: int, message: str):
        """Handle progress update.

        Args:
            percent: Progress percentage
            message: Status message
        """
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)
        self.log_output.append(f"[{percent}%] {message}")

    def _on_finished(self, success: bool, message: str):
        """Handle deployment completion.

        Args:
            success: Whether deployment was successful
            message: Result message
        """
        self.deployment_successful = success

        if success:
            self.status_label.setText("✅ " + message)
            self.log_output.append("")
            self.log_output.append("=== Deployment Completed Successfully ===")
        else:
            self.status_label.setText("❌ " + message)
            self.log_output.append("")
            self.log_output.append(f"=== Deployment Failed: {message} ===")

        # Enable the Finish button
        self.wizard().button(QWizard.WizardButton.FinishButton).setEnabled(True)
        self.completeChanged.emit()

    def isComplete(self):
        """Check if page is complete."""
        return (
            self.deployment_thread is not None
            and not self.deployment_thread.isRunning()
        )

    def cleanupPage(self):
        """Clean up when leaving page."""
        if self.deployment_thread and self.deployment_thread.isRunning():
            self.deployment_thread.request_stop()
            self.deployment_thread.wait(5000)


class SSHDeployWizard(QWizard):
    """Wizard for deploying LabLink server via SSH."""

    def __init__(self, parent=None):
        """Initialize SSH deployment wizard."""
        super().__init__(parent)

        self.setWindowTitle("Deploy Server via SSH")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setMinimumSize(700, 500)

        # Add pages
        self.connection_page = ConnectionPage()
        self.addPage(self.connection_page)

        self.options_page = DeploymentOptionsPage()
        self.addPage(self.options_page)

        self.progress_page = DeploymentProgressPage()
        self.addPage(self.progress_page)

        # Disable back button on progress page
        self.progress_page.setFinalPage(True)

    def accept(self):
        """Handle wizard completion."""
        if self.progress_page.deployment_successful:
            QMessageBox.information(
                self,
                "Deployment Successful",
                "The LabLink server has been successfully deployed!\n\n"
                "You can now connect to it using the connection dialog.",
            )

        super().accept()
