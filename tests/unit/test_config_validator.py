"""
Comprehensive tests for the configuration validator module.

Tests cover:
- ConfigValidator class
- Server settings validation
- Path validation
- Equipment settings validation
- Error handling validation
- Logging configuration validation
- Security settings validation
- WebSocket settings validation
- Result printing
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from server.config.validator import ConfigValidator, validate_config


class TestConfigValidator:
    """Test ConfigValidator class."""

    def test_validator_initialization(self):
        """Test ConfigValidator initializes with empty lists."""
        validator = ConfigValidator()

        assert validator.errors == []
        assert validator.warnings == []
        assert validator.info == []

    @patch('server.config.validator.settings')
    def test_valid_configuration(self, mock_settings):
        """Test validation passes with valid configuration."""
        # Configure mock settings with valid values
        mock_settings.api_port = 8000
        mock_settings.ws_port = 8001
        mock_settings.host = "127.0.0.1"
        mock_settings.data_dir = "/tmp/data"
        mock_settings.log_dir = "/tmp/logs"
        mock_settings.profile_dir = "/tmp/profiles"
        mock_settings.enable_tls = False
        mock_settings.visa_backend = "@py"
        mock_settings.connection_timeout_ms = 5000
        mock_settings.command_timeout_ms = 1000
        mock_settings.enable_auto_reconnect = False
        mock_settings.enable_health_monitoring = False
        mock_settings.log_level = "INFO"
        mock_settings.log_to_file = True
        mock_settings.log_rotation_size_mb = 10
        mock_settings.log_retention_days = 30
        mock_settings.require_authentication = False
        mock_settings.ws_max_connections = 50
        mock_settings.ws_message_queue_size = 100
        mock_settings.validate_all = Mock(return_value=[])

        validator = ConfigValidator()
        is_valid = validator.validate()

        assert is_valid is True
        assert len(validator.errors) == 0

    @patch('server.config.validator.settings')
    def test_port_conflict_error(self, mock_settings):
        """Test error when API and WebSocket ports are the same."""
        mock_settings.api_port = 8000
        mock_settings.ws_port = 8000  # Same as API port
        mock_settings.host = "127.0.0.1"
        mock_settings.data_dir = "/tmp/data"
        mock_settings.log_dir = "/tmp/logs"
        mock_settings.profile_dir = "/tmp/profiles"
        mock_settings.enable_tls = False
        mock_settings.visa_backend = "@py"
        mock_settings.connection_timeout_ms = 5000
        mock_settings.command_timeout_ms = 1000
        mock_settings.enable_auto_reconnect = False
        mock_settings.enable_health_monitoring = False
        mock_settings.log_level = "INFO"
        mock_settings.log_to_file = True
        mock_settings.log_rotation_size_mb = 10
        mock_settings.log_retention_days = 30
        mock_settings.require_authentication = False
        mock_settings.ws_max_connections = 50
        mock_settings.ws_message_queue_size = 100
        mock_settings.validate_all = Mock(return_value=[])

        validator = ConfigValidator()
        is_valid = validator.validate()

        assert is_valid is False
        assert len(validator.errors) > 0
        assert any("port" in error.lower() for error in validator.errors)

    @patch('server.config.validator.settings')
    def test_privileged_port_warning(self, mock_settings):
        """Test warning when using privileged ports (<1024)."""
        mock_settings.api_port = 80
        mock_settings.ws_port = 443
        mock_settings.host = "127.0.0.1"
        mock_settings.data_dir = "/tmp/data"
        mock_settings.log_dir = "/tmp/logs"
        mock_settings.profile_dir = "/tmp/profiles"
        mock_settings.enable_tls = False
        mock_settings.visa_backend = "@py"
        mock_settings.connection_timeout_ms = 5000
        mock_settings.command_timeout_ms = 1000
        mock_settings.enable_auto_reconnect = False
        mock_settings.enable_health_monitoring = False
        mock_settings.log_level = "INFO"
        mock_settings.log_to_file = True
        mock_settings.log_rotation_size_mb = 10
        mock_settings.log_retention_days = 30
        mock_settings.require_authentication = False
        mock_settings.ws_max_connections = 50
        mock_settings.ws_message_queue_size = 100
        mock_settings.validate_all = Mock(return_value=[])

        validator = ConfigValidator()
        validator.validate()

        assert len(validator.warnings) >= 2  # At least warnings for both ports
        assert any("root" in warning.lower() or "privileges" in warning.lower()
                  for warning in validator.warnings)

    @patch('server.config.validator.settings')
    def test_host_binding_info(self, mock_settings):
        """Test info messages for different host bindings."""
        mock_settings.api_port = 8000
        mock_settings.ws_port = 8001
        mock_settings.host = "0.0.0.0"
        mock_settings.data_dir = "/tmp/data"
        mock_settings.log_dir = "/tmp/logs"
        mock_settings.profile_dir = "/tmp/profiles"
        mock_settings.enable_tls = False
        mock_settings.visa_backend = "@py"
        mock_settings.connection_timeout_ms = 5000
        mock_settings.command_timeout_ms = 1000
        mock_settings.enable_auto_reconnect = False
        mock_settings.enable_health_monitoring = False
        mock_settings.log_level = "INFO"
        mock_settings.log_to_file = True
        mock_settings.log_rotation_size_mb = 10
        mock_settings.log_retention_days = 30
        mock_settings.require_authentication = True
        mock_settings.api_key = "test_key"
        mock_settings.enable_cors = False
        mock_settings.ws_max_connections = 50
        mock_settings.ws_message_queue_size = 100
        mock_settings.validate_all = Mock(return_value=[])

        validator = ConfigValidator()
        validator.validate()

        assert any("0.0.0.0" in info for info in validator.info)

    @patch('server.config.validator.settings')
    @patch('server.config.validator.Path')
    def test_tls_missing_cert_file(self, mock_path, mock_settings):
        """Test error when TLS is enabled but cert file missing."""
        mock_settings.api_port = 8000
        mock_settings.ws_port = 8001
        mock_settings.host = "127.0.0.1"
        mock_settings.data_dir = "/tmp/data"
        mock_settings.log_dir = "/tmp/logs"
        mock_settings.profile_dir = "/tmp/profiles"
        mock_settings.enable_tls = True
        mock_settings.cert_file = "/path/to/missing/cert.pem"
        mock_settings.key_file = "/path/to/missing/key.pem"
        mock_settings.visa_backend = "@py"
        mock_settings.connection_timeout_ms = 5000
        mock_settings.command_timeout_ms = 1000
        mock_settings.enable_auto_reconnect = False
        mock_settings.enable_health_monitoring = False
        mock_settings.log_level = "INFO"
        mock_settings.log_to_file = True
        mock_settings.log_rotation_size_mb = 10
        mock_settings.log_retention_days = 30
        mock_settings.require_authentication = False
        mock_settings.ws_max_connections = 50
        mock_settings.ws_message_queue_size = 100
        mock_settings.validate_all = Mock(return_value=[])

        # Mock Path to return objects that report files don't exist
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = False
        mock_path.return_value = mock_path_instance

        validator = ConfigValidator()
        is_valid = validator.validate()

        assert is_valid is False
        assert any("certificate" in error.lower() or "cert" in error.lower()
                  for error in validator.errors)

    @patch('server.config.validator.settings')
    def test_tls_enabled_without_cert_file(self, mock_settings):
        """Test error when TLS enabled but cert_file not specified."""
        mock_settings.api_port = 8000
        mock_settings.ws_port = 8001
        mock_settings.host = "127.0.0.1"
        mock_settings.data_dir = "/tmp/data"
        mock_settings.log_dir = "/tmp/logs"
        mock_settings.profile_dir = "/tmp/profiles"
        mock_settings.enable_tls = True
        mock_settings.cert_file = None
        mock_settings.key_file = None
        mock_settings.visa_backend = "@py"
        mock_settings.connection_timeout_ms = 5000
        mock_settings.command_timeout_ms = 1000
        mock_settings.enable_auto_reconnect = False
        mock_settings.enable_health_monitoring = False
        mock_settings.log_level = "INFO"
        mock_settings.log_to_file = True
        mock_settings.log_rotation_size_mb = 10
        mock_settings.log_retention_days = 30
        mock_settings.require_authentication = False
        mock_settings.ws_max_connections = 50
        mock_settings.ws_message_queue_size = 100
        mock_settings.validate_all = Mock(return_value=[])

        validator = ConfigValidator()
        is_valid = validator.validate()

        assert is_valid is False
        assert len(validator.errors) >= 2  # Both cert and key file errors

    @patch('server.config.validator.settings')
    def test_unusual_visa_backend_warning(self, mock_settings):
        """Test warning for unusual VISA backend."""
        mock_settings.api_port = 8000
        mock_settings.ws_port = 8001
        mock_settings.host = "127.0.0.1"
        mock_settings.data_dir = "/tmp/data"
        mock_settings.log_dir = "/tmp/logs"
        mock_settings.profile_dir = "/tmp/profiles"
        mock_settings.enable_tls = False
        mock_settings.visa_backend = "@custom"  # Unusual backend
        mock_settings.connection_timeout_ms = 5000
        mock_settings.command_timeout_ms = 1000
        mock_settings.enable_auto_reconnect = False
        mock_settings.enable_health_monitoring = False
        mock_settings.log_level = "INFO"
        mock_settings.log_to_file = True
        mock_settings.log_rotation_size_mb = 10
        mock_settings.log_retention_days = 30
        mock_settings.require_authentication = False
        mock_settings.ws_max_connections = 50
        mock_settings.ws_message_queue_size = 100
        mock_settings.validate_all = Mock(return_value=[])

        validator = ConfigValidator()
        validator.validate()

        assert any("VISA" in warning and "backend" in warning for warning in validator.warnings)

    @patch('server.config.validator.settings')
    def test_short_timeout_warnings(self, mock_settings):
        """Test warnings for very short timeout values."""
        mock_settings.api_port = 8000
        mock_settings.ws_port = 8001
        mock_settings.host = "127.0.0.1"
        mock_settings.data_dir = "/tmp/data"
        mock_settings.log_dir = "/tmp/logs"
        mock_settings.profile_dir = "/tmp/profiles"
        mock_settings.enable_tls = False
        mock_settings.visa_backend = "@py"
        mock_settings.connection_timeout_ms = 500  # Very short
        mock_settings.command_timeout_ms = 50      # Very short
        mock_settings.enable_auto_reconnect = False
        mock_settings.enable_health_monitoring = False
        mock_settings.log_level = "INFO"
        mock_settings.log_to_file = True
        mock_settings.log_rotation_size_mb = 10
        mock_settings.log_retention_days = 30
        mock_settings.require_authentication = False
        mock_settings.ws_max_connections = 50
        mock_settings.ws_message_queue_size = 100
        mock_settings.validate_all = Mock(return_value=[])

        validator = ConfigValidator()
        validator.validate()

        assert any("timeout" in warning.lower() for warning in validator.warnings)
        assert len([w for w in validator.warnings if "timeout" in w.lower()]) >= 2

    @patch('server.config.validator.settings')
    def test_high_reconnect_attempts_warning(self, mock_settings):
        """Test warning for high number of reconnect attempts."""
        mock_settings.api_port = 8000
        mock_settings.ws_port = 8001
        mock_settings.host = "127.0.0.1"
        mock_settings.data_dir = "/tmp/data"
        mock_settings.log_dir = "/tmp/logs"
        mock_settings.profile_dir = "/tmp/profiles"
        mock_settings.enable_tls = False
        mock_settings.visa_backend = "@py"
        mock_settings.connection_timeout_ms = 5000
        mock_settings.command_timeout_ms = 1000
        mock_settings.enable_auto_reconnect = True
        mock_settings.reconnect_attempts = 10  # High number
        mock_settings.reconnect_delay_ms = 1000
        mock_settings.reconnect_backoff_multiplier = 2
        mock_settings.enable_health_monitoring = False
        mock_settings.log_level = "INFO"
        mock_settings.log_to_file = True
        mock_settings.log_rotation_size_mb = 10
        mock_settings.log_retention_days = 30
        mock_settings.require_authentication = False
        mock_settings.ws_max_connections = 50
        mock_settings.ws_message_queue_size = 100
        mock_settings.validate_all = Mock(return_value=[])

        validator = ConfigValidator()
        validator.validate()

        assert any("reconnect" in warning.lower() for warning in validator.warnings)

    @patch('server.config.validator.settings')
    def test_frequent_health_check_warning(self, mock_settings):
        """Test warning for very frequent health checks."""
        mock_settings.api_port = 8000
        mock_settings.ws_port = 8001
        mock_settings.host = "127.0.0.1"
        mock_settings.data_dir = "/tmp/data"
        mock_settings.log_dir = "/tmp/logs"
        mock_settings.profile_dir = "/tmp/profiles"
        mock_settings.enable_tls = False
        mock_settings.visa_backend = "@py"
        mock_settings.connection_timeout_ms = 5000
        mock_settings.command_timeout_ms = 1000
        mock_settings.enable_auto_reconnect = False
        mock_settings.enable_health_monitoring = True
        mock_settings.health_check_interval_sec = 5  # Very frequent
        mock_settings.log_level = "INFO"
        mock_settings.log_to_file = True
        mock_settings.log_rotation_size_mb = 10
        mock_settings.log_retention_days = 30
        mock_settings.require_authentication = False
        mock_settings.ws_max_connections = 50
        mock_settings.ws_message_queue_size = 100
        mock_settings.validate_all = Mock(return_value=[])

        validator = ConfigValidator()
        validator.validate()

        assert any("health check" in warning.lower() for warning in validator.warnings)

    @patch('server.config.validator.settings')
    def test_invalid_log_level_error(self, mock_settings):
        """Test error for invalid log level."""
        mock_settings.api_port = 8000
        mock_settings.ws_port = 8001
        mock_settings.host = "127.0.0.1"
        mock_settings.data_dir = "/tmp/data"
        mock_settings.log_dir = "/tmp/logs"
        mock_settings.profile_dir = "/tmp/profiles"
        mock_settings.enable_tls = False
        mock_settings.visa_backend = "@py"
        mock_settings.connection_timeout_ms = 5000
        mock_settings.command_timeout_ms = 1000
        mock_settings.enable_auto_reconnect = False
        mock_settings.enable_health_monitoring = False
        mock_settings.log_level = "INVALID"  # Invalid log level
        mock_settings.log_to_file = True
        mock_settings.log_rotation_size_mb = 10
        mock_settings.log_retention_days = 30
        mock_settings.require_authentication = False
        mock_settings.ws_max_connections = 50
        mock_settings.ws_message_queue_size = 100
        mock_settings.validate_all = Mock(return_value=[])

        validator = ConfigValidator()
        is_valid = validator.validate()

        assert is_valid is False
        assert any("log level" in error.lower() for error in validator.errors)

    @patch('server.config.validator.settings')
    def test_log_rotation_warnings(self, mock_settings):
        """Test warnings for log rotation settings."""
        mock_settings.api_port = 8000
        mock_settings.ws_port = 8001
        mock_settings.host = "127.0.0.1"
        mock_settings.data_dir = "/tmp/data"
        mock_settings.log_dir = "/tmp/logs"
        mock_settings.profile_dir = "/tmp/profiles"
        mock_settings.enable_tls = False
        mock_settings.visa_backend = "@py"
        mock_settings.connection_timeout_ms = 5000
        mock_settings.command_timeout_ms = 1000
        mock_settings.enable_auto_reconnect = False
        mock_settings.enable_health_monitoring = False
        mock_settings.log_level = "INFO"
        mock_settings.log_to_file = True
        mock_settings.log_rotation_size_mb = 0.5  # Very small
        mock_settings.log_retention_days = 3       # Short retention
        mock_settings.require_authentication = False
        mock_settings.ws_max_connections = 50
        mock_settings.ws_message_queue_size = 100
        mock_settings.validate_all = Mock(return_value=[])

        validator = ConfigValidator()
        validator.validate()

        assert len([w for w in validator.warnings if "log" in w.lower()]) >= 2

    @patch('server.config.validator.settings')
    def test_authentication_required_without_api_key(self, mock_settings):
        """Test error when authentication required but no API key."""
        mock_settings.api_port = 8000
        mock_settings.ws_port = 8001
        mock_settings.host = "127.0.0.1"
        mock_settings.data_dir = "/tmp/data"
        mock_settings.log_dir = "/tmp/logs"
        mock_settings.profile_dir = "/tmp/profiles"
        mock_settings.enable_tls = False
        mock_settings.visa_backend = "@py"
        mock_settings.connection_timeout_ms = 5000
        mock_settings.command_timeout_ms = 1000
        mock_settings.enable_auto_reconnect = False
        mock_settings.enable_health_monitoring = False
        mock_settings.log_level = "INFO"
        mock_settings.log_to_file = True
        mock_settings.log_rotation_size_mb = 10
        mock_settings.log_retention_days = 30
        mock_settings.require_authentication = True
        mock_settings.api_key = None  # No API key
        mock_settings.ws_max_connections = 50
        mock_settings.ws_message_queue_size = 100
        mock_settings.validate_all = Mock(return_value=[])

        validator = ConfigValidator()
        is_valid = validator.validate()

        assert is_valid is False
        assert any("authentication" in error.lower() or "API key" in error
                  for error in validator.errors)

    @patch('server.config.validator.settings')
    def test_network_exposed_without_authentication_warning(self, mock_settings):
        """Test warning when server exposed to network without authentication."""
        mock_settings.api_port = 8000
        mock_settings.ws_port = 8001
        mock_settings.host = "0.0.0.0"  # Network exposed
        mock_settings.data_dir = "/tmp/data"
        mock_settings.log_dir = "/tmp/logs"
        mock_settings.profile_dir = "/tmp/profiles"
        mock_settings.enable_tls = False
        mock_settings.visa_backend = "@py"
        mock_settings.connection_timeout_ms = 5000
        mock_settings.command_timeout_ms = 1000
        mock_settings.enable_auto_reconnect = False
        mock_settings.enable_health_monitoring = False
        mock_settings.log_level = "INFO"
        mock_settings.log_to_file = True
        mock_settings.log_rotation_size_mb = 10
        mock_settings.log_retention_days = 30
        mock_settings.require_authentication = False  # No auth
        mock_settings.enable_cors = False
        mock_settings.ws_max_connections = 50
        mock_settings.ws_message_queue_size = 100
        mock_settings.validate_all = Mock(return_value=[])

        validator = ConfigValidator()
        validator.validate()

        assert any("security" in warning.lower() or "authentication" in warning.lower()
                  for warning in validator.warnings)

    @patch('server.config.validator.settings')
    def test_cors_all_origins_warning(self, mock_settings):
        """Test warning when CORS allows all origins on network server."""
        mock_settings.api_port = 8000
        mock_settings.ws_port = 8001
        mock_settings.host = "0.0.0.0"
        mock_settings.data_dir = "/tmp/data"
        mock_settings.log_dir = "/tmp/logs"
        mock_settings.profile_dir = "/tmp/profiles"
        mock_settings.enable_tls = False
        mock_settings.visa_backend = "@py"
        mock_settings.connection_timeout_ms = 5000
        mock_settings.command_timeout_ms = 1000
        mock_settings.enable_auto_reconnect = False
        mock_settings.enable_health_monitoring = False
        mock_settings.log_level = "INFO"
        mock_settings.log_to_file = True
        mock_settings.log_rotation_size_mb = 10
        mock_settings.log_retention_days = 30
        mock_settings.require_authentication = True
        mock_settings.api_key = "test_key"
        mock_settings.enable_cors = True
        mock_settings.cors_origins = "*"  # All origins
        mock_settings.ws_max_connections = 50
        mock_settings.ws_message_queue_size = 100
        mock_settings.validate_all = Mock(return_value=[])

        validator = ConfigValidator()
        validator.validate()

        assert any("CORS" in warning for warning in validator.warnings)

    @patch('server.config.validator.settings')
    def test_websocket_max_connections_validation(self, mock_settings):
        """Test WebSocket max connections validation."""
        mock_settings.api_port = 8000
        mock_settings.ws_port = 8001
        mock_settings.host = "127.0.0.1"
        mock_settings.data_dir = "/tmp/data"
        mock_settings.log_dir = "/tmp/logs"
        mock_settings.profile_dir = "/tmp/profiles"
        mock_settings.enable_tls = False
        mock_settings.visa_backend = "@py"
        mock_settings.connection_timeout_ms = 5000
        mock_settings.command_timeout_ms = 1000
        mock_settings.enable_auto_reconnect = False
        mock_settings.enable_health_monitoring = False
        mock_settings.log_level = "INFO"
        mock_settings.log_to_file = True
        mock_settings.log_rotation_size_mb = 10
        mock_settings.log_retention_days = 30
        mock_settings.require_authentication = False
        mock_settings.ws_max_connections = 0  # Invalid
        mock_settings.ws_message_queue_size = 100
        mock_settings.validate_all = Mock(return_value=[])

        validator = ConfigValidator()
        is_valid = validator.validate()

        assert is_valid is False
        assert any("WebSocket" in error and "connections" in error for error in validator.errors)

    @patch('server.config.validator.settings')
    def test_high_websocket_connections_warning(self, mock_settings):
        """Test warning for very high max WebSocket connections."""
        mock_settings.api_port = 8000
        mock_settings.ws_port = 8001
        mock_settings.host = "127.0.0.1"
        mock_settings.data_dir = "/tmp/data"
        mock_settings.log_dir = "/tmp/logs"
        mock_settings.profile_dir = "/tmp/profiles"
        mock_settings.enable_tls = False
        mock_settings.visa_backend = "@py"
        mock_settings.connection_timeout_ms = 5000
        mock_settings.command_timeout_ms = 1000
        mock_settings.enable_auto_reconnect = False
        mock_settings.enable_health_monitoring = False
        mock_settings.log_level = "INFO"
        mock_settings.log_to_file = True
        mock_settings.log_rotation_size_mb = 10
        mock_settings.log_retention_days = 30
        mock_settings.require_authentication = False
        mock_settings.ws_max_connections = 150  # Very high
        mock_settings.ws_message_queue_size = 100
        mock_settings.validate_all = Mock(return_value=[])

        validator = ConfigValidator()
        validator.validate()

        assert any("WebSocket" in warning and "connections" in warning
                  for warning in validator.warnings)

    @patch('server.config.validator.settings')
    def test_small_message_queue_warning(self, mock_settings):
        """Test warning for small WebSocket message queue."""
        mock_settings.api_port = 8000
        mock_settings.ws_port = 8001
        mock_settings.host = "127.0.0.1"
        mock_settings.data_dir = "/tmp/data"
        mock_settings.log_dir = "/tmp/logs"
        mock_settings.profile_dir = "/tmp/profiles"
        mock_settings.enable_tls = False
        mock_settings.visa_backend = "@py"
        mock_settings.connection_timeout_ms = 5000
        mock_settings.command_timeout_ms = 1000
        mock_settings.enable_auto_reconnect = False
        mock_settings.enable_health_monitoring = False
        mock_settings.log_level = "INFO"
        mock_settings.log_to_file = True
        mock_settings.log_rotation_size_mb = 10
        mock_settings.log_retention_days = 30
        mock_settings.require_authentication = False
        mock_settings.ws_max_connections = 50
        mock_settings.ws_message_queue_size = 5  # Very small
        mock_settings.validate_all = Mock(return_value=[])

        validator = ConfigValidator()
        validator.validate()

        assert any("message queue" in warning.lower() for warning in validator.warnings)

    @patch('server.config.validator.settings')
    def test_settings_level_warnings_included(self, mock_settings):
        """Test that settings-level validation warnings are included."""
        mock_settings.api_port = 8000
        mock_settings.ws_port = 8001
        mock_settings.host = "127.0.0.1"
        mock_settings.data_dir = "/tmp/data"
        mock_settings.log_dir = "/tmp/logs"
        mock_settings.profile_dir = "/tmp/profiles"
        mock_settings.enable_tls = False
        mock_settings.visa_backend = "@py"
        mock_settings.connection_timeout_ms = 5000
        mock_settings.command_timeout_ms = 1000
        mock_settings.enable_auto_reconnect = False
        mock_settings.enable_health_monitoring = False
        mock_settings.log_level = "INFO"
        mock_settings.log_to_file = True
        mock_settings.log_rotation_size_mb = 10
        mock_settings.log_retention_days = 30
        mock_settings.require_authentication = False
        mock_settings.ws_max_connections = 50
        mock_settings.ws_message_queue_size = 100
        # Mock validate_all to return some warnings
        mock_settings.validate_all = Mock(return_value=[
            "Settings warning 1",
            "Settings warning 2"
        ])

        validator = ConfigValidator()
        validator.validate()

        assert "Settings warning 1" in validator.warnings
        assert "Settings warning 2" in validator.warnings

    @patch('builtins.print')
    @patch('server.config.validator.settings')
    def test_print_results_with_errors(self, mock_settings, mock_print):
        """Test print_results method with errors."""
        mock_settings.api_port = 8000
        mock_settings.ws_port = 8000  # Conflict
        mock_settings.host = "127.0.0.1"
        mock_settings.data_dir = "/tmp/data"
        mock_settings.log_dir = "/tmp/logs"
        mock_settings.profile_dir = "/tmp/profiles"
        mock_settings.enable_tls = False
        mock_settings.visa_backend = "@py"
        mock_settings.connection_timeout_ms = 5000
        mock_settings.command_timeout_ms = 1000
        mock_settings.enable_auto_reconnect = False
        mock_settings.enable_health_monitoring = False
        mock_settings.log_level = "INFO"
        mock_settings.log_to_file = True
        mock_settings.log_rotation_size_mb = 10
        mock_settings.log_retention_days = 30
        mock_settings.require_authentication = False
        mock_settings.ws_max_connections = 50
        mock_settings.ws_message_queue_size = 100
        mock_settings.validate_all = Mock(return_value=[])

        validator = ConfigValidator()
        validator.validate()
        result = validator.print_results()

        assert result is False  # Should return False due to errors
        # Check that print was called
        assert mock_print.called

    @patch('builtins.print')
    @patch('server.config.validator.settings')
    def test_print_results_valid_config(self, mock_settings, mock_print):
        """Test print_results method with valid config."""
        mock_settings.api_port = 8000
        mock_settings.ws_port = 8001
        mock_settings.host = "127.0.0.1"
        mock_settings.data_dir = "/tmp/data"
        mock_settings.log_dir = "/tmp/logs"
        mock_settings.profile_dir = "/tmp/profiles"
        mock_settings.enable_tls = False
        mock_settings.visa_backend = "@py"
        mock_settings.connection_timeout_ms = 5000
        mock_settings.command_timeout_ms = 1000
        mock_settings.enable_auto_reconnect = False
        mock_settings.enable_health_monitoring = False
        mock_settings.log_level = "INFO"
        mock_settings.log_to_file = True
        mock_settings.log_rotation_size_mb = 10
        mock_settings.log_retention_days = 30
        mock_settings.require_authentication = False
        mock_settings.ws_max_connections = 50
        mock_settings.ws_message_queue_size = 100
        mock_settings.validate_all = Mock(return_value=[])

        validator = ConfigValidator()
        validator.validate()
        result = validator.print_results()

        assert result is True  # Should return True for valid config
        assert mock_print.called


class TestValidateConfigFunction:
    """Test the validate_config convenience function."""

    @patch('server.config.validator.ConfigValidator')
    def test_validate_config_function(self, mock_validator_class):
        """Test validate_config function calls validator correctly."""
        # Setup mock
        mock_validator = Mock()
        mock_validator.validate.return_value = True
        mock_validator.print_results.return_value = True
        mock_validator_class.return_value = mock_validator

        # Call function
        result = validate_config()

        # Verify
        assert result is True
        mock_validator.validate.assert_called_once()
        mock_validator.print_results.assert_called_once()


# Mark all tests as unit tests
pytestmark = pytest.mark.unit
