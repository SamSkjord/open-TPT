"""
CurveFinder corner detection using iterative circular fitting.

Based on Ai & Tsai (2014) - "Automatic Horizontal Curve Identification
and Measurement Method Using GPS Data"

Uses Kasa's least-squares circle fitting to find segments with consistent
radii, then classifies them as corners or straights.
"""

import math
from typing import List, Tuple, Optional
from dataclasses import dataclass
import numpy as np
from lap_timing.data.track_loader import Track, TrackPoint


@dataclass
class Corner:
    """Detected corner on track."""
    id: int
    name: str
    entry_distance: float
    apex_distance: float
    exit_distance: float
    entry_index: int
    apex_index: int
    exit_index: int
    min_radius: float
    avg_radius: float
    total_angle: float
    direction: str


@dataclass
class Segment:
    """A segment with consistent radius."""
    start_index: int
    end_index: int
    start_distance: float
    end_distance: float
    radius: float           # Fitted radius (inf for straights)
    center_x: float         # Circle center
    center_y: float
    fitting_error: float    # RMS error of fit
    direction: Optional[str]  # "left", "right", or None
    segment_type: str       # "corner" or "straight"


class KasaCircleFitter:
    """
    Kasa's algebraic circle fitting method.

    Fits a circle to 2D points by minimizing the algebraic distance:
    F = sum[(x-a)² + (y-b)² - R²]²

    This is faster and simpler than geometric fitting, though slightly
    biased for small arcs. Good enough for GPS data.
    """

    @staticmethod
    def fit(x: np.ndarray, y: np.ndarray) -> Tuple[float, float, float, float]:
        """
        Fit circle to points using Kasa's method.

        Args:
            x: Array of x coordinates
            y: Array of y coordinates

        Returns:
            (center_x, center_y, radius, rms_error)
            Returns (nan, nan, inf, inf) if fitting fails (collinear points)
        """
        n = len(x)
        if n < 3:
            return (float('nan'), float('nan'), float('inf'), float('inf'))

        # Center the data for numerical stability
        x_mean = np.mean(x)
        y_mean = np.mean(y)
        u = x - x_mean
        v = y - y_mean

        # Build the system of equations
        # [sum(u²)  sum(uv)] [A]   [sum(u³ + uv²)]
        # [sum(uv)  sum(v²)] [B] = [sum(v³ + vu²)]

        Suu = np.sum(u * u)
        Suv = np.sum(u * v)
        Svv = np.sum(v * v)
        Suuu = np.sum(u * u * u)
        Svvv = np.sum(v * v * v)
        Suvv = np.sum(u * v * v)
        Svuu = np.sum(v * u * u)

        # Solve 2x2 linear system
        det = Suu * Svv - Suv * Suv

        if abs(det) < 1e-10:
            # Points are collinear - treat as straight line (infinite radius)
            return (float('nan'), float('nan'), float('inf'), 0.0)

        # Circle center in centered coordinates
        uc = (Svv * (Suuu + Suvv) - Suv * (Svvv + Svuu)) / (2 * det)
        vc = (Suu * (Svvv + Svuu) - Suv * (Suuu + Suvv)) / (2 * det)

        # Radius
        R = math.sqrt(uc * uc + vc * vc + (Suu + Svv) / n)

        # Transform back to original coordinates
        center_x = uc + x_mean
        center_y = vc + y_mean

        # Calculate RMS fitting error
        distances = np.sqrt((x - center_x)**2 + (y - center_y)**2)
        errors = distances - R
        rms_error = np.sqrt(np.mean(errors**2))

        return (center_x, center_y, R, rms_error)


