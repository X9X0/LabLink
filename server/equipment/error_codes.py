"""
Equipment Error Code Database
=============================

Provides error code lookup and interpretation for various lab equipment.
Maps numeric error codes to human-readable messages and troubleshooting tips.
"""

import logging
from typing import Dict, Optional, List, Any
from enum import Enum
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ErrorSeverity(str, Enum):
    """Severity levels for equipment errors."""
    INFO = "info"  # Informational message
    WARNING = "warning"  # Warning but equipment operational
    ERROR = "error"  # Error affecting operation
    CRITICAL = "critical"  # Critical error, equipment non-functional
    FATAL = "fatal"  # Fatal error requiring service


class ErrorCategory(str, Enum):
    """Categories of equipment errors."""
    COMMUNICATION = "communication"  # Communication/protocol errors
    HARDWARE = "hardware"  # Hardware failures
    CALIBRATION = "calibration"  # Calibration-related errors
    OPERATION = "operation"  # Operational errors
    SAFETY = "safety"  # Safety-related errors
    CONFIGURATION = "configuration"  # Configuration errors
    POWER = "power"  # Power-related issues
    TEMPERATURE = "temperature"  # Temperature issues
    FIRMWARE = "firmware"  # Firmware errors
    UNKNOWN = "unknown"  # Unknown category


class ErrorCodeInfo(BaseModel):
    """Information about a specific error code."""
    code: int = Field(..., description="Error code number")
    name: str = Field(..., description="Short error name")
    message: str = Field(..., description="Detailed error message")
    severity: ErrorSeverity = Field(..., description="Error severity")
    category: ErrorCategory = Field(..., description="Error category")

    # Troubleshooting
    possible_causes: List[str] = Field(default_factory=list, description="Possible causes")
    recommended_actions: List[str] = Field(default_factory=list, description="Recommended actions")

    # Documentation
    manual_reference: Optional[str] = Field(None, description="Manual page reference")
    additional_info: Optional[str] = Field(None, description="Additional information")

    # Recovery
    auto_recoverable: bool = Field(default=False, description="Can auto-recover from this error")
    requires_reset: bool = Field(default=False, description="Requires equipment reset")
    requires_service: bool = Field(default=False, description="Requires service/repair")


