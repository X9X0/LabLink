"""Automated test sequences module for LabLink.

This module provides comprehensive test automation capabilities including:
- Test sequence creation and management
- Parameter sweeping for characterization
- Automated execution with pass/fail validation
- Test result archival and trending
- Template library for common tests
"""

from .models import (
    TestSequence,
    TestStep,
    TestResult,
    ParameterSweep,
    TestStatus,
    StepType,
)
from .executor import TestExecutor
from .validator import TestValidator
from .templates import TestTemplateLibrary

__all__ = [
    "TestSequence",
    "TestStep",
    "TestResult",
    "ParameterSweep",
    "TestStatus",
    "StepType",
    "TestExecutor",
    "TestValidator",
    "TestTemplateLibrary",
]

# Global test executor instance
_test_executor = None


def initialize_test_executor(equipment_manager, database_manager) -> TestExecutor:
    """Initialize the global test executor.

    Args:
        equipment_manager: Equipment manager instance
        database_manager: Database manager instance

    Returns:
        TestExecutor instance
    """
    global _test_executor
    _test_executor = TestExecutor(equipment_manager, database_manager)
    return _test_executor


def get_test_executor() -> TestExecutor:
    """Get the global test executor instance.

    Returns:
        TestExecutor instance

    Raises:
        RuntimeError: If test executor not initialized
    """
    if _test_executor is None:
        raise RuntimeError("Test executor not initialized. Call initialize_test_executor() first.")
    return _test_executor
