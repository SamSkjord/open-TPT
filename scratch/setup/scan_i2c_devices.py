#!/usr/bin/env python3
"""
Comprehensive I2C bus scanner for the CM4 system.

Scans all I2C buses and identifies known devices, including those behind
the TCA9548A I2C multiplexer. Requires i2c-tools and appropriate permissions.


chmod +x /home/claude/scan_i2c_devices.py
sudo python3 /home/claude/scan_i2c_devices.py
```

This script will:
1. **Find all I2C buses** (i2c-0, i2c-1, i2c-10, etc.)
2. **Scan each bus** for connected devices
3. **Identify known devices** including:
   - PCF85063A RTC (0x51)
   - Battery monitor (0x4B)
   - IMU sensors (0x68/0x69)
   - Neokey board (0x30/0x31)
   - TCA9548A muxer (0x70-0x77)
4. **Scan behind each TCA9548A** muxer:
   - Iterate through all 8 channels
   - Detect MLX90640 thermal cameras (0x33)
   - Detect ADS1015 ADCs (0x48)
   - Detect VL53L1X ToF sensors (0x29)

The output will show a hierarchical view like:
```
Bus i2c-1
──────────────────────
  Direct devices:
    0x30: Neokey 1x4
    0x51: PCF85063A RTC
    0x68: IMU (MPU6050/MPU9250)

  TCA9548A Multiplexer at 0x70:
    Channel 0:
      0x33: MLX90640 thermal camera
    Channel 1:
      0x33: MLX90640 thermal camera




"""

import subprocess
import sys
from typing import Dict, List, Optional, Tuple

# Known I2C device addresses and their identities
KNOWN_DEVICES = {
    0x0C: "ADS1015 ADC (alternative address)",
    0x29: "VL53L1X ToF sensor",
    0x33: "MLX90640 thermal camera",
    0x48: "ADS1015 ADC (default address)",
    0x51: "PCF85063A RTC / EEPROM",
    0x52: "EEPROM (alternative)",
    0x68: "IMU (MPU6050/MPU9250/ICM20948)",
    0x69: "IMU (alternative address)",
    0x70: "TCA9548A I2C Multiplexer (channel 0)",
    0x71: "TCA9548A I2C Multiplexer (channel 1)",
    0x72: "TCA9548A I2C Multiplexer (channel 2)",
    0x73: "TCA9548A I2C Multiplexer (channel 3)",
    0x74: "TCA9548A I2C Multiplexer (channel 4)",
    0x75: "TCA9548A I2C Multiplexer (channel 5)",
    0x76: "TCA9548A I2C Multiplexer (channel 6) / BMP280",
    0x77: "TCA9548A I2C Multiplexer (channel 7) / BMP280",
    0x30: "Neokey 1x4 (default)",
    0x31: "Neokey 1x4 (alternative)",
    0x4B: "Battery monitor (BQ27441/LC709203F)",
}

TCA9548A_ADDRESSES = range(0x70, 0x78)


def run_command(cmd: List[str]) -> Tuple[int, str, str]:
    """Run a shell command and return (returncode, stdout, stderr)."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def get_i2c_buses() -> List[int]:
    """Get list of available I2C bus numbers."""
    returncode, stdout, stderr = run_command(["i2cdetect", "-l"])
    if returncode != 0:
        print(f"Error running i2cdetect: {stderr}")
        return []

    buses = []
    for line in stdout.strip().split("\n"):
        if "i2c-" in line:
            try:
                bus_num = int(line.split("i2c-")[1].split()[0])
                buses.append(bus_num)
            except (IndexError, ValueError):
                continue

    return sorted(buses)


def scan_i2c_bus(bus: int) -> List[int]:
    """Scan an I2C bus and return list of detected device addresses."""
    returncode, stdout, stderr = run_command(["i2cdetect", "-y", str(bus)])
    if returncode != 0:
        print(f"  Error scanning bus {bus}: {stderr}")
        return []

    devices = []
    lines = stdout.strip().split("\n")

    # Skip header line
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue

        # First element is the row label (00:, 10:, etc)
        for addr_str in parts[1:]:
            if addr_str != "--" and addr_str != "UU":
                try:
                    addr = int(addr_str, 16)
                    devices.append(addr)
                except ValueError:
                    continue

    return devices


def select_mux_channel(bus: int, mux_addr: int, channel: int) -> bool:
    """Select a channel on the TCA9548A multiplexer."""
    if channel < 0 or channel > 7:
        return False

    # Write channel bitmask to the mux
    channel_mask = 1 << channel
    returncode, _, _ = run_command(
        ["i2cset", "-y", str(bus), f"0x{mux_addr:02x}", f"0x{channel_mask:02x}"]
    )
    return returncode == 0


def disable_mux(bus: int, mux_addr: int) -> bool:
    """Disable all channels on the TCA9548A multiplexer."""
    returncode, _, _ = run_command(
        ["i2cset", "-y", str(bus), f"0x{mux_addr:02x}", "0x00"]
    )
    return returncode == 0


def scan_mux_channels(bus: int, mux_addr: int) -> Dict[int, List[int]]:
    """Scan all channels behind a TCA9548A multiplexer."""
    channel_devices = {}

    for channel in range(8):
        if not select_mux_channel(bus, mux_addr, channel):
            continue

        # Small delay to let mux settle
        subprocess.run(["sleep", "0.1"])

        devices = scan_i2c_bus(bus)
        # Filter out the mux itself from the scan results
        devices = [d for d in devices if d not in TCA9548A_ADDRESSES]

        if devices:
            channel_devices[channel] = devices

    # Disable mux after scanning
    disable_mux(bus, mux_addr)

    return channel_devices


def identify_device(addr: int) -> str:
    """Return a description of the device at the given address."""
    return KNOWN_DEVICES.get(addr, f"Unknown device")


def main():
    print("=" * 70)
    print("I2C Device Scanner")
    print("=" * 70)
    print()

    # Check for i2c-tools
    returncode, _, _ = run_command(["which", "i2cdetect"])
    if returncode != 0:
        print("Error: i2c-tools not installed.")
        print("Install with: sudo apt install i2c-tools")
        return 1

    buses = get_i2c_buses()
    if not buses:
        print("No I2C buses found!")
        return 1

    print(f"Found I2C buses: {', '.join(f'i2c-{b}' for b in buses)}")
    print()

    for bus in buses:
        print(f"{'─' * 70}")
        print(f"Bus i2c-{bus}")
        print(f"{'─' * 70}")

        devices = scan_i2c_bus(bus)

        if not devices:
            print("  No devices detected")
            print()
            continue

        # Separate muxes from regular devices
        muxes = [d for d in devices if d in TCA9548A_ADDRESSES]
        regular_devices = [d for d in devices if d not in TCA9548A_ADDRESSES]

        # Display regular devices
        if regular_devices:
            print("\n  Direct devices:")
            for addr in sorted(regular_devices):
                print(f"    0x{addr:02X}: {identify_device(addr)}")

        # Scan behind each multiplexer
        for mux_addr in sorted(muxes):
            print(f"\n  TCA9548A Multiplexer at 0x{mux_addr:02X}:")
            channel_devices = scan_mux_channels(bus, mux_addr)

            if not channel_devices:
                print("    No devices found on any channel")
            else:
                for channel in sorted(channel_devices.keys()):
                    print(f"    Channel {channel}:")
                    for addr in sorted(channel_devices[channel]):
                        print(f"      0x{addr:02X}: {identify_device(addr)}")

        print()

    print("=" * 70)
    print("Scan complete")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
