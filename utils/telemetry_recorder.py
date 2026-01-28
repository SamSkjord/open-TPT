"""
Telemetry Recorder for openTPT.
Records sensor data to CSV files for later analysis.
"""

import csv
import logging
import os
import time
import threading
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger('openTPT.telemetry')


@dataclass
class TelemetryFrame:
    """A single frame of telemetry data."""
    timestamp: float

    # TPMS data (per tyre)
    tpms_fl_pressure: Optional[float] = None
    tpms_fl_temp: Optional[float] = None
    tpms_fr_pressure: Optional[float] = None
    tpms_fr_temp: Optional[float] = None
    tpms_rl_pressure: Optional[float] = None
    tpms_rl_temp: Optional[float] = None
    tpms_rr_pressure: Optional[float] = None
    tpms_rr_temp: Optional[float] = None

    # Tyre thermal data (3-zone temps)
    tyre_fl_inner: Optional[float] = None
    tyre_fl_centre: Optional[float] = None
    tyre_fl_outer: Optional[float] = None
    tyre_fr_inner: Optional[float] = None
    tyre_fr_centre: Optional[float] = None
    tyre_fr_outer: Optional[float] = None
    tyre_rl_inner: Optional[float] = None
    tyre_rl_centre: Optional[float] = None
    tyre_rl_outer: Optional[float] = None
    tyre_rr_inner: Optional[float] = None
    tyre_rr_centre: Optional[float] = None
    tyre_rr_outer: Optional[float] = None

    # Brake temps
    brake_fl: Optional[float] = None
    brake_fr: Optional[float] = None
    brake_rl: Optional[float] = None
    brake_rr: Optional[float] = None

    # IMU data
    accel_x: Optional[float] = None
    accel_y: Optional[float] = None
    accel_z: Optional[float] = None
    gyro_x: Optional[float] = None
    gyro_y: Optional[float] = None
    gyro_z: Optional[float] = None

    # OBD2 data
    obd_speed_kmh: Optional[float] = None
    engine_rpm: Optional[int] = None
    throttle_percent: Optional[float] = None
    coolant_temp_c: Optional[float] = None
    oil_temp_c: Optional[float] = None
    intake_temp_c: Optional[float] = None
    map_kpa: Optional[int] = None
    boost_kpa: Optional[int] = None
    maf_gs: Optional[float] = None
    battery_soc: Optional[float] = None
    brake_pressure_input_bar: Optional[float] = None
    brake_pressure_output_bar: Optional[float] = None

    # Fuel tracking data
    fuel_level_percent: Optional[float] = None
    fuel_rate_lph: Optional[float] = None
    fuel_consumption_lap_litres: Optional[float] = None

    # GPS data
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    gps_speed_kmh: Optional[float] = None
    gps_heading: Optional[float] = None

    # Lap timing data
    lap_number: Optional[int] = None
    lap_time: Optional[float] = None
    lap_delta: Optional[float] = None
    sector: Optional[int] = None
    sector_time: Optional[float] = None
    track_position: Optional[float] = None
    track_name: Optional[str] = None

    # Heart rate data
    heart_rate_bpm: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for CSV writing."""
        return {
            'timestamp': self.timestamp,
            'tpms_fl_pressure': self.tpms_fl_pressure,
            'tpms_fl_temp': self.tpms_fl_temp,
            'tpms_fr_pressure': self.tpms_fr_pressure,
            'tpms_fr_temp': self.tpms_fr_temp,
            'tpms_rl_pressure': self.tpms_rl_pressure,
            'tpms_rl_temp': self.tpms_rl_temp,
            'tpms_rr_pressure': self.tpms_rr_pressure,
            'tpms_rr_temp': self.tpms_rr_temp,
            'tyre_fl_inner': self.tyre_fl_inner,
            'tyre_fl_centre': self.tyre_fl_centre,
            'tyre_fl_outer': self.tyre_fl_outer,
            'tyre_fr_inner': self.tyre_fr_inner,
            'tyre_fr_centre': self.tyre_fr_centre,
            'tyre_fr_outer': self.tyre_fr_outer,
            'tyre_rl_inner': self.tyre_rl_inner,
            'tyre_rl_centre': self.tyre_rl_centre,
            'tyre_rl_outer': self.tyre_rl_outer,
            'tyre_rr_inner': self.tyre_rr_inner,
            'tyre_rr_centre': self.tyre_rr_centre,
            'tyre_rr_outer': self.tyre_rr_outer,
            'brake_fl': self.brake_fl,
            'brake_fr': self.brake_fr,
            'brake_rl': self.brake_rl,
            'brake_rr': self.brake_rr,
            'accel_x': self.accel_x,
            'accel_y': self.accel_y,
            'accel_z': self.accel_z,
            'gyro_x': self.gyro_x,
            'gyro_y': self.gyro_y,
            'gyro_z': self.gyro_z,
            'obd_speed_kmh': self.obd_speed_kmh,
            'engine_rpm': self.engine_rpm,
            'throttle_percent': self.throttle_percent,
            'coolant_temp_c': self.coolant_temp_c,
            'oil_temp_c': self.oil_temp_c,
            'intake_temp_c': self.intake_temp_c,
            'map_kpa': self.map_kpa,
            'boost_kpa': self.boost_kpa,
            'maf_gs': self.maf_gs,
            'battery_soc': self.battery_soc,
            'brake_pressure_input_bar': self.brake_pressure_input_bar,
            'brake_pressure_output_bar': self.brake_pressure_output_bar,
            'fuel_level_percent': self.fuel_level_percent,
            'fuel_rate_lph': self.fuel_rate_lph,
            'fuel_consumption_lap_litres': self.fuel_consumption_lap_litres,
            'gps_latitude': self.gps_latitude,
            'gps_longitude': self.gps_longitude,
            'gps_speed_kmh': self.gps_speed_kmh,
            'gps_heading': self.gps_heading,
            'lap_number': self.lap_number,
            'lap_time': self.lap_time,
            'lap_delta': self.lap_delta,
            'sector': self.sector,
            'sector_time': self.sector_time,
            'track_position': self.track_position,
            'track_name': self.track_name,
            'heart_rate_bpm': self.heart_rate_bpm,
        }


class TelemetryRecorder:
    """
    Records telemetry data to CSV files.

    Usage:
        recorder = TelemetryRecorder()
        recorder.start_recording()
        # ... in main loop ...
        recorder.record_frame(frame)
        # ... when done ...
        recorder.stop_recording()
        if user_wants_to_save:
            recorder.save()
        else:
            recorder.discard()
    """

    # Storage locations in order of preference
    USB_PATH = "/mnt/usb/telemetry"
    FALLBACK_PATH = "/home/pi/telemetry"

    def __init__(self, output_dir: Optional[str] = None):
        """
        Initialise the recorder.

        Args:
            output_dir: Directory to save telemetry files. If None, auto-selects
                        USB (/mnt/usb/telemetry) if mounted, else SD card fallback.
        """
        self.recording = False
        self.frames: List[TelemetryFrame] = []
        self.start_time: Optional[float] = None
        self.temp_filename: Optional[str] = None
        self.lock = threading.Lock()

        # Select output directory
        if output_dir:
            self.output_dir = output_dir
        else:
            self.output_dir = self._select_output_dir()

        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)
        logger.info("Telemetry recorder using: %s", self.output_dir)

    def _select_output_dir(self) -> str:
        """Select best available output directory (USB preferred, SD fallback)."""
        # Check if USB is mounted and writable
        usb_mount = "/mnt/usb"
        if os.path.ismount(usb_mount):
            try:
                # Test write access
                test_file = os.path.join(usb_mount, ".write_test")
                with open(test_file, 'w') as f:
                    f.write("test")
                os.remove(test_file)
                logger.info("USB storage available for telemetry")
                return self.USB_PATH
            except (IOError, OSError) as e:
                logger.warning("USB mounted but not writable: %s", e)

        logger.info("Using SD card fallback for telemetry")
        return self.FALLBACK_PATH

    def start_recording(self):
        """Start a new recording session."""
        with self.lock:
            self.recording = True
            self.frames = []
            self.start_time = time.time()
            # Generate temp filename based on start time
            dt = datetime.fromtimestamp(self.start_time)
            self.temp_filename = dt.strftime("telemetry_%Y%m%d_%H%M%S.csv")
            logger.info("Recording started: %s", self.temp_filename)

    def stop_recording(self):
        """Stop the current recording session."""
        with self.lock:
            self.recording = False
            duration = time.time() - self.start_time if self.start_time else 0
            logger.info("Recording stopped: %d frames, %.1fs", len(self.frames), duration)

    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self.recording

    def get_duration(self) -> float:
        """Get current recording duration in seconds."""
        if not self.start_time:
            return 0.0
        return time.time() - self.start_time

    def get_frame_count(self) -> int:
        """Get number of recorded frames."""
        return len(self.frames)

    def record_frame(self, frame: TelemetryFrame):
        """
        Record a single frame of telemetry data.

        Args:
            frame: TelemetryFrame with sensor data
        """
        if not self.recording:
            return

        with self.lock:
            self.frames.append(frame)

    def save(self) -> Optional[str]:
        """
        Save the recorded data to a CSV file.

        Returns:
            Path to saved file, or None if no data
        """
        with self.lock:
            if not self.frames:
                logger.warning("No frames to save")
                return None

            filepath = os.path.join(self.output_dir, self.temp_filename)

            try:
                with open(filepath, 'w', newline='', encoding='utf-8') as f:
                    # Get fieldnames from first frame
                    fieldnames = list(self.frames[0].to_dict().keys())
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()

                    for frame in self.frames:
                        writer.writerow(frame.to_dict())

                logger.info("Saved %d frames to %s", len(self.frames), filepath)
                self._clear()
                return filepath

            except (IOError, OSError, KeyError, TypeError) as e:
                logger.error("Error saving telemetry: %s", e)
                self._clear()  # Clear frames even on error to prevent stale data
                return None

    def discard(self):
        """Discard the current recording without saving."""
        with self.lock:
            frame_count = len(self.frames)
            self._clear()
            logger.info("Discarded %d frames", frame_count)

    def _clear(self):
        """Clear recording data."""
        self.frames = []
        self.start_time = None
        self.temp_filename = None
