"""Server configuration settings."""

from pydantic_settings import BaseSettings
from pydantic import Field, validator
from typing import Optional, Literal
from pathlib import Path
import logging


class Settings(BaseSettings):
    """LabLink server settings with comprehensive configuration options."""

    # ==================== Server Configuration ====================
    host: str = Field(default="0.0.0.0", description="Server host address")
    api_port: int = Field(default=8000, ge=1024, le=65535, description="API server port")
    ws_port: int = Field(default=8001, ge=1024, le=65535, description="WebSocket server port")
    debug: bool = Field(default=False, description="Enable debug mode")
    server_name: str = Field(default="LabLink Server", description="Server instance name")

    # ==================== Data Storage ====================
    data_dir: str = Field(default="./data", description="Data storage directory")
    log_dir: str = Field(default="./logs", description="Log file directory")
    profile_dir: str = Field(default="./profiles", description="Equipment profile directory")
    buffer_size: int = Field(default=1000, ge=100, description="Data buffer size")
    data_format: Literal["hdf5", "csv", "numpy", "json"] = Field(
        default="hdf5", description="Default data export format"
    )
    max_file_size_mb: int = Field(default=100, ge=1, description="Maximum data file size in MB")
    enable_compression: bool = Field(default=True, description="Enable data compression")

    # ==================== Equipment Configuration ====================
    auto_discover_devices: bool = Field(default=True, description="Auto-discover devices on startup")
    enable_mock_equipment: bool = Field(default=False, description="Auto-register mock equipment on startup")
    mock_equipment_types: str = Field(default="oscilloscope,power_supply,electronic_load", description="Comma-separated list of mock equipment types to register")
    visa_backend: str = Field(default="@py", description="PyVISA backend (@py, @ni, @sim)")
    connection_timeout_ms: int = Field(default=10000, ge=1000, description="Equipment connection timeout (ms)")
    command_timeout_ms: int = Field(default=5000, ge=100, description="Command execution timeout (ms)")

    # ==================== Error Handling & Recovery ====================
    enable_auto_reconnect: bool = Field(default=True, description="Enable automatic reconnection")
    reconnect_attempts: int = Field(default=3, ge=1, le=10, description="Number of reconnection attempts")
    reconnect_delay_ms: int = Field(default=1000, ge=100, description="Delay between reconnection attempts (ms)")
    reconnect_backoff_multiplier: float = Field(default=2.0, ge=1.0, description="Exponential backoff multiplier")

    enable_health_monitoring: bool = Field(default=True, description="Enable equipment health monitoring")
    health_check_interval_sec: int = Field(default=30, ge=5, description="Health check interval (seconds)")

    enable_command_retry: bool = Field(default=True, description="Enable command retry on failure")
    max_command_retries: int = Field(default=2, ge=0, le=5, description="Maximum command retry attempts")
    retry_delay_ms: int = Field(default=500, ge=100, description="Delay between command retries (ms)")

    # ==================== Logging Configuration ====================
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Logging level"
    )
    log_format: Literal["json", "text"] = Field(default="text", description="Log output format")
    log_to_file: bool = Field(default=True, description="Enable file logging")
    log_rotation_size_mb: int = Field(default=10, ge=1, description="Log file rotation size (MB)")
    log_retention_days: int = Field(default=30, ge=1, description="Log file retention period (days)")
    enable_performance_logging: bool = Field(default=False, description="Log performance metrics")

    # ==================== WebSocket Configuration ====================
    ws_max_connections: int = Field(default=10, ge=1, description="Maximum WebSocket connections")
    ws_heartbeat_interval_sec: int = Field(default=30, ge=5, description="WebSocket heartbeat interval")
    ws_message_queue_size: int = Field(default=1000, ge=10, description="WebSocket message queue size")
    ws_compression_enabled: bool = Field(default=True, description="Enable WebSocket compression")

    # ==================== Enhanced WebSocket Features (v0.15.0) ====================
    # Stream Recording
    ws_recording_enabled: bool = Field(default=False, description="Enable WebSocket stream recording")
    ws_recording_format: Literal["json", "jsonl", "csv", "binary"] = Field(
        default="jsonl", description="Recording format (json, jsonl, csv, binary)"
    )
    ws_recording_dir: str = Field(default="./data/ws_recordings", description="Recording output directory")
    ws_recording_max_size_mb: int = Field(default=100, ge=1, description="Maximum recording file size (MB)")
    ws_recording_timestamps: bool = Field(default=True, description="Include timestamps in recordings")
    ws_recording_metadata: bool = Field(default=True, description="Include metadata in recordings")
    ws_recording_compress: bool = Field(default=True, description="Compress recording files (gzip)")

    # Backpressure & Flow Control
    ws_backpressure_enabled: bool = Field(default=True, description="Enable backpressure handling")
    ws_queue_warning_threshold: int = Field(default=750, ge=1, description="Queue warning threshold (messages)")
    ws_drop_low_priority: bool = Field(default=True, description="Drop low priority messages when queue is full")
    ws_rate_limit_enabled: bool = Field(default=True, description="Enable per-connection rate limiting")
    ws_max_messages_per_second: int = Field(default=100, ge=1, description="Maximum messages per second per connection")
    ws_burst_size: int = Field(default=50, ge=1, description="Burst size for rate limiter")

    # ==================== API Configuration ====================
    enable_cors: bool = Field(default=True, description="Enable CORS")
    cors_origins: str = Field(default="*", description="CORS allowed origins (comma-separated)")
    enable_rate_limiting: bool = Field(default=False, description="Enable API rate limiting")
    rate_limit_requests: int = Field(default=100, ge=1, description="Rate limit: requests per window")
    rate_limit_window_sec: int = Field(default=60, ge=1, description="Rate limit window (seconds)")

    # ==================== Security ====================
    api_key: Optional[str] = Field(default=None, description="API authentication key")
    enable_tls: bool = Field(default=False, description="Enable TLS/HTTPS")
    cert_file: Optional[str] = Field(default=None, description="TLS certificate file path")
    key_file: Optional[str] = Field(default=None, description="TLS private key file path")
    require_authentication: bool = Field(default=False, description="Require API authentication")

    # ==================== Equipment Profiles ====================
    enable_profiles: bool = Field(default=True, description="Enable equipment profiles")
    auto_load_profiles: bool = Field(default=True, description="Auto-load profiles on connection")
    profile_format: Literal["json", "yaml"] = Field(default="json", description="Profile file format")

    # ==================== Safety & Interlocks ====================
    enable_safety_limits: bool = Field(default=True, description="Enable safety limit checking")
    enforce_slew_rate: bool = Field(default=True, description="Enforce slew rate limiting")
    safe_state_on_disconnect: bool = Field(default=True, description="Disable outputs on equipment disconnect")
    log_safety_events: bool = Field(default=True, description="Log safety violations and events")
    allow_limit_override: bool = Field(default=False, description="Allow admin to override safety limits")
    emergency_stop_timeout_sec: int = Field(default=300, ge=0, description="Auto-clear emergency stop after timeout (0=manual only)")

    # ==================== Equipment Locks & Sessions ====================
    enable_equipment_locks: bool = Field(default=True, description="Enable equipment lock management")
    lock_timeout_sec: int = Field(default=300, ge=0, description="Equipment lock timeout (0=no timeout)")
    session_timeout_sec: int = Field(default=600, ge=0, description="Client session timeout (0=no timeout)")
    enable_lock_queue: bool = Field(default=True, description="Enable lock queueing when equipment is busy")
    enable_observer_mode: bool = Field(default=True, description="Enable observer (read-only) mode")
    auto_release_on_disconnect: bool = Field(default=True, description="Auto-release locks when session ends")
    log_lock_events: bool = Field(default=True, description="Log lock/unlock events")

    # ==================== Equipment State Management ====================
    enable_state_management: bool = Field(default=True, description="Enable equipment state management")
    state_dir: str = Field(default="./states", description="Equipment state storage directory")
    enable_state_persistence: bool = Field(default=True, description="Save states to disk")
    enable_state_versioning: bool = Field(default=True, description="Enable state version tracking")
    max_states_per_equipment: int = Field(default=100, ge=1, description="Maximum states to keep per equipment")
    auto_capture_on_connect: bool = Field(default=False, description="Automatically capture state when connecting")

    # ==================== Data Acquisition ====================
    enable_acquisition: bool = Field(default=True, description="Enable data acquisition system")
    acquisition_export_dir: str = Field(default="./data/acquisitions", description="Acquisition data export directory")
    default_sample_rate: float = Field(default=1.0, gt=0, description="Default acquisition sample rate (Hz)")
    default_buffer_size: int = Field(default=10000, ge=100, description="Default circular buffer size")
    max_acquisition_duration: int = Field(default=3600, ge=1, description="Maximum acquisition duration (seconds)")
    auto_export_on_stop: bool = Field(default=False, description="Automatically export data when acquisition stops")

    class Config:
        env_file = ".env"
        env_prefix = "LABLINK_"
        case_sensitive = False

    @validator("log_dir", "data_dir", "profile_dir", "state_dir", "acquisition_export_dir", "ws_recording_dir")
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
            warnings.append("Debug mode enabled on non-localhost - potential security risk")

        # Check TLS configuration
        if self.enable_tls and (not self.cert_file or not self.key_file):
            warnings.append("TLS enabled but certificate files not specified")

        # Check authentication
        if not self.require_authentication and not self.host.startswith("127."):
            warnings.append("No authentication on non-localhost - potential security risk")

        # Check CORS
        if self.enable_cors and self.cors_origins == "*":
            warnings.append("CORS allows all origins - consider restricting in production")

        return warnings

    def get_numeric_log_level(self) -> int:
        """Get numeric logging level."""
        return getattr(logging, self.log_level)


# Global settings instance
settings = Settings()
