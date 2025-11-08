"""Configuration validator for LabLink server."""

import logging
from pathlib import Path
from .settings import settings

logger = logging.getLogger(__name__)


class ConfigValidator:
    """Validates server configuration and provides detailed feedback."""

    def __init__(self):
        self.errors = []
        self.warnings = []
        self.info = []

    def validate(self) -> bool:
        """
        Validate all configuration settings.

        Returns:
            bool: True if configuration is valid (no errors), False otherwise
        """
        self._validate_server_settings()
        self._validate_paths()
        self._validate_equipment_settings()
        self._validate_error_handling()
        self._validate_logging()
        self._validate_security()
        self._validate_websocket()

        # Add settings-level warnings
        for warning in settings.validate_all():
            self.warnings.append(warning)

        return len(self.errors) == 0

    def _validate_server_settings(self):
        """Validate server configuration."""
        # Check port conflicts
        if settings.api_port == settings.ws_port:
            self.errors.append(f"API port and WebSocket port cannot be the same: {settings.api_port}")

        # Check port range
        if settings.api_port < 1024:
            self.warnings.append(f"API port {settings.api_port} < 1024 may require root privileges")

        if settings.ws_port < 1024:
            self.warnings.append(f"WebSocket port {settings.ws_port} < 1024 may require root privileges")

        # Check host binding
        if settings.host == "0.0.0.0":
            self.info.append("Server bound to all interfaces (0.0.0.0)")
        else:
            self.info.append(f"Server bound to {settings.host}")

    def _validate_paths(self):
        """Validate file paths."""
        # Data directory
        data_path = Path(settings.data_dir)
        if not data_path.exists():
            self.info.append(f"Data directory will be created: {data_path}")

        # Log directory
        log_path = Path(settings.log_dir)
        if not log_path.exists():
            self.info.append(f"Log directory will be created: {log_path}")

        # Profile directory
        profile_path = Path(settings.profile_dir)
        if not profile_path.exists():
            self.info.append(f"Profile directory will be created: {profile_path}")

        # TLS certificates
        if settings.enable_tls:
            if settings.cert_file:
                cert_path = Path(settings.cert_file)
                if not cert_path.exists():
                    self.errors.append(f"TLS certificate file not found: {cert_path}")
            else:
                self.errors.append("TLS enabled but cert_file not specified")

            if settings.key_file:
                key_path = Path(settings.key_file)
                if not key_path.exists():
                    self.errors.append(f"TLS key file not found: {key_path}")
            else:
                self.errors.append("TLS enabled but key_file not specified")

    def _validate_equipment_settings(self):
        """Validate equipment configuration."""
        # Check VISA backend
        valid_backends = ["@py", "@ni", "@sim"]
        if settings.visa_backend not in valid_backends:
            self.warnings.append(
                f"Unusual VISA backend '{settings.visa_backend}'. "
                f"Expected one of: {', '.join(valid_backends)}"
            )

        # Check timeouts
        if settings.connection_timeout_ms < 1000:
            self.warnings.append(
                f"Connection timeout {settings.connection_timeout_ms}ms is very short, "
                "may cause connection failures"
            )

        if settings.command_timeout_ms < 100:
            self.warnings.append(
                f"Command timeout {settings.command_timeout_ms}ms is very short, "
                "may cause command failures"
            )

    def _validate_error_handling(self):
        """Validate error handling configuration."""
        if settings.enable_auto_reconnect:
            if settings.reconnect_attempts > 5:
                self.warnings.append(
                    f"High number of reconnect attempts ({settings.reconnect_attempts}) "
                    "may cause long delays"
                )

            total_reconnect_time = sum(
                settings.reconnect_delay_ms * (settings.reconnect_backoff_multiplier ** i)
                for i in range(settings.reconnect_attempts)
            )
            if total_reconnect_time > 30000:
                self.warnings.append(
                    f"Total reconnection time could exceed 30 seconds "
                    f"({total_reconnect_time:.0f}ms)"
                )

        if settings.enable_health_monitoring:
            if settings.health_check_interval_sec < 10:
                self.warnings.append(
                    f"Health check interval {settings.health_check_interval_sec}s is very frequent"
                )

    def _validate_logging(self):
        """Validate logging configuration."""
        # Check log level
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if settings.log_level not in valid_levels:
            self.errors.append(
                f"Invalid log level '{settings.log_level}'. "
                f"Must be one of: {', '.join(valid_levels)}"
            )

        # Check log rotation
        if settings.log_to_file:
            if settings.log_rotation_size_mb < 1:
                self.warnings.append("Log rotation size is very small, files may rotate frequently")

            if settings.log_retention_days < 7:
                self.warnings.append(
                    f"Log retention period ({settings.log_retention_days} days) is short"
                )

    def _validate_security(self):
        """Validate security settings."""
        # Check authentication
        if settings.require_authentication and not settings.api_key:
            self.errors.append("Authentication required but no API key configured")

        # Check production readiness
        if settings.host != "127.0.0.1" and settings.host != "localhost":
            if not settings.require_authentication:
                self.warnings.append(
                    "Server exposed to network without authentication - security risk"
                )

            if settings.enable_cors and settings.cors_origins == "*":
                self.warnings.append(
                    "CORS allows all origins on network-exposed server - security risk"
                )

    def _validate_websocket(self):
        """Validate WebSocket configuration."""
        if settings.ws_max_connections < 1:
            self.errors.append("WebSocket max connections must be at least 1")

        if settings.ws_max_connections > 100:
            self.warnings.append(
                f"High max WebSocket connections ({settings.ws_max_connections}) "
                "may impact performance"
            )

        if settings.ws_message_queue_size < 10:
            self.warnings.append(
                f"Small WebSocket message queue ({settings.ws_message_queue_size}) "
                "may drop messages under high load"
            )

    def print_results(self):
        """Print validation results to console."""
        print("\n" + "=" * 70)
        print("LabLink Configuration Validation")
        print("=" * 70)

        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for i, error in enumerate(self.errors, 1):
                print(f"  {i}. {error}")

        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for i, warning in enumerate(self.warnings, 1):
                print(f"  {i}. {warning}")

        if self.info:
            print(f"\nℹ️  INFO ({len(self.info)}):")
            for i, info in enumerate(self.info, 1):
                print(f"  {i}. {info}")

        print("\n" + "=" * 70)

        if self.errors:
            print("❌ Configuration is INVALID - please fix errors above")
        else:
            print("✅ Configuration is VALID")

        if self.warnings:
            print(f"⚠️  {len(self.warnings)} warning(s) - review recommended")

        print("=" * 70 + "\n")

        return len(self.errors) == 0


def validate_config() -> bool:
    """
    Validate configuration and print results.

    Returns:
        bool: True if valid, False otherwise
    """
    validator = ConfigValidator()
    is_valid = validator.validate()
    validator.print_results()
    return is_valid
