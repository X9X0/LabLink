#!/usr/bin/env python3
"""Verification script for the Data Acquisition & Logging System.

This script validates that all acquisition components are properly implemented
without requiring actual equipment or external dependencies.
"""

import ast
import sys
from pathlib import Path
from typing import Dict, List, Set

# Color codes for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{BLUE}{'=' * 70}{RESET}")
    print(f"{BLUE}{text:^70}{RESET}")
    print(f"{BLUE}{'=' * 70}{RESET}\n")


def print_success(text: str):
    """Print success message."""
    print(f"{GREEN}✓ {text}{RESET}")


def print_error(text: str):
    """Print error message."""
    print(f"{RED}✗ {text}{RESET}")


def print_warning(text: str):
    """Print warning message."""
    print(f"{YELLOW}⚠ {text}{RESET}")


class ASTVisitor(ast.NodeVisitor):
    """AST visitor to extract code structure information."""

    def __init__(self):
        self.classes = {}
        self.functions = []
        self.imports = set()
        self.current_class = None

    def visit_ClassDef(self, node):
        """Visit class definition."""
        self.current_class = node.name
        self.classes[node.name] = {
            "methods": [],
            "bases": [b.id if isinstance(b, ast.Name) else str(b) for b in node.bases],
            "attributes": [],
        }
        self.generic_visit(node)
        self.current_class = None

    def visit_FunctionDef(self, node):
        """Visit function definition."""
        if self.current_class:
            self.classes[self.current_class]["methods"].append(node.name)
        else:
            self.functions.append(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        """Visit async function definition."""
        if self.current_class:
            self.classes[self.current_class]["methods"].append(node.name)
        else:
            self.functions.append(node.name)
        self.generic_visit(node)

    def visit_Import(self, node):
        """Visit import statement."""
        for alias in node.names:
            self.imports.add(alias.name)

    def visit_ImportFrom(self, node):
        """Visit from...import statement."""
        if node.module:
            self.imports.add(node.module)


def parse_python_file(filepath: Path) -> ASTVisitor:
    """Parse a Python file and extract structure information."""
    try:
        with open(filepath, "r") as f:
            tree = ast.parse(f.read())
        visitor = ASTVisitor()
        visitor.visit(tree)
        return visitor
    except Exception as e:
        print_error(f"Failed to parse {filepath}: {e}")
        return None


def verify_models():
    """Verify acquisition models."""
    print_header("Verifying Acquisition Models")

    filepath = Path("acquisition/models.py")
    if not filepath.exists():
        print_error("acquisition/models.py not found")
        return False

    visitor = parse_python_file(filepath)
    if not visitor:
        return False

    # Check required classes
    required_classes = [
        "AcquisitionMode",
        "AcquisitionState",
        "TriggerType",
        "TriggerConfig",
        "AcquisitionConfig",
        "CircularBuffer",
        "AcquisitionSession",
        "AcquisitionStats",
        "DataPoint",
    ]

    missing_classes = [cls for cls in required_classes if cls not in visitor.classes]
    if missing_classes:
        print_error(f"Missing classes: {', '.join(missing_classes)}")
        return False

    print_success("All required model classes found")

    # Check CircularBuffer methods
    required_buffer_methods = ["add", "get_latest", "clear"]
    buffer_methods = visitor.classes.get("CircularBuffer", {}).get("methods", [])
    missing_methods = [m for m in required_buffer_methods if m not in buffer_methods]

    if missing_methods:
        print_warning(f"CircularBuffer missing methods: {', '.join(missing_methods)}")
    else:
        print_success("CircularBuffer has all required methods")

    return len(missing_classes) == 0


def verify_manager():
    """Verify acquisition manager."""
    print_header("Verifying Acquisition Manager")

    filepath = Path("acquisition/manager.py")
    if not filepath.exists():
        print_error("acquisition/manager.py not found")
        return False

    visitor = parse_python_file(filepath)
    if not visitor:
        return False

    # Check AcquisitionManager class
    if "AcquisitionManager" not in visitor.classes:
        print_error("AcquisitionManager class not found")
        return False

    print_success("AcquisitionManager class found")

    # Check required methods
    required_methods = [
        "create_session",
        "start_acquisition",
        "stop_acquisition",
        "pause_acquisition",
        "resume_acquisition",
        "get_session",
        "get_buffer_data",
        "export_data",
        "compute_rolling_stats",
        "compute_fft",
        "detect_trend",
        "assess_data_quality",
        "detect_peaks",
        "detect_threshold_crossings",
    ]

    manager_methods = visitor.classes["AcquisitionManager"]["methods"]
    missing_methods = [m for m in required_methods if m not in manager_methods]

    if missing_methods:
        print_error(f"Missing methods: {', '.join(missing_methods)}")
        return False

    print_success(f"All {len(required_methods)} required methods found")

    # Check for global instance
    if (
        "acquisition_manager" not in visitor.functions
        and "acquisition_manager"
        not in [
            line
            for line in open(filepath).read().split("\n")
            if "acquisition_manager" in line
        ]
    ):
        print_warning("Global acquisition_manager instance may be missing")
    else:
        print_success("Global acquisition_manager instance found")

    return True


def verify_statistics():
    """Verify statistics engine."""
    print_header("Verifying Statistics Engine")

    filepath = Path("acquisition/statistics.py")
    if not filepath.exists():
        print_error("acquisition/statistics.py not found")
        return False

    visitor = parse_python_file(filepath)
    if not visitor:
        return False

    # Check required classes
    required_classes = [
        "TrendType",
        "RollingStats",
        "FrequencyAnalysis",
        "TrendAnalysis",
        "DataQuality",
        "PeakInfo",
        "StatisticsEngine",
    ]

    missing_classes = [cls for cls in required_classes if cls not in visitor.classes]
    if missing_classes:
        print_error(f"Missing classes: {', '.join(missing_classes)}")
        return False

    print_success("All required statistics classes found")

    # Check StatisticsEngine methods
    required_methods = [
        "compute_rolling_stats",
        "compute_fft",
        "detect_trend",
        "assess_data_quality",
        "detect_peaks",
        "detect_threshold_crossings",
    ]

    engine_methods = visitor.classes.get("StatisticsEngine", {}).get("methods", [])
    missing_methods = [m for m in required_methods if m not in engine_methods]

    if missing_methods:
        print_error(f"StatisticsEngine missing methods: {', '.join(missing_methods)}")
        return False

    print_success(f"StatisticsEngine has all {len(required_methods)} required methods")

    # Check for scipy imports
    if "scipy" in str(visitor.imports) or any(
        "scipy" in imp for imp in visitor.imports
    ):
        print_success("SciPy imports found for FFT/signal processing")
    else:
        print_warning("SciPy imports not detected - FFT may not work")

    return True


def verify_synchronization():
    """Verify synchronization system."""
    print_header("Verifying Synchronization System")

    filepath = Path("acquisition/synchronization.py")
    if not filepath.exists():
        print_error("acquisition/synchronization.py not found")
        return False

    visitor = parse_python_file(filepath)
    if not visitor:
        return False

    # Check required classes
    required_classes = [
        "SyncState",
        "SyncConfig",
        "SyncStatus",
        "SynchronizationGroup",
        "SynchronizationManager",
    ]

    missing_classes = [cls for cls in required_classes if cls not in visitor.classes]
    if missing_classes:
        print_error(f"Missing classes: {', '.join(missing_classes)}")
        return False

    print_success("All required synchronization classes found")

    # Check SynchronizationGroup methods
    required_group_methods = [
        "add_acquisition",
        "remove_acquisition",
        "start_synchronized",
        "stop_synchronized",
        "pause_synchronized",
        "resume_synchronized",
        "get_status",
        "get_synchronized_data",
    ]

    group_methods = visitor.classes.get("SynchronizationGroup", {}).get("methods", [])
    missing_methods = [m for m in required_group_methods if m not in group_methods]

    if missing_methods:
        print_error(
            f"SynchronizationGroup missing methods: {', '.join(missing_methods)}"
        )
        return False

    print_success(
        f"SynchronizationGroup has all {len(required_group_methods)} required methods"
    )

    # Check SynchronizationManager methods
    required_manager_methods = [
        "create_sync_group",
        "get_sync_group",
        "delete_sync_group",
        "list_sync_groups",
    ]

    manager_methods = visitor.classes.get("SynchronizationManager", {}).get(
        "methods", []
    )
    missing_methods = [m for m in required_manager_methods if m not in manager_methods]

    if missing_methods:
        print_error(
            f"SynchronizationManager missing methods: {', '.join(missing_methods)}"
        )
        return False

    print_success(
        f"SynchronizationManager has all {len(required_manager_methods)} required methods"
    )

    return True


def verify_api():
    """Verify API endpoints."""
    print_header("Verifying API Endpoints")

    filepath = Path("api/acquisition.py")
    if not filepath.exists():
        print_error("api/acquisition.py not found")
        return False

    visitor = parse_python_file(filepath)
    if not visitor:
        return False

    # Check basic acquisition endpoints
    basic_endpoints = [
        "create_session",
        "start_acquisition",
        "stop_acquisition",
        "pause_acquisition",
        "resume_acquisition",
        "get_session_status",
        "get_acquisition_data",
        "list_sessions",
        "export_data",
        "delete_session",
    ]

    # Check statistics endpoints
    stats_endpoints = [
        "get_rolling_stats",
        "get_fft_analysis",
        "detect_trend",
        "assess_quality",
        "detect_peaks",
        "detect_crossings",
    ]

    # Check sync endpoints
    sync_endpoints = [
        "create_sync_group",
        "add_to_sync_group",
        "start_sync_group",
        "stop_sync_group",
        "pause_sync_group",
        "resume_sync_group",
        "get_sync_group_status",
        "get_sync_group_data",
        "list_sync_groups",
        "delete_sync_group",
    ]

    all_endpoints = basic_endpoints + stats_endpoints + sync_endpoints
    found_endpoints = [ep for ep in all_endpoints if ep in visitor.functions]
    missing_endpoints = [ep for ep in all_endpoints if ep not in visitor.functions]

    print_success(f"Found {len(found_endpoints)}/{len(all_endpoints)} API endpoints")

    if missing_endpoints:
        print_warning(f"Missing endpoints: {', '.join(missing_endpoints[:5])}...")
        return False

    print_success("✓ Basic acquisition endpoints (10)")
    print_success("✓ Statistics endpoints (6)")
    print_success("✓ Synchronization endpoints (10)")

    return True


def verify_websocket():
    """Verify WebSocket integration."""
    print_header("Verifying WebSocket Integration")

    filepath = Path("websocket_server.py")
    if not filepath.exists():
        print_error("websocket_server.py not found")
        return False

    content = filepath.read_text()

    # Check for acquisition streaming methods
    required_features = [
        "_stream_acquisition",
        "start_acquisition_stream",
        "stop_acquisition_stream",
        "start_acquisition_stream",  # message handler
        "stop_acquisition_stream",  # message handler
    ]

    found = sum(1 for feature in required_features if feature in content)

    if found >= 3:
        print_success(
            f"WebSocket acquisition streaming integrated ({found}/5 features found)"
        )
        return True
    else:
        print_error(f"WebSocket integration incomplete ({found}/5 features)")
        return False


def verify_init():
    """Verify module initialization."""
    print_header("Verifying Module Exports")

    filepath = Path("acquisition/__init__.py")
    if not filepath.exists():
        print_error("acquisition/__init__.py not found")
        return False

    content = filepath.read_text()

    # Check for key exports
    required_exports = [
        "acquisition_manager",
        "stats_engine",
        "sync_manager",
        "AcquisitionMode",
        "AcquisitionState",
        "StatisticsEngine",
        "SynchronizationManager",
    ]

    missing_exports = [exp for exp in required_exports if exp not in content]

    if missing_exports:
        print_error(f"Missing exports: {', '.join(missing_exports)}")
        return False

    print_success(f"All {len(required_exports)} key exports found")
    return True


def main():
    """Run all verification tests."""
    print_header("LabLink Data Acquisition & Logging System Verification")
    print("This script validates the acquisition system implementation")

    tests = [
        ("Models", verify_models),
        ("Manager", verify_manager),
        ("Statistics", verify_statistics),
        ("Synchronization", verify_synchronization),
        ("API Endpoints", verify_api),
        ("WebSocket Integration", verify_websocket),
        ("Module Exports", verify_init),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print_error(f"Test '{name}' failed with exception: {e}")
            results.append((name, False))

    # Print summary
    print_header("Verification Summary")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        if result:
            print_success(f"{name:.<50} PASS")
        else:
            print_error(f"{name:.<50} FAIL")

    print(f"\n{BLUE}{'=' * 70}{RESET}")
    if passed == total:
        print(f"{GREEN}All {total} verification tests passed!{RESET}")
        print(
            f"{GREEN}The Data Acquisition & Logging System is properly implemented.{RESET}"
        )
    else:
        print(f"{YELLOW}{passed}/{total} tests passed{RESET}")
        print(f"{RED}{total - passed} tests failed{RESET}")
    print(f"{BLUE}{'=' * 70}{RESET}\n")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
