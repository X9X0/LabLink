"""Server configuration settings."""

import logging
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """LabLink server settings with comprehensive configuration options."""

    # ==================== Server Configuration ====================
    host: str = Field(default="0.0.0.0", description="Server host address")
    api_port: int = Field(
        default=8000, ge=1024, le=65535, description="API server port"
    )
    ws_port: int = Field(
        default=8001, ge=1024, le=65535, description="WebSocket server port"
    )
    debug: bool = Field(default=False, description="Enable debug mode")
    server_name: str = Field(
        default="LabLink Server", description="Server instance name"
    )

    # ==================== Data Storage ====================
    data_dir: str = Field(default="./data", description="Data storage directory")
    log_dir: str = Field(default="./logs", description="Log file directory")
    profile_dir: str = Field(
        default="./profiles", description="Equipment profile directory"
    )
    buffer_size: int = Field(default=1000, ge=100, description="Data buffer size")
    data_format: Literal["hdf5", "csv", "numpy", "json"] = Field(
        default="hdf5", description="Default data export format"
    )
    max_file_size_mb: int = Field(
        default=100, ge=1, description="Maximum data file size in MB"
    )
    enable_compression: bool = Field(
        default=True, description="Enable data compression"
    )

    # ==================== Equipment Configuration ====================
    auto_discover_devices: bool = Field(
        default=True, description="Auto-discover devices on startup"
    )
    enable_mock_equipment: bool = Field(
        default=False, description="Auto-register mock equipment on startup"
    )
    mock_equipment_types: str = Field(
        default="oscilloscope,power_supply,electronic_load",
        description="Comma-separated list of mock equipment types to register",
    )
    visa_backend: str = Field(
        default="@py", description="PyVISA backend (@py, @ni, @sim)"
    )
    connection_timeout_ms: int = Field(
        default=10000, ge=1000, description="Equipment connection timeout (ms)"
    )
    command_timeout_ms: int = Field(
        default=5000, ge=100, description="Command execution timeout (ms)"
    )

    # ==================== Error Handling & Recovery ====================
    enable_auto_reconnect: bool = Field(
        default=True, description="Enable automatic reconnection"
    )
    reconnect_attempts: int = Field(
        default=3, ge=1, le=10, description="Number of reconnection attempts"
    )
    reconnect_delay_ms: int = Field(
        default=1000, ge=100, description="Delay between reconnection attempts (ms)"
    )
    reconnect_backoff_multiplier: float = Field(
        default=2.0, ge=1.0, description="Exponential backoff multiplier"
    )

    enable_health_monitoring: bool = Field(
        default=True, description="Enable equipment health monitoring"
    )
    health_check_interval_sec: int = Field(
        default=30, ge=5, description="Health check interval (seconds)"
    )

    enable_command_retry: bool = Field(
        default=True, description="Enable command retry on failure"
    )
    max_command_retries: int = Field(
        default=2, ge=0, le=5, description="Maximum command retry attempts"
    )
    retry_delay_ms: int = Field(
        default=500, ge=100, description="Delay between command retries (ms)"
    )

    # ==================== Logging Configuration ====================
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Logging level"
    )
    log_format: Literal["json", "text"] = Field(
        default="text", description="Log output format"
    )
    log_to_file: bool = Field(default=True, description="Enable file logging")
    log_rotation_size_mb: int = Field(
        default=10, ge=1, description="Log file rotation size (MB)"
    )
    log_retention_days: int = Field(
        default=30, ge=1, description="Log file retention period (days)"
    )
    enable_performance_logging: bool = Field(
        default=False, description="Log performance metrics"
    )

    # ==================== WebSocket Configuration ====================
    ws_max_connections: int = Field(
        default=10, ge=1, description="Maximum WebSocket connections"
    )
    ws_heartbeat_interval_sec: int = Field(
        default=30, ge=5, description="WebSocket heartbeat interval"
    )
    ws_message_queue_size: int = Field(
        default=1000, ge=10, description="WebSocket message queue size"
    )
    ws_compression_enabled: bool = Field(
        default=True, description="Enable WebSocket compression"
    )

    # ==================== Enhanced WebSocket Features (v0.15.0) ====================
    # Stream Recording
    ws_recording_enabled: bool = Field(
        default=False, description="Enable WebSocket stream recording"
    )
    ws_recording_format: Literal["json", "jsonl", "csv", "binary"] = Field(
        default="jsonl", description="Recording format (json, jsonl, csv, binary)"
    )
    ws_recording_dir: str = Field(
        default="./data/ws_recordings", description="Recording output directory"
    )
    ws_recording_max_size_mb: int = Field(
        default=100, ge=1, description="Maximum recording file size (MB)"
    )
    ws_recording_timestamps: bool = Field(
        default=True, description="Include timestamps in recordings"
    )
    ws_recording_metadata: bool = Field(
        default=True, description="Include metadata in recordings"
    )
    ws_recording_compress: bool = Field(
        default=True, description="Compress recording files (gzip)"
    )

    # Backpressure & Flow Control
    ws_backpressure_enabled: bool = Field(
        default=True, description="Enable backpressure handling"
    )
    ws_queue_warning_threshold: int = Field(
        default=750, ge=1, description="Queue warning threshold (messages)"
    )
    ws_drop_low_priority: bool = Field(
        default=True, description="Drop low priority messages when queue is full"
    )
    ws_rate_limit_enabled: bool = Field(
        default=True, description="Enable per-connection rate limiting"
    )
    ws_max_messages_per_second: int = Field(
        default=100, ge=1, description="Maximum messages per second per connection"
    )
    ws_burst_size: int = Field(
        default=50, ge=1, description="Burst size for rate limiter"
    )

    # ==================== API Configuration ====================
    enable_cors: bool = Field(default=True, description="Enable CORS")
    cors_origins: str = Field(
        default="*", description="CORS allowed origins (comma-separated)"
    )
    enable_rate_limiting: bool = Field(
        default=False, description="Enable API rate limiting"
    )
    rate_limit_requests: int = Field(
        default=100, ge=1, description="Rate limit: requests per window"
    )
    rate_limit_window_sec: int = Field(
        default=60, ge=1, description="Rate limit window (seconds)"
    )

    # ==================== Basic Security ====================
    api_key: Optional[str] = Field(
        default=None,
        description="API authentication key (legacy, use advanced security instead)",
    )
    enable_tls: bool = Field(default=False, description="Enable TLS/HTTPS")
    cert_file: Optional[str] = Field(
        default=None, description="TLS certificate file path"
    )
    key_file: Optional[str] = Field(
        default=None, description="TLS private key file path"
    )
    require_authentication: bool = Field(
        default=False, description="Require API authentication"
    )

    # ==================== Advanced Security System (v0.23.0) ====================
    # Security Enable/Disable
    enable_advanced_security: bool = Field(
        default=False, description="Enable advanced security system (JWT, RBAC, etc.)"
    )
    security_db_path: str = Field(
        default="./data/security.db", description="Security database path"
    )

    # JWT Authentication
    jwt_secret_key: Optional[str] = Field(
        default=None, description="JWT signing secret key (auto-generated if not set)"
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_access_token_expire_minutes: int = Field(
        default=30, ge=1, le=1440, description="JWT access token expiration (minutes)"
    )
    jwt_refresh_token_expire_days: int = Field(
        default=7, ge=1, le=365, description="JWT refresh token expiration (days)"
    )

    # Password Requirements
    password_min_length: int = Field(
        default=8, ge=6, le=128, description="Minimum password length"
    )
    password_require_uppercase: bool = Field(
        default=True, description="Require uppercase letter in password"
    )
    password_require_lowercase: bool = Field(
        default=True, description="Require lowercase letter in password"
    )
    password_require_digit: bool = Field(
        default=True, description="Require digit in password"
    )
    password_require_special: bool = Field(
        default=False, description="Require special character in password"
    )
    password_expiration_days: int = Field(
        default=90, ge=0, description="Password expiration period (0=no expiration)"
    )

    # Account Lockout
    enable_account_lockout: bool = Field(
        default=True, description="Enable account lockout after failed attempts"
    )
    max_failed_login_attempts: int = Field(
        default=5,
        ge=3,
        le=20,
        description="Maximum failed login attempts before lockout",
    )
    account_lockout_duration_minutes: int = Field(
        default=30, ge=1, le=1440, description="Account lockout duration (minutes)"
    )

    # IP Whitelisting
    enable_ip_whitelist: bool = Field(
        default=False, description="Enable IP whitelisting"
    )
    ip_whitelist_enforce: bool = Field(
        default=False, description="Enforce IP whitelist (deny non-whitelisted IPs)"
    )

    # Session Management
    session_timeout_minutes: int = Field(
        default=60, ge=5, le=1440, description="Session timeout (minutes)"
    )
    max_sessions_per_user: int = Field(
        default=5, ge=1, le=50, description="Maximum concurrent sessions per user"
    )

    # API Key Management
    api_key_max_age_days: int = Field(
        default=365, ge=1, le=3650, description="Maximum API key age (days)"
    )
    api_key_rotation_warning_days: int = Field(
        default=30, ge=1, le=365, description="Warn before API key expiration (days)"
    )

    # Security Audit Logging
    enable_security_audit_log: bool = Field(
        default=True, description="Enable security audit logging"
    )
    security_log_retention_days: int = Field(
        default=90, ge=1, le=3650, description="Security audit log retention (days)"
    )
    security_log_failed_logins: bool = Field(
        default=True, description="Log failed login attempts"
    )
    security_log_permission_denials: bool = Field(
        default=True, description="Log permission denials"
    )

    # Default Admin Account (created on first startup)
    create_default_admin: bool = Field(
        default=True, description="Create default admin account on first startup"
    )
    default_admin_username: str = Field(
        default="admin", description="Default admin username"
    )
    default_admin_password: str = Field(
        default="LabLink@2025",
        description="Default admin password (change immediately!)",
    )
    default_admin_email: str = Field(
        default="admin@lablink.local", description="Default admin email"
    )

    # OAuth2 Authentication (v0.25.0)
    enable_oauth2: bool = Field(
        default=False, description="Enable OAuth2 authentication providers"
    )

    # Google OAuth2
    oauth2_google_enabled: bool = Field(
        default=False, description="Enable Google OAuth2"
    )
    oauth2_google_client_id: Optional[str] = Field(
        default=None, description="Google OAuth2 client ID"
    )
    oauth2_google_client_secret: Optional[str] = Field(
        default=None, description="Google OAuth2 client secret"
    )

    # GitHub OAuth2
    oauth2_github_enabled: bool = Field(
        default=False, description="Enable GitHub OAuth2"
    )
    oauth2_github_client_id: Optional[str] = Field(
        default=None, description="GitHub OAuth2 client ID"
    )
    oauth2_github_client_secret: Optional[str] = Field(
        default=None, description="GitHub OAuth2 client secret"
    )

    # Microsoft OAuth2
    oauth2_microsoft_enabled: bool = Field(
        default=False, description="Enable Microsoft OAuth2"
    )
    oauth2_microsoft_client_id: Optional[str] = Field(
        default=None, description="Microsoft OAuth2 client ID"
    )
    oauth2_microsoft_client_secret: Optional[str] = Field(
        default=None, description="Microsoft OAuth2 client secret"
    )

    # ==================== Equipment Profiles ====================
    enable_profiles: bool = Field(default=True, description="Enable equipment profiles")
    auto_load_profiles: bool = Field(
        default=True, description="Auto-load profiles on connection"
    )
    profile_format: Literal["json", "yaml"] = Field(
        default="json", description="Profile file format"
    )

    # ==================== Safety & Interlocks ====================
    enable_safety_limits: bool = Field(
        default=True, description="Enable safety limit checking"
    )
    enforce_slew_rate: bool = Field(
        default=True, description="Enforce slew rate limiting"
    )
    safe_state_on_disconnect: bool = Field(
        default=True, description="Disable outputs on equipment disconnect"
    )
    log_safety_events: bool = Field(
        default=True, description="Log safety violations and events"
    )
    allow_limit_override: bool = Field(
        default=False, description="Allow admin to override safety limits"
    )
    emergency_stop_timeout_sec: int = Field(
        default=300,
        ge=0,
        description="Auto-clear emergency stop after timeout (0=manual only)",
    )

    # ==================== Equipment Locks & Sessions ====================
    enable_equipment_locks: bool = Field(
        default=True, description="Enable equipment lock management"
    )
    lock_timeout_sec: int = Field(
        default=300, ge=0, description="Equipment lock timeout (0=no timeout)"
    )
    session_timeout_sec: int = Field(
        default=600, ge=0, description="Client session timeout (0=no timeout)"
    )
    enable_lock_queue: bool = Field(
        default=True, description="Enable lock queueing when equipment is busy"
    )
    enable_observer_mode: bool = Field(
        default=True, description="Enable observer (read-only) mode"
    )
    auto_release_on_disconnect: bool = Field(
        default=True, description="Auto-release locks when session ends"
    )
    log_lock_events: bool = Field(default=True, description="Log lock/unlock events")

    # ==================== Equipment State Management ====================
    enable_state_management: bool = Field(
        default=True, description="Enable equipment state management"
    )
    state_dir: str = Field(
        default="./states", description="Equipment state storage directory"
    )
    enable_state_persistence: bool = Field(
        default=True, description="Save states to disk"
    )
    enable_state_versioning: bool = Field(
        default=True, description="Enable state version tracking"
    )
    max_states_per_equipment: int = Field(
        default=100, ge=1, description="Maximum states to keep per equipment"
    )
    auto_capture_on_connect: bool = Field(
        default=False, description="Automatically capture state when connecting"
    )

    # ==================== Data Acquisition ====================
    enable_acquisition: bool = Field(
        default=True, description="Enable data acquisition system"
    )
    acquisition_export_dir: str = Field(
        default="./data/acquisitions", description="Acquisition data export directory"
    )
    default_sample_rate: float = Field(
        default=1.0, gt=0, description="Default acquisition sample rate (Hz)"
    )
    default_buffer_size: int = Field(
        default=10000, ge=100, description="Default circular buffer size"
    )
    max_acquisition_duration: int = Field(
        default=3600, ge=1, description="Maximum acquisition duration (seconds)"
    )
    auto_export_on_stop: bool = Field(
        default=False, description="Automatically export data when acquisition stops"
    )

    # ==================== Waveform Capture & Analysis (v0.16.0) ====================
    enable_waveform_analysis: bool = Field(
        default=True, description="Enable advanced waveform analysis"
    )
    waveform_cache_size: int = Field(
        default=100, ge=10, description="Maximum cached waveforms per equipment"
    )
    waveform_export_dir: str = Field(
        default="./data/waveforms", description="Waveform export directory"
    )

    # Acquisition settings
    default_num_averages: int = Field(
        default=1, ge=1, le=100, description="Default number of waveforms to average"
    )
    enable_high_resolution: bool = Field(
        default=False, description="Enable high-resolution mode by default"
    )
    default_decimation_points: int = Field(
        default=1000, ge=100, description="Default decimation target points"
    )

    # Persistence settings
    enable_persistence: bool = Field(
        default=True, description="Enable persistence mode"
    )
    persistence_max_waveforms: int = Field(
        default=100, ge=10, description="Maximum waveforms in persistence buffer"
    )
    persistence_decay_time: float = Field(
        default=1.0, gt=0, description="Variable persistence decay time (seconds)"
    )

    # Histogram settings
    histogram_default_bins: int = Field(
        default=100, ge=10, le=1000, description="Default histogram bin count"
    )

    # Math channel settings
    enable_math_channels: bool = Field(
        default=True, description="Enable math channel operations"
    )
    fft_default_window: str = Field(
        default="hann", description="Default FFT window function"
    )
    math_average_count: int = Field(
        default=10,
        ge=2,
        le=100,
        description="Default averaging count for math operations",
    )

    # Continuous acquisition
    max_continuous_rate_hz: float = Field(
        default=100.0, gt=0, description="Maximum continuous acquisition rate (Hz)"
    )
    continuous_buffer_size: int = Field(
        default=1000, ge=100, description="Continuous acquisition buffer size"
    )

    # ==================== Backup & Restore Configuration (v0.21.0) ====================
    backup_dir: str = Field(
        default="./data/backups", description="Directory to store backups"
    )
    enable_auto_backup: bool = Field(
        default=True, description="Enable automatic scheduled backups"
    )
    auto_backup_interval_hours: int = Field(
        default=24, ge=1, le=168, description="Interval between auto backups (hours)"
    )
    backup_retention_days: int = Field(
        default=30, ge=1, le=365, description="Days to keep backups"
    )
    max_backup_count: int = Field(
        default=10, ge=1, le=100, description="Maximum number of backups to keep"
    )

    # Backup content
    backup_include_config: bool = Field(
        default=True, description="Include configuration in backups"
    )
    backup_include_profiles: bool = Field(
        default=True, description="Include equipment profiles in backups"
    )
    backup_include_states: bool = Field(
        default=True, description="Include equipment states in backups"
    )
    backup_include_database: bool = Field(
        default=True, description="Include database files in backups"
    )
    backup_include_acquisitions: bool = Field(
        default=False, description="Include acquisition data in backups"
    )
    backup_include_logs: bool = Field(
        default=False, description="Include log files in backups"
    )
    backup_include_calibration: bool = Field(
        default=True, description="Include calibration data in backups"
    )

    # Backup options
    backup_compression: Literal["none", "gzip", "zip", "tar.gz"] = Field(
        default="tar.gz", description="Backup compression method"
    )
    backup_verify_after_creation: bool = Field(
        default=True, description="Verify backups after creation"
    )
    backup_calculate_checksums: bool = Field(
        default=True, description="Calculate SHA-256 checksums for backups"
    )

    # ==================== Equipment Discovery Configuration (v0.22.0) ====================
    # Discovery methods
    enable_discovery: bool = Field(
        default=True, description="Enable equipment discovery system"
    )
    enable_mdns_discovery: bool = Field(
        default=True, description="Enable mDNS/Bonjour discovery"
    )
    enable_visa_discovery: bool = Field(
        default=True, description="Enable VISA resource scanning"
    )
    enable_usb_discovery: bool = Field(
        default=True, description="Enable USB device scanning"
    )
    enable_auto_discovery: bool = Field(
        default=False, description="Enable automatic background discovery (disabled by default to avoid interference with measurements)"
    )

    # Discovery intervals (only used if enable_auto_discovery=True)
    mdns_scan_interval_sec: int = Field(
        default=600, ge=10, description="mDNS scan interval in seconds (default 10 min)"
    )
    visa_scan_interval_sec: int = Field(
        default=300, ge=10, description="VISA scan interval in seconds (default 5 min)"
    )

    # Discovery scope
    discovery_scan_tcpip: bool = Field(default=True, description="Scan TCPIP resources")
    discovery_scan_usb: bool = Field(default=True, description="Scan USB resources")
    discovery_scan_gpib: bool = Field(default=False, description="Scan GPIB resources")
    discovery_scan_serial: bool = Field(
        default=True, description="Scan serial resources (enable for USB-to-serial devices like BK 1685B)"
    )

    # Connection testing
    discovery_test_connections: bool = Field(
        default=True, description="Test discovered devices"
    )
    discovery_query_idn: bool = Field(
        default=True, description="Query *IDN? for device identification"
    )

    # History and caching
    discovery_enable_history: bool = Field(
        default=True, description="Track connection history"
    )
    discovery_history_retention_days: int = Field(
        default=90, ge=1, description="Days to keep history"
    )
    discovery_enable_recommendations: bool = Field(
        default=True, description="Enable smart recommendations"
    )
    discovery_cache_devices: bool = Field(
        default=True, description="Cache discovered devices"
    )
    discovery_cache_ttl_sec: int = Field(
        default=300, ge=60, description="Cache TTL (seconds)"
    )

    class Config:
        env_file = ".env"
        env_prefix = "LABLINK_"
        case_sensitive = False

    @validator(
        "log_dir",
        "data_dir",
        "profile_dir",
        "state_dir",
        "acquisition_export_dir",
        "ws_recording_dir",
        "waveform_export_dir",
        "backup_dir",
    )
    def create_directories(cls, v):
        """Ensure directories exist."""
        path = Path(v)
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    @validator("api_port", "ws_port")
    def validate_different_ports(cls, v, values):
        """Ensure API and WebSocket ports are different."""
        if "api_port" in values and v == values["api_port"]:
            raise ValueError("WebSocket port must be different from API port")
        return v

    def validate_all(self) -> list[str]:
        """Validate all settings and return warnings."""
        warnings = []

        # Check if debug is enabled in production
        if self.debug and not self.host.startswith("127."):
            warnings.append(
                "Debug mode enabled on non-localhost - potential security risk"
            )

        # Check TLS configuration
        if self.enable_tls and (not self.cert_file or not self.key_file):
            warnings.append("TLS enabled but certificate files not specified")

        # Check authentication
        if not self.require_authentication and not self.host.startswith("127."):
            warnings.append(
                "No authentication on non-localhost - potential security risk"
            )

        # Check CORS
        if self.enable_cors and self.cors_origins == "*":
            warnings.append(
                "CORS allows all origins - consider restricting in production"
            )

        return warnings

    def get_numeric_log_level(self) -> int:
        """Get numeric logging level."""
        return getattr(logging, self.log_level)


# Global settings instance
settings = Settings()
