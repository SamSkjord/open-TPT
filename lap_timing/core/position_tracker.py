"""
Position tracker - maps GPS coordinates to track positions.

Uses KD-tree spatial indexing for O(log n) lookups.
"""

import logging
import math
from dataclasses import dataclass
from typing import Optional

from lap_timing.data.models import GPSPoint, TrackPosition
from lap_timing.data.track_loader import Track, TrackPoint
from lap_timing.utils.geometry import haversine_distance

logger = logging.getLogger('openTPT.lap_timing.position')

try:
    from scipy.spatial import cKDTree
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    logger.warning("scipy not available, falling back to linear search")


@dataclass
class NearestResult:
    """Result of nearest centerline point query."""
    index: int
    distance: float  # Meters from GPS point to centerline
    track_point: TrackPoint


class PositionTracker:
    """Maps GPS coordinates to track positions using KD-tree spatial index."""

    def __init__(self, track: Track):
        self.track = track
        self.centerline = track.centerline
        self.track_length = track.length

        # Build spatial index
        if HAS_SCIPY:
            self._build_kdtree()
        else:
            self.kdtree = None

    def _build_kdtree(self):
        """Build KD-tree spatial index of centerline points."""
        # Convert centerline to array of (lat, lon) for KD-tree
        coords = [(p.lat, p.lon) for p in self.centerline]
        self.kdtree = cKDTree(coords)

    def find_nearest_centerline_point(self, lat: float, lon: float) -> NearestResult:
        """
        Find nearest centerline point to GPS coordinate.

        Args:
            lat, lon: GPS coordinates

        Returns:
            NearestResult with index and distance
        """
        if HAS_SCIPY and self.kdtree:
            # Query KD-tree (fast: O(log n))
            # Note: This uses Euclidean distance on lat/lon, which is approximate
            # but sufficient for finding nearest point
            dist, idx = self.kdtree.query([lat, lon])

            # Calculate accurate distance using haversine
            nearest_point = self.centerline[idx]
            accurate_dist = haversine_distance(
                lat, lon,
                nearest_point.lat, nearest_point.lon
            )

            return NearestResult(
                index=idx,
                distance=accurate_dist,
                track_point=nearest_point
            )
        else:
            # Fallback: Linear search (slower: O(n))
            min_dist = float('inf')
            nearest_idx = 0

            for i, point in enumerate(self.centerline):
                dist = haversine_distance(lat, lon, point.lat, point.lon)
                if dist < min_dist:
                    min_dist = dist
                    nearest_idx = i

            return NearestResult(
                index=nearest_idx,
                distance=min_dist,
                track_point=self.centerline[nearest_idx]
            )

    def get_track_position(self, gps_point: GPSPoint) -> TrackPosition:
        """
        Convert GPS point to track position.

        Args:
            gps_point: GPS reading

        Returns:
            TrackPosition with distance along track and lateral offset
        """
        # Find nearest centerline point
        nearest = self.find_nearest_centerline_point(
            gps_point.lat,
            gps_point.lon
        )

        # Distance along track is the cumulative distance of nearest point
        distance_along_track = nearest.track_point.distance

        # Lateral offset (perpendicular distance from centerline)
        # Positive = right of centerline, negative = left
        lateral_offset = self._calculate_lateral_offset(
            gps_point.lat,
            gps_point.lon,
            nearest.index
        )

        # Progress fraction (0.0 to 1.0)
        progress_fraction = distance_along_track / self.track_length if self.track_length > 0 else 0.0

        return TrackPosition(
            distance_along_track=distance_along_track,
            lateral_offset=lateral_offset,
            segment_index=nearest.index,
            progress_fraction=progress_fraction,
            timestamp=gps_point.timestamp
        )

    def _calculate_lateral_offset(self, lat: float, lon: float, segment_idx: int) -> float:
        """
        Calculate lateral offset from centerline (signed distance).

        Uses cross product to determine which side of centerline vehicle is on.

        Args:
            lat, lon: GPS coordinates
            segment_idx: Index of nearest centerline segment

        Returns:
            Lateral offset in meters (+ve = right, -ve = left)
        """
        # Get centerline segment
        current_point = self.centerline[segment_idx]

        # Get next point for direction vector
        if segment_idx < len(self.centerline) - 1:
            next_point = self.centerline[segment_idx + 1]
        else:
            # Wrap around to start for last segment
            next_point = self.centerline[0]

        # Vector from current to next point (centerline direction)
        dx = next_point.lon - current_point.lon
        dy = next_point.lat - current_point.lat

        # Vector from current point to GPS point
        px = lon - current_point.lon
        py = lat - current_point.lat

        # Cross product determines side
        # Positive = right, negative = left
        cross = dx * py - dy * px

        # Calculate perpendicular distance
        distance = haversine_distance(lat, lon, current_point.lat, current_point.lon)

        # Apply sign based on side
        return distance if cross > 0 else -distance

    def get_interpolated_position(
        self,
        lat: float,
        lon: float,
        look_ahead: int = 2
    ) -> TrackPosition:
        """
        Get interpolated position with sub-meter precision.

        Interpolates between centerline segments for more accurate positioning.

        Args:
            lat, lon: GPS coordinates
            look_ahead: Number of segments to check ahead/behind

        Returns:
            TrackPosition with interpolated distance
        """
        # Find nearest point
        nearest = self.find_nearest_centerline_point(lat, lon)
        base_idx = nearest.index

        # Check surrounding segments for better interpolation
        best_dist = nearest.distance
        best_idx = base_idx
        best_progress = 0.0

        for offset in range(-look_ahead, look_ahead + 1):
            idx = (base_idx + offset) % len(self.centerline)
            next_idx = (idx + 1) % len(self.centerline)

            current = self.centerline[idx]
            next_point = self.centerline[next_idx]

            # Project GPS point onto this segment
            # Calculate projection factor (0.0 to 1.0 along segment)
            dx = next_point.lon - current.lon
            dy = next_point.lat - current.lat
            px = lon - current.lon
            py = lat - current.lat

            segment_length_sq = dx * dx + dy * dy
            if segment_length_sq < 1e-10:
                continue

            t = max(0.0, min(1.0, (px * dx + py * dy) / segment_length_sq))

            # Interpolated point on segment
            interp_lat = current.lat + t * dy
            interp_lon = current.lon + t * dx

            # Distance from GPS point to interpolated point
            dist = haversine_distance(lat, lon, interp_lat, interp_lon)

            if dist < best_dist:
                best_dist = dist
                best_idx = idx
                best_progress = t

        # Calculate interpolated distance along track
        current = self.centerline[best_idx]
        next_point = self.centerline[(best_idx + 1) % len(self.centerline)]

        segment_length = haversine_distance(
            current.lat, current.lon,
            next_point.lat, next_point.lon
        )

        interpolated_distance = current.distance + best_progress * segment_length

        # Lateral offset
        lateral_offset = self._calculate_lateral_offset(lat, lon, best_idx)

        # Progress fraction
        progress_fraction = interpolated_distance / self.track_length if self.track_length > 0 else 0.0

        return TrackPosition(
            distance_along_track=interpolated_distance,
            lateral_offset=lateral_offset,
            segment_index=best_idx,
            progress_fraction=progress_fraction,
            timestamp=0.0  # Will be set by caller
        )
