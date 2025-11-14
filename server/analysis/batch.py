"""Batch processing engine for parallel data analysis."""

import asyncio
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List

from .models import BatchJobConfig, BatchJobResult, BatchJobStatus

logger = logging.getLogger(__name__)


class BatchProcessor:
    """Batch processing engine."""

    def __init__(self):
        """Initialize batch processor."""
        self.active_jobs: Dict[str, BatchJobResult] = {}

    async def submit_job(self, config: BatchJobConfig) -> str:
        """Submit batch job for processing.

        Args:
            config: Batch job configuration

        Returns:
            Job ID
        """
        job_id = f"batch_{uuid.uuid4().hex[:8]}"

        # Create job result object
        job_result = BatchJobResult(
            job_id=job_id,
            status=BatchJobStatus.PENDING,
            config=config,
            started_at=datetime.now(),
            total_files=len(config.input_files),
        )

        self.active_jobs[job_id] = job_result

        # Start processing asynchronously
        if config.parallel:
            asyncio.create_task(self._process_parallel(job_id, config))
        else:
            asyncio.create_task(self._process_sequential(job_id, config))

        logger.info(f"Submitted batch job {job_id}: {config.job_name}")

        return job_id

    async def _process_parallel(self, job_id: str, config: BatchJobConfig):
        """Process files in parallel.

        Args:
            job_id: Job ID
            config: Job configuration
        """
        job_result = self.active_jobs[job_id]
        job_result.status = BatchJobStatus.RUNNING

        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Process files in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
            futures = []

            for input_file in config.input_files:
                future = executor.submit(
                    self._process_file,
                    input_file,
                    output_dir,
                    config.operation,
                    config.operation_config,
                )
                futures.append((future, input_file))

            # Collect results
            for future, input_file in futures:
                try:
                    output_file = future.result()
                    job_result.completed_files += 1
                    job_result.output_files.append(output_file)
                    logger.info(f"Processed {input_file} -> {output_file}")
                except Exception as e:
                    job_result.failed_files += 1
                    error_msg = f"Error processing {input_file}: {str(e)}"
                    job_result.errors.append(error_msg)
                    logger.error(error_msg)

        # Mark job complete
        job_result.completed_at = datetime.now()
        if job_result.failed_files == 0:
            job_result.status = BatchJobStatus.COMPLETED
        else:
            job_result.status = BatchJobStatus.FAILED

        logger.info(
            f"Batch job {job_id} completed: {job_result.completed_files}/{job_result.total_files} successful"
        )

    async def _process_sequential(self, job_id: str, config: BatchJobConfig):
        """Process files sequentially.

        Args:
            job_id: Job ID
            config: Job configuration
        """
        job_result = self.active_jobs[job_id]
        job_result.status = BatchJobStatus.RUNNING

        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Process files one by one
        for input_file in config.input_files:
            try:
                output_file = await asyncio.to_thread(
                    self._process_file,
                    input_file,
                    output_dir,
                    config.operation,
                    config.operation_config,
                )
                job_result.completed_files += 1
                job_result.output_files.append(output_file)
                logger.info(f"Processed {input_file} -> {output_file}")
            except Exception as e:
                job_result.failed_files += 1
                error_msg = f"Error processing {input_file}: {str(e)}"
                job_result.errors.append(error_msg)
                logger.error(error_msg)

        # Mark job complete
        job_result.completed_at = datetime.now()
        if job_result.failed_files == 0:
            job_result.status = BatchJobStatus.COMPLETED
        else:
            job_result.status = BatchJobStatus.FAILED

        logger.info(
            f"Batch job {job_id} completed: {job_result.completed_files}/{job_result.total_files} successful"
        )

    def _process_file(
        self,
        input_file: str,
        output_dir: Path,
        operation: str,
        operation_config: Dict[str, Any],
    ) -> str:
        """Process single file.

        Args:
            input_file: Input file path
            output_dir: Output directory
            operation: Operation to perform
            operation_config: Operation configuration

        Returns:
            Output file path
        """
        input_path = Path(input_file)

        # Load data
        data = self._load_data(input_path)

        # Perform operation
        result = self._apply_operation(data, operation, operation_config)

        # Save result
        output_file = output_dir / f"{input_path.stem}_{operation}{input_path.suffix}"
        self._save_data(result, output_file)

        return str(output_file)

    def _load_data(self, file_path: Path) -> Dict[str, Any]:
        """Load data from file.

        Args:
            file_path: File path

        Returns:
            Loaded data dictionary
        """
        if file_path.suffix == ".json":
            with open(file_path, "r") as f:
                return json.load(f)
        elif file_path.suffix == ".csv":
            # Simple CSV loading
            import csv

            with open(file_path, "r") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                # Convert to columnar format
                data = {}
                if rows:
                    for key in rows[0].keys():
                        data[key] = [float(row[key]) for row in rows]
                return data
        else:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")

    def _save_data(self, data: Dict[str, Any], file_path: Path):
        """Save data to file.

        Args:
            data: Data to save
            file_path: Output file path
        """
        if file_path.suffix == ".json":
            with open(file_path, "w") as f:
                json.dump(data, f, indent=2)
        elif file_path.suffix == ".csv":
            import csv

            with open(file_path, "w", newline="") as f:
                if data:
                    writer = csv.DictWriter(f, fieldnames=data.keys())
                    writer.writeheader()
                    # Convert columnar to row format
                    num_rows = len(data[list(data.keys())[0]])
                    for i in range(num_rows):
                        row = {key: data[key][i] for key in data.keys()}
                        writer.writerow(row)
        else:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")

    def _apply_operation(
        self, data: Dict[str, Any], operation: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply operation to data.

        Args:
            data: Input data
            operation: Operation name
            config: Operation configuration

        Returns:
            Processed data
        """
        # This is a simplified implementation
        # In a full implementation, this would call the appropriate analysis functions
        result = data.copy()

        if operation == "filter":
            # Apply filtering (placeholder)
            result["filtered_data"] = result.get("y_data", [])

        elif operation == "fit":
            # Apply curve fitting (placeholder)
            result["fitted_data"] = result.get("y_data", [])

        elif operation == "resample":
            # Apply resampling (placeholder)
            result["resampled_data"] = result.get("y_data", [])

        else:
            logger.warning(f"Unknown operation: {operation}")

        return result

    def get_job_status(self, job_id: str) -> BatchJobResult:
        """Get batch job status.

        Args:
            job_id: Job ID

        Returns:
            BatchJobResult

        Raises:
            KeyError: If job not found
        """
        if job_id not in self.active_jobs:
            raise KeyError(f"Job {job_id} not found")

        return self.active_jobs[job_id]

    def cancel_job(self, job_id: str):
        """Cancel running batch job.

        Args:
            job_id: Job ID
        """
        if job_id in self.active_jobs:
            job_result = self.active_jobs[job_id]
            if job_result.status == BatchJobStatus.RUNNING:
                job_result.status = BatchJobStatus.CANCELLED
                job_result.completed_at = datetime.now()
                logger.info(f"Cancelled batch job {job_id}")

    def list_jobs(self) -> List[BatchJobResult]:
        """List all batch jobs.

        Returns:
            List of BatchJobResult objects
        """
        return list(self.active_jobs.values())
