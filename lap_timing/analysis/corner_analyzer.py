"""
Corner speed analysis - track and compare speeds through corners.

Matches GPS points to corners and tracks minimum speed through each corner,
comparing against historical bests. Calculates lateral and longitudinal G-forces.
"""

import math
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
from lap_timing.data.models import GPSPoint, TrackPosition, Lap
from lap_timing.analysis.corner_detector import Corner

# Gravity constant for G-force calculations
GRAVITY = 9.81  # m/s²


def normalize_heading_delta(h1: float, h2: float) -> float:
    """
    Calculate heading change from h1 to h2, handling 0°/360° wraparound.

    Args:
        h1: Initial heading (degrees, 0-360)
        h2: Final heading (degrees, 0-360)

    Returns:
        Heading change in degrees (-180 to +180)
        Positive = clockwise (turning right)
        Negative = counter-clockwise (turning left)
    """
    delta = h2 - h1
    # Normalize to -180 to +180 range
    while delta > 180:
        delta -= 360
    while delta < -180:
        delta += 360
    return delta


@dataclass
class CornerSpeedRecord:
    """Speed through a corner during a lap."""
    corner_id: int
    lap_number: int
    min_speed: float             # Minimum speed (m/s)
    min_speed_distance: float    # Where minimum occurred (meters from S/F)
    entry_speed: float           # Speed at corner entry
    exit_speed: float            # Speed at corner exit
    avg_speed: float             # Average speed through corner
    peak_lateral_g: float = 0.0  # Peak lateral G (calculated from speed and radius)
    peak_longitudinal_g: float = 0.0  # Peak longitudinal G (braking negative, accel positive)
    peak_yaw_rate: float = 0.0   # Peak yaw rate (deg/s, +ve = right, -ve = left)
    peak_yaw_acceleration: float = 0.0  # Peak yaw acceleration (deg/s²)
    timestamp: datetime = field(default_factory=datetime.now)
    lap_time: Optional[float] = None