class CurveFinderDetector:
    """
    Detect corners using iterative circular fitting (CurveFinder algorithm).

    Segments the track by fitting circles to groups of points and detecting
    where the fitting error increases significantly (segment boundaries).
    """

    def __init__(
        self,
        min_points: int = 5,              # Minimum points to start fitting
        max_points: int = 20,             # Maximum points in a segment (reduced for tighter segmentation)
        error_threshold: float = 1.0,     # Max RMS error (meters) before splitting
        error_increase_ratio: float = 1.5, # Split if error increases by this factor
        min_corner_radius: float = 100.0, # Max radius to be a corner (meters)
        min_corner_angle: float = 15.0,   # Min angle to be a corner (degrees)
        merge_same_direction: bool = True # Merge consecutive same-direction corners
    ):
        """
        Initialise CurveFinder detector.

        Args:
            min_points: Minimum points to attempt circle fitting
            max_points: Maximum points in a single segment
            error_threshold: Absolute RMS error threshold for splitting
            error_increase_ratio: Relative error increase that triggers split
            min_corner_radius: Maximum radius to classify as corner
            min_corner_angle: Minimum total angle to classify as corner
            merge_same_direction: Merge consecutive corners of same direction
        """
        self.min_points = min_points
        self.max_points = max_points
        self.error_threshold = error_threshold
        self.error_increase_ratio = error_increase_ratio
        self.min_corner_radius = min_corner_radius
        self.min_corner_angle = min_corner_angle
        self.merge_same_direction = merge_same_direction

        self.fitter = KasaCircleFitter()

    def detect_corners(self, track: Track) -> List[Corner]:
        """
        Detect all corners on the track.

        Args:
            track: Track with centerline

        Returns:
            List of detected corners
        """
        centerline = track.centerline

        if len(centerline) < self.min_points:
            return []

        # Convert to local coordinates (meters)
        coords = self._to_local_coords(centerline)

        # Segment the track using iterative fitting
        segments = self._segment_track(centerline, coords)

        # Optionally merge same-direction corners
        if self.merge_same_direction:
            segments = self._merge_segments(segments, centerline, coords)

        # Convert corner segments to Corner objects
        corners = self._segments_to_corners(segments, centerline, coords)

        return corners

    def get_segments(self, track: Track) -> List[Segment]:
        """Get all segments (for visualization/debugging)."""
        centerline = track.centerline

        if len(centerline) < self.min_points:
            return []

        coords = self._to_local_coords(centerline)
        return self._segment_track(centerline, coords)

    def _to_local_coords(self, centerline: List[TrackPoint]) -> np.ndarray:
        """Convert lat/lon to local x/y coordinates in meters."""
        if not centerline:
            return np.array([])

        ref_lat = centerline[0].lat
        ref_lon = centerline[0].lon

        coords = np.zeros((len(centerline), 2))
        for i, pt in enumerate(centerline):
            coords[i, 0] = (pt.lon - ref_lon) * 111320 * math.cos(math.radians(ref_lat))
            coords[i, 1] = (pt.lat - ref_lat) * 110540

        return coords

    def _segment_track(
        self,
        centerline: List[TrackPoint],
        coords: np.ndarray
    ) -> List[Segment]:
        """
        Segment the track using iterative circular fitting.

        Algorithm:
        1. Start with min_points
        2. Fit circle, record error
        3. Add points while error stays acceptable
        4. When error spikes, end segment and start new one
        """
        n = len(centerline)
        segments = []

        start_idx = 0

        while start_idx < n - self.min_points:
            # Find the best end point for this segment
            best_end_idx = start_idx + self.min_points - 1
            best_radius = float('inf')
            best_center = (0.0, 0.0)
            best_error = float('inf')
            prev_error = None

            for end_idx in range(start_idx + self.min_points - 1,
                                 min(start_idx + self.max_points, n)):
                # Fit circle to points [start_idx : end_idx + 1]
                x = coords[start_idx:end_idx + 1, 0]
                y = coords[start_idx:end_idx + 1, 1]

                cx, cy, radius, error = self.fitter.fit(x, y)

                # Check if we should stop extending this segment
                should_split = False

                if error > self.error_threshold:
                    should_split = True
                elif prev_error is not None and prev_error > 0:
                    if error > prev_error * self.error_increase_ratio:
                        should_split = True

                if should_split and end_idx > start_idx + self.min_points:
                    # Use the previous best fit
                    break

                # This is a valid extension
                best_end_idx = end_idx
                best_radius = radius
                best_center = (cx, cy)
                best_error = error
                prev_error = error

            # Create segment
            segment = self._create_segment(
                start_idx, best_end_idx, centerline, coords,
                best_radius, best_center, best_error
            )
            segments.append(segment)

            # Move to next segment (with 1 point overlap for continuity)
            start_idx = best_end_idx

        # Handle remaining points
        if start_idx < n - 1:
            x = coords[start_idx:, 0]
            y = coords[start_idx:, 1]
            cx, cy, radius, error = self.fitter.fit(x, y)
            segment = self._create_segment(
                start_idx, n - 1, centerline, coords,
                radius, (cx, cy), error
            )
            segments.append(segment)

        return segments

    def _create_segment(
        self,
        start_idx: int,
        end_idx: int,
        centerline: List[TrackPoint],
        coords: np.ndarray,
        radius: float,
        center: Tuple[float, float],
        error: float
    ) -> Segment:
        """Create a Segment object with classification."""
        # Calculate total angle
        total_angle = 0.0
        if radius < float('inf') and radius > 0:
            arc_length = centerline[end_idx].distance - centerline[start_idx].distance
            total_angle = math.degrees(arc_length / radius)

        # Determine direction using signed curvature (same method as ASC)
        # Calculate average signed curvature across the segment
        direction = None
        if end_idx - start_idx >= 2:
            total_signed_curvature = 0.0
            count = 0
            for i in range(start_idx + 1, end_idx):
                # 3-point curvature calculation
                x1, y1 = coords[i - 1]
                x2, y2 = coords[i]
                x3, y3 = coords[i + 1]

                # Triangle area
                area = abs((x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2)) / 2.0)

                if area > 1e-6:
                    # Side lengths
                    a = math.sqrt((x2 - x3)**2 + (y2 - y3)**2)
                    b = math.sqrt((x1 - x3)**2 + (y1 - y3)**2)
                    c = math.sqrt((x1 - x2)**2 + (y1 - y2)**2)

                    if a * b * c > 1e-6:
                        radius_local = (a * b * c) / (4.0 * area)
                        if radius_local > 0.1:
                            # Sign from cross product (same as ASC)
                            cross = (x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)
                            sign = 1.0 if cross > 0 else -1.0
                            total_signed_curvature += sign / radius_local
                            count += 1

            if count > 0:
                avg_signed_curvature = total_signed_curvature / count
                if avg_signed_curvature > 0.001:
                    direction = "left"
                elif avg_signed_curvature < -0.001:
                    direction = "right"

        # Classify as corner or straight
        if (radius <= self.min_corner_radius and
            total_angle >= self.min_corner_angle):
            segment_type = "corner"
        else:
            segment_type = "straight"

        return Segment(
            start_index=start_idx,
            end_index=end_idx,
            start_distance=centerline[start_idx].distance,
            end_distance=centerline[end_idx].distance,
            radius=radius,
            center_x=center[0],
            center_y=center[1],
            fitting_error=error,
            direction=direction,
            segment_type=segment_type
        )

    def _merge_segments(
        self,
        segments: List[Segment],
        centerline: List[TrackPoint],
        coords: np.ndarray,
        max_corner_span: float = 150.0
    ) -> List[Segment]:
        """Merge consecutive corner segments of the same direction."""
        if len(segments) <= 1:
            return segments

        merged = []
        i = 0

        while i < len(segments):
            current = segments[i]

            if current.segment_type != "corner":
                merged.append(current)
                i += 1
                continue

            # Try to merge with following same-direction corners
            merge_end_idx = current.end_index
            j = i + 1

            while j < len(segments):
                next_seg = segments[j]

                if next_seg.segment_type == "corner":
                    if next_seg.direction == current.direction:
                        potential_span = (centerline[next_seg.end_index].distance -
                                         centerline[current.start_index].distance)
                        if potential_span <= max_corner_span:
                            merge_end_idx = next_seg.end_index
                            j += 1
                            continue
                    break
                elif next_seg.segment_type == "straight":
                    # Only absorb short straights
                    straight_len = next_seg.end_distance - next_seg.start_distance
                    if straight_len <= 30.0 and j + 1 < len(segments):
                        following = segments[j + 1]
                        if (following.segment_type == "corner" and
                            following.direction == current.direction):
                            j += 1
                            continue
                    break
                else:
                    break

            # Create merged segment if needed
            if j > i + 1:
                # Re-fit circle to merged region
                x = coords[current.start_index:merge_end_idx + 1, 0]
                y = coords[current.start_index:merge_end_idx + 1, 1]
                cx, cy, radius, error = self.fitter.fit(x, y)

                merged_seg = self._create_segment(
                    current.start_index, merge_end_idx,
                    centerline, coords, radius, (cx, cy), error
                )
                # Force corner type
                merged_seg.segment_type = "corner"
                merged_seg.direction = current.direction
                merged.append(merged_seg)
            else:
                merged.append(current)

            i = j

        return merged

    def _segments_to_corners(
        self,
        segments: List[Segment],
        centerline: List[TrackPoint],
        coords: np.ndarray
    ) -> List[Corner]:
        """Convert corner segments to Corner objects."""
        corners = []
        corner_id = 1

        for seg in segments:
            if seg.segment_type != "corner":
                continue

            # Find apex (point closest to fitted circle center, or midpoint)
            if not math.isnan(seg.center_x):
                min_dist = float('inf')
                apex_idx = (seg.start_index + seg.end_index) // 2
                for i in range(seg.start_index, seg.end_index + 1):
                    dist = math.sqrt(
                        (coords[i, 0] - seg.center_x)**2 +
                        (coords[i, 1] - seg.center_y)**2
                    )
                    # Apex is where we're closest to center (inside the curve)
                    if dist < min_dist:
                        min_dist = dist
                        apex_idx = i
            else:
                apex_idx = (seg.start_index + seg.end_index) // 2

            # Calculate total angle
            arc_length = seg.end_distance - seg.start_distance
            if seg.radius > 0 and seg.radius < float('inf'):
                total_angle = math.degrees(arc_length / seg.radius)
            else:
                total_angle = 0.0

            corner = Corner(
                id=corner_id,
                name=f"Corner {corner_id}",
                entry_distance=seg.start_distance,
                apex_distance=centerline[apex_idx].distance,
                exit_distance=seg.end_distance,
                entry_index=seg.start_index,
                apex_index=apex_idx,
                exit_index=seg.end_index,
                min_radius=seg.radius,
                avg_radius=seg.radius,  # Same for fitted circle
                total_angle=total_angle,
                direction=seg.direction or "left"
            )
            corners.append(corner)
            corner_id += 1

        return corners
