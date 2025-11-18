"""
Comprehensive tests for the error code database.

Tests cover:
- ErrorSeverity and ErrorCategory enums
- ErrorCodeInfo model
- ErrorCodeDatabase class:
  - Initialization and code loading
  - Error code lookup
  - Vendor-specific codes
  - Error message formatting
  - Troubleshooting information
  - Adding custom codes
  - Searching and filtering
  - Severity and category filtering
"""

import pytest
from typing import List

from server.equipment.error_codes import (
    ErrorSeverity,
    ErrorCategory,
    ErrorCodeInfo,
    ErrorCodeDatabase,
    get_error_code_db,
    initialize_error_code_db,
)


# ==================== Fixtures ====================


@pytest.fixture
def error_db():
    """Create a fresh error code database for each test."""
    return ErrorCodeDatabase()


# ==================== Enum Tests ====================


class TestErrorCodeEnums:
    """Test error code enumeration types."""

    def test_error_severity_values(self):
        """Test ErrorSeverity enum has all expected values."""
        assert ErrorSeverity.INFO == "info"
        assert ErrorSeverity.WARNING == "warning"
        assert ErrorSeverity.ERROR == "error"
        assert ErrorSeverity.CRITICAL == "critical"
        assert ErrorSeverity.FATAL == "fatal"

    def test_error_category_values(self):
        """Test ErrorCategory enum has all expected values."""
        assert ErrorCategory.COMMUNICATION == "communication"
        assert ErrorCategory.HARDWARE == "hardware"
        assert ErrorCategory.CALIBRATION == "calibration"
        assert ErrorCategory.OPERATION == "operation"
        assert ErrorCategory.SAFETY == "safety"
        assert ErrorCategory.CONFIGURATION == "configuration"
        assert ErrorCategory.POWER == "power"
        assert ErrorCategory.TEMPERATURE == "temperature"
        assert ErrorCategory.FIRMWARE == "firmware"
        assert ErrorCategory.UNKNOWN == "unknown"


# ==================== ErrorCodeInfo Model Tests ====================


class TestErrorCodeInfo:
    """Test ErrorCodeInfo Pydantic model."""

    def test_minimal_error_code_info(self):
        """Test creating minimal ErrorCodeInfo."""
        info = ErrorCodeInfo(
            code=-100,
            name="Command Error",
            message="Generic command error",
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.COMMUNICATION,
        )

        assert info.code == -100
        assert info.name == "Command Error"
        assert info.message == "Generic command error"
        assert info.severity == ErrorSeverity.ERROR
        assert info.category == ErrorCategory.COMMUNICATION
        assert info.possible_causes == []
        assert info.recommended_actions == []
        assert info.auto_recoverable is False
        assert info.requires_reset is False
        assert info.requires_service is False

    def test_full_error_code_info(self):
        """Test creating full ErrorCodeInfo with all fields."""
        info = ErrorCodeInfo(
            code=-310,
            name="System Error",
            message="Internal system error",
            severity=ErrorSeverity.CRITICAL,
            category=ErrorCategory.HARDWARE,
            possible_causes=["Internal system failure", "Firmware issue"],
            recommended_actions=["Restart equipment", "Update firmware", "Contact service"],
            manual_reference="Section 5.3.2",
            additional_info="May require factory service",
            auto_recoverable=False,
            requires_reset=True,
            requires_service=True,
        )

        assert info.code == -310
        assert info.severity == ErrorSeverity.CRITICAL
        assert len(info.possible_causes) == 2
        assert len(info.recommended_actions) == 3
        assert info.manual_reference == "Section 5.3.2"
        assert info.requires_reset is True
        assert info.requires_service is True

    def test_auto_recoverable_error(self):
        """Test ErrorCodeInfo for auto-recoverable error."""
        info = ErrorCodeInfo(
            code=-350,
            name="Queue Overflow",
            message="Error queue overflow",
            severity=ErrorSeverity.WARNING,
            category=ErrorCategory.OPERATION,
            auto_recoverable=True,
        )

        assert info.auto_recoverable is True
        assert info.requires_reset is False
        assert info.requires_service is False


# ==================== ErrorCodeDatabase Tests ====================


