#!/usr/bin/env python3
"""LabLink test runner script."""

import sys
import subprocess
import argparse
from pathlib import Path


def run_command(cmd, description):
    """Run a command and return success status."""
    print(f"\n{'='*60}")
    print(f"{description}")
    print(f"{'='*60}")
    print(f"Running: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, capture_output=False)

    if result.returncode == 0:
        print(f"\n✓ {description} - PASSED")
    else:
        print(f"\n✗ {description} - FAILED")

    return result.returncode == 0


def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(
        description="LabLink Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all tests
  python run_tests.py

  # Run only unit tests
  python run_tests.py --unit

  # Run with coverage
  python run_tests.py --coverage

  # Run specific test file
  python run_tests.py --file tests/unit/test_settings.py

  # Run tests matching pattern
  python run_tests.py --pattern "test_buffer"

  # Skip slow tests
  python run_tests.py --fast
        """
    )

    parser.add_argument(
        "--unit",
        action="store_true",
        help="Run only unit tests"
    )

    parser.add_argument(
        "--integration",
        action="store_true",
        help="Run only integration tests"
    )

    parser.add_argument(
        "--e2e",
        action="store_true",
        help="Run only end-to-end tests"
    )

    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Run tests with coverage report"
    )

    parser.add_argument(
        "--html",
        action="store_true",
        help="Generate HTML coverage report"
    )

    parser.add_argument(
        "--fast",
        action="store_true",
        help="Skip slow tests"
    )

    parser.add_argument(
        "--file",
        type=str,
        help="Run specific test file"
    )

    parser.add_argument(
        "--pattern",
        type=str,
        help="Run tests matching pattern"
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output"
    )

    parser.add_argument(
        "--parallel",
        "-n",
        type=int,
        help="Run tests in parallel (requires pytest-xdist)"
    )

    args = parser.parse_args()

    # Build pytest command
    cmd = ["python", "-m", "pytest"]

    # Add test selection
    if args.unit:
        cmd.extend(["-m", "unit"])
        description = "Unit Tests"
    elif args.integration:
        cmd.extend(["-m", "integration"])
        description = "Integration Tests"
    elif args.e2e:
        cmd.extend(["-m", "e2e"])
        description = "End-to-End Tests"
    else:
        description = "All Tests"

    # Add coverage
    if args.coverage:
        cmd.extend([
            "--cov=client",
            "--cov=server",
            "--cov-report=term-missing"
        ])
        if args.html:
            cmd.append("--cov-report=html")

    # Skip slow tests
    if args.fast:
        cmd.extend(["-m", "not slow"])
        description += " (Fast)"

    # Specific file
    if args.file:
        cmd.append(args.file)
        description = f"Test File: {args.file}"

    # Pattern matching
    if args.pattern:
        cmd.extend(["-k", args.pattern])
        description += f" (Pattern: {args.pattern})"

    # Verbosity
    if args.verbose:
        cmd.append("-vv")

    # Parallel execution
    if args.parallel:
        cmd.extend(["-n", str(args.parallel)])
        description += f" (Parallel: {args.parallel} workers)"

    # Run tests
    success = run_command(cmd, description)

    # Print summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")

    if success:
        print("✓ All tests passed!")
        if args.coverage and args.html:
            print("\nCoverage report generated: htmlcov/index.html")
        return 0
    else:
        print("✗ Some tests failed!")
        print("\nCheck the output above for details")
        return 1


if __name__ == "__main__":
    sys.exit(main())
