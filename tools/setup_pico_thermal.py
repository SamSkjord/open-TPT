#!/usr/bin/env python3
"""
Pico Thermal Setup and Diagnostic Tool

Reads full thermal frames from all Pico I2C slaves and displays
them as heatmaps for initial setup, alignment, and diagnostics.

Usage:
    python3 setup_pico_thermal.py              # Single snapshot
    python3 setup_pico_thermal.py --live       # Live updating view
    python3 setup_pico_thermal.py --save       # Save snapshot to file
"""

import sys
import os
import time
import argparse
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib import animation
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import board
    import busio
    from hardware.i2c_mux import I2CMux
    I2C_AVAILABLE = True
except ImportError:
    I2C_AVAILABLE = False
    print("WARNING: I2C libraries not available - running in demo mode")


# Pico I2C slave register addresses
class PicoRegisters:
    FIRMWARE_VERSION = 0x10
    FPS = 0x13
    DETECTED = 0x14
    CONFIDENCE = 0x15
    FRAME_DATA_START = 0x51  # Full 768-pixel frame


class PicoThermalVisualizer:
    """Visualizes thermal data from Pico I2C slaves."""

    PICO_I2C_ADDR = 0x08
    MLX_WIDTH = 32
    MLX_HEIGHT = 24

    # Tyre positions to I2C mux channels
    POSITION_TO_CHANNEL = {
        "FL": 0,
        "FR": 1,
        "RL": 2,
        "RR": 3,
    }

    def __init__(self):
        """Initialize the visualizer."""
        self.i2c = None
        self.mux = None
        self.frames = {}
        self.zone_data = {}

        if I2C_AVAILABLE:
            try:
                self.i2c = busio.I2C(board.SCL, board.SDA)
                self.mux = I2CMux()
                print("I2C initialized successfully")
            except Exception as e:
                print(f"Error initializing I2C: {e}")
                I2C_AVAILABLE = False

    def read_byte(self, register):
        """Read a single byte from Pico."""
        try:
            self.i2c.writeto(self.PICO_I2C_ADDR, bytes([register]))
            result = bytearray(1)
            self.i2c.readfrom_into(self.PICO_I2C_ADDR, result)
            return result[0]
        except Exception:
            return None

    def read_frame(self):
        """Read full 768-pixel thermal frame from Pico."""
        try:
            import struct

            # Read 1536 bytes (768 pixels × 2 bytes)
            self.i2c.writeto(self.PICO_I2C_ADDR, bytes([PicoRegisters.FRAME_DATA_START]))
            result = bytearray(1536)
            self.i2c.readfrom_into(self.PICO_I2C_ADDR, result)

            # Unpack as 768 signed int16 values (little-endian)
            temps_tenths = struct.unpack('<768h', result)

            # Convert from tenths of °C to °C
            temps_celsius = np.array(temps_tenths, dtype=float) / 10.0

            # Reshape to 24x32
            return temps_celsius.reshape(self.MLX_HEIGHT, self.MLX_WIDTH)

        except Exception as e:
            print(f"Error reading frame: {e}")
            return None

    def read_all_frames(self):
        """Read thermal frames from all Pico slaves."""
        if not I2C_AVAILABLE:
            # Demo mode - generate synthetic data
            return self._generate_demo_frames()

        frames = {}
        zone_data = {}

        for position, channel in self.POSITION_TO_CHANNEL.items():
            try:
                # Select channel
                if not self.mux.select_channel(channel):
                    print(f"Failed to select channel {channel} for {position}")
                    continue

                time.sleep(0.1)

                # Read status
                version = self.read_byte(PicoRegisters.FIRMWARE_VERSION)
                fps = self.read_byte(PicoRegisters.FPS)
                detected = self.read_byte(PicoRegisters.DETECTED)
                confidence = self.read_byte(PicoRegisters.CONFIDENCE)

                if version is not None:
                    print(f"{position}: Firmware v{version}, {fps} fps, " +
                          f"Detected: {bool(detected)}, Confidence: {confidence}%")

                    # Read full thermal frame
                    frame = self.read_frame()
                    if frame is not None:
                        frames[position] = frame
                        zone_data[position] = {
                            "detected": bool(detected),
                            "confidence": confidence,
                            "fps": fps,
                        }
                else:
                    print(f"{position}: No Pico found on channel {channel}")

            except Exception as e:
                print(f"Error reading {position}: {e}")

        # Deselect all channels
        self.mux.deselect_all()

        return frames, zone_data

    def _generate_demo_frames(self):
        """Generate synthetic demo data for testing without hardware."""
        frames = {}
        zone_data = {}

        for i, position in enumerate(["FL", "FR", "RL", "RR"]):
            # Create gradient pattern
            x = np.linspace(0, 1, self.MLX_WIDTH)
            y = np.linspace(0, 1, self.MLX_HEIGHT)
            X, Y = np.meshgrid(x, y)

            # Different pattern for each tyre
            if position == "FL":
                frame = 25 + 10 * (X + Y)
            elif position == "FR":
                frame = 30 + 15 * np.sin(X * np.pi) * np.cos(Y * np.pi)
            elif position == "RL":
                frame = 28 + 8 * (X ** 2 + Y ** 2)
            else:  # RR
                frame = 35 + 12 * (1 - X) * Y

            frames[position] = frame
            zone_data[position] = {
                "detected": True,
                "confidence": 85 + i * 3,
                "fps": 11,
            }

        return frames, zone_data

    def create_visualization(self, frames, zone_data, save_path=None):
        """Create and display thermal heatmap visualization."""
        # Create figure with 2x2 grid
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle('Pico Thermal Camera Setup - Full Frame View',
                     fontsize=16, fontweight='bold')

        # Position mapping to subplot
        positions = [
            ("FL", 0, 0, "Front Left"),
            ("FR", 0, 1, "Front Right"),
            ("RL", 1, 0, "Rear Left"),
            ("RR", 1, 1, "Rear Right"),
        ]

        for position, row, col, title in positions:
            ax = axes[row, col]

            if position in frames:
                frame = frames[position]
                info = zone_data.get(position, {})

                # Calculate temperature range
                vmin = np.floor(np.min(frame))
                vmax = np.ceil(np.max(frame))

                # Plot heatmap
                im = ax.imshow(frame, cmap='hot', aspect='auto',
                              vmin=vmin, vmax=vmax, interpolation='nearest')

                # Add colorbar
                cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
                cbar.set_label('Temperature (°C)', rotation=270, labelpad=15)

                # Add border around detected tyre region
                if info.get('detected'):
                    # Add green border for detected tyre
                    rect = Rectangle((0, 0), self.MLX_WIDTH-1, self.MLX_HEIGHT-1,
                                   linewidth=3, edgecolor='lime', facecolor='none')
                    ax.add_patch(rect)

                # Add title with info
                detected_str = "✓ Detected" if info.get('detected') else "✗ Not Detected"
                conf_str = f"{info.get('confidence', 0)}%"
                fps_str = f"{info.get('fps', 0)} fps"

                title_text = f"{title}\n{detected_str} | Conf: {conf_str} | {fps_str}"
                ax.set_title(title_text, fontsize=12, fontweight='bold')

                # Add temperature stats
                stats_text = (f"Min: {np.min(frame):.1f}°C\n"
                            f"Max: {np.max(frame):.1f}°C\n"
                            f"Avg: {np.mean(frame):.1f}°C")
                ax.text(0.02, 0.98, stats_text,
                       transform=ax.transAxes,
                       fontsize=9,
                       verticalalignment='top',
                       bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

            else:
                # No data for this position
                ax.text(0.5, 0.5, f'{title}\nNo Data',
                       ha='center', va='center', fontsize=14,
                       transform=ax.transAxes)
                ax.set_facecolor('#f0f0f0')

            # Set axis labels
            ax.set_xlabel('Column (32 pixels)')
            ax.set_ylabel('Row (24 pixels)')
            ax.grid(True, alpha=0.3)

        plt.tight_layout()

        # Save if requested
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"Saved visualization to {save_path}")

        plt.show()

    def live_view(self, interval_ms=500):
        """Create live updating view of thermal data."""
        if not I2C_AVAILABLE:
            print("Live view not available in demo mode")
            return

        # Create figure
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle('Pico Thermal Camera - Live View (Press Ctrl+C to stop)',
                     fontsize=16, fontweight='bold')

        # Initialize plots
        positions = [
            ("FL", 0, 0, "Front Left"),
            ("FR", 0, 1, "Front Right"),
            ("RL", 1, 0, "Rear Left"),
            ("RR", 1, 1, "Rear Right"),
        ]

        images = {}
        colorbars = {}

        for position, row, col, title in positions:
            ax = axes[row, col]
            ax.set_title(title, fontsize=12, fontweight='bold')
            ax.set_xlabel('Column (32 pixels)')
            ax.set_ylabel('Row (24 pixels)')
            ax.grid(True, alpha=0.3)

            # Initialize with zeros
            frame = np.zeros((self.MLX_HEIGHT, self.MLX_WIDTH))
            im = ax.imshow(frame, cmap='hot', aspect='auto',
                          vmin=20, vmax=50, interpolation='nearest')
            images[position] = im

            # Add colorbar
            cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_label('Temperature (°C)', rotation=270, labelpad=15)
            colorbars[position] = cbar

        def update(frame_num):
            """Update function for animation."""
            frames, zone_data = self.read_all_frames()

            for position, row, col, title in positions:
                if position in frames:
                    frame = frames[position]
                    info = zone_data.get(position, {})

                    # Update image data
                    images[position].set_data(frame)

                    # Update colorbar limits
                    vmin = np.floor(np.min(frame))
                    vmax = np.ceil(np.max(frame))
                    images[position].set_clim(vmin, vmax)

                    # Update title with info
                    detected_str = "✓" if info.get('detected') else "✗"
                    conf_str = f"{info.get('confidence', 0)}%"
                    fps_str = f"{info.get('fps', 0)} fps"

                    title_text = f"{title} {detected_str} | {conf_str} | {fps_str}"
                    axes[row, col].set_title(title_text, fontsize=12, fontweight='bold')

            return list(images.values())

        # Create animation
        anim = animation.FuncAnimation(fig, update, interval=interval_ms,
                                      blit=False, cache_frame_data=False)

        plt.tight_layout()
        plt.show()


