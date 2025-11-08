#!/usr/bin/env python3
"""Verification script for Scheduled Operations System (v0.9.0).

This script verifies the implementation of the scheduler system using
AST parsing to check code structure without requiring dependencies.
"""

import ast
import sys
from pathlib import Path
from typing import List, Set, Dict


class SchedulerVerifier:
    """Verifies scheduler system implementation."""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.checks_passed = 0
        self.checks_failed = 0

    def verify_all(self) -> bool:
        """Run all verification checks."""
        print("=" * 70)
        print("Verifying Scheduled Operations System (v0.9.0)")
        print("=" * 70)
        print()

        checks = [
            ("Scheduler Data Models", self.verify_models),
            ("Scheduler Manager", self.verify_manager),
            ("Schedule API Endpoints", self.verify_api),
            ("Module Exports", self.verify_exports),
            ("Main App Integration", self.verify_integration),
        ]

        for check_name, check_func in checks:
            print(f"Checking {check_name}...", end=" ")
            try:
                if check_func():
                    print("✓ PASS")
                    self.checks_passed += 1
                else:
                    print("✗ FAIL")
                    self.checks_failed += 1
            except Exception as e:
                print(f"✗ ERROR: {e}")
                self.checks_failed += 1
                self.errors.append(f"{check_name}: {e}")

        print()
        print("=" * 70)
        print(f"Results: {self.checks_passed} passed, {self.checks_failed} failed")
        print("=" * 70)

        if self.errors:
            print("\nErrors:")
            for error in self.errors:
                print(f"  - {error}")

        if self.warnings:
            print("\nWarnings:")
            for warning in self.warnings:
                print(f"  - {warning}")

        return self.checks_failed == 0

    def verify_models(self) -> bool:
        """Verify scheduler/models.py exists and has required models."""
        models_file = Path("scheduler/models.py")
        if not models_file.exists():
            self.errors.append("scheduler/models.py not found")
            return False

        with open(models_file) as f:
            tree = ast.parse(f.read())

        # Required classes
        required_classes = {
            "ScheduleType", "JobStatus", "TriggerType",
            "ScheduleConfig", "JobExecution", "JobHistory", "ScheduleStatistics"
        }

        found_classes = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        missing = required_classes - found_classes

        if missing:
            self.errors.append(f"Missing model classes: {missing}")
            return False

        # Check ScheduleConfig has key fields
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "ScheduleConfig":
                # Look for field annotations
                annotations = []
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        annotations.append(item.target.id)

                required_fields = {"job_id", "name", "schedule_type", "trigger_type"}
                if not required_fields.issubset(set(annotations)):
                    self.errors.append("ScheduleConfig missing required fields")
                    return False

        return True

    def verify_manager(self) -> bool:
        """Verify scheduler/manager.py has SchedulerManager class."""
        manager_file = Path("scheduler/manager.py")
        if not manager_file.exists():
            self.errors.append("scheduler/manager.py not found")
            return False

        with open(manager_file) as f:
            content = f.read()
            tree = ast.parse(content)

        # Find SchedulerManager class
        manager_class = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "SchedulerManager":
                manager_class = node
                break

        if not manager_class:
            self.errors.append("SchedulerManager class not found")
            return False

        # Required methods
        required_methods = {
            "start", "shutdown", "create_job", "update_job", "delete_job",
            "pause_job", "resume_job", "run_job_now",
            "get_job", "list_jobs", "get_execution", "list_executions",
            "get_job_history", "get_statistics"
        }

        found_methods = {node.name for node in manager_class.body if isinstance(node, ast.AsyncFunctionDef) or isinstance(node, ast.FunctionDef)}
        missing = required_methods - found_methods

        if missing:
            self.errors.append(f"SchedulerManager missing methods: {missing}")
            return False

        # Check for APScheduler import
        if "AsyncIOScheduler" not in content:
            self.errors.append("APScheduler not imported")
            return False

        # Check for global instance
        if "scheduler_manager" not in content:
            self.errors.append("Global scheduler_manager instance not found")
            return False

        return True

    def verify_api(self) -> bool:
        """Verify api/scheduler.py has required endpoints."""
        api_file = Path("api/scheduler.py")
        if not api_file.exists():
            self.errors.append("api/scheduler.py not found")
            return False

        with open(api_file) as f:
            content = f.read()
            tree = ast.parse(content)

        # Check for router
        if "APIRouter" not in content or "router = APIRouter()" not in content:
            self.errors.append("APIRouter not created")
            return False

        # Find decorated functions (endpoints)
        endpoints = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Attribute):
                        if isinstance(decorator.value, ast.Name) and decorator.value.id == "router":
                            endpoints.append(node.name)
                    elif isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                        if isinstance(decorator.func.value, ast.Name) and decorator.func.value.id == "router":
                            endpoints.append(node.name)

        # Required endpoints
        required_endpoints = {
            "create_job", "get_job", "list_jobs", "delete_job",
            "pause_job", "resume_job", "run_job_now",
            "get_execution", "list_executions", "get_job_history",
            "get_statistics"
        }

        missing = required_endpoints - set(endpoints)
        if missing:
            self.errors.append(f"Missing API endpoints: {missing}")
            return False

        return True

    def verify_exports(self) -> bool:
        """Verify scheduler/__init__.py exports required items."""
        init_file = Path("scheduler/__init__.py")
        if not init_file.exists():
            self.errors.append("scheduler/__init__.py not found")
            return False

        with open(init_file) as f:
            content = f.read()

        required_exports = {
            "ScheduleType", "JobStatus", "TriggerType",
            "ScheduleConfig", "JobExecution", "JobHistory",
            "scheduler_manager"
        }

        for export in required_exports:
            if export not in content:
                self.errors.append(f"Missing export: {export}")
                return False

        return True

    def verify_integration(self) -> bool:
        """Verify scheduler is integrated into main.py."""
        main_file = Path("main.py")
        if not main_file.exists():
            self.errors.append("main.py not found")
            return False

        with open(main_file) as f:
            content = f.read()

        # Check imports
        if "scheduler_router" not in content:
            self.errors.append("scheduler_router not imported in main.py")
            return False

        # Check router included
        if 'app.include_router(scheduler_router' not in content:
            self.errors.append("scheduler_router not added to app")
            return False

        # Check scheduler manager started
        if "scheduler_manager.start()" not in content:
            self.errors.append("scheduler_manager.start() not called in lifespan")
            return False

        # Check scheduler manager shutdown
        if "scheduler_manager.shutdown()" not in content:
            self.errors.append("scheduler_manager.shutdown() not called in cleanup")
            return False

        # Check version
        if '"0.9.0"' not in content and "'0.9.0'" not in content:
            self.warnings.append("Version may not be updated to 0.9.0")

        return True


def main():
    """Run verification."""
    verifier = SchedulerVerifier()
    success = verifier.verify_all()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
