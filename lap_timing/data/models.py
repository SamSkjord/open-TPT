"""
Core data structures for lap timing system.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from datetime import datetime


@dataclass
class GPSPoint:
    """Single 10Hz GPS reading."""
    timestamp: float          # Unix timestamp (ms precision)
    lat: float               # Decimal degrees
    lon: float               # Decimal degrees
    altitude: float = 0.0    # Meters
    speed: float = 0.0       # m/s
    heading: float = 0.0     # Degrees
    accuracy: float = 5.0    # GPS accuracy estimate (meters)


@dataclass
class TrackPosition:
    """Vehicle position relative to track reference line."""
    distance_along_track: float  # Meters from S/F line (0 to track_length)
    lateral_offset: float        # Meters from centerline (+ve = right)
    segment_index: int           # Index of nearest centerline segment
    progress_fraction: float     # 0.0 to 1.0 (lap completion)
    timestamp: float             # When this position was calculated


@dataclass
class StartFinishLine:
    """S/F line definition."""
    point1: Tuple[float, float]  # (lat, lon) - one end
    point2: Tuple[float, float]  # (lat, lon) - other end
    center: Tuple[float, float]  # Midpoint
    heading: float               # Perpendicular to track direction
    width: float                 # Line width in meters


@dataclass
class Lap:
    """Completed lap data."""
    lap_number: int
    start_time: float         # Unix timestamp
    end_time: float           # Unix timestamp
    duration: float           # Seconds (high precision)
    gps_points: List[GPSPoint] = field(default_factory=list)
    positions: List[TrackPosition] = field(default_factory=list)
    is_valid: bool = True
    max_speed: float = 0.0
    avg_speed: float = 0.0


@dataclass
class Delta:
    """Real-time delta information."""
    position: TrackPosition
    time_delta: float        # Seconds (+ve = slower, -ve = faster)
    distance_delta: float    # Meters ahead/behind
    reference_lap: int       # Which lap we're comparing to
    predicted_lap_time: float # Estimated final time


@dataclass
class Corner:
    """Detected corner on track."""
    id: int                          # Unique corner identifier
    name: str                        # "Corner 1", etc.
    entry_distance: float            # Meters from S/F
    apex_distance: float             # Meters from S/F
    exit_distance: float             # Meters from S/F
    min_radius: float                # Minimum radius in meters
    avg_radius: float                # Average radius
    angle: float                     # Total angle turned (degrees)
    direction: str                   # "left" or "right"


@dataclass
class CornerSpeedRecord:
    """Speed through a corner during a lap."""
    corner_id: int
    min_speed: float                 # Minimum speed (m/s)
    min_speed_distance: float        # Where minimum occurred
    entry_speed: float               # Speed at entry
    exit_speed: float                # Speed at exit
    timestamp: datetime = field(default_factory=datetime.now)
    lap_time: Optional[float] = None
