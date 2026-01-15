"""
Hybrid corner detection combining ASC detection with Kasa radius fitting.

Uses:
- ASC algorithm for corner detection (curvature-based, proven accurate)
- Kasa's least-squares circle fitting for more accurate radius measurement

This gives:
- Reliable corner detection including gentle sweeps (from ASC)
- More accurate radius values (from Kasa fitting vs 3-point curvature)
"""

import math
from typing import List, Tuple
from dataclasses import dataclass
import numpy as np
from lap_timing.data.track_loader import Track, TrackPoint
from lap_timing.analysis.asc_corner_detector import ASCCornerDetector


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
    min_radius: float        # From curvature analysis (tightest point)
    avg_radius: float        # From Kasa fitting (average radius)
    fitted_radius: float     # From Kasa fitting
    fitting_error: float     # Kasa fit RMS error
    total_angle: float
    direction: str
    is_chicane: bool = False  # True if this is a merged chicane


class HybridCornerDetector:
    """
    Hybrid corner detector: ASC detection + Kasa radius fitting.

    Uses ASC's proven curvature-based detection to find corners,
    then applies Kasa circle fitting to get more accurate radius values.
    """

    def __init__(
        self,
        # ASC parameters (detection)
        curvature_peak_threshold: float = 0.005,
        min_cut_distance: float = 15.0,
        straight_fill_distance: float = 100.0,
        min_corner_radius: float = 100.0,
        min_corner_angle: float = 15.0,
        merge_same_direction: bool = True,
        # Chicane detection parameters
        merge_chicanes: bool = True,
        max_chicane_gap: float = 30.0,
        max_chicane_length: float = 200.0
    ):
        """
        Initialise hybrid detector.

        Args:
            curvature_peak_threshold: Curvature threshold for peak detection
            min_cut_distance: Minimum distance between cuts
            straight_fill_distance: Maximum gap to fill with cuts
            min_corner_radius: Maximum radius to classify as corner
            min_corner_angle: Minimum angle to classify as corner
            merge_same_direction: Merge consecutive same-direction corners
            merge_chicanes: Merge consecutive opposite-direction corners into chicanes
            max_chicane_gap: Maximum gap between corners to merge as chicane (meters)
            max_chicane_length: Maximum total length of merged chicane (meters)
        """
        # Chicane parameters
        self.merge_chicanes = merge_chicanes
        self.max_chicane_gap = max_chicane_gap
        self.max_chicane_length = max_chicane_length

        # Create underlying ASC detector
        self.asc = ASCCornerDetector(
            curvature_peak_threshold=curvature_peak_threshold,
            min_cut_distance=min_cut_distance,
            straight_fill_distance=straight_fill_distance,
            min_corner_radius=min_corner_radius,
            min_corner_angle=min_corner_angle,
            merge_same_direction=merge_same_direction
        )

    def detect_corners(self, track: Track) -> List[Corner]:
        """
        Detect corners using ASC algorithm with Kasa radius refinement.

        Args:
            track: Track with centerline

        Returns:
            List of detected corners with Kasa-fitted radii
        """
        # Use ASC to detect corners
        asc_corners = self.asc.detect_corners(track)

        if not asc_corners:
            return []

        # Convert to local coordinates for Kasa fitting
        coords = self._to_local_coords(track.centerline)

        # Convert ASC corners to hybrid corners with Kasa radii
        corners = []
        for c in asc_corners:
            # Kasa fit for this corner's points
            x = coords[c.entry_index:c.exit_index + 1, 0]
            y = coords[c.entry_index:c.exit_index + 1, 1]
            _, _, fitted_radius, fitting_error = self._kasa_fit(x, y)

            corner = Corner(
                id=c.id,
                name=c.name,
                entry_distance=c.entry_distance,
                apex_distance=c.apex_distance,
                exit_distance=c.exit_distance,
                entry_index=c.entry_index,
                apex_index=c.apex_index,
                exit_index=c.exit_index,
                min_radius=c.min_radius,        # From ASC (curvature-based)
                avg_radius=fitted_radius,       # From Kasa fitting
                fitted_radius=fitted_radius,    # From Kasa fitting
                fitting_error=fitting_error,
                total_angle=c.total_angle,
                direction=c.direction,
                is_chicane=False
            )
            corners.append(corner)

        # Merge chicanes if enabled
        if self.merge_chicanes:
            corners = self._merge_chicanes(corners, coords)

        return corners

    def _to_local_coords(self, centerline: List[TrackPoint]) -> np.ndarray:
        """Convert lat/lon to local x/y in meters."""
        if not centerline:
            return np.array([])

        ref_lat = centerline[0].lat
        ref_lon = centerline[0].lon

        coords = np.zeros((len(centerline), 2))
        for i, pt in enumerate(centerline):
            coords[i, 0] = (pt.lon - ref_lon) * 111320 * math.cos(math.radians(ref_lat))
            coords[i, 1] = (pt.lat - ref_lat) * 110540

        return coords

    def _kasa_fit(self, x: np.ndarray, y: np.ndarray) -> Tuple[float, float, float, float]:
        """
        Kasa's algebraic circle fitting.

        Fits a circle to 2D points by minimizing algebraic distance.

        Args:
            x: Array of x coordinates
            y: Array of y coordinates

        Returns:
            (center_x, center_y, radius, rms_error)
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
            # Collinear points - infinite radius
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

    def _merge_chicanes(
        self,
        corners: List[Corner],
        coords: np.ndarray
    ) -> List[Corner]:
        """
        Merge consecutive opposite-direction corners into chicanes.

        A chicane is defined as:
        - Two consecutive corners with opposite directions (left-right or right-left)
        - Gap between them is less than max_chicane_gap
        - Total span is less than max_chicane_length

        Args:
            corners: List of detected corners
            coords: Local x/y coordinates for Kasa fitting

        Returns:
            List of corners with chicanes merged
        """
        if len(corners) < 2:
            return corners

        merged = []
        i = 0

        while i < len(corners):
            current = corners[i]

            # Check if we can merge with next corner as a chicane
            if i + 1 < len(corners):
                next_corner = corners[i + 1]

                # Check chicane conditions
                gap = next_corner.entry_distance - current.exit_distance
                total_length = next_corner.exit_distance - current.entry_distance
                opposite_directions = current.direction != next_corner.direction

                if (opposite_directions and
                    gap <= self.max_chicane_gap and
                    total_length <= self.max_chicane_length):

                    # Merge into chicane
                    # Use the tighter radius as min_radius
                    min_radius = min(current.min_radius, next_corner.min_radius)

                    # Kasa fit for combined chicane
                    x = coords[current.entry_index:next_corner.exit_index + 1, 0]
                    y = coords[current.entry_index:next_corner.exit_index + 1, 1]
                    _, _, fitted_radius, fitting_error = self._kasa_fit(x, y)

                    # Total angle is sum of both corners
                    total_angle = current.total_angle + next_corner.total_angle

                    # Apex is the tighter of the two
                    if current.min_radius <= next_corner.min_radius:
                        apex_distance = current.apex_distance
                        apex_index = current.apex_index
                    else:
                        apex_distance = next_corner.apex_distance
                        apex_index = next_corner.apex_index

                    # Direction is the first corner's direction (entry direction)
                    direction = current.direction

                    chicane = Corner(
                        id=current.id,  # Keep first corner's ID
                        name=f"Corner {current.id} (Chicane)",
                        entry_distance=current.entry_distance,
                        apex_distance=apex_distance,
                        exit_distance=next_corner.exit_distance,
                        entry_index=current.entry_index,
                        apex_index=apex_index,
                        exit_index=next_corner.exit_index,
                        min_radius=min_radius,
                        avg_radius=fitted_radius,
                        fitted_radius=fitted_radius,
                        fitting_error=fitting_error,
                        total_angle=total_angle,
                        direction=direction,
                        is_chicane=True
                    )
                    merged.append(chicane)
                    i += 2  # Skip both corners
                    continue

            # No merge - add current corner as-is
            merged.append(current)
            i += 1

        # Renumber corners sequentially
        for idx, corner in enumerate(merged, 1):
            if corner.is_chicane:
                corner.name = f"Corner {idx} (Chicane)"
            else:
                corner.name = f"Corner {idx}"
            corner.id = idx

        return merged
