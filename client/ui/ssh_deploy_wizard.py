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

            # Copy server files
            self.progress.emit(20, "Copying server files...")

            try:
                with SCPClient(ssh.get_transport(), progress=self._scp_progress) as scp:
                    # Copy entire server directory
                    source = Path(source_path)
                    if source.is_dir():
                        # Determine what to copy based on deployment mode
                        if deployment_mode == "docker":
                            # Docker mode: copy all necessary files including docker-compose.yml, Dockerfile, etc.
                            patterns = ["*.py", "*.yml", "*.yaml", "Dockerfile*", "requirements.txt", "*.md", "*.sh", "*.conf", "*.json"]
                        else:
                            # Python mode: copy only Python files and requirements
                            patterns = ["*.py", "requirements.txt", "*.md"]

                        for pattern in patterns:
                            for file in source.rglob(pattern):
                                if "__pycache__" in str(file) or ".git" in str(file):
                                    continue

                                relative = file.relative_to(source)
                                # Convert Path to POSIX-style string for remote path
                                relative_str = relative.as_posix()
                                remote_file = f"{server_path}/{relative_str}"

                                # Create remote directory structure
                                remote_dir = "/".join(remote_file.split("/")[:-1])
                                ssh.exec_command(f"mkdir -p {remote_dir}")

                                # Copy file
                                local_file = str(file.absolute())
                                scp.put(local_file, remote_file)
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

        self.progress.emit(85, "Starting Docker containers...")

        commands = [
            f"cd {server_path}",
            # Build and start containers
            "docker compose up -d --build",
        ]

        for i, cmd in enumerate(commands):
            if self._stop_requested:
                return

            self.progress.emit(85 + i * 7, f"Running: {cmd}...")
            stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)

            # Read output in real-time
            for line in stdout:
                logger.info(f"Docker: {line.strip()}")

            exit_code = stdout.channel.recv_exit_status()

            if exit_code != 0:
                error = stderr.read().decode()
                raise Exception(f"Docker deployment failed: {error}")

        self.progress.emit(99, "Docker containers started")

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
