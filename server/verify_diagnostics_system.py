#!/usr/bin/env python3
"""Verification script for Equipment Diagnostics System (v0.10.0).

This script verifies the implementation of the diagnostics system using
AST parsing to check code structure without requiring dependencies.
"""

import ast
import sys
from pathlib import Path
from typing import List, Set


class DiagnosticsVerifier:
    """Verifies diagnostics system implementation."""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.checks_passed = 0
        self.checks_failed = 0

    def verify_all(self) -> bool:
        """Run all verification checks."""
        print("=" * 70)
        print("Verifying Equipment Diagnostics System (v0.10.0)")
        print("=" * 70)
        print()

        checks = [
            ("Diagnostics Data Models", self.verify_models),
            ("Diagnostics Manager", self.verify_manager),
            ("Diagnostics API Endpoints", self.verify_api),
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
        """Verify diagnostics/models.py exists and has required models."""
        models_file = Path("diagnostics/models.py")
        if not models_file.exists():
            self.errors.append("diagnostics/models.py not found")
            return False

        with open(models_file) as f:
            tree = ast.parse(f.read())

        # Required classes
        required_classes = {
            "DiagnosticStatus", "DiagnosticCategory", "HealthStatus",
            "DiagnosticTest", "DiagnosticResult",
            "ConnectionDiagnostics", "CommunicationDiagnostics",
            "PerformanceBenchmark", "EquipmentHealth",
            "DiagnosticReport", "SystemDiagnostics"
        }

        found_classes = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        missing = required_classes - found_classes

        if missing:
            self.errors.append(f"Missing model classes: {missing}")
            return False

        # Check EquipmentHealth has key fields
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "EquipmentHealth":
                # Look for field annotations
                annotations = []
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        annotations.append(item.target.id)

                required_fields = {"equipment_id", "health_status", "health_score"}
                if not required_fields.issubset(set(annotations)):
                    self.errors.append("EquipmentHealth missing required fields")
                    return False

        return True

    def verify_manager(self) -> bool:
        """Verify diagnostics/manager.py has DiagnosticsManager class."""
        manager_file = Path("diagnostics/manager.py")
        if not manager_file.exists():
            self.errors.append("diagnostics/manager.py not found")
            return False

        with open(manager_file) as f:
            content = f.read()
            tree = ast.parse(content)

        # Find DiagnosticsManager class
        manager_class = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "DiagnosticsManager":
                manager_class = node
                break

        if not manager_class:
            self.errors.append("DiagnosticsManager class not found")
            return False

        # Required methods
        required_methods = {
            "check_equipment_health",
            "_check_connection",
            "_check_communication",
            "_run_performance_benchmark",
            "_check_functionality",
            "generate_diagnostic_report",
            "get_system_diagnostics",
            "record_connection",
            "record_disconnection",
            "record_command"
        }

        found_methods = {node.name for node in manager_class.body if isinstance(node, ast.AsyncFunctionDef) or isinstance(node, ast.FunctionDef)}
        missing = required_methods - found_methods

        if missing:
            self.errors.append(f"DiagnosticsManager missing methods: {missing}")
            return False

        # Check for psutil import
        if "psutil" not in content:
            self.errors.append("psutil not imported")
            return False

        # Check for global instance
        if "diagnostics_manager" not in content:
            self.errors.append("Global diagnostics_manager instance not found")
            return False

        return True

    def verify_api(self) -> bool:
        """Verify api/diagnostics.py has required endpoints."""
        api_file = Path("api/diagnostics.py")
        if not api_file.exists():
            self.errors.append("api/diagnostics.py not found")
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

        # Required endpoints (at least these)
        required_endpoints = {
            "get_equipment_health", "get_all_equipment_health", "get_cached_health",
            "check_connection", "get_communication_diagnostics",
            "run_benchmark", "get_benchmark_history",
            "generate_diagnostic_report", "get_system_diagnostics"
        }

        missing = required_endpoints - set(endpoints)
        if missing:
            self.errors.append(f"Missing API endpoints: {missing}")
            return False

        return True

    def verify_exports(self) -> bool:
        """Verify diagnostics/__init__.py exports required items."""
        init_file = Path("diagnostics/__init__.py")
        if not init_file.exists():
            self.errors.append("diagnostics/__init__.py not found")
            return False

        with open(init_file) as f:
            content = f.read()

        required_exports = {
            "DiagnosticStatus", "DiagnosticCategory", "HealthStatus",
            "DiagnosticTest", "DiagnosticResult",
            "ConnectionDiagnostics", "CommunicationDiagnostics",
            "PerformanceBenchmark", "EquipmentHealth",
            "DiagnosticReport", "SystemDiagnostics",
            "diagnostics_manager"
        }

        for export in required_exports:
            if export not in content:
                self.errors.append(f"Missing export: {export}")
                return False

        return True

    def verify_integration(self) -> bool:
        """Verify diagnostics is integrated into main.py."""
        main_file = Path("main.py")
        if not main_file.exists():
            self.errors.append("main.py not found")
            return False

        with open(main_file) as f:
            content = f.read()

        # Check imports
        if "diagnostics_router" not in content:
            self.errors.append("diagnostics_router not imported in main.py")
            return False

        # Check router included
        if 'app.include_router(diagnostics_router' not in content:
            self.errors.append("diagnostics_router not added to app")
            return False

        # Check version
        if '"0.10.0"' not in content and "'0.10.0'" not in content:
            self.warnings.append("Version may not be updated to 0.10.0")

        return True


def main():
    """Run verification."""
    verifier = DiagnosticsVerifier()
    success = verifier.verify_all()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