class CornerAnalyzer:
    """Analyze and track speeds through corners."""

    def __init__(self, corners: List[Corner]):
        """
        Initialise corner analyzer.

        Args:
            corners: List of detected corners on track
        """
        self.corners = corners
        self.best_speeds: Dict[int, CornerSpeedRecord] = {}  # corner_id -> best record

    def analyze_lap(self, lap: Lap) -> List[CornerSpeedRecord]:
        """
        Analyze speeds through all corners for a lap.

        Args:
            lap: Completed lap with GPS points and positions

        Returns:
            List of corner speed records for this lap
        """
        records = []

        for corner in self.corners:
            record = self._analyze_corner(corner, lap)
            if record:
                records.append(record)

                # Update best if this is faster
                if corner.id not in self.best_speeds or \
                   record.min_speed > self.best_speeds[corner.id].min_speed:
                    self.best_speeds[corner.id] = record

        return records

    def _analyze_corner(self, corner: Corner, lap: Lap) -> Optional[CornerSpeedRecord]:
        """
        Analyze speed through a single corner.

        Args:
            corner: Corner definition
            lap: Lap data

        Returns:
            CornerSpeedRecord or None if no data for this corner
        """
        # Find GPS points within corner region
        corner_points = []
        entry_speed = None
        exit_speed = None

        for i, pos in enumerate(lap.positions):
            if pos.distance_along_track >= corner.entry_distance and \
               pos.distance_along_track <= corner.exit_distance:
                corner_points.append((pos, lap.gps_points[i]))

                # Record entry and exit speeds
                if entry_speed is None:
                    entry_speed = lap.gps_points[i].speed

                exit_speed = lap.gps_points[i].speed

        if not corner_points:
            return None

        # Find minimum speed and calculate G-forces
        min_speed = float('inf')
        min_speed_distance = 0.0
        speeds = []
        peak_lateral_g = 0.0
        peak_longitudinal_g = 0.0
        peak_yaw_rate = 0.0
        peak_yaw_acceleration = 0.0

        # Track yaw rates for acceleration calculation
        yaw_rates = []  # (timestamp, yaw_rate)

        for idx, (pos, gps) in enumerate(corner_points):
            speeds.append(gps.speed)
            if gps.speed < min_speed:
                min_speed = gps.speed
                min_speed_distance = pos.distance_along_track

            # Calculate lateral G: v² / (r * g)
            # Use corner's min_radius as approximation of turn radius
            if corner.min_radius > 0:
                lateral_g = (gps.speed ** 2) / (corner.min_radius * GRAVITY)
                peak_lateral_g = max(peak_lateral_g, lateral_g)

            # Calculate longitudinal G and yaw rate from previous point
            if idx > 0:
                prev_gps = corner_points[idx - 1][1]
                dt = gps.timestamp - prev_gps.timestamp
                if dt > 0:
                    # Longitudinal acceleration in m/s²
                    accel = (gps.speed - prev_gps.speed) / dt
                    longitudinal_g = accel / GRAVITY
                    # Track peak magnitude (negative for braking, positive for acceleration)
                    if abs(longitudinal_g) > abs(peak_longitudinal_g):
                        peak_longitudinal_g = longitudinal_g

                    # Calculate yaw rate (deg/s)
                    heading_delta = normalize_heading_delta(prev_gps.heading, gps.heading)
                    yaw_rate = heading_delta / dt
                    yaw_rates.append((gps.timestamp, yaw_rate))

                    # Track peak yaw rate (preserve sign for direction)
                    if abs(yaw_rate) > abs(peak_yaw_rate):
                        peak_yaw_rate = yaw_rate

        # Calculate yaw acceleration from yaw rate changes
        for i in range(1, len(yaw_rates)):
            t1, yr1 = yaw_rates[i - 1]
            t2, yr2 = yaw_rates[i]
            dt = t2 - t1
            if dt > 0:
                yaw_accel = (yr2 - yr1) / dt  # deg/s²
                if abs(yaw_accel) > abs(peak_yaw_acceleration):
                    peak_yaw_acceleration = yaw_accel

        # Calculate average speed
        avg_speed = sum(speeds) / len(speeds) if speeds else 0.0

        return CornerSpeedRecord(
            corner_id=corner.id,
            lap_number=lap.lap_number,
            min_speed=min_speed,
            min_speed_distance=min_speed_distance,
            entry_speed=entry_speed if entry_speed else 0.0,
            exit_speed=exit_speed if exit_speed else 0.0,
            avg_speed=avg_speed,
            peak_lateral_g=peak_lateral_g,
            peak_longitudinal_g=peak_longitudinal_g,
            peak_yaw_rate=peak_yaw_rate,
            peak_yaw_acceleration=peak_yaw_acceleration,
            lap_time=lap.duration
        )

    def get_corner_delta(self, corner_id: int, current_speed: float) -> Optional[float]:
        """
        Get delta vs best speed for a corner.

        Args:
            corner_id: Corner ID
            current_speed: Current minimum speed through corner (m/s)

        Returns:
            Delta in m/s (positive = faster than best, negative = slower)
            None if no best speed recorded
        """
        if corner_id not in self.best_speeds:
            return None

        best_speed = self.best_speeds[corner_id].min_speed
        return current_speed - best_speed

    def get_corner_summary(self, corner_id: int) -> Optional[Dict]:
        """
        Get summary information for a corner.

        Args:
            corner_id: Corner ID

        Returns:
            Dict with corner info and best speed, or None
        """
        corner = next((c for c in self.corners if c.id == corner_id), None)
        if not corner:
            return None

        best = self.best_speeds.get(corner_id)

        return {
            'corner': corner,
            'best_speed': best.min_speed if best else None,
            'best_lap': best.lap_number if best else None,
            'best_lap_time': best.lap_time if best else None
        }

    def get_all_corner_summaries(self) -> List[Dict]:
        """
        Get summaries for all corners.

        Returns:
            List of corner summary dicts
        """
        return [self.get_corner_summary(c.id) for c in self.corners]

    def compare_laps(self, lap1: Lap, lap2: Lap) -> Dict[int, Dict]:
        """
        Compare corner speeds between two laps.

        Args:
            lap1: First lap
            lap2: Second lap

        Returns:
            Dict mapping corner_id to comparison data
        """
        records1 = {r.corner_id: r for r in self.analyze_lap(lap1)}
        records2 = {r.corner_id: r for r in self.analyze_lap(lap2)}

        comparison = {}

        for corner_id in records1.keys():
            if corner_id in records2:
                r1 = records1[corner_id]
                r2 = records2[corner_id]

                comparison[corner_id] = {
                    'corner_name': next(c.name for c in self.corners if c.id == corner_id),
                    'lap1_min_speed': r1.min_speed,
                    'lap2_min_speed': r2.min_speed,
                    'delta_speed': r2.min_speed - r1.min_speed,  # m/s
                    'delta_kmh': (r2.min_speed - r1.min_speed) * 3.6,  # km/h
                }

        return comparison