class ErrorCodeDatabase:
    """Database of equipment error codes with lookup capabilities."""

    def __init__(self):
        """Initialize error code database."""
        self._error_codes: Dict[str, Dict[int, ErrorCodeInfo]] = {}
        self._initialize_standard_codes()
        self._initialize_vendor_codes()

        logger.info("Error code database initialized")

    def _initialize_standard_codes(self):
        """Initialize standard SCPI/IEEE 488.2 error codes."""
        standard_codes = {
            # Standard SCPI Error Codes (IEEE 488.2)
            0: ErrorCodeInfo(
                code=0,
                name="No Error",
                message="No error has occurred",
                severity=ErrorSeverity.INFO,
                category=ErrorCategory.OPERATION
            ),

            # Command Errors (-100 to -199)
            -100: ErrorCodeInfo(
                code=-100,
                name="Command Error",
                message="Generic command error",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.COMMUNICATION,
                possible_causes=["Invalid command syntax", "Unknown command"],
                recommended_actions=["Check command syntax", "Verify equipment capabilities"]
            ),
            -101: ErrorCodeInfo(
                code=-101,
                name="Invalid Character",
                message="Invalid character in command",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.COMMUNICATION,
                possible_causes=["Special character in command", "Encoding issue"],
                recommended_actions=["Remove special characters", "Check command encoding"]
            ),
            -102: ErrorCodeInfo(
                code=-102,
                name="Syntax Error",
                message="Command syntax error",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.COMMUNICATION,
                possible_causes=["Missing parameter", "Incorrect parameter order"],
                recommended_actions=["Check command syntax in manual", "Verify parameter format"]
            ),
            -103: ErrorCodeInfo(
                code=-103,
                name="Invalid Separator",
                message="Invalid separator in command",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.COMMUNICATION,
                possible_causes=["Wrong delimiter used", "Missing comma or space"],
                recommended_actions=["Use correct separator (comma or space)", "Check command format"]
            ),
            -108: ErrorCodeInfo(
                code=-108,
                name="Parameter Not Allowed",
                message="Parameter not allowed with this command",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.COMMUNICATION,
                possible_causes=["Extra parameter provided", "Wrong command form"],
                recommended_actions=["Remove extra parameters", "Check command documentation"]
            ),

            # Execution Errors (-200 to -299)
            -200: ErrorCodeInfo(
                code=-200,
                name="Execution Error",
                message="Generic execution error",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.OPERATION,
                possible_causes=["Command cannot execute in current state", "Invalid operation"],
                recommended_actions=["Check equipment state", "Verify operation prerequisites"]
            ),
            -221: ErrorCodeInfo(
                code=-221,
                name="Settings Conflict",
                message="Settings conflict detected",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.CONFIGURATION,
                possible_causes=["Conflicting settings", "Invalid combination"],
                recommended_actions=["Review all settings", "Resolve conflicts"]
            ),
            -222: ErrorCodeInfo(
                code=-222,
                name="Data Out of Range",
                message="Data value out of valid range",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.OPERATION,
                possible_causes=["Value too high or low", "Outside equipment limits"],
                recommended_actions=["Check equipment specifications", "Use value within range"]
            ),
            -224: ErrorCodeInfo(
                code=-224,
                name="Illegal Parameter Value",
                message="Parameter value is illegal",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.OPERATION,
                possible_causes=["Invalid parameter value", "Wrong parameter type"],
                recommended_actions=["Check allowed values", "Verify parameter type"]
            ),

            # Hardware Errors (-300 to -399)
            -300: ErrorCodeInfo(
                code=-300,
                name="Hardware Error",
                message="Generic hardware error",
                severity=ErrorSeverity.CRITICAL,
                category=ErrorCategory.HARDWARE,
                possible_causes=["Hardware failure", "Component malfunction"],
                recommended_actions=["Power cycle equipment", "Contact service if persists"],
                requires_reset=True
            ),
            -310: ErrorCodeInfo(
                code=-310,
                name="System Error",
                message="Internal system error",
                severity=ErrorSeverity.CRITICAL,
                category=ErrorCategory.HARDWARE,
                possible_causes=["Internal system failure", "Firmware issue"],
                recommended_actions=["Restart equipment", "Update firmware", "Contact service"],
                requires_reset=True,
                requires_service=True
            ),
            -330: ErrorCodeInfo(
                code=-330,
                name="Self-Test Failed",
                message="Self-test procedure failed",
                severity=ErrorSeverity.CRITICAL,
                category=ErrorCategory.HARDWARE,
                possible_causes=["Hardware component failure", "Calibration drift"],
                recommended_actions=["Run diagnostics", "Perform calibration", "Contact service"],
                requires_service=True
            ),
            -350: ErrorCodeInfo(
                code=-350,
                name="Queue Overflow",
                message="Error queue overflow",
                severity=ErrorSeverity.WARNING,
                category=ErrorCategory.OPERATION,
                possible_causes=["Too many errors", "Errors not being cleared"],
                recommended_actions=["Clear error queue", "Reduce error rate"],
                auto_recoverable=True
            ),

            # Query Errors (-400 to -499)
            -400: ErrorCodeInfo(
                code=-400,
                name="Query Error",
                message="Generic query error",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.COMMUNICATION,
                possible_causes=["Query interrupted", "Query not allowed"],
                recommended_actions=["Resend query", "Check equipment state"]
            ),
            -410: ErrorCodeInfo(
                code=-410,
                name="Query Interrupted",
                message="Query interrupted by command",
                severity=ErrorSeverity.WARNING,
                category=ErrorCategory.COMMUNICATION,
                possible_causes=["New command before query response", "Communication timing issue"],
                recommended_actions=["Wait for query response", "Implement proper timing"],
                auto_recoverable=True
            ),
            -420: ErrorCodeInfo(
                code=-420,
                name="Query Unterminated",
                message="Query not properly terminated",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.COMMUNICATION,
                possible_causes=["Missing terminator", "Incomplete query"],
                recommended_actions=["Add proper terminator", "Complete query syntax"]
            ),
        }

        self._error_codes["standard"] = standard_codes

    def _initialize_vendor_codes(self):
        """Initialize vendor-specific error codes."""

        # Rigol-specific error codes
        rigol_codes = {
            100: ErrorCodeInfo(
                code=100,
                name="Trigger Not Ready",
                message="Trigger system not ready",
                severity=ErrorSeverity.WARNING,
                category=ErrorCategory.OPERATION,
                possible_causes=["Trigger not armed", "Acquisition in progress"],
                recommended_actions=["Wait for acquisition to complete", "Rearm trigger"]
            ),
            200: ErrorCodeInfo(
                code=200,
                name="Output Protected",
                message="Output protection activated",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.SAFETY,
                possible_causes=["Overcurrent", "Overvoltage", "Short circuit"],
                recommended_actions=["Check load", "Remove fault", "Reset protection"],
                requires_reset=True
            ),
            300: ErrorCodeInfo(
                code=300,
                name="Temperature Warning",
                message="Equipment temperature high",
                severity=ErrorSeverity.WARNING,
                category=ErrorCategory.TEMPERATURE,
                possible_causes=["Insufficient cooling", "High ambient temperature", "Blocked vents"],
                recommended_actions=["Improve ventilation", "Reduce load", "Check cooling system"]
            ),
        }
        self._error_codes["rigol"] = rigol_codes

        # BK Precision-specific error codes
        bk_codes = {
            1: ErrorCodeInfo(
                code=1,
                name="OVP Trip",
                message="Over-voltage protection tripped",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.SAFETY,
                possible_causes=["Output voltage exceeded limit", "Load issue"],
                recommended_actions=["Check OVP setting", "Verify load", "Reset output"],
                requires_reset=True
            ),
            2: ErrorCodeInfo(
                code=2,
                name="OCP Trip",
                message="Over-current protection tripped",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.SAFETY,
                possible_causes=["Output current exceeded limit", "Short circuit"],
                recommended_actions=["Check OCP setting", "Check for shorts", "Reset output"],
                requires_reset=True
            ),
            3: ErrorCodeInfo(
                code=3,
                name="OTP Trip",
                message="Over-temperature protection tripped",
                severity=ErrorSeverity.CRITICAL,
                category=ErrorCategory.TEMPERATURE,
                possible_causes=["Equipment overheating", "Cooling failure"],
                recommended_actions=["Allow cooling", "Check ventilation", "Reduce load"],
                requires_reset=True
            ),
            10: ErrorCodeInfo(
                code=10,
                name="Remote Interlock",
                message="Remote interlock open",
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.SAFETY,
                possible_causes=["Interlock connector open", "Safety interlock activated"],
                recommended_actions=["Check interlock connections", "Verify safety conditions"]
            ),
        }
        self._error_codes["bk_precision"] = bk_codes

    def lookup_error(
        self,
        error_code: int,
        vendor: str = "standard"
    ) -> Optional[ErrorCodeInfo]:
        """
        Look up error code information.

        Args:
            error_code: Error code number
            vendor: Vendor identifier (standard, rigol, bk_precision, etc.)

        Returns:
            Error code information, or None if not found
        """
        vendor_db = self._error_codes.get(vendor.lower(), {})
        error_info = vendor_db.get(error_code)

        # Fall back to standard codes if not found in vendor codes
        if not error_info and vendor != "standard":
            error_info = self._error_codes.get("standard", {}).get(error_code)

        return error_info

    def get_error_message(
        self,
        error_code: int,
        vendor: str = "standard"
    ) -> str:
        """
        Get human-readable error message.

        Args:
            error_code: Error code number
            vendor: Vendor identifier

        Returns:
            Error message string
        """
        error_info = self.lookup_error(error_code, vendor)

        if error_info:
            return f"[{error_info.code}] {error_info.name}: {error_info.message}"
        else:
            return f"Unknown error code: {error_code}"

    def get_troubleshooting_info(
        self,
        error_code: int,
        vendor: str = "standard"
    ) -> Dict[str, Any]:
        """
        Get detailed troubleshooting information.

        Args:
            error_code: Error code number
            vendor: Vendor identifier

        Returns:
            Dictionary with troubleshooting information
        """
        error_info = self.lookup_error(error_code, vendor)

        if not error_info:
            return {
                "error_code": error_code,
                "found": False,
                "message": "Unknown error code"
            }

        return {
            "error_code": error_code,
            "found": True,
            "name": error_info.name,
            "message": error_info.message,
            "severity": error_info.severity.value,
            "category": error_info.category.value,
            "possible_causes": error_info.possible_causes,
            "recommended_actions": error_info.recommended_actions,
            "auto_recoverable": error_info.auto_recoverable,
            "requires_reset": error_info.requires_reset,
            "requires_service": error_info.requires_service,
            "manual_reference": error_info.manual_reference,
            "additional_info": error_info.additional_info
        }

    def add_vendor_code(
        self,
        vendor: str,
        error_info: ErrorCodeInfo
    ):
        """
        Add a vendor-specific error code.

        Args:
            vendor: Vendor identifier
            error_info: Error code information
        """
        if vendor.lower() not in self._error_codes:
            self._error_codes[vendor.lower()] = {}

        self._error_codes[vendor.lower()][error_info.code] = error_info
        logger.info(f"Added error code {error_info.code} for vendor {vendor}")

    def get_all_codes(self, vendor: str = "standard") -> Dict[int, ErrorCodeInfo]:
        """
        Get all error codes for a vendor.

        Args:
            vendor: Vendor identifier

        Returns:
            Dictionary of error codes
        """
        return self._error_codes.get(vendor.lower(), {})

    def search_errors(
        self,
        query: str,
        vendor: Optional[str] = None
    ) -> List[ErrorCodeInfo]:
        """
        Search error codes by keyword.

        Args:
            query: Search query
            vendor: Vendor to search (None for all)

        Returns:
            List of matching error codes
        """
        results = []
        query_lower = query.lower()

        # Determine vendors to search
        vendors = [vendor.lower()] if vendor else self._error_codes.keys()

        for v in vendors:
            for error_info in self._error_codes.get(v, {}).values():
                # Search in name and message
                if (query_lower in error_info.name.lower() or
                    query_lower in error_info.message.lower()):
                    results.append(error_info)

        return results

    def get_errors_by_severity(
        self,
        severity: ErrorSeverity,
        vendor: Optional[str] = None
    ) -> List[ErrorCodeInfo]:
        """
        Get all errors of specific severity.

        Args:
            severity: Error severity
            vendor: Vendor to filter (None for all)

        Returns:
            List of error codes with specified severity
        """
        results = []
        vendors = [vendor.lower()] if vendor else self._error_codes.keys()

        for v in vendors:
            for error_info in self._error_codes.get(v, {}).values():
                if error_info.severity == severity:
                    results.append(error_info)

        return results

    def get_errors_by_category(
        self,
        category: ErrorCategory,
        vendor: Optional[str] = None
    ) -> List[ErrorCodeInfo]:
        """
        Get all errors of specific category.

        Args:
            category: Error category
            vendor: Vendor to filter (None for all)

        Returns:
            List of error codes in specified category
        """
        results = []
        vendors = [vendor.lower()] if vendor else self._error_codes.keys()

        for v in vendors:
            for error_info in self._error_codes.get(v, {}).values():
                if error_info.category == category:
                    results.append(error_info)

        return results


# Global error code database instance
error_code_db: Optional[ErrorCodeDatabase] = None


def get_error_code_db() -> Optional[ErrorCodeDatabase]:
    """Get the global error code database instance."""
    return error_code_db


def initialize_error_code_db() -> ErrorCodeDatabase:
    """
    Initialize the global error code database.

    Returns:
        Initialized error code database
    """
    global error_code_db
    error_code_db = ErrorCodeDatabase()
    return error_code_db
