"""
Corner detection from track centerline using curvature analysis.

Identifies corners by calculating curvature at each point and finding
regions where curvature exceeds a threshold (tight turns).
"""

import math
from typing import List, Tuple
from dataclasses import dataclass
from lap_timing.data.track_loader import Track, TrackPoint
from lap_timing.utils.geometry import haversine_distance


@dataclass
class Corner:
    """Detected corner on track."""
    id: int
    name: str
    entry_distance: float      # Meters from S/F
    apex_distance: float        # Meters from S/F (max curvature point)
    exit_distance: float        # Meters from S/F
    entry_index: int            # Centerline point index
    apex_index: int             # Centerline point index
    exit_index: int             # Centerline point index
    min_radius: float           # Minimum radius in meters
    avg_radius: float           # Average radius through corner
    total_angle: float          # Total angle turned (degrees)
    direction: str              # "left" or "right"


class CornerDetector:
    """Detect corners from track centerline using curvature analysis."""

    def __init__(self, min_radius: float = 100.0, min_angle: float = 15.0,
                 edge_buffer: float = 30.0):
        """
        Initialise corner detector.

        Args:
            min_radius: Minimum radius to consider a corner (meters)
            min_angle: Minimum total angle to consider a corner (degrees)
            edge_buffer: Ignore corners within this distance from start/end (meters)
        """
        self.min_radius = min_radius
        self.min_angle = min_angle
        self.edge_buffer = edge_buffer

    def detect_corners(self, track: Track) -> List[Corner]:
        """
        Detect all corners on the track.

        Args:
            track: Track with centerline

        Returns:
            List of detected corners
        """
        centerline = track.centerline

        if len(centerline) < 5:
            return []

        # Calculate curvature at each point
        curvatures = self._calculate_curvatures(centerline)

        # Find regions where curvature exceeds threshold
        corner_regions = self._find_corner_regions(curvatures, centerline)

        # Split long regions at curvature minima (before merging)
        split_regions = self._split_long_regions(corner_regions, centerline, curvatures)

        # Merge close regions (chicanes) - but not if direction changes
        merged_regions = self._merge_close_regions(split_regions, centerline, curvatures)

        # Get track length for edge filtering
        track_length = centerline[-1].distance if centerline else 0.0

        # Detect if this is a loop track (first/last centerline points close together)
        # For loop tracks, don't filter corners near S/F - they're real corners
        is_loop_track = False
        if len(centerline) >= 2:
            first_pt = centerline[0]
            last_pt = centerline[-1]
            closure_distance = haversine_distance(
                first_pt.lat, first_pt.lon,
                last_pt.lat, last_pt.lon
            )
            # If first/last points within 50m, treat as loop track
            is_loop_track = closure_distance < 50.0

        # Create Corner objects
        corners = []
        corner_number = 1  # Sequential numbering
        for region in merged_regions:
            corner = self._create_corner(
                corner_number, region, centerline, curvatures,
                track_length, is_loop_track
            )
            if corner:
                corners.append(corner)
                corner_number += 1  # Only increment if corner was created

        # Sort corners by track distance and renumber sequentially
        corners.sort(key=lambda c: c.apex_distance)
        for i, corner in enumerate(corners):
            corner.id = i + 1
            corner.name = f"Corner {i + 1}"

        return corners

    def _calculate_curvatures(self, centerline: List[TrackPoint]) -> List[float]:
        """
        Calculate curvature at each centerline point.

        Curvature = 1/radius (positive = left turn, negative = right turn)

        Uses three-point circle fitting method.
        """
        curvatures = []

        for i in range(len(centerline)):
            # Use points before, at, and after current point
            i_prev = (i - 1) % len(centerline)
            i_curr = i
            i_next = (i + 1) % len(centerline)

            p1 = centerline[i_prev]
            p2 = centerline[i_curr]
            p3 = centerline[i_next]

            # Calculate curvature from three points
            curvature = self._calculate_curvature_from_points(p1, p2, p3)
            curvatures.append(curvature)

        return curvatures

    def _calculate_curvature_from_points(
        self,
        p1: TrackPoint,
        p2: TrackPoint,
        p3: TrackPoint
    ) -> float:
        """
        Calculate curvature from three points using circumcircle method.

        Returns curvature in 1/meters (signed: positive=left, negative=right)
        """
        # Convert to approximate meters (small scale approximation)
        # Use p2 as origin
        x1 = (p1.lon - p2.lon) * 111320 * math.cos(math.radians(p2.lat))
        y1 = (p1.lat - p2.lat) * 110540
        x2 = 0.0
        y2 = 0.0
        x3 = (p3.lon - p2.lon) * 111320 * math.cos(math.radians(p2.lat))
        y3 = (p3.lat - p2.lat) * 110540

        # Calculate circumcircle radius using cross product method
        # Area of triangle
        area = abs((x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2)) / 2.0)

        if area < 1e-6:
            return 0.0  # Points are collinear (straight line)

        # Side lengths
        a = math.sqrt((x2 - x3)**2 + (y2 - y3)**2)
        b = math.sqrt((x1 - x3)**2 + (y1 - y3)**2)
        c = math.sqrt((x1 - x2)**2 + (y1 - y2)**2)

        # Circumradius
        radius = (a * b * c) / (4.0 * area)

        if radius < 0.1:  # Avoid division by zero
            return 0.0

        # Determine sign (left vs right turn) using cross product
        cross = (x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)
        sign = 1.0 if cross > 0 else -1.0

        return sign / radius

    def _find_corner_regions(
        self,
        curvatures: List[float],
        centerline: List[TrackPoint]
    ) -> List[Tuple[int, int]]:
        """
        Find contiguous regions where curvature exceeds threshold.

        Args:
            curvatures: Curvature at each centerline point
            centerline: Track centerline points

        Returns list of (start_index, end_index) tuples.
        """
        threshold = 1.0 / self.min_radius
        regions = []
        in_corner = False
        start_idx = 0

        for i, curvature in enumerate(curvatures):
            if abs(curvature) > threshold:
                if not in_corner:
                    # Start of corner region
                    start_idx = i
                    in_corner = True
            else:
                if in_corner:
                    # End of corner region
                    end_idx = i - 1
                    # Filter out isolated single-point spikes (noise)
                    if start_idx == end_idx:
                        if not self._is_isolated_spike(start_idx, curvatures, threshold, centerline):
                            regions.append((start_idx, end_idx))
                    else:
                        regions.append((start_idx, end_idx))
                    in_corner = False

        # Handle wrap-around (corner at start/end of track)
        if in_corner:
            end_idx = len(curvatures) - 1
            if start_idx == end_idx:
                if not self._is_isolated_spike(start_idx, curvatures, threshold, centerline):
                    regions.append((start_idx, end_idx))
            else:
                regions.append((start_idx, end_idx))

        return regions

    def _is_isolated_spike(
        self,
        idx: int,
        curvatures: List[float],
        threshold: float,
        centerline: List[TrackPoint] = None,
        search_distance: float = 50.0
    ) -> bool:
        """
        Check if a single-point curvature spike is isolated (noise) vs part of a real corner.

        A spike is considered isolated (noise) if it has no nearby points with:
        1. Significant curvature magnitude, AND
        2. The SAME SIGN (same turn direction)

        Real corners have consistent turn direction. Noise spikes at straight sections
        often have random/alternating directions from GPS jitter.

        Args:
            idx: Index of the spike to check
            curvatures: Curvature at each centerline point
            threshold: Curvature threshold for a corner
            centerline: Track centerline (for distance-based search)
            search_distance: How far to search for neighboring elevated curvature (meters)
        """
        neighbor_threshold = threshold * 0.5  # Neighbors should have at least half the curvature
        spike_curvature = curvatures[idx]
        spike_sign = 1 if spike_curvature > 0 else -1

        if centerline is not None:
            # Distance-based search - look for same-sign elevated curvature within search_distance
            spike_distance = centerline[idx].distance

            for i, curv in enumerate(curvatures):
                if i == idx:
                    continue
                point_distance = centerline[i].distance
                if abs(point_distance - spike_distance) <= search_distance:
                    # Check magnitude AND sign match
                    if abs(curv) > neighbor_threshold:
                        neighbor_sign = 1 if curv > 0 else -1
                        if neighbor_sign == spike_sign:
                            return False  # Has same-direction significant neighbor - not isolated

            return True  # No same-direction significant neighbors within search distance
        else:
            # Fallback: index-based search (check 3 points on each side)
            check_range = 3
            for offset in range(1, check_range + 1):
                if idx - offset >= 0:
                    curv = curvatures[idx - offset]
                    if abs(curv) > neighbor_threshold:
                        neighbor_sign = 1 if curv > 0 else -1
                        if neighbor_sign == spike_sign:
                            return False
                if idx + offset < len(curvatures):
                    curv = curvatures[idx + offset]
                    if abs(curv) > neighbor_threshold:
                        neighbor_sign = 1 if curv > 0 else -1
                        if neighbor_sign == spike_sign:
                            return False

            return True

    def _split_long_regions(
        self,
        regions: List[Tuple[int, int]],
        centerline: List[TrackPoint],
        curvatures: List[float],
        max_span: float = 80.0,
        min_split_distance: float = 25.0
    ) -> List[Tuple[int, int]]:
        """
        Split long corner regions at local curvature minima (recursive).

        Long regions (>max_span) that maintain curvature above threshold throughout
        may contain multiple distinct corners. Split them at points where curvature
        is locally minimum (the "straightest" part between apexes).

        Uses a queue-based approach to recursively split until all regions are
        within max_span or no valid split points remain.

        Args:
            regions: List of (start_index, end_index) tuples
            centerline: Track centerline points
            curvatures: Curvature at each point
            max_span: Only split regions longer than this (meters)
            min_split_distance: Minimum distance from region boundary for a valid split point
        """
        result = []
        # Use a queue so we can re-process split sub-regions
        queue = list(regions)

        while queue:
            start_idx, end_idx = queue.pop(0)
            span = abs(centerline[end_idx].distance - centerline[start_idx].distance)

            if span <= max_span:
                # Short enough - keep as is
                result.append((start_idx, end_idx))
                continue

            # Find local minima in curvature magnitude within this region
            # A local minimum is a point where |curvature| < both neighbors
            minima = []
            for i in range(start_idx + 1, end_idx):
                prev_curv = abs(curvatures[i - 1])
                curr_curv = abs(curvatures[i])
                next_curv = abs(curvatures[i + 1])

                if curr_curv < prev_curv and curr_curv < next_curv:
                    # Check it's not too close to boundaries
                    dist_from_start = centerline[i].distance - centerline[start_idx].distance
                    dist_from_end = centerline[end_idx].distance - centerline[i].distance

                    if dist_from_start >= min_split_distance and dist_from_end >= min_split_distance:
                        minima.append((i, curr_curv))

            if not minima:
                # No valid split points - keep as is (even if too long)
                result.append((start_idx, end_idx))
                continue

            # Find the maximum curvature in the region (for comparison)
            max_curv = max(abs(curvatures[i]) for i in range(start_idx, end_idx + 1))

            # Filter minima: only keep those significantly lower than max
            # A good split point should have curvature at most 60% of max
            significant_minima = [
                (idx, curv) for idx, curv in minima
                if curv < max_curv * 0.6
            ]

            if not significant_minima:
                # No significant dips - keep as is
                result.append((start_idx, end_idx))
                continue

            # Take the BEST (lowest curvature) split point only
            # This ensures we split at the most distinct boundary
            best_split_idx = min(significant_minima, key=lambda x: x[1])[0]

            # Create two sub-regions and add back to queue for re-processing
            # Region 1: start to just before split point
            sub1 = (start_idx, best_split_idx - 1)
            # Region 2: just after split point to end
            sub2 = (best_split_idx + 1, end_idx)

            # Add back to queue - they'll be checked again for length
            queue.append(sub1)
            queue.append(sub2)

        return result

    def _merge_close_regions(
        self,
        regions: List[Tuple[int, int]],
        centerline: List[TrackPoint],
        curvatures: List[float],
        merge_distance: float = 20.0,
        max_corner_span: float = 80.0
    ) -> List[Tuple[int, int]]:
        """
        Merge corner regions that are close together (chicanes).

        Only keeps regions separate if they turn in different directions AND
        both would be significant corners (>40° each). Small direction changes
        (sweeps into corners) are merged with the main corner.

        Args:
            regions: List of (start, end) index pairs
            centerline: Track centerline
            curvatures: Curvature at each point (positive=left, negative=right)
            merge_distance: Maximum distance between regions to merge (meters)
            max_corner_span: Maximum span for a merged corner (meters) - prevents
                            over-merging multiple distinct corners
        """
        if len(regions) <= 1:
            return regions

        def get_region_direction(start_idx: int, end_idx: int) -> str:
            """Get dominant turn direction for a region."""
            total_curvature = sum(curvatures[i] for i in range(start_idx, end_idx + 1))
            return "left" if total_curvature > 0 else "right"

        def estimate_region_angle(start_idx: int, end_idx: int) -> float:
            """Estimate total angle turned in a region (rough calculation)."""
            total_angle = 0.0
            for i in range(start_idx, end_idx):
                if i + 1 < len(centerline):
                    arc_length = abs(centerline[i + 1].distance - centerline[i].distance)
                    total_angle += abs(curvatures[i]) * arc_length
            return math.degrees(total_angle)

        def get_region_span(start_idx: int, end_idx: int) -> float:
            """Get the distance span of a region in meters."""
            return abs(centerline[end_idx].distance - centerline[start_idx].distance)

        # Minimum angle for a region to be considered a "significant" corner
        # Below this, it's just a sweep/wobble that should merge with adjacent corner
        min_significant_angle = 35.0

        merged = []
        current_start, current_end = regions[0]
        current_direction = get_region_direction(current_start, current_end)

        for i in range(1, len(regions)):
            next_start, next_end = regions[i]
            next_direction = get_region_direction(next_start, next_end)

            # Distance between end of current and start of next
            gap_distance = abs(
                centerline[next_start].distance -
                centerline[current_end].distance
            )

            # Calculate what the merged span would be
            merged_span = abs(centerline[next_end].distance - centerline[current_start].distance)

            if gap_distance < merge_distance and merged_span <= max_corner_span:
                # Close together AND won't create too large a corner - decide whether to merge
                if current_direction == next_direction:
                    # Same direction - merge
                    current_end = next_end
                else:
                    # Different directions - only keep separate if BOTH are significant
                    current_angle = estimate_region_angle(current_start, current_end)
                    next_angle = estimate_region_angle(next_start, next_end)

                    if current_angle >= min_significant_angle and next_angle >= min_significant_angle:
                        # Both significant - keep separate (true chicane)
                        merged.append((current_start, current_end))
                        current_start, current_end = next_start, next_end
                        current_direction = next_direction
                    else:
                        # One or both are small wobbles - merge them
                        current_end = next_end
                        # Update direction to the larger region's direction
                        current_direction = get_region_direction(current_start, current_end)
            else:
                # Too far apart OR would create too large a corner - don't merge
                merged.append((current_start, current_end))
                current_start, current_end = next_start, next_end
                current_direction = next_direction

        merged.append((current_start, current_end))
        return merged

    def _create_corner(
        self,
        corner_id: int,
        region: Tuple[int, int],
        centerline: List[TrackPoint],
        curvatures: List[float],
        track_length: float,
        is_loop_track: bool = False
    ) -> Corner:
        """
        Create Corner object from detected region.

        Args:
            corner_id: Sequential corner number
            region: (start_index, end_index)
            centerline: Track centerline
            curvatures: Curvature at each point
            track_length: Total track length for edge filtering
            is_loop_track: True if track is a loop (skip edge filtering)
        """
        start_idx, end_idx = region

        # Find apex (point of maximum curvature)
        max_curvature = 0.0
        apex_idx = start_idx

        for i in range(start_idx, end_idx + 1):
            if abs(curvatures[i]) > abs(max_curvature):
                max_curvature = curvatures[i]
                apex_idx = i

        # Calculate corner properties
        entry_distance = centerline[start_idx].distance
        apex_distance = centerline[apex_idx].distance
        exit_distance = centerline[end_idx].distance

        # NOTE: Edge buffer filtering removed - corners detected by curvature are real corners
        # regardless of their position on the track. Both loop and point-to-point tracks
        # can have corners near start/finish lines.

        # Calculate radii
        min_radius = abs(1.0 / max_curvature) if max_curvature != 0 else float('inf')

        # Average radius
        avg_curvature = sum(abs(curvatures[i]) for i in range(start_idx, end_idx + 1)) / (end_idx - start_idx + 1)
        avg_radius = 1.0 / avg_curvature if avg_curvature > 0 else float('inf')

        # Total angle turned (sum of curvature * arc length)
        total_angle = 0.0
        for i in range(start_idx, end_idx):
            next_i = i + 1
            arc_length = haversine_distance(
                centerline[i].lat, centerline[i].lon,
                centerline[next_i].lat, centerline[next_i].lon
            )
            total_angle += abs(curvatures[i]) * arc_length

        total_angle = math.degrees(total_angle)

        # Filter out non-corners (not enough angle)
        if total_angle < self.min_angle:
            return None

        # Direction
        direction = "left" if max_curvature > 0 else "right"

        return Corner(
            id=corner_id,
            name=f"Corner {corner_id}",
            entry_distance=entry_distance,
            apex_distance=apex_distance,
            exit_distance=exit_distance,
            entry_index=start_idx,
            apex_index=apex_idx,
            exit_index=end_idx,
            min_radius=min_radius,
            avg_radius=avg_radius,
            total_angle=total_angle,
            direction=direction
        )