def main():
    parser = argparse.ArgumentParser(
        description="Pico Thermal Setup - Visualize thermal data from Pico I2C slaves"
    )
    parser.add_argument(
        "--live", "-l",
        action="store_true",
        help="Live updating view (press Ctrl+C to stop)"
    )
    parser.add_argument(
        "--save", "-s",
        metavar="PATH",
        help="Save snapshot to file (e.g., thermal_snapshot.png)"
    )
    parser.add_argument(
        "--interval", "-i",
        type=int,
        default=500,
        help="Update interval in milliseconds for live view (default: 500)"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Pico Thermal Camera Setup Tool")
    print("=" * 60)

    # Create visualizer
    viz = PicoThermalVisualizer()

    if args.live:
        # Live updating view
        print("\nStarting live view (press Ctrl+C to stop)...")
        try:
            viz.live_view(interval_ms=args.interval)
        except KeyboardInterrupt:
            print("\nStopped by user")

    else:
        # Single snapshot
        print("\nReading thermal frames from all Picos...")
        frames, zone_data = viz.read_all_frames()

        if not frames:
            print("\nERROR: No thermal data received from any Pico!")
            print("Check:")
            print("  1. Picos are powered and running firmware")
            print("  2. I2C connections (GP26=SDA, GP27=SCL)")
            print("  3. I2C multiplexer is connected and powered")
            return 1

        print(f"\nReceived data from {len(frames)} Pico(s)")

        # Generate filename if saving
        save_path = args.save
        if save_path == True or save_path == "":
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = f"thermal_snapshot_{timestamp}.png"

        # Create visualization
        viz.create_visualization(frames, zone_data, save_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
