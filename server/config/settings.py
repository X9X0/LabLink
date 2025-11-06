"""Server configuration settings."""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """LabLink server settings."""

    # Server Configuration
    host: str = "0.0.0.0"
    api_port: int = 8000
    ws_port: int = 8001
    debug: bool = False

    # Data Storage
    data_dir: str = "./data"
    log_dir: str = "./logs"
    buffer_size: int = 1000
    data_format: str = "hdf5"

    # Equipment Configuration
    auto_discover_devices: bool = True
    visa_backend: str = "@py"  # Use pyvisa-py backend

    # Security
    api_key: Optional[str] = None
    enable_tls: bool = False
    cert_file: Optional[str] = None
    key_file: Optional[str] = None

    class Config:
        env_file = ".env"
        env_prefix = "LABLINK_"


# Global settings instance
settings = Settings()
