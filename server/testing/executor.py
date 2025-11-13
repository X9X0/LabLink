"""Test sequence execution engine."""

import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
import time

from .models import (
    TestSequence,
    TestStep,
    TestExecution,
    TestResult,
    TestStatus,
    StepType,
    ParameterSweep,
)
from .validator import TestValidator

logger = logging.getLogger(__name__)


class TestExecutor:
    """Executes automated test sequences."""

    def __init__(self, equipment_manager, database_manager):
        """Initialize test executor.

        Args:
            equipment_manager: Equipment manager instance
            database_manager: Database manager instance
        """
        self.equipment_manager = equipment_manager
        self.database_manager = database_manager
        self.validator = TestValidator()

        # Active executions
        self.executions: Dict[str, TestExecution] = {}

        # Execution control
        self.abort_flags: Dict[str, bool] = {}

        logger.info("Test executor initialized")

    async def execute_sequence(
        self,
        sequence: TestSequence,
        executed_by: str,
        environment: Optional[Dict[str, Any]] = None
    ) -> TestExecution:
        """Execute a test sequence.

        Args:
            sequence: Test sequence to execute
            executed_by: User executing the test
            environment: Environmental conditions (temp, humidity, etc.)

        Returns:
            TestExecution with results
        """
        # Create execution instance
        execution = TestExecution(
            sequence_id=sequence.sequence_id,
            sequence_name=sequence.name,
            steps=[step.copy(deep=True) for step in sequence.steps],
            total_steps=len(sequence.steps),
            executed_by=executed_by,
            environment=environment or {},
        )

        self.executions[execution.execution_id] = execution
        self.abort_flags[execution.execution_id] = False

        logger.info(f"Starting test sequence: {sequence.name} (ID: {execution.execution_id})")

        execution.status = TestStatus.RUNNING
        execution.started_at = datetime.now()

        try:
            # Execute steps
            for i, step in enumerate(execution.steps):
                # Check abort flag
                if self.abort_flags.get(execution.execution_id, False):
                    logger.warning(f"Test aborted by user: {execution.execution_id}")
                    execution.status = TestStatus.ABORTED
                    break

                execution.current_step = i
                step_start = time.time()

                logger.info(f"Executing step {step.step_number}: {step.name}")

                try:
                    # Execute step based on type
                    if step.step_type == StepType.COMMAND:
                        await self._execute_command_step(step)
                    elif step.step_type == StepType.MEASUREMENT:
                        await self._execute_measurement_step(step, execution)
                    elif step.step_type == StepType.DELAY:
                        await self._execute_delay_step(step)
                    elif step.step_type == StepType.VALIDATION:
                        await self._execute_validation_step(step)
                    elif step.step_type == StepType.SWEEP:
                        await self._execute_sweep_step(step, execution)
                    elif step.step_type == StepType.SETUP:
                        await self._execute_setup_step(step)
                    elif step.step_type == StepType.CLEANUP:
                        await self._execute_cleanup_step(step)
                    else:
                        logger.warning(f"Unknown step type: {step.step_type}")
                        step.status = TestStatus.ERROR
                        step.error_message = f"Unknown step type: {step.step_type}"

                    step.duration_seconds = time.time() - step_start
                    step.executed_at = datetime.now()

                except Exception as e:
                    logger.error(f"Error executing step {step.step_number}: {e}")
                    step.status = TestStatus.ERROR
                    step.error_message = str(e)
                    step.passed = False
                    step.duration_seconds = time.time() - step_start

                    if sequence.abort_on_fail and step.critical:
                        logger.error(f"Critical step failed, aborting test")
                        execution.status = TestStatus.FAILED
                        break

            # Calculate results
            execution.completed_at = datetime.now()
            execution.duration_seconds = (
                execution.completed_at - execution.started_at
            ).total_seconds()
            execution.calculate_results()

            # Archive results
            await self._archive_results(execution, sequence)

            logger.info(
                f"Test sequence completed: {sequence.name} - "
                f"Status: {execution.status}, Pass rate: {execution.pass_rate:.1f}%"
            )

        except Exception as e:
            logger.error(f"Fatal error executing test sequence: {e}")
            execution.status = TestStatus.ERROR
            execution.completed_at = datetime.now()
            execution.duration_seconds = (
                execution.completed_at - execution.started_at
            ).total_seconds()

        # Cleanup
        if execution.execution_id in self.abort_flags:
            del self.abort_flags[execution.execution_id]

        return execution

    async def _execute_command_step(self, step: TestStep):
        """Execute a command step."""
        if not step.equipment_id or not step.command:
            raise ValueError("Command step requires equipment_id and command")

        equipment = self.equipment_manager.get_equipment(step.equipment_id)
        if not equipment:
            raise ValueError(f"Equipment not found: {step.equipment_id}")

        # Send command
        response = await equipment.write(step.command)

        # Check expected response if specified
        if step.expected_response:
            if response != step.expected_response:
                step.status = TestStatus.FAILED
                step.passed = False
                step.error_message = f"Expected '{step.expected_response}', got '{response}'"
            else:
                step.status = TestStatus.PASSED
                step.passed = True
        else:
            step.status = TestStatus.PASSED
            step.passed = True

    async def _execute_measurement_step(self, step: TestStep, execution: TestExecution):
        """Execute a measurement step."""
        if not step.equipment_id or not step.measurement_type:
            raise ValueError("Measurement step requires equipment_id and measurement_type")

        equipment = self.equipment_manager.get_equipment(step.equipment_id)
        if not equipment:
            raise ValueError(f"Equipment not found: {step.equipment_id}")

        # Take measurement (implementation depends on equipment type)
        # This is a simplified version - actual implementation would vary by equipment
        measurement_command = step.measurement_params.get("command")
        if measurement_command:
            response = await equipment.query(measurement_command)
            try:
                value = float(response)
                step.measured_value = value

                # Store in execution measurements
                if step.measurement_type not in execution.measurements:
                    execution.measurements[step.measurement_type] = []
                execution.measurements[step.measurement_type].append(value)

                step.status = TestStatus.PASSED
                step.passed = True

            except ValueError:
                step.status = TestStatus.ERROR
                step.error_message = f"Could not parse measurement: {response}"
                step.passed = False
        else:
            raise ValueError("Measurement step requires command in measurement_params")

    async def _execute_delay_step(self, step: TestStep):
        """Execute a delay step."""
        await asyncio.sleep(step.delay_seconds)
        step.status = TestStatus.PASSED
        step.passed = True

    async def _execute_validation_step(self, step: TestStep):
        """Execute a validation step."""
        if step.measured_value is None:
            raise ValueError("Validation step requires previous measurement")

        passed = self.validator.validate(
            step.measured_value,
            step.validation_operator,
            step.validation_value,
            step.validation_range,
            step.tolerance_percent,
        )

        step.passed = passed
        step.status = TestStatus.PASSED if passed else TestStatus.FAILED

        if not passed:
            step.error_message = (
                f"Validation failed: {step.measured_value} {step.validation_operator} "
                f"{step.validation_value or step.validation_range}"
            )

    async def _execute_sweep_step(self, step: TestStep, execution: TestExecution):
        """Execute a parameter sweep step."""
        if not all([step.sweep_parameter, step.sweep_start, step.sweep_stop]):
            raise ValueError("Sweep step requires parameter, start, and stop values")

        # Create sweep configuration
        sweep = ParameterSweep(
            parameter_name=step.sweep_parameter,
            start_value=step.sweep_start,
            stop_value=step.sweep_stop,
            step_size=step.sweep_step,
            num_points=step.sweep_points,
            measurement_type=step.measurement_type,
        )

        # Generate sweep points
        points = sweep.generate_sweep_points()

        logger.info(f"Parameter sweep: {sweep.parameter_name} from {step.sweep_start} to {step.sweep_stop} ({len(points)} points)")

        equipment = self.equipment_manager.get_equipment(step.equipment_id)
        if not equipment:
            raise ValueError(f"Equipment not found: {step.equipment_id}")

        # Execute sweep
        for point in points:
            # Set parameter value
            set_command = f"{sweep.parameter_name} {point}"
            await equipment.write(set_command)

            # Wait for settling
            await asyncio.sleep(sweep.settling_time)

            # Take measurement
            measure_command = step.measurement_params.get("command")
            if measure_command:
                response = await equipment.query(measure_command)
                try:
                    value = float(response)
                    sweep.measured_values.append(value)
                except ValueError:
                    logger.error(f"Could not parse measurement at {point}: {response}")
                    sweep.measured_values.append(float('nan'))

        # Store sweep results
        execution.sweep_results.append(sweep)

        step.status = TestStatus.PASSED
        step.passed = True

    async def _execute_setup_step(self, step: TestStep):
        """Execute a setup step."""
        if step.command and step.equipment_id:
            equipment = self.equipment_manager.get_equipment(step.equipment_id)
            if equipment:
                await equipment.write(step.command)

        step.status = TestStatus.PASSED
        step.passed = True

    async def _execute_cleanup_step(self, step: TestStep):
        """Execute a cleanup step."""
        if step.command and step.equipment_id:
            equipment = self.equipment_manager.get_equipment(step.equipment_id)
            if equipment:
                await equipment.write(step.command)

        step.status = TestStatus.PASSED
        step.passed = True

    async def _archive_results(self, execution: TestExecution, sequence: TestSequence):
        """Archive test results to database."""
        result = TestResult(
            execution_id=execution.execution_id,
            sequence_id=sequence.sequence_id,
            sequence_name=sequence.name,
            status=execution.status,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            duration_seconds=execution.duration_seconds,
            total_steps=execution.total_steps,
            passed_steps=execution.passed_steps,
            failed_steps=execution.failed_steps,
            pass_rate=execution.pass_rate,
            measurements=execution.measurements,
            sweep_results=[sweep.dict() for sweep in execution.sweep_results],
            executed_by=execution.executed_by,
            equipment_ids=sequence.equipment_ids,
            environment=execution.environment,
            notes=execution.notes,
        )

        # Store in database (implementation depends on database schema)
        # For now, we'll log it
        logger.info(f"Test result archived: {result.result_id}")

        # Could integrate with database manager here
        # await self.database_manager.archive_test_result(result)

    def abort_test(self, execution_id: str):
        """Abort a running test.

        Args:
            execution_id: Execution ID to abort
        """
        if execution_id in self.abort_flags:
            self.abort_flags[execution_id] = True
            logger.warning(f"Abort requested for test: {execution_id}")
        else:
            logger.warning(f"Test not found or already completed: {execution_id}")

    def get_execution(self, execution_id: str) -> Optional[TestExecution]:
        """Get execution by ID.

        Args:
            execution_id: Execution ID

        Returns:
            TestExecution if found, None otherwise
        """
        return self.executions.get(execution_id)

    def get_active_executions(self) -> Dict[str, TestExecution]:
        """Get all active test executions.

        Returns:
            Dictionary of active executions
        """
        return {
            eid: exec
            for eid, exec in self.executions.items()
            if exec.status == TestStatus.RUNNING
        }
