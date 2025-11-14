"""Common test sequence templates."""

from typing import List

from .models import StepType, TestSequence, TestStep, ValidationOperator


class TestTemplateLibrary:
    """Library of common test sequence templates."""

    @staticmethod
    def voltage_accuracy_test(
        equipment_id: str, test_points: List[float], tolerance_percent: float = 1.0
    ) -> TestSequence:
        """Create voltage accuracy test template.

        Args:
            equipment_id: Equipment to test
            test_points: List of voltage test points
            tolerance_percent: Acceptable tolerance

        Returns:
            TestSequence
        """
        steps = []
        step_num = 1

        # Setup
        steps.append(
            TestStep(
                step_number=step_num,
                step_type=StepType.SETUP,
                name="Initialize equipment",
                equipment_id=equipment_id,
                command="*RST",
            )
        )
        step_num += 1

        # Test each voltage point
        for voltage in test_points:
            # Set voltage
            steps.append(
                TestStep(
                    step_number=step_num,
                    step_type=StepType.COMMAND,
                    name=f"Set voltage to {voltage}V",
                    equipment_id=equipment_id,
                    command=f"VOLT {voltage}",
                )
            )
            step_num += 1

            # Delay for settling
            steps.append(
                TestStep(
                    step_number=step_num,
                    step_type=StepType.DELAY,
                    name="Wait for settling",
                    delay_seconds=0.5,
                )
            )
            step_num += 1

            # Measure voltage
            steps.append(
                TestStep(
                    step_number=step_num,
                    step_type=StepType.MEASUREMENT,
                    name=f"Measure voltage at {voltage}V",
                    equipment_id=equipment_id,
                    measurement_type="voltage",
                    measurement_params={"command": "MEAS:VOLT?"},
                )
            )
            step_num += 1

            # Validate
            steps.append(
                TestStep(
                    step_number=step_num,
                    step_type=StepType.VALIDATION,
                    name=f"Validate voltage within {tolerance_percent}%",
                    validation_operator=ValidationOperator.EQUAL,
                    validation_value=voltage,
                    tolerance_percent=tolerance_percent,
                )
            )
            step_num += 1

        # Cleanup
        steps.append(
            TestStep(
                step_number=step_num,
                step_type=StepType.CLEANUP,
                name="Reset equipment",
                equipment_id=equipment_id,
                command="OUTP OFF",
            )
        )

        return TestSequence(
            name="Voltage Accuracy Test",
            description=f"Voltage accuracy test at {len(test_points)} points with {tolerance_percent}% tolerance",
            equipment_ids=[equipment_id],
            steps=steps,
            category="acceptance",
            is_template=True,
            template_name="voltage_accuracy",
        )

    @staticmethod
    def frequency_response_sweep(
        equipment_id: str, start_freq: float, stop_freq: float, num_points: int = 50
    ) -> TestSequence:
        """Create frequency response sweep template.

        Args:
            equipment_id: Equipment to test
            start_freq: Start frequency (Hz)
            stop_freq: Stop frequency (Hz)
            num_points: Number of frequency points

        Returns:
            TestSequence
        """
        steps = [
            TestStep(
                step_number=1,
                step_type=StepType.SETUP,
                name="Initialize equipment",
                equipment_id=equipment_id,
                command="*RST",
            ),
            TestStep(
                step_number=2,
                step_type=StepType.SWEEP,
                name=f"Frequency sweep {start_freq}-{stop_freq}Hz",
                equipment_id=equipment_id,
                sweep_parameter="FREQ",
                sweep_start=start_freq,
                sweep_stop=stop_freq,
                sweep_points=num_points,
                measurement_type="amplitude",
                measurement_params={"command": "MEAS:VOLT:AC?"},
            ),
            TestStep(
                step_number=3,
                step_type=StepType.CLEANUP,
                name="Reset equipment",
                equipment_id=equipment_id,
                command="OUTP OFF",
            ),
        ]

        return TestSequence(
            name="Frequency Response Sweep",
            description=f"Frequency response from {start_freq} to {stop_freq} Hz",
            equipment_ids=[equipment_id],
            steps=steps,
            category="characterization",
            is_template=True,
            template_name="frequency_response",
        )

    @staticmethod
    def get_all_templates() -> List[str]:
        """Get list of available template names."""
        return ["voltage_accuracy", "frequency_response"]
