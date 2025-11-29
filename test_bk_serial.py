#!/usr/bin/env python3
"""Direct serial test for BK Precision 1902B power supply.

This script bypasses LabLink and talks directly to the power supply via serial.
Use this to verify commands and syntax.

Usage:
    python3 test_bk_serial.py /dev/ttyUSB0

Commands:
    GMAX  - Get max voltage/current
    GETD  - Get voltage/current readings
    GOUT  - Get output state (0=OFF, 1=ON)
    GETS  - Get voltage/current setpoints
    VOLT{vvv} - Set voltage (e.g., VOLT120 = 12.0V)
    CURR{ccc} - Set current (e.g., CURR050 = 5.0A)
    SOUT0 - Turn output ON
    SOUT1 - Turn output OFF
"""

import serial
import sys
import time


def send_command(ser, command):
    """Send command and read response."""
    print(f"\n>>> Sending: {command}")

    # Send command with CR termination
    ser.write((command + '\r').encode('ascii'))
    ser.flush()

    # Read response until we get OK\r
    response = b''
    start_time = time.time()
    timeout = 2.0

    while True:
        if ser.in_waiting > 0:
            byte = ser.read(1)
            response += byte

            # Check for completion (ends with OK\r)
            if response.endswith(b'OK\r'):
                break

        # Timeout check
        if time.time() - start_time > timeout:
            print(f"TIMEOUT! Partial response: {response}")
            return None

    # Decode and parse
    response_str = response.decode('ascii', errors='ignore')
    response_str = response_str.strip()

    # Remove OK suffix
    if response_str.endswith('OK'):
        response_str = response_str[:-2].strip()

    print(f"<<< Response: {response_str}")
    return response_str


def parse_getd(response):
    """Parse GETD response: VVVVIIIIIM"""
    if len(response) < 9:
        print(f"ERROR: Invalid GETD response length: {len(response)}")
        return

    voltage = int(response[:4]) / 100.0
    current = int(response[4:8]) / 1000.0
    mode = int(response[8])
    mode_str = "CV" if mode == 0 else "CC"

    print(f"    Voltage: {voltage:.2f}V")
    print(f"    Current: {current:.3f}A")
    print(f"    Mode: {mode_str}")


def parse_gets(response):
    """Parse GETS response: VVVCCC"""
    if len(response) < 6:
        print(f"ERROR: Invalid GETS response length: {len(response)}")
        return

    voltage = int(response[:3]) / 10.0
    current = int(response[3:6]) / 10.0

    print(f"    Voltage setpoint: {voltage:.1f}V")
    print(f"    Current setpoint: {current:.1f}A")


def parse_gmax(response):
    """Parse GMAX response: VVVCCC"""
    if len(response) < 6:
        print(f"ERROR: Invalid GMAX response length: {len(response)}")
        return

    max_voltage = int(response[:3]) / 10.0
    max_current = int(response[3:6]) / 10.0

    print(f"    Max voltage: {max_voltage:.1f}V")
    print(f"    Max current: {max_current:.1f}A")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 test_bk_serial.py /dev/ttyUSB0")
        print("\nTo find your device, run: ls -la /dev/tty* | grep USB")
        sys.exit(1)

    port = sys.argv[1]

    print(f"Opening serial port: {port}")
    print("Settings: 9600 8N1, termination=CR")

    try:
        # Open serial port with BK Precision settings
        ser = serial.Serial(
            port=port,
            baudrate=9600,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=2.0,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False
        )

        print(f"✓ Port opened successfully\n")
        print("=" * 60)

        # Test commands
        print("\n1. Testing GMAX (Get max voltage/current)")
        response = send_command(ser, "GMAX")
        if response:
            parse_gmax(response)

        print("\n" + "=" * 60)
        print("\n2. Testing GETS (Get setpoints)")
        response = send_command(ser, "GETS")
        if response:
            parse_gets(response)

        print("\n" + "=" * 60)
        print("\n3. Testing GETD (Get actual readings)")
        response = send_command(ser, "GETD")
        if response:
            parse_getd(response)

        print("\n" + "=" * 60)
        print("\n4. Testing GOUT (Get output state)")
        response = send_command(ser, "GOUT")
        if response:
            # GOUT returns "0" for ON, "1" for OFF (inverted like SOUT)
            state = "ON" if response.strip() == "0" else "OFF"
            print(f"    Output state: {state}")

        print("\n" + "=" * 60)
        print("\n5. Manual command mode")
        print("Enter commands (or 'quit' to exit):")
        print("Examples:")
        print("  VOLT120  - Set 12.0V")
        print("  CURR050  - Set 5.0A")
        print("  SOUT0    - Turn output ON")
        print("  SOUT1    - Turn output OFF")
        print("  GETD     - Read voltage/current")

        while True:
            try:
                cmd = input("\nCommand> ").strip()
                if cmd.lower() in ['quit', 'exit', 'q']:
                    break
                if not cmd:
                    continue

                response = send_command(ser, cmd)

                # Auto-parse known commands
                if cmd == "GETD" and response:
                    parse_getd(response)
                elif cmd == "GETS" and response:
                    parse_gets(response)
                elif cmd == "GMAX" and response:
                    parse_gmax(response)
                elif cmd == "GOUT" and response:
                    # GOUT returns "0" for ON, "1" for OFF (inverted like SOUT)
                    state = "ON" if response.strip() == "0" else "OFF"
                    print(f"    Output: {state}")

            except KeyboardInterrupt:
                print("\n\nExiting...")
                break

        ser.close()
        print("\nSerial port closed.")

    except serial.SerialException as e:
        print(f"ERROR: Could not open serial port: {e}")
        print("\nTroubleshooting:")
        print("  1. Check device is connected: ls -la /dev/tty* | grep USB")
        print("  2. Check permissions: sudo chmod 666 /dev/ttyUSB0")
        print("  3. Make sure no other program is using the port")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
