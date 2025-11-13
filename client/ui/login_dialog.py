"""Login dialog for LabLink server authentication."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox,
    QDialogButtonBox, QGroupBox, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


class LoginDialog(QDialog):
    """Dialog for logging into LabLink server."""

    # Signal emitted when login is successful
    login_successful = pyqtSignal(dict)  # Emits user data

    def __init__(self, api_client=None, parent=None):
        """Initialize login dialog.

        Args:
            api_client: LabLinkClient instance for authentication
            parent: Parent widget
        """
        super().__init__(parent)

        self.api_client = api_client
        self.user_data = None

        self.setWindowTitle("Login to LabLink")
        self.setModal(True)
        self.setMinimumWidth(400)

        self._setup_ui()
        self._load_saved_credentials()

    def _setup_ui(self):
        """Set up user interface."""
        layout = QVBoxLayout(self)

        # Title
        title_label = QLabel("LabLink Authentication")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # Subtitle
        subtitle_label = QLabel("Please enter your credentials to continue")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_label.setStyleSheet("color: gray;")
        layout.addWidget(subtitle_label)

        layout.addSpacing(20)

        # Login form group
        form_group = QGroupBox("Credentials")
        form_layout = QFormLayout()

        # Username
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter username or email")
        self.username_input.returnPressed.connect(self._on_login)
        form_layout.addRow("Username:", self.username_input)

        # Password
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Enter password")
        self.password_input.returnPressed.connect(self._on_login)
        form_layout.addRow("Password:", self.password_input)

        # Remember me checkbox
        self.remember_me_checkbox = QCheckBox("Remember me")
        self.remember_me_checkbox.setToolTip("Save credentials for next login")
        form_layout.addRow("", self.remember_me_checkbox)

        form_group.setLayout(form_layout)
        layout.addWidget(form_group)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: red;")
        self.status_label.hide()
        layout.addWidget(self.status_label)

        # Info box
        info_label = QLabel(
            "<small><b>Default credentials:</b><br>"
            "Username: admin<br>"
            "Password: LabLink@2025<br>"
            "<i>Change password after first login!</i></small>"
        )
        info_label.setStyleSheet("background-color: #f0f0f0; padding: 10px; border-radius: 5px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Dialog buttons
        button_layout = QHBoxLayout()

        self.login_button = QPushButton("Login")
        self.login_button.setDefault(True)
        self.login_button.clicked.connect(self._on_login)
        button_layout.addWidget(self.login_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        layout.addLayout(button_layout)

    def _load_saved_credentials(self):
        """Load saved credentials if remember me was enabled."""
        try:
            from PyQt6.QtCore import QSettings
            settings = QSettings("LabLink", "Client")

            if settings.value("remember_me", False, type=bool):
                username = settings.value("username", "", type=str)
                if username:
                    self.username_input.setText(username)
                    self.remember_me_checkbox.setChecked(True)
                    # Focus password field if username is pre-filled
                    self.password_input.setFocus()
            else:
                # Focus username field
                self.username_input.setFocus()
        except Exception as e:
            print(f"Failed to load saved credentials: {e}")
            self.username_input.setFocus()

    def _save_credentials(self):
        """Save credentials if remember me is enabled."""
        try:
            from PyQt6.QtCore import QSettings
            settings = QSettings("LabLink", "Client")

            if self.remember_me_checkbox.isChecked():
                settings.setValue("remember_me", True)
                settings.setValue("username", self.username_input.text())
            else:
                settings.setValue("remember_me", False)
                settings.remove("username")
        except Exception as e:
            print(f"Failed to save credentials: {e}")

    def _on_login(self):
        """Handle login button click."""
        username = self.username_input.text().strip()
        password = self.password_input.text()

        if not username or not password:
            self._show_error("Please enter both username and password")
            return

        # Disable login button and show loading state
        self.login_button.setEnabled(False)
        self.login_button.setText("Logging in...")
        self.status_label.hide()

        # Attempt login
        try:
            if self.api_client:
                # Use API client to login
                response = self.api_client.login(username, password)

                if response and "access_token" in response:
                    # Login successful
                    self.user_data = response.get("user", {})
                    self._save_credentials()

                    # Show success message
                    self.status_label.setText("Login successful!")
                    self.status_label.setStyleSheet("color: green;")
                    self.status_label.show()

                    # Emit signal and accept dialog
                    self.login_successful.emit(self.user_data)
                    self.accept()
                else:
                    self._show_error("Login failed: Invalid response from server")
            else:
                self._show_error("No API client available")

        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "Unauthorized" in error_msg:
                self._show_error("Invalid username or password")
            elif "connection" in error_msg.lower():
                self._show_error("Cannot connect to server. Please check your connection.")
            else:
                self._show_error(f"Login failed: {error_msg}")

        finally:
            # Re-enable login button
            self.login_button.setEnabled(True)
            self.login_button.setText("Login")

    def _show_error(self, message: str):
        """Show error message.

        Args:
            message: Error message to display
        """
        self.status_label.setText(f"⚠ {message}")
        self.status_label.setStyleSheet("color: red;")
        self.status_label.show()

    def get_user_data(self) -> dict:
        """Get user data from successful login.

        Returns:
            User data dictionary
        """
        return self.user_data or {}
