"""Automated test sequences module for LabLink.

This module provides comprehensive test automation capabilities including:
- Test sequence creation and management
- Parameter sweeping for characterization
- Automated execution with pass/fail validation
- Test result archival and trending
- Template library for common tests
"""

from .executor import TestExecutor
from .models import (ParameterSweep, StepType, TestExecution, TestResult,
                     TestSequence, TestStatus, TestStep)
from .templates import TestTemplateLibrary
from .validator import TestValidator

__all__ = [
    "TestSequence",
    "TestStep",
    "TestResult",
    "TestExecution",
    "ParameterSweep",
    "TestStatus",
    "StepType",
    "TestExecutor",
    "TestValidator",
    "TestTemplateLibrary",
    "get_test_executor",
    "initialize_test_executor",
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
        raise RuntimeError(
            "Test executor not initialized. Call initialize_test_executor() first."
        )
    return _test_executor
