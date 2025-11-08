#!/usr/bin/env python3
"""
Validation script for new equipment drivers.
Performs syntax checks and validates class structure without requiring dependencies.
"""

import sys
import ast
import os


def check_file_syntax(filepath):
    """Check if a Python file has valid syntax."""
    try:
        with open(filepath, 'r') as f:
            code = f.read()
        ast.parse(code)
        return True, None
    except SyntaxError as e:
        return False, str(e)


def extract_classes(filepath):
    """Extract class names from a Python file."""
    with open(filepath, 'r') as f:
        code = f.read()
    tree = ast.parse(code)
    classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    return classes


def extract_methods(filepath, classname):
    """Extract method names from a class in a Python file."""
    with open(filepath, 'r') as f:
        code = f.read()
    tree = ast.parse(code)

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == classname:
            methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            return methods
    return []


def validate_driver(filepath, expected_class, expected_methods):
    """Validate a driver file."""
    print(f"\nValidating {os.path.basename(filepath)}...")

    # Check syntax
    valid, error = check_file_syntax(filepath)
    if not valid:
        print(f"  ✗ Syntax Error: {error}")
        return False

    print(f"  ✓ Syntax valid")

    # Check class exists
    classes = extract_classes(filepath)
    if expected_class not in classes:
        print(f"  ✗ Class '{expected_class}' not found")
        print(f"    Found classes: {classes}")
        return False

    print(f"  ✓ Class '{expected_class}' exists")

    # Check methods
    methods = extract_methods(filepath, expected_class)
    missing_methods = set(expected_methods) - set(methods)

    if missing_methods:
        print(f"  ✗ Missing methods: {missing_methods}")
        return False

    print(f"  ✓ All required methods present ({len(expected_methods)} methods)")

    return True


def main():
    """Run validation on all new drivers."""
    print("="*60)
    print("LabLink New Equipment Driver Validation")
    print("="*60)

    base_path = "/home/x9x0/LabLink/server/equipment"

    # Required methods for all equipment drivers
    base_methods = ['__init__', 'get_info', 'get_status', 'execute_command']

    # Additional methods for oscilloscopes
    scope_methods = base_methods + [
        'get_waveform', 'get_waveform_raw', 'set_timebase', 'set_channel',
        'trigger_single', 'trigger_run', 'trigger_stop', 'autoscale', 'get_measurements'
    ]

    # Additional methods for electronic loads
    load_methods = base_methods + [
        'set_mode', 'set_current', 'set_voltage', 'set_resistance',
        'set_power', 'set_input', 'get_readings'
    ]

    # Additional methods for power supplies
    ps_methods = base_methods + [
        'set_voltage', 'set_current', 'set_output', 'get_readings', 'get_setpoints'
    ]

    results = []

    # Test Rigol DS1104 in rigol_scope.py
    results.append(validate_driver(
        f"{base_path}/rigol_scope.py",
        "RigolDS1104",
        scope_methods
    ))

    # Test Rigol DL3021A
    results.append(validate_driver(
        f"{base_path}/rigol_electronic_load.py",
        "RigolDL3021A",
        load_methods
    ))

    # Test BK 9205B
    results.append(validate_driver(
        f"{base_path}/bk_power_supply.py",
        "BK9205B",
        ['__init__']  # Inherits from base, just check it exists
    ))

    # Test BK 1685B
    results.append(validate_driver(
        f"{base_path}/bk_power_supply.py",
        "BK1685B",
        ['__init__']  # Inherits from base, just check it exists
    ))

    # Check equipment manager imports
    print(f"\nValidating equipment manager registration...")
    manager_valid, error = check_file_syntax(f"{base_path}/manager.py")

    if not manager_valid:
        print(f"  ✗ Syntax Error in manager.py: {error}")
        results.append(False)
    else:
        # Check that new classes are imported
        with open(f"{base_path}/manager.py", 'r') as f:
            manager_code = f.read()

        imports_ok = (
            "RigolDS1104" in manager_code and
            "RigolDL3021A" in manager_code and
            "BK9205B" in manager_code and
            "BK1685B" in manager_code
        )

        if imports_ok:
            print(f"  ✓ All new drivers imported in manager.py")
            results.append(True)
        else:
            print(f"  ✗ Not all drivers imported in manager.py")
            results.append(False)

    # Check __init__.py exports
    print(f"\nValidating __init__.py exports...")
    init_valid, error = check_file_syntax(f"{base_path}/__init__.py")

    if not init_valid:
        print(f"  ✗ Syntax Error in __init__.py: {error}")
        results.append(False)
    else:
        with open(f"{base_path}/__init__.py", 'r') as f:
            init_code = f.read()

        exports_ok = (
            "RigolDS1104" in init_code and
            "RigolDL3021A" in init_code and
            "BK9205B" in init_code and
            "BK1685B" in init_code
        )

        if exports_ok:
            print(f"  ✓ All new drivers exported in __init__.py")
            results.append(True)
        else:
            print(f"  ✗ Not all drivers exported in __init__.py")
            results.append(False)

    # Summary
    print(f"\n{'='*60}")
    passed = sum(results)
    total = len(results)
    print(f"Validation Summary: {passed}/{total} checks passed")
    print(f"{'='*60}")

    if all(results):
        print("\n✓ All validation checks passed!")
        print("  Drivers are ready for testing with actual hardware.")
        return 0
    else:
        print("\n✗ Some validation checks failed.")
        print("  Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
