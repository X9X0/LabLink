"""Test validation and pass/fail criteria."""

import logging
from typing import Dict, Optional

from .models import ValidationOperator

logger = logging.getLogger(__name__)


class TestValidator:
    """Validates test measurements against criteria."""

    def validate(
        self,
        measured_value: float,
        operator: Optional[ValidationOperator],
        expected_value: Optional[float] = None,
        value_range: Optional[Dict[str, float]] = None,
        tolerance_percent: float = 0.0,
    ) -> bool:
        """Validate a measurement.

        Args:
            measured_value: Measured value
            operator: Comparison operator
            expected_value: Expected value
            value_range: Range dict with 'min' and 'max'
            tolerance_percent: Tolerance as percentage

        Returns:
            True if validation passes, False otherwise
        """
        if operator is None:
            return True  # No validation specified

        try:
            if operator == ValidationOperator.IN_RANGE:
                if not value_range:
                    raise ValueError("IN_RANGE requires value_range")
                return value_range["min"] <= measured_value <= value_range["max"]

            elif operator == ValidationOperator.OUT_OF_RANGE:
                if not value_range:
                    raise ValueError("OUT_OF_RANGE requires value_range")
                return not (value_range["min"] <= measured_value <= value_range["max"])

            elif expected_value is not None:
                # Apply tolerance
                tolerance = abs(expected_value * tolerance_percent / 100.0)

                if operator == ValidationOperator.EQUAL:
                    return abs(measured_value - expected_value) <= tolerance
                elif operator == ValidationOperator.NOT_EQUAL:
                    return abs(measured_value - expected_value) > tolerance
                elif operator == ValidationOperator.LESS_THAN:
                    return measured_value < expected_value
                elif operator == ValidationOperator.LESS_EQUAL:
                    return measured_value <= expected_value
                elif operator == ValidationOperator.GREATER_THAN:
                    return measured_value > expected_value
                elif operator == ValidationOperator.GREATER_EQUAL:
                    return measured_value >= expected_value

            return False

        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False
