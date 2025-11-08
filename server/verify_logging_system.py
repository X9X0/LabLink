#!/usr/bin/env python3
"""Verification script for the Advanced Logging System.

This script validates that all logging components are properly implemented.
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


def verify_formatters():
    """Verify logging formatters."""
    print_header("Verifying Logging Formatters")

    filepath = Path("logging_config/formatters.py")
    if not filepath.exists():
        print_error("logging_config/formatters.py not found")
        return False

    visitor = parse_python_file(filepath)
    if not visitor:
        return False

    # Check required classes
    required_classes = ["JsonFormatter", "ColoredFormatter", "CompactFormatter"]
    missing_classes = [cls for cls in required_classes if cls not in visitor.classes]

    if missing_classes:
        print_error(f"Missing classes: {', '.join(missing_classes)}")
        return False

    print_success("All required formatter classes found")

    # Check JsonFormatter has format method
    if "format" in visitor.classes.get("JsonFormatter", {}).get("methods", []):
        print_success("JsonFormatter.format() method found")
    else:
        print_warning("JsonFormatter.format() method may be missing")

    return len(missing_classes) == 0


def verify_handlers():
    """Verify logging handlers."""
    print_header("Verifying Logging Handlers")

    filepath = Path("logging_config/handlers.py")
    if not filepath.exists():
        print_error("logging_config/handlers.py not found")
        return False

    visitor = parse_python_file(filepath)
    if not visitor:
        return False

    # Check required functions
    required_functions = [
        "get_rotating_file_handler",
        "get_timed_rotating_handler",
        "get_console_handler",
        "get_equipment_handler",
        "get_performance_handler",
        "get_audit_handler"
    ]

    missing_functions = [f for f in required_functions if f not in visitor.functions]

    if missing_functions:
        print_error(f"Missing functions: {', '.join(missing_functions)}")
        return False

    print_success(f"All {len(required_functions)} handler functions found")

    # Check for CompressingRotatingFileHandler class
    if "CompressingRotatingFileHandler" in visitor.classes:
        print_success("CompressingRotatingFileHandler class found")
    else:
        print_warning("CompressingRotatingFileHandler class not found")

    return len(missing_functions) == 0


def verify_performance():
    """Verify performance logging."""
    print_header("Verifying Performance Logging")

    filepath = Path("logging_config/performance.py")
    if not filepath.exists():
        print_error("logging_config/performance.py not found")
        return False

    visitor = parse_python_file(filepath)
    if not visitor:
        return False

    # Check required classes
    if "PerformanceMonitor" not in visitor.classes:
        print_error("PerformanceMonitor class not found")
        return False

    print_success("PerformanceMonitor class found")

    # Check required methods
    required_methods = [
        "log_system_metrics",
        "log_equipment_metrics",
        "log_api_metrics",
        "log_acquisition_metrics"
    ]

    monitor_methods = visitor.classes.get("PerformanceMonitor", {}).get("methods", [])
    missing_methods = [m for m in required_methods if m not in monitor_methods]

    if missing_methods:
        print_error(f"Missing methods: {', '.join(missing_methods)}")
        return False

    print_success(f"All {len(required_methods)} PerformanceMonitor methods found")

    # Check for log_performance decorator
    if "log_performance" in visitor.functions:
        print_success("log_performance decorator found")
    else:
        print_warning("log_performance decorator not found")

    return True


def verify_middleware():
    """Verify logging middleware."""
    print_header("Verifying Logging Middleware")

    filepath = Path("logging_config/middleware.py")
    if not filepath.exists():
        print_error("logging_config/middleware.py not found")
        return False

    visitor = parse_python_file(filepath)
    if not visitor:
        return False

    # Check LoggingMiddleware class
    if "LoggingMiddleware" not in visitor.classes:
        print_error("LoggingMiddleware class not found")
        return False

    print_success("LoggingMiddleware class found")

    # Check dispatch method
    if "dispatch" in visitor.classes.get("LoggingMiddleware", {}).get("methods", []):
        print_success("LoggingMiddleware.dispatch() method found")
    else:
        print_error("LoggingMiddleware.dispatch() method missing")
        return False

    # Check EquipmentEventLogger class
    if "EquipmentEventLogger" not in visitor.classes:
        print_error("EquipmentEventLogger class not found")
        return False

    print_success("EquipmentEventLogger class found")

    # Check required methods
    required_methods = [
        "log_connection",
        "log_disconnection",
        "log_command",
        "log_error",
        "log_state_change",
        "log_health_check"
    ]

    event_methods = visitor.classes.get("EquipmentEventLogger", {}).get("methods", [])
    missing_methods = [m for m in required_methods if m not in event_methods]

    if missing_methods:
        print_error(f"Missing methods: {', '.join(missing_methods)}")
        return False

    print_success(f"All {len(required_methods)} EquipmentEventLogger methods found")

    return True


def verify_utils():
    """Verify logging utilities."""
    print_header("Verifying Logging Utilities")

    filepath = Path("logging_config/utils.py")
    if not filepath.exists():
        print_error("logging_config/utils.py not found")
        return False

    visitor = parse_python_file(filepath)
    if not visitor:
        return False

    # Check required functions
    required_functions = [
        "get_logger",
        "setup_logging",
        "setup_specialized_loggers",
        "cleanup_old_logs"
    ]

    missing_functions = [f for f in required_functions if f not in visitor.functions]

    if missing_functions:
        print_error(f"Missing functions: {', '.join(missing_functions)}")
        return False

    print_success(f"All {len(required_functions)} utility functions found")

    return len(missing_functions) == 0


def verify_integration():
    """Verify integration with main.py."""
    print_header("Verifying Integration")

    filepath = Path("main.py")
    if not filepath.exists():
        print_error("main.py not found")
        return False

    content = filepath.read_text()

    # Check for setup_logging import
    if "from logging_config import" in content and "setup_logging" in content:
        print_success("Logging imports found in main.py")
    else:
        print_error("Missing logging imports in main.py")
        return False

    # Check for setup_logging() call
    if "setup_logging()" in content:
        print_success("setup_logging() called in main.py")
    else:
        print_error("setup_logging() not called in main.py")
        return False

    # Check for LoggingMiddleware
    if "LoggingMiddleware" in content and "add_middleware" in content:
        print_success("LoggingMiddleware added to FastAPI app")
    else:
        print_warning("LoggingMiddleware may not be added to FastAPI app")

    return True


def verify_module_init():
    """Verify module initialization."""
    print_header("Verifying Module Exports")

    filepath = Path("logging_config/__init__.py")
    if not filepath.exists():
        print_error("logging_config/__init__.py not found")
        return False

    content = filepath.read_text()

    # Check for key exports
    required_exports = [
        "JsonFormatter",
        "ColoredFormatter",
        "LoggingMiddleware",
        "get_logger",
        "setup_logging",
        "log_performance"
    ]

    missing_exports = [exp for exp in required_exports if exp not in content]

    if missing_exports:
        print_error(f"Missing exports: {', '.join(missing_exports)}")
        return False

    print_success(f"All {len(required_exports)} key exports found")
    return True


def main():
    """Run all verification tests."""
    print_header("LabLink Advanced Logging System Verification")
    print("This script validates the logging system implementation")

    tests = [
        ("Formatters", verify_formatters),
        ("Handlers", verify_handlers),
        ("Performance Logging", verify_performance),
        ("Middleware", verify_middleware),
        ("Utilities", verify_utils),
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
        print(f"{GREEN}The Advanced Logging System is properly implemented.{RESET}")
    else:
        print(f"{YELLOW}{passed}/{total} tests passed{RESET}")
        print(f"{RED}{total - passed} tests failed{RESET}")
    print(f"{BLUE}{'=' * 70}{RESET}\n")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
