"""
System menu mixin for openTPT.
GPS Status, IMU Calibration, Radar, and System Status.
"""

import logging
import subprocess

logger = logging.getLogger('openTPT.menu.system')


class SystemMenuMixin:
    """Mixin providing GPS, IMU, Radar, and System Status menu functionality."""

    # Shutdown/Reboot methods

    def _shutdown(self) -> str:
        """Shutdown the system."""
        try:
            subprocess.run(
                ["sudo", "shutdown", "now"],
                timeout=10,
                check=False,
                capture_output=True
            )
            return "Shutting down..."
        except subprocess.TimeoutExpired:
            return "Shutdown command timed out"
        except (OSError, subprocess.SubprocessError) as e:
            return f"Shutdown failed: {e}"

    def _reboot(self) -> str:
        """Reboot the system."""
        try:
            subprocess.run(
                ["sudo", "reboot"],
                timeout=10,
                check=False,
                capture_output=True
            )
            return "Rebooting..."
        except subprocess.TimeoutExpired:
            return "Reboot command timed out"
        except (OSError, subprocess.SubprocessError) as e:
            return f"Reboot failed: {e}"

    # GPS Status methods

    def _get_gps_fix_label(self) -> str:
        """Get GPS fix status label."""
        if not self.gps_handler:
            return "Fix: No GPS"
        snapshot = self.gps_handler.get_snapshot()
        if not snapshot or not snapshot.data:
            return "Fix: No data"
        has_fix = snapshot.data.get("has_fix", False)
        if has_fix:
            return "Fix: Yes"
        return "Fix: No (searching)"

    def _get_gps_satellites_label(self) -> str:
        """Get GPS satellite count label."""
        if not self.gps_handler:
            return "Sats: --"
        snapshot = self.gps_handler.get_snapshot()
        if not snapshot or not snapshot.data:
            return "Sats: --"
        sats = snapshot.data.get("satellites", 0)
        return f"Sats: {sats}"

    def _get_gps_speed_label(self) -> str:
        """Get GPS speed label."""
        if not self.gps_handler:
            return "Speed: --"
        snapshot = self.gps_handler.get_snapshot()
        if not snapshot or not snapshot.data:
            return "Speed: --"
        if not snapshot.data.get("has_fix", False):
            return "Speed: -- (no fix)"
        speed = snapshot.data.get("speed_kmh", 0)
        return f"Speed: {speed:.1f} km/h"

    def _get_gps_position_label(self) -> str:
        """Get GPS position label."""
        if not self.gps_handler:
            return "Pos: --"
        snapshot = self.gps_handler.get_snapshot()
        if not snapshot or not snapshot.data:
            return "Pos: --"
        if not snapshot.data.get("has_fix", False):
            return "Pos: -- (no fix)"
        lat = snapshot.data.get("latitude", 0)
        lon = snapshot.data.get("longitude", 0)
        # Format with direction indicators
        lat_dir = "N" if lat >= 0 else "S"
        lon_dir = "E" if lon >= 0 else "W"
        return f"{abs(lat):.4f}{lat_dir} {abs(lon):.4f}{lon_dir}"

    def _get_gps_port_label(self) -> str:
        """Get GPS serial port label."""
        from config import GPS_SERIAL_PORT, GPS_BAUD_RATE, GPS_ENABLED

        if not GPS_ENABLED:
            return "Port: Disabled"
        return f"{GPS_SERIAL_PORT} @ {GPS_BAUD_RATE}"

    def _get_gps_update_rate_label(self) -> str:
        """Get GPS update rate label."""
        if not self.gps_handler:
            return "Rate: --"
        snapshot = self.gps_handler.get_snapshot()
        if not snapshot or not snapshot.data:
            return "Rate: --"
        rate = snapshot.data.get("update_rate", 0)
        return f"Rate: {rate:.1f} Hz"

    def _get_gps_antenna_label(self) -> str:
        """Get GPS antenna status label."""
        if not self.gps_handler:
            return "Antenna: --"
        snapshot = self.gps_handler.get_snapshot()
        if not snapshot or not snapshot.data:
            return "Antenna: --"
        status = snapshot.data.get("antenna_status", 0)
        status_labels = {
            0: "Antenna: Unknown",
            1: "Antenna: FAULT",
            2: "Antenna: Internal",
            3: "Antenna: External",
        }
        return status_labels.get(status, f"Antenna: {status}")

    # IMU Calibration methods

    def _get_imu_zero_label(self) -> str:
        """Get label for zero calibration step."""
        if self.imu_cal_step == "zero_done":
            return "1. Zero [OK]"
        return "1. Zero (level)"

    def _get_imu_accel_label(self) -> str:
        """Get label for acceleration calibration step."""
        if self.imu_cal_step == "accel_done":
            return "2. Accelerate [OK]"
        return "2. Accelerate"

    def _get_imu_turn_label(self) -> str:
        """Get label for turn calibration step."""
        if self.imu_cal_step == "turn_done":
            return "3. Turn Left [OK]"
        return "3. Turn Left"

    def _imu_calibrate_zero(self) -> str:
        """Step 1: Zero calibration - park on level ground."""
        if not self.imu_handler:
            return "No IMU available"
        result = self.imu_handler.calibrate_zero()
        self.imu_cal_step = "zero_done"
        return result

    def _imu_calibrate_accel(self) -> str:
        """Step 2: Detect longitudinal axis - accelerate gently."""
        if not self.imu_handler:
            return "No IMU available"
        if self.imu_cal_step != "zero_done":
            return "Do step 1 first"
        # Detect which axis changed most during acceleration
        result = self.imu_handler.calibrate_detect_axis()
        if "error" in result:
            return result["error"]
        # Acceleration = positive longitudinal
        axis_str = result["axis_str"]
        self.imu_handler.calibrate_set_longitudinal(axis_str)
        self.imu_cal_step = "accel_done"
        return f"Longitudinal: {axis_str}"

    def _imu_calibrate_turn(self) -> str:
        """Step 3: Detect lateral axis - turn left."""
        if not self.imu_handler:
            return "No IMU available"
        if self.imu_cal_step != "accel_done":
            return "Do step 2 first"
        # Detect which axis changed most during turn
        result = self.imu_handler.calibrate_detect_axis()
        if "error" in result:
            return result["error"]
        # Left turn = positive lateral (rightward force on driver)
        axis_str = result["axis_str"]
        self.imu_handler.calibrate_set_lateral(axis_str)
        self.imu_cal_step = "turn_done"
        return f"Lateral: {axis_str} - Done!"

    # Radar methods

    def _get_radar_enabled_label(self) -> str:
        """Get radar enabled status label."""
        if not self.radar_handler:
            return "Enabled: N/A"
        enabled = self.radar_handler.enabled
        return f"Enabled: {'Yes' if enabled else 'No'}"

    def _toggle_radar_enabled(self) -> str:
        """Toggle radar enabled state."""
        if not self.radar_handler:
            return "Radar not available"
        self.radar_handler.enabled = not self.radar_handler.enabled
        self._settings.set("radar.enabled", self.radar_handler.enabled)
        return f"Radar {'enabled' if self.radar_handler.enabled else 'disabled'}"

    def _get_radar_status_label(self) -> str:
        """Get radar operational status."""
        if not self.radar_handler:
            return "Status: No handler"
        if not self.radar_handler.enabled:
            return "Status: Disabled"
        if self.radar_handler.driver is None:
            return "Status: No driver"
        if self.radar_handler.running:
            return "Status: Running"
        return "Status: Stopped"

    def _get_radar_tracks_label(self) -> str:
        """Get current radar track count."""
        if not self.radar_handler:
            return "Tracks: --"
        if not self.radar_handler.enabled:
            return "Tracks: --"
        tracks = self.radar_handler.get_tracks()
        count = len(tracks) if tracks else 0
        return f"Tracks: {count}"

    def _get_radar_channel_label(self) -> str:
        """Get radar CAN channel."""
        if not self.radar_handler:
            return "Channel: --"
        return f"Channel: {self.radar_handler.radar_channel}"

    # System Status methods

    def _get_system_ip_label(self) -> str:
        """Get system IP address."""
        try:
            result = subprocess.run(
                ["hostname", "-I"], capture_output=True, text=True, timeout=5
            )
            ips = result.stdout.strip().split()
            if ips:
                return f"IP: {ips[0]}"
            return "IP: Not connected"
        except Exception as e:
            logger.debug("Failed to get IP address: %s", e)
            return "IP: Unknown"

    def _get_system_storage_label(self) -> str:
        """Get system storage info."""
        try:
            result = subprocess.run(
                ["df", "-h", "/"], capture_output=True, text=True, timeout=5
            )
            lines = result.stdout.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 4:
                    used = parts[2]
                    avail = parts[3]
                    return f"Storage: {used} / {avail} free"
            return "Storage: Unknown"
        except Exception as e:
            logger.debug("Failed to get storage info: %s", e)
            return "Storage: Unknown"

    def _get_system_uptime_label(self) -> str:
        """Get system uptime."""
        try:
            result = subprocess.run(
                ["uptime", "-p"], capture_output=True, text=True, timeout=5
            )
            uptime = result.stdout.strip()
            # Shorten "up X hours, Y minutes" to fit menu
            uptime = (
                uptime.replace("up ", "").replace(" hours", "h").replace(" hour", "h")
            )
            uptime = uptime.replace(" minutes", "m").replace(" minute", "m")
            uptime = uptime.replace(" days", "d").replace(" day", "d")
            uptime = uptime.replace(",", "")
            return f"Up: {uptime}"
        except Exception as e:
            logger.debug("Failed to get uptime: %s", e)
            return "Uptime: Unknown"

    def _get_sensor_status_label(self) -> str:
        """Get summary of active sensors."""
        active = []
        if self.tpms_handler:
            active.append("TPMS")
        if self.radar_handler and self.radar_handler.enabled:
            active.append("Radar")
        if self.imu_handler:
            active.append("IMU")
        if self.gps_handler:
            active.append("GPS")
        if self.neodriver_handler:
            active.append("LED")
        if active:
            return f"Active: {', '.join(active)}"
        return "Active: None"
