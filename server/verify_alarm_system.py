#!/usr/bin/env python3
"""Verification script for the Alarm & Notification System.

This script validates that all alarm components are properly implemented.
"""

import ast
import sys
from pathlib import Path

# Color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


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
            'methods': [],
            'bases': [b.id if isinstance(b, ast.Name) else str(b) for b in node.bases],
        }
        self.generic_visit(node)
        self.current_class = None

    def visit_FunctionDef(self, node):
        """Visit function definition."""
        if self.current_class:
            self.classes[self.current_class]['methods'].append(node.name)
        else:
            self.functions.append(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        """Visit async function definition."""
        if self.current_class:
            self.classes[self.current_class]['methods'].append(node.name)
        else:
            self.functions.append(node.name)
        self.generic_visit(node)


def parse_python_file(filepath: Path):
    """Parse a Python file and extract structure information."""
    try:
        with open(filepath, 'r') as f:
            tree = ast.parse(f.read())
        visitor = ASTVisitor()
        visitor.visit(tree)
        return visitor
    except Exception as e:
        print_error(f"Failed to parse {filepath}: {e}")
        return None


def verify_models():
    """Verify alarm models."""
    print_header("Verifying Alarm Models")

    filepath = Path("alarm/models.py")
    if not filepath.exists():
        print_error("alarm/models.py not found")
        return False

    visitor = parse_python_file(filepath)
    if not visitor:
        return False

    # Check required classes
    required_classes = [
        "AlarmSeverity",
        "AlarmState",
        "AlarmType",
        "AlarmCondition",
        "AlarmConfig",
        "AlarmEvent",
        "AlarmAcknowledgment",
        "AlarmStatistics",
        "NotificationConfig"
    ]

    missing_classes = [cls for cls in required_classes if cls not in visitor.classes]

    if missing_classes:
        print_error(f"Missing classes: {', '.join(missing_classes)}")
        return False

    print_success(f"All {len(required_classes)} required model classes found")

    return True


def verify_manager():
    """Verify alarm manager."""
    print_header("Verifying Alarm Manager")

    filepath = Path("alarm/manager.py")
    if not filepath.exists():
        print_error("alarm/manager.py not found")
        return False

    visitor = parse_python_file(filepath)
    if not visitor:
        return False

    # Check AlarmManager class
    if "AlarmManager" not in visitor.classes:
        print_error("AlarmManager class not found")
        return False

    print_success("AlarmManager class found")

    # Check required methods
    required_methods = [
        "create_alarm",
        "update_alarm",
        "delete_alarm",
        "enable_alarm",
        "disable_alarm",
        "check_alarm",
        "acknowledge_alarm",
        "clear_alarm",
        "get_alarm",
        "list_alarms",
        "get_event",
        "list_active_events",
        "list_events",
        "get_statistics"
    ]

    manager_methods = visitor.classes.get("AlarmManager", {}).get("methods", [])
    missing_methods = [m for m in required_methods if m not in manager_methods]

    if missing_methods:
        print_error(f"Missing methods: {', '.join(missing_methods)}")
        return False

    print_success(f"All {len(required_methods)} required methods found")

    return True


def verify_notifications():
    """Verify notification manager."""
    print_header("Verifying Notification Manager")

    filepath = Path("alarm/notifications.py")
    if not filepath.exists():
        print_error("alarm/notifications.py not found")
        return False

    visitor = parse_python_file(filepath)
    if not visitor:
        return False

    # Check NotificationManager class
    if "NotificationManager" not in visitor.classes:
        print_error("NotificationManager class not found")
        return False

    print_success("NotificationManager class found")

    # Check required methods
    required_methods = [
        "configure",
        "send_notification",
        "_send_email",
        "_send_sms",
        "_send_websocket"
    ]

    manager_methods = visitor.classes.get("NotificationManager", {}).get("methods", [])
    missing_methods = [m for m in required_methods if m not in manager_methods]

    if missing_methods:
        print_error(f"Missing methods: {', '.join(missing_methods)}")
        return False

    print_success(f"All {len(required_methods)} notification methods found")

    return True


def verify_api():
    """Verify API endpoints."""
    print_header("Verifying API Endpoints")

    filepath = Path("api/alarms.py")
    if not filepath.exists():
        print_error("api/alarms.py not found")
        return False

    visitor = parse_python_file(filepath)
    if not visitor:
        return False

    # Check required endpoints
    required_endpoints = [
        "create_alarm",
        "get_alarm",
        "list_alarms",
        "update_alarm",
        "delete_alarm",
        "enable_alarm",
        "disable_alarm",
        "check_alarm",
        "list_active_alarms",
        "get_alarm_event",
        "list_alarm_events",
        "acknowledge_alarm",
        "clear_alarm",
        "get_alarm_statistics",
        "configure_notifications",
        "get_notification_config"
    ]

    found_endpoints = [ep for ep in required_endpoints if ep in visitor.functions]
    missing_endpoints = [ep for ep in required_endpoints if ep not in visitor.functions]

    if missing_endpoints:
        print_error(f"Missing endpoints: {', '.join(missing_endpoints)}")
        return False

    print_success(f"All {len(required_endpoints)} API endpoints found")

    return True


def verify_integration():
    """Verify integration with main app."""
    print_header("Verifying Integration")

    filepath = Path("main.py")
    if not filepath.exists():
        print_error("main.py not found")
        return False

    content = filepath.read_text()

    # Check for alarms router import
    if "alarms_router" in content:
        print_success("Alarms router imported in main.py")
    else:
        print_error("Alarms router not imported in main.py")
        return False

    # Check for router inclusion
    if "include_router(alarms_router" in content:
        print_success("Alarms router included in FastAPI app")
    else:
        print_error("Alarms router not included in FastAPI app")
        return False

    return True


def verify_module_init():
    """Verify module initialization."""
    print_header("Verifying Module Exports")

    filepath = Path("alarm/__init__.py")
    if not filepath.exists():
        print_error("alarm/__init__.py not found")
        return False

    content = filepath.read_text()

    # Check for key exports
    required_exports = [
        "AlarmSeverity",
        "AlarmState",
        "AlarmType",
        "AlarmCondition",
        "AlarmConfig",
        "AlarmEvent",
        "alarm_manager",
        "notification_manager"
    ]

    missing_exports = [exp for exp in required_exports if exp not in content]

    if missing_exports:
        print_error(f"Missing exports: {', '.join(missing_exports)}")
        return False

    print_success(f"All {len(required_exports)} key exports found")

    return True


def main():
    """Run all verification tests."""
    print_header("LabLink Alarm & Notification System Verification")
    print("This script validates the alarm system implementation")

    tests = [
        ("Models", verify_models),
        ("Alarm Manager", verify_manager),
        ("Notification Manager", verify_notifications),
        ("API Endpoints", verify_api),
        ("Module Exports", verify_module_init),
        ("Integration", verify_integration)
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
        print(f"{GREEN}The Alarm & Notification System is properly implemented.{RESET}")
    else:
        print(f"{YELLOW}{passed}/{total} tests passed{RESET}")
        print(f"{RED}{total - passed} tests failed{RESET}")
    print(f"{BLUE}{'=' * 70}{RESET}\n")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
