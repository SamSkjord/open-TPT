#!/usr/bin/env python3
"""
Test script for MLX90614 single-point IR temperature sensors.
Tests reading from 4 MLX90614 sensors via I2C multiplexer.

Usage:
    python3 test_mlx90614.py
    python3 test_mlx90614.py --continuous
"""

import sys
import os
import time
import argparse

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hardware.mlx90614_handler import MLX90614Handler


def test_single_read():
    """Test a single temperature reading from all sensors."""
    print("=== MLX90614 Single Read Test ===\n")

    # Create handler
    handler = MLX90614Handler()

    if not handler.sensors:
        print("ERROR: No MLX90614 sensors initialized!")
        return False

    # Read once
    print("Reading temperatures...")
    handler._read_sensors()

    # Get results
    temps = handler.get_all_temperatures()

    print("\nResults:")
    print("-" * 50)
    for position in ["FL", "FR", "RL", "RR"]:
        temp = temps.get(position)
        if temp is not None:
            print(f"  {position}: {temp:6.2f}°C")
        else:
            print(f"  {position}: No data")
    print("-" * 50)

    return True


def test_continuous():
    """Test continuous temperature reading."""
    print("=== MLX90614 Continuous Test ===")
    print("Press Ctrl+C to stop\n")

    # Create handler
    handler = MLX90614Handler()

    if not handler.sensors:
        print("ERROR: No MLX90614 sensors initialized!")
        return False

    # Start background thread
    handler.start()

    try:
        while True:
            # Get latest temps
            temps = handler.get_all_temperatures()

            # Clear line and print
            sys.stdout.write("\r")
            sys.stdout.write(
                f"FL: {temps.get('FL', 0):6.2f}°C | "
                f"FR: {temps.get('FR', 0):6.2f}°C | "
                f"RL: {temps.get('RL', 0):6.2f}°C | "
                f"RR: {temps.get('RR', 0):6.2f}°C"
            )
            sys.stdout.flush()

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n\nStopping...")
        handler.stop()

    return True


def test_thermal_data_compatibility():
    """Test that synthetic thermal images work correctly."""
    print("=== MLX90614 Thermal Data Compatibility Test ===\n")

    handler = MLX90614Handler()

    if not handler.sensors:
        print("ERROR: No MLX90614 sensors initialized!")
        return False

    # Read once
    handler._read_sensors()

    # Test get_thermal_data() compatibility
    print("Testing get_thermal_data() API compatibility...")

    # Get all thermal data
    all_data = handler.get_thermal_data()

    for position, data in all_data.items():
        if data is not None:
            print(f"\n{position}:")
            print(f"  Shape: {data.shape} (should be 24x32)")
            print(f"  Min: {data.min():.2f}°C")
            print(f"  Max: {data.max():.2f}°C")
            print(f"  Mean: {data.mean():.2f}°C")
            print(f"  Uniform: {(data == data[0,0]).all()} (should be True for single-point)")
        else:
            print(f"\n{position}: No data")

    # Test get_temperature_range() compatibility
    print("\nTesting get_temperature_range() API compatibility...")
    for position in ["FL", "FR", "RL", "RR"]:
        min_temp, max_temp = handler.get_temperature_range(position)
        if min_temp is not None:
            print(f"  {position}: min={min_temp:.2f}°C, max={max_temp:.2f}°C (should be equal)")
        else:
            print(f"  {position}: No data")

    return True


def main():
    parser = argparse.ArgumentParser(description="Test MLX90614 IR temperature sensors")
    parser.add_argument(
        "--continuous",
        "-c",
        action="store_true",
        help="Run continuous test (press Ctrl+C to stop)"
    )
    parser.add_argument(
        "--compat",
        action="store_true",
        help="Test thermal data API compatibility"
    )

    args = parser.parse_args()

    try:
        if args.compat:
            success = test_thermal_data_compatibility()
        elif args.continuous:
            success = test_continuous()
        else:
            success = test_single_read()

        if success:
            print("\n✓ Test completed successfully")
            return 0
        else:
            print("\n✗ Test failed")
            return 1

    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