class TestErrorCodeDatabase:
    """Test ErrorCodeDatabase functionality."""

    def test_database_initialization(self, error_db):
        """Test database initializes with standard and vendor codes."""
        # Check standard codes are loaded
        standard_codes = error_db.get_all_codes("standard")
        assert len(standard_codes) > 0
        assert 0 in standard_codes  # No error code
        assert -100 in standard_codes  # Command error
        assert -200 in standard_codes  # Execution error
        assert -300 in standard_codes  # Hardware error

        # Check Rigol codes are loaded
        rigol_codes = error_db.get_all_codes("rigol")
        assert len(rigol_codes) > 0
        assert 100 in rigol_codes
        assert 200 in rigol_codes
        assert 300 in rigol_codes

        # Check BK Precision codes are loaded
        bk_codes = error_db.get_all_codes("bk_precision")
        assert len(bk_codes) > 0
        assert 1 in bk_codes
        assert 2 in bk_codes
        assert 3 in bk_codes

    def test_lookup_standard_error(self, error_db):
        """Test looking up standard error code."""
        error_info = error_db.lookup_error(-100, "standard")

        assert error_info is not None
        assert error_info.code == -100
        assert error_info.name == "Command Error"
        assert error_info.severity == ErrorSeverity.ERROR
        assert error_info.category == ErrorCategory.COMMUNICATION

    def test_lookup_no_error(self, error_db):
        """Test looking up error code 0 (no error)."""
        error_info = error_db.lookup_error(0, "standard")

        assert error_info is not None
        assert error_info.code == 0
        assert error_info.name == "No Error"
        assert error_info.severity == ErrorSeverity.INFO

    def test_lookup_vendor_specific_error(self, error_db):
        """Test looking up vendor-specific error code."""
        # Rigol temperature warning
        error_info = error_db.lookup_error(300, "rigol")

        assert error_info is not None
        assert error_info.code == 300
        assert error_info.name == "Temperature Warning"
        assert error_info.category == ErrorCategory.TEMPERATURE

        # BK OVP trip
        error_info = error_db.lookup_error(1, "bk_precision")

        assert error_info is not None
        assert error_info.code == 1
        assert error_info.name == "OVP Trip"
        assert error_info.category == ErrorCategory.SAFETY

    def test_lookup_fallback_to_standard(self, error_db):
        """Test fallback to standard codes when not found in vendor codes."""
        # Look up standard error code using vendor parameter
        error_info = error_db.lookup_error(-100, "rigol")

        assert error_info is not None
        assert error_info.code == -100
        assert error_info.name == "Command Error"

    def test_lookup_nonexistent_error(self, error_db):
        """Test looking up non-existent error code."""
        error_info = error_db.lookup_error(99999, "standard")

        assert error_info is None

    def test_lookup_case_insensitive_vendor(self, error_db):
        """Test vendor name is case-insensitive."""
        error_info1 = error_db.lookup_error(300, "RIGOL")
        error_info2 = error_db.lookup_error(300, "Rigol")
        error_info3 = error_db.lookup_error(300, "rigol")

        assert error_info1 is not None
        assert error_info2 is not None
        assert error_info3 is not None
        assert error_info1.code == error_info2.code == error_info3.code

    def test_get_error_message_standard(self, error_db):
        """Test getting formatted error message for standard error."""
        message = error_db.get_error_message(-102, "standard")

        assert "[-102]" in message
        assert "Syntax Error" in message
        assert "Command syntax error" in message

    def test_get_error_message_vendor(self, error_db):
        """Test getting formatted error message for vendor error."""
        message = error_db.get_error_message(200, "rigol")

        assert "[200]" in message
        assert "Output Protected" in message

    def test_get_error_message_unknown(self, error_db):
        """Test getting error message for unknown error code."""
        message = error_db.get_error_message(88888, "standard")

        assert "Unknown error code" in message
        assert "88888" in message

    def test_get_troubleshooting_info_found(self, error_db):
        """Test getting troubleshooting info for known error."""
        info = error_db.get_troubleshooting_info(-100, "standard")

        assert info["found"] is True
        assert info["error_code"] == -100
        assert info["name"] == "Command Error"
        assert info["severity"] == "error"
        assert info["category"] == "communication"
        assert len(info["possible_causes"]) > 0
        assert len(info["recommended_actions"]) > 0
        assert "auto_recoverable" in info
        assert "requires_reset" in info
        assert "requires_service" in info

    def test_get_troubleshooting_info_not_found(self, error_db):
        """Test getting troubleshooting info for unknown error."""
        info = error_db.get_troubleshooting_info(99999, "standard")

        assert info["found"] is False
        assert info["error_code"] == 99999
        assert "Unknown error code" in info["message"]

    def test_get_troubleshooting_info_safety_error(self, error_db):
        """Test troubleshooting info for safety-related error."""
        info = error_db.get_troubleshooting_info(2, "bk_precision")

        assert info["found"] is True
        assert info["name"] == "OCP Trip"
        assert info["category"] == "safety"
        assert info["requires_reset"] is True
        assert "short circuit" in str(info["possible_causes"]).lower()

    def test_add_vendor_code_new_vendor(self, error_db):
        """Test adding error code for new vendor."""
        new_error = ErrorCodeInfo(
            code=500,
            name="Custom Error",
            message="Custom vendor error",
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.OPERATION,
        )

        error_db.add_vendor_code("keysight", new_error)

        # Verify code was added
        retrieved = error_db.lookup_error(500, "keysight")
        assert retrieved is not None
        assert retrieved.code == 500
        assert retrieved.name == "Custom Error"

    def test_add_vendor_code_existing_vendor(self, error_db):
        """Test adding error code to existing vendor."""
        new_error = ErrorCodeInfo(
            code=999,
            name="New Rigol Error",
            message="New error for Rigol",
            severity=ErrorSeverity.WARNING,
            category=ErrorCategory.OPERATION,
        )

        error_db.add_vendor_code("rigol", new_error)

        # Verify code was added
        retrieved = error_db.lookup_error(999, "rigol")
        assert retrieved is not None
        assert retrieved.code == 999
        assert retrieved.name == "New Rigol Error"

        # Verify existing codes still exist
        existing = error_db.lookup_error(100, "rigol")
        assert existing is not None

    def test_add_vendor_code_case_insensitive(self, error_db):
        """Test adding vendor code with different cases."""
        new_error = ErrorCodeInfo(
            code=600,
            name="Test Error",
            message="Test message",
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.OPERATION,
        )

        error_db.add_vendor_code("TESTVENDOR", new_error)

        # Should be retrievable with any case
        assert error_db.lookup_error(600, "testvendor") is not None
        assert error_db.lookup_error(600, "TESTVENDOR") is not None
        assert error_db.lookup_error(600, "TestVendor") is not None

    def test_get_all_codes_standard(self, error_db):
        """Test getting all standard codes."""
        codes = error_db.get_all_codes("standard")

        assert isinstance(codes, dict)
        assert len(codes) > 10  # Should have many standard codes
        assert all(isinstance(k, int) for k in codes.keys())
        assert all(isinstance(v, ErrorCodeInfo) for v in codes.values())

    def test_get_all_codes_vendor(self, error_db):
        """Test getting all codes for a vendor."""
        rigol_codes = error_db.get_all_codes("rigol")

        assert isinstance(rigol_codes, dict)
        assert len(rigol_codes) > 0
        assert 100 in rigol_codes
        assert 200 in rigol_codes
        assert 300 in rigol_codes

    def test_get_all_codes_nonexistent_vendor(self, error_db):
        """Test getting codes for non-existent vendor."""
        codes = error_db.get_all_codes("nonexistent")

        assert codes == {}

    def test_search_errors_by_name(self, error_db):
        """Test searching errors by name."""
        results = error_db.search_errors("command")

        assert len(results) > 0
        assert any(e.name == "Command Error" for e in results)

    def test_search_errors_by_message(self, error_db):
        """Test searching errors by message text."""
        results = error_db.search_errors("overflow")

        assert len(results) > 0
        assert any("overflow" in e.message.lower() for e in results)

    def test_search_errors_case_insensitive(self, error_db):
        """Test search is case-insensitive."""
        results1 = error_db.search_errors("COMMAND")
        results2 = error_db.search_errors("command")
        results3 = error_db.search_errors("Command")

        assert len(results1) > 0
        assert len(results1) == len(results2) == len(results3)

    def test_search_errors_vendor_specific(self, error_db):
        """Test searching within specific vendor."""
        results = error_db.search_errors("protection", vendor="rigol")

        assert len(results) > 0
        assert all("rigol" in str(r).lower() or "Output Protected" in r.name for r in results)

    def test_search_errors_all_vendors(self, error_db):
        """Test searching across all vendors."""
        results = error_db.search_errors("error")

        assert len(results) > 0
        # Should find errors from multiple vendors

    def test_search_errors_no_results(self, error_db):
        """Test searching with no matches."""
        results = error_db.search_errors("xyzabc123nonexistent")

        assert len(results) == 0

    def test_get_errors_by_severity_critical(self, error_db):
        """Test getting errors by severity level."""
        critical_errors = error_db.get_errors_by_severity(ErrorSeverity.CRITICAL)

        assert len(critical_errors) > 0
        assert all(e.severity == ErrorSeverity.CRITICAL for e in critical_errors)
        assert any(e.code == -300 for e in critical_errors)  # Hardware error
        assert any(e.code == -310 for e in critical_errors)  # System error

    def test_get_errors_by_severity_warning(self, error_db):
        """Test getting warning-level errors."""
        warnings = error_db.get_errors_by_severity(ErrorSeverity.WARNING)

        assert len(warnings) > 0
        assert all(e.severity == ErrorSeverity.WARNING for e in warnings)

    def test_get_errors_by_severity_vendor_specific(self, error_db):
        """Test getting errors by severity for specific vendor."""
        rigol_errors = error_db.get_errors_by_severity(ErrorSeverity.ERROR, vendor="rigol")

        # Should only include Rigol errors
        assert all(e.code > 0 for e in rigol_errors)  # Rigol uses positive codes

    def test_get_errors_by_severity_all_vendors(self, error_db):
        """Test getting errors by severity across all vendors."""
        errors = error_db.get_errors_by_severity(ErrorSeverity.ERROR)

        assert len(errors) > 0
        # Should include errors from multiple vendors

    def test_get_errors_by_category_communication(self, error_db):
        """Test getting errors by category."""
        comm_errors = error_db.get_errors_by_category(ErrorCategory.COMMUNICATION)

        assert len(comm_errors) > 0
        assert all(e.category == ErrorCategory.COMMUNICATION for e in comm_errors)
        assert any(e.code == -100 for e in comm_errors)  # Command error
        assert any(e.code == -101 for e in comm_errors)  # Invalid character

    def test_get_errors_by_category_hardware(self, error_db):
        """Test getting hardware-related errors."""
        hw_errors = error_db.get_errors_by_category(ErrorCategory.HARDWARE)

        assert len(hw_errors) > 0
        assert all(e.category == ErrorCategory.HARDWARE for e in hw_errors)

    def test_get_errors_by_category_safety(self, error_db):
        """Test getting safety-related errors."""
        safety_errors = error_db.get_errors_by_category(ErrorCategory.SAFETY)

        assert len(safety_errors) > 0
        assert all(e.category == ErrorCategory.SAFETY for e in safety_errors)
        # Should include BK protection errors
        assert any(e.code == 1 for e in safety_errors)  # OVP
        assert any(e.code == 2 for e in safety_errors)  # OCP

    def test_get_errors_by_category_temperature(self, error_db):
        """Test getting temperature-related errors."""
        temp_errors = error_db.get_errors_by_category(ErrorCategory.TEMPERATURE)

        assert len(temp_errors) > 0
        assert all(e.category == ErrorCategory.TEMPERATURE for e in temp_errors)

    def test_get_errors_by_category_vendor_specific(self, error_db):
        """Test getting errors by category for specific vendor."""
        bk_safety = error_db.get_errors_by_category(ErrorCategory.SAFETY, vendor="bk_precision")

        assert len(bk_safety) > 0
        assert all(e.category == ErrorCategory.SAFETY for e in bk_safety)
        # Should only be BK errors
        assert all(e.code > 0 for e in bk_safety)

    def test_standard_scpi_codes_complete(self, error_db):
        """Test that standard SCPI error codes are comprehensive."""
        standard = error_db.get_all_codes("standard")

        # Check for presence of key SCPI error ranges
        command_errors = [c for c in standard.keys() if -199 <= c <= -100]
        execution_errors = [c for c in standard.keys() if -299 <= c <= -200]
        hardware_errors = [c for c in standard.keys() if -399 <= c <= -300]
        query_errors = [c for c in standard.keys() if -499 <= c <= -400]

        assert len(command_errors) > 0
        assert len(execution_errors) > 0
        assert len(hardware_errors) > 0
        assert len(query_errors) > 0

    def test_vendor_codes_rigol(self, error_db):
        """Test Rigol-specific error codes."""
        rigol = error_db.get_all_codes("rigol")

        # Check for key Rigol errors
        assert 100 in rigol  # Trigger not ready
        assert 200 in rigol  # Output protected
        assert 300 in rigol  # Temperature warning

        trigger_error = rigol[100]
        assert trigger_error.severity == ErrorSeverity.WARNING

        output_error = rigol[200]
        assert output_error.category == ErrorCategory.SAFETY
        assert output_error.requires_reset is True

    def test_vendor_codes_bk_precision(self, error_db):
        """Test BK Precision-specific error codes."""
        bk = error_db.get_all_codes("bk_precision")

        # Check for protection errors
        assert 1 in bk  # OVP
        assert 2 in bk  # OCP
        assert 3 in bk  # OTP
        assert 10 in bk  # Remote interlock

        ovp = bk[1]
        assert ovp.category == ErrorCategory.SAFETY
        assert ovp.requires_reset is True

        otp = bk[3]
        assert otp.severity == ErrorSeverity.CRITICAL
        assert otp.category == ErrorCategory.TEMPERATURE


