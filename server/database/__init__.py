"""Database integration module for LabLink.

This module provides centralized data storage using SQLite for:
- Command history logging
- Measurement archival
- Equipment usage statistics
- User activity tracking
- Historical data search and query
"""

from .manager import DatabaseManager
from .migrations import MigrationManager
from .models import (CommandRecord, DatabaseConfig, DataSessionRecord,
                     EquipmentUsageRecord, MeasurementRecord)

__all__ = [
    "CommandRecord",
    "MeasurementRecord",
    "EquipmentUsageRecord",
    "DataSessionRecord",
    "DatabaseConfig",
    "DatabaseManager",
    "MigrationManager",
]

# Global database manager instance
_db_manager = None


def initialize_database_manager(db_path: str = "data/lablink.db") -> DatabaseManager:
    """Initialize the global database manager.

    Args:
        db_path: Path to SQLite database file

    Returns:
        DatabaseManager instance
    """
    global _db_manager
    _db_manager = DatabaseManager(db_path)
    _db_manager.initialize()
    return _db_manager


def get_database_manager() -> DatabaseManager:
    """Get the global database manager instance.

    Returns:
        DatabaseManager instance

    Raises:
        RuntimeError: If database manager not initialized
    """
    if _db_manager is None:
        raise RuntimeError(
            "Database manager not initialized. Call initialize_database_manager() first."
        )
    return _db_manager
