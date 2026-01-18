"""
Core data structures for lap timing system.

Unit Conventions
----------------
All measurements in this module use SI units unless otherwise noted:

- Time: seconds (float, Unix timestamps with millisecond precision)
- Distance: metres
- Speed: metres per second (m/s)
- Angles: degrees (0-360 for headings, signed for corner angles)
- Coordinates: decimal degrees (WGS84)
- Fuel: litres or percentage (0-100)

Note: Some UI display code may convert to km/h or other units for display,
but all internal calculations and storage use these base units.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from datetime import datetime


@dataclass
class GPSPoint:
    """
    Single 10Hz GPS reading with position and motion data.

    Attributes:
        timestamp: Unix timestamp in seconds with millisecond precision.
        lat: Latitude in decimal degrees (WGS84, -90 to +90).
        lon: Longitude in decimal degrees (WGS84, -180 to +180).
        altitude: Altitude above sea level in metres.
        speed: Ground speed in metres per second (m/s).
        heading: Course over ground in degrees (0-360, 0=North, 90=East).
        accuracy: GPS horizontal accuracy estimate in metres. Lower is better,
            typically 2-5m for good fix, 10+ for poor conditions.
    """
    timestamp: float
    lat: float
    lon: float
    altitude: float = 0.0
    speed: float = 0.0
    heading: float = 0.0
    accuracy: float = 5.0


@dataclass
class TrackPosition:
    """
    Vehicle position relative to track reference line (centreline).

    Used for delta calculations and progress tracking during a lap.

    Attributes:
        distance_along_track: Distance in metres from S/F line along the
            centreline. Range: 0 to track_length.
        lateral_offset: Perpendicular distance in metres from centreline.
            Positive = right of line, negative = left of line.
        segment_index: Index of the nearest centreline segment (0-based).
        progress_fraction: Lap completion as fraction 0.0 to 1.0.
        timestamp: Unix timestamp in seconds when position was calculated.
    """
    distance_along_track: float
    lateral_offset: float
    segment_index: int
    progress_fraction: float
    timestamp: float


@dataclass
class StartFinishLine:
    """
    Start/Finish line definition for lap crossing detection.

    The S/F line is defined as a line segment perpendicular to the track
    direction. Lap crossings are detected when the vehicle path intersects
    this line segment.

    Attributes:
        point1: One end of line as (lat, lon) tuple in decimal degrees.
        point2: Other end of line as (lat, lon) tuple in decimal degrees.
        centre: Midpoint of line as (lat, lon) tuple in decimal degrees.
        heading: Direction perpendicular to track in degrees (0-360).
        width: Total line width in metres (distance from point1 to point2).
    """
    point1: Tuple[float, float]
    point2: Tuple[float, float]
    centre: Tuple[float, float]
    heading: float
    width: float


@dataclass
class Lap:
    """
    Completed lap data with timing, telemetry, and fuel information.

    Attributes:
        lap_number: Sequential lap number (1-based) within the session.
        start_time: Unix timestamp in seconds when lap started (S/F crossing).
        end_time: Unix timestamp in seconds when lap ended (next S/F crossing).
        duration: Lap time in seconds with high precision (millisecond accuracy).
        gps_points: List of GPS readings captured during the lap at 10Hz.
        positions: List of track positions computed from GPS data.
        is_valid: False if lap was invalidated (e.g., off-track, incomplete).
        max_speed: Maximum speed during lap in metres per second (m/s).
        avg_speed: Average speed during lap in metres per second (m/s).
        fuel_used_litres: Fuel consumed during lap in litres (if available).
        fuel_at_start_percent: Fuel tank level at lap start as percentage 0-100.
        fuel_at_end_percent: Fuel tank level at lap end as percentage 0-100.
    """
    lap_number: int
    start_time: float
    end_time: float
    duration: float
    gps_points: List[GPSPoint] = field(default_factory=list)
    positions: List[TrackPosition] = field(default_factory=list)
    is_valid: bool = True
    max_speed: float = 0.0
    avg_speed: float = 0.0
    fuel_used_litres: Optional[float] = None
    fuel_at_start_percent: Optional[float] = None
    fuel_at_end_percent: Optional[float] = None


@dataclass
class Delta:
    """
    Real-time delta information comparing current lap to reference.

    Provides live feedback on performance relative to a reference lap
    (typically best lap or previous lap).

    Attributes:
        position: Current track position for this delta calculation.
        time_delta: Time difference in seconds. Positive = slower than
            reference, negative = faster than reference.
        distance_delta: Distance ahead/behind in metres. Positive = ahead
            of reference position, negative = behind.
        reference_lap: Lap number of the reference lap being compared to.
        predicted_lap_time: Estimated final lap time in seconds based on
            current delta and remaining distance.
    """
    position: TrackPosition
    time_delta: float
    distance_delta: float
    reference_lap: int
    predicted_lap_time: float


@dataclass
class Corner:
    """
    Detected corner on track centreline.

    Corners are automatically detected from the track centreline geometry
    and used for corner-speed analysis.

    Attributes:
        id: Unique corner identifier (1-based, sequential around track).
        name: Display name, e.g., "Corner 1", "Hairpin", etc.
        entry_distance: Distance in metres from S/F line to corner entry.
        apex_distance: Distance in metres from S/F line to apex (tightest point).
        exit_distance: Distance in metres from S/F line to corner exit.
        min_radius: Minimum (tightest) radius in metres at the apex.
        avg_radius: Average radius in metres across the entire corner.
        angle: Total angle turned through corner in degrees (always positive).
        direction: Turn direction - "left" or "right".
    """
    id: int
    name: str
    entry_distance: float
    apex_distance: float
    exit_distance: float
    min_radius: float
    avg_radius: float
    angle: float
    direction: str


@dataclass
class CornerSpeedRecord:
    """
    Speed data through a corner during a specific lap.

    Records speed at key points through a corner for performance analysis
    and comparison between laps.

    Attributes:
        corner_id: ID of the corner this record belongs to.
        min_speed: Minimum speed in metres per second (m/s) reached in corner.
        min_speed_distance: Distance in metres from S/F where minimum occurred.
        entry_speed: Speed in metres per second (m/s) at corner entry point.
        exit_speed: Speed in metres per second (m/s) at corner exit point.
        timestamp: When this record was created.
        lap_time: Total lap time in seconds for the lap this record belongs to.
    """
    corner_id: int
    min_speed: float
    min_speed_distance: float
    entry_speed: float
    exit_speed: float
    timestamp: datetime = field(default_factory=datetime.now)
    lap_time: Optional[float] = None