# ==================== Global Instance Tests ====================


class TestGlobalInstance:
    """Test global error code database instance management."""

    def test_initialize_global_instance(self):
        """Test initializing global error code database."""
        db = initialize_error_code_db()

        assert db is not None
        assert isinstance(db, ErrorCodeDatabase)

        # Verify it's the global instance
        global_db = get_error_code_db()
        assert global_db is db

    def test_get_global_instance_before_init(self):
        """Test getting global instance before initialization."""
        # Note: This test assumes the global instance might be initialized
        # by other tests or imports. In isolation it would return None.
        db = get_error_code_db()

        # If initialized, should be ErrorCodeDatabase
        if db is not None:
            assert isinstance(db, ErrorCodeDatabase)


# ==================== Integration Tests ====================


class TestErrorCodeIntegration:
    """Integration tests for error code database."""

    def test_full_error_lookup_workflow(self, error_db):
        """Test complete workflow of error lookup and troubleshooting."""
        # 1. Lookup error
        error_info = error_db.lookup_error(-310, "standard")
        assert error_info is not None

        # 2. Get formatted message
        message = error_db.get_error_message(-310, "standard")
        assert "System Error" in message

        # 3. Get troubleshooting info
        troubleshooting = error_db.get_troubleshooting_info(-310, "standard")
        assert troubleshooting["found"] is True
        assert troubleshooting["severity"] == "critical"
        assert troubleshooting["requires_service"] is True

    def test_vendor_error_with_fallback(self, error_db):
        """Test vendor-specific error with fallback to standard."""
        # Vendor-specific error
        vendor_error = error_db.lookup_error(200, "rigol")
        assert vendor_error is not None
        assert vendor_error.name == "Output Protected"

        # Standard error via vendor lookup (fallback)
        standard_error = error_db.lookup_error(-100, "rigol")
        assert standard_error is not None
        assert standard_error.name == "Command Error"

    def test_search_and_filter_workflow(self, error_db):
        """Test searching and filtering errors."""
        # 1. Search for temperature-related errors
        temp_search = error_db.search_errors("temperature")
        assert len(temp_search) > 0

        # 2. Filter by category
        temp_category = error_db.get_errors_by_category(ErrorCategory.TEMPERATURE)
        assert len(temp_category) > 0

        # 3. Filter by severity
        critical_errors = error_db.get_errors_by_severity(ErrorSeverity.CRITICAL)
        assert len(critical_errors) > 0

    def test_add_and_retrieve_custom_error(self, error_db):
        """Test adding and retrieving custom error code."""
        # Create custom error
        custom_error = ErrorCodeInfo(
            code=1000,
            name="Custom Test Error",
            message="This is a custom test error",
            severity=ErrorSeverity.WARNING,
            category=ErrorCategory.OPERATION,
            possible_causes=["Test condition"],
            recommended_actions=["Take test action"],
        )

        # Add to database
        error_db.add_vendor_code("custom_vendor", custom_error)

        # Retrieve and verify
        retrieved = error_db.lookup_error(1000, "custom_vendor")
        assert retrieved is not None
        assert retrieved.name == "Custom Test Error"

        # Get troubleshooting info
        info = error_db.get_troubleshooting_info(1000, "custom_vendor")
        assert info["found"] is True
        assert info["name"] == "Custom Test Error"
        assert len(info["possible_causes"]) == 1
        assert len(info["recommended_actions"]) == 1
