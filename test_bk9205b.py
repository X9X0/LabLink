#!/usr/bin/env python3
"""
Manual test script for BK Precision 9205B power supply.
Tests basic VISA/SCPI commands to verify device communication.
"""

import sys
import time
import pyvisa


def test_bk9205b():
    """Test basic communication with BK 9205B power supply."""
    print("=" * 70)
    print("BK Precision 9205B Power Supply - Manual Test")
    print("=" * 70)

    # Initialize PyVISA resource manager
    try:
        rm = pyvisa.ResourceManager('@py')
        print(f"\nPyVISA backend: {rm}")
    except Exception as e:
        print(f"\nERROR: Failed to initialize PyVISA: {e}")
        return False

    # List all available VISA resources
    print("\n1. Discovering VISA resources...")
    try:
        resources = rm.list_resources()
        print(f"   Found {len(resources)} VISA resource(s):")
        for i, resource in enumerate(resources, 1):
            print(f"   [{i}] {resource}")
    except Exception as e:
        print(f"   ERROR: Failed to list resources: {e}")
        return False

    if not resources:
        print("\n   No VISA resources found!")
        print("   - Check USB connections")
        print("   - Verify device is powered on")
        print("   - Check USB permissions in Docker (privileged: true)")
        return False

    # Find BK 9205B (USB VID:PID = 2ec7:9200 = 11975:37376 in decimal)
    print("\n2. Looking for BK 9205B (USB VID:PID 2ec7:9200 = 11975:37376 decimal)...")
    bk9205b_resource = None

    for resource in resources:
        # Parse USB resource string: USB0::VID::PID::SERIAL::INSTR
        if resource.startswith('USB'):
            parts = resource.split('::')
            if len(parts) >= 3:
                try:
                    vid_decimal = int(parts[1])
                    pid_decimal = int(parts[2])
                    vid_hex = f"{vid_decimal:04x}"
                    pid_hex = f"{pid_decimal:04x}"

                    print(f"   Found USB device: {resource}")
                    print(f"      VID:PID = {vid_hex}:{pid_hex} (decimal {vid_decimal}:{pid_decimal})")

                    # Check if this is the BK 9205B (VID=0x2ec7, PID=0x9200)
                    if vid_decimal == 11975 and pid_decimal == 37376:
                        bk9205b_resource = resource
                        print(f"      ✓ This is the BK 9205B!")
                        break
                except (ValueError, IndexError):
                    print(f"   Found USB device (couldn't parse IDs): {resource}")
        elif 'ASRL' in resource:
            print(f"   Found Serial device: {resource} (skipping)")

    if not bk9205b_resource:
        print("\n   BK 9205B not found automatically.")
        print("\n   Available resources:")
        for i, resource in enumerate(resources, 1):
            print(f"   [{i}] {resource}")

        selection = input("\n   Enter resource number to test (or 'q' to quit): ").strip()
        if selection.lower() == 'q':
            return False

        try:
            idx = int(selection) - 1
            if 0 <= idx < len(resources):
                bk9205b_resource = resources[idx]
            else:
                print("   Invalid selection!")
                return False
        except ValueError:
            print("   Invalid input!")
            return False

    print(f"\n3. Connecting to: {bk9205b_resource}")

    try:
        # Open device with appropriate timeout and termination
        device = rm.open_resource(
            bk9205b_resource,
            timeout=5000,  # 5 second timeout
            write_termination='\n',
            read_termination='\n'
        )
        print(f"   Connected successfully!")
        print(f"   Timeout: {device.timeout}ms")
        print(f"   Write termination: {repr(device.write_termination)}")
        print(f"   Read termination: {repr(device.read_termination)}")
    except Exception as e:
        print(f"   ERROR: Failed to connect: {e}")
        return False

    # Test basic SCPI commands
    print("\n4. Testing commands (without device.clear() - BK 9205B doesn't like it)...")

    # Test both standard SCPI and simpler commands
    commands = [
        # Standard SCPI (may not work)
        ("*IDN?", "Device identification (standard SCPI)"),
        ("*OPC?", "Operation complete query (standard SCPI)"),
        ("SYST:ERR?", "System error query (standard SCPI)"),
        ("MEAS:VOLT?", "Measure output voltage (standard SCPI)"),
        ("MEAS:CURR?", "Measure output current (standard SCPI)"),
        # Simple commands (more likely to work)
        ("VOLT?", "Query voltage setpoint"),
        ("CURR?", "Query current setpoint"),
        ("OUTP?", "Query output state"),
        ("ISET?", "Query current setpoint (alternate)"),
        ("VSET?", "Query voltage setpoint (alternate)"),
        ("GETD", "Get device data (BK custom command)"),
        ("GETS", "Get status (BK custom command)"),
        ("GPAL", "Get all parameters (BK custom command)"),
    ]

    results = {}

    for cmd, description in commands:
        print(f"\n   Testing: {cmd:20s} ({description})")
        try:
            # Don't call device.clear() - it causes VI_ERROR_NSUP_OPER on BK 9205B
            response = device.query(cmd)
            print(f"   Response: {response.strip()}")
            results[cmd] = response.strip()
        except pyvisa.errors.VisaIOError as e:
            print(f"   ERROR: {e}")
            results[cmd] = f"ERROR: {e}"
        except Exception as e:
            print(f"   ERROR: {e}")
            results[cmd] = f"ERROR: {e}"

        time.sleep(0.3)  # Small delay between commands

    # Try setting safe test values (if output is off)
    print("\n5. Testing command writing (safe values)...")

    try:
        # Check if output is on
        output_state = device.query("OUTP?").strip()
        print(f"   Current output state: {output_state}")

        if output_state in ["0", "OFF"]:
            print("\n   Output is OFF - safe to test set commands")

            test_commands = [
                ("VOLT 5.0", "Set voltage to 5.0V"),
                ("CURR 0.5", "Set current limit to 0.5A"),
                ("VOLT?", "Query voltage setpoint"),
                ("CURR?", "Query current setpoint"),
            ]

            for cmd, description in test_commands:
                print(f"\n   Sending: {cmd:15s} ({description})")
                try:
                    if '?' in cmd:
                        response = device.query(cmd)
                        print(f"   Response: {response.strip()}")
                    else:
                        device.write(cmd)
                        print(f"   Success!")
                except Exception as e:
                    print(f"   ERROR: {e}")

                time.sleep(0.2)
        else:
            print("\n   Output is ON - skipping set commands for safety")
            print("   Turn off output to test voltage/current setting")

    except Exception as e:
        print(f"   ERROR during set command testing: {e}")

    # Close connection
    print("\n6. Closing connection...")
    try:
        device.close()
        print("   Connection closed successfully")
    except Exception as e:
        print(f"   Warning: Error closing connection: {e}")

    # Summary
    print("\n" + "=" * 70)
    print("Test Summary:")
    print("=" * 70)

    success_count = sum(1 for v in results.values() if not v.startswith("ERROR"))
    total_count = len(results)

    print(f"\nSuccessful commands: {success_count}/{total_count}")

    if "*IDN?" in results and not results["*IDN?"].startswith("ERROR"):
        print(f"\nDevice Identity: {results['*IDN?']}")

    if success_count == 0:
        print("\n⚠ WARNING: No commands succeeded!")
        print("Possible issues:")
        print("  - Wrong device driver/protocol")
        print("  - Incorrect SCPI command set")
        print("  - Communication settings mismatch")
        print("  - Device firmware issue")
    elif success_count < total_count:
        print("\n⚠ PARTIAL SUCCESS: Some commands failed")
        print("Check which commands work and which don't above")
    else:
        print("\n✓ SUCCESS: All commands worked!")

    print("\n" + "=" * 70)

    return success_count > 0


if __name__ == "__main__":
    try:
        success = test_bk9205b()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
