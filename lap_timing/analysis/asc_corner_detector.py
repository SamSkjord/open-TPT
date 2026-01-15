"""
ASC (Automated Segmentation based on Curvature) corner detection.

Based on VEHITS 2024 paper - segments track using a 5-phase algorithm:
1. Peak Detection - place cuts at curvature peaks
2. Redundancy Reduction - merge close cuts
3. Straight Section Filling - add equidistant cuts in long sections
4. Curvature Sign Changes - add cuts at direction transitions
5. Final Filtering - remove remaining close cuts

This produces cleaner segmentation than threshold-based region detection.
"""

import math
from typing import List, Tuple, Optional
from dataclasses import dataclass
from lap_timing.data.track_loader import Track, TrackPoint
from lap_timing.utils.geometry import haversine_distance


@dataclass
class Corner:
    """Detected corner on track."""
    id: int
    name: str
    entry_distance: float      # Meters from S/F
    apex_distance: float       # Meters from S/F (max curvature point)
    exit_distance: float       # Meters from S/F
    entry_index: int           # Centerline point index
    apex_index: int            # Centerline point index
    exit_index: int            # Centerline point index
    min_radius: float          # Minimum radius in meters
    avg_radius: float          # Average radius through corner
    total_angle: float         # Total angle turned (degrees)
    direction: str             # "left" or "right"


@dataclass
class TrackSegment:
    """A segment of track between two cuts."""
    start_index: int
    end_index: int
    start_distance: float
    end_distance: float
    segment_type: str          # "corner" or "straight"
    avg_curvature: float       # Average signed curvature
    max_curvature: float       # Maximum absolute curvature
    direction: Optional[str]   # "left", "right", or None for straights


class ASCCornerDetector:
    """
    Detect corners using Automated Segmentation based on Curvature (ASC).

    Unlike threshold-based detection, ASC places "cuts" at key geometric
    features (peaks, sign changes) to create natural segment boundaries.
    """

    def __init__(
        self,
        curvature_peak_threshold: float = 0.005,  # 1/200m radius
        min_cut_distance: float = 15.0,           # Minimum meters between cuts
        straight_fill_distance: float = 100.0,    # Add cuts every N meters in straights
        min_corner_angle: float = 15.0,           # Minimum angle to be a corner (degrees)
        min_corner_radius: float = 100.0,         # Max radius to be a corner (meters)
        merge_same_direction: bool = True         # Merge consecutive same-direction corners
    ):
        """
        Initialize ASC detector.

        Args:
            curvature_peak_threshold: Minimum curvature magnitude for peak detection
            min_cut_distance: Minimum distance between cuts (for merging)
            straight_fill_distance: Distance between artificial cuts in straights
            min_corner_angle: Minimum total angle to classify as corner
            min_corner_radius: Maximum average radius to classify as corner
            merge_same_direction: Merge consecutive corners turning the same direction
        """
        self.curvature_peak_threshold = curvature_peak_threshold
        self.min_cut_distance = min_cut_distance
        self.straight_fill_distance = straight_fill_distance
        self.min_corner_angle = min_corner_angle
        self.min_corner_radius = min_corner_radius
        self.merge_same_direction = merge_same_direction

    def detect_corners(self, track: Track) -> List[Corner]:
        """
        Detect all corners on the track using ASC algorithm.

        Args:
            track: Track with centerline

        Returns:
            List of detected corners sorted by distance
        """
        centerline = track.centerline

        if len(centerline) < 5:
            return []

        # Calculate curvature at each point
        curvatures = self._calculate_curvatures(centerline)

        # ASC 5-phase algorithm
        cuts = self._phase1_peak_detection(centerline, curvatures)
        cuts = self._phase2_redundancy_reduction(cuts, centerline)
        cuts = self._phase3_straight_filling(cuts, centerline)
        cuts = self._phase4_sign_changes(cuts, centerline, curvatures)
        cuts = self._phase5_final_filtering(cuts, centerline)

        # Create segments from cuts
        segments = self._create_segments(cuts, centerline, curvatures)

        # Optionally merge consecutive same-direction corner segments
        if self.merge_same_direction:
            segments = self._merge_corner_segments(segments, centerline, curvatures)

        # Convert corner segments to Corner objects
        corners = self._segments_to_corners(segments, centerline, curvatures)

        return corners

    def get_segments(self, track: Track) -> List[TrackSegment]:
        """
        Get all track segments (corners and straights).

        Useful for visualization and debugging.
        """
        centerline = track.centerline

        if len(centerline) < 5:
            return []

        curvatures = self._calculate_curvatures(centerline)

        cuts = self._phase1_peak_detection(centerline, curvatures)
        cuts = self._phase2_redundancy_reduction(cuts, centerline)
        cuts = self._phase3_straight_filling(cuts, centerline)
        cuts = self._phase4_sign_changes(cuts, centerline, curvatures)
        cuts = self._phase5_final_filtering(cuts, centerline)

        return self._create_segments(cuts, centerline, curvatures)

    def _calculate_curvatures(self, centerline: List[TrackPoint]) -> List[float]:
        """
        Calculate curvature at each centerline point.

        Uses three-point circle fitting (circumcircle method).
        Curvature = 1/radius (positive = left turn, negative = right turn)
        """
        curvatures = []

        for i in range(len(centerline)):
            i_prev = (i - 1) % len(centerline)
            i_next = (i + 1) % len(centerline)

            p1 = centerline[i_prev]
            p2 = centerline[i]
            p3 = centerline[i_next]

            curvature = self._curvature_from_points(p1, p2, p3)
            curvatures.append(curvature)

        return curvatures

    def _curvature_from_points(
        self,
        p1: TrackPoint,
        p2: TrackPoint,
        p3: TrackPoint
    ) -> float:
        """Calculate signed curvature from three points using circumcircle."""
        # Convert to local meters (p2 as origin)
        x1 = (p1.lon - p2.lon) * 111320 * math.cos(math.radians(p2.lat))
        y1 = (p1.lat - p2.lat) * 110540
        x2 = 0.0
        y2 = 0.0
        x3 = (p3.lon - p2.lon) * 111320 * math.cos(math.radians(p2.lat))
        y3 = (p3.lat - p2.lat) * 110540

        # Triangle area
        area = abs((x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2)) / 2.0)

        if area < 1e-6:
            return 0.0  # Collinear

        # Side lengths
        a = math.sqrt((x2 - x3)**2 + (y2 - y3)**2)
        b = math.sqrt((x1 - x3)**2 + (y1 - y3)**2)
        c = math.sqrt((x1 - x2)**2 + (y1 - y2)**2)

        # Circumradius
        radius = (a * b * c) / (4.0 * area)

        if radius < 0.1:
            return 0.0

        # Sign from cross product (positive = left turn)
        cross = (x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)
        sign = 1.0 if cross > 0 else -1.0

        return sign / radius

    def _phase1_peak_detection(
        self,
        centerline: List[TrackPoint],
        curvatures: List[float]
    ) -> List[int]:
        """
        Phase 1: Find curvature peaks and place cuts.

        A peak is a local maximum in |curvature| that exceeds the threshold.
        """
        cuts = []
        n = len(curvatures)

        for i in range(1, n - 1):
            curr = abs(curvatures[i])
            prev = abs(curvatures[i - 1])
            next_c = abs(curvatures[i + 1])

            # Local maximum above threshold
            if curr > prev and curr > next_c and curr > self.curvature_peak_threshold:
                cuts.append(i)

        return cuts

    def _phase2_redundancy_reduction(
        self,
        cuts: List[int],
        centerline: List[TrackPoint]
    ) -> List[int]:
        """
        Phase 2: Merge cuts that are too close together.

        When two cuts are within min_cut_distance, keep the one with
        higher curvature (more significant feature).
        """
        if len(cuts) <= 1:
            return cuts

        # Sort by distance
        cuts = sorted(cuts, key=lambda i: centerline[i].distance)

        merged = []
        i = 0

        while i < len(cuts):
            current = cuts[i]

            # Find all cuts within min_cut_distance
            group = [current]
            j = i + 1
            while j < len(cuts):
                dist = abs(centerline[cuts[j]].distance - centerline[current].distance)
                if dist < self.min_cut_distance:
                    group.append(cuts[j])
                    j += 1
                else:
                    break

            # Keep the cut with highest curvature in group
            # (We don't have curvatures here, so just keep middle one for now)
            # In practice, this could be improved by passing curvatures
            merged.append(group[len(group) // 2])
            i = j

        return merged

    def _phase3_straight_filling(
        self,
        cuts: List[int],
        centerline: List[TrackPoint]
    ) -> List[int]:
        """
        Phase 3: Fill long cut-less sections with equidistant cuts.

        Straight sections without natural features still need segmentation
        for analysis purposes.
        """
        if not cuts:
            # No cuts yet - create initial ones at regular intervals
            cuts = []
            total_distance = centerline[-1].distance
            num_cuts = int(total_distance / self.straight_fill_distance)

            for i in range(1, num_cuts):
                target_dist = i * self.straight_fill_distance
                idx = self._find_index_at_distance(centerline, target_dist)
                if idx is not None:
                    cuts.append(idx)

            return sorted(cuts)

        # Sort existing cuts
        cuts = sorted(cuts, key=lambda i: centerline[i].distance)

        new_cuts = list(cuts)

        # Check gaps between consecutive cuts
        for i in range(len(cuts) - 1):
            start_dist = centerline[cuts[i]].distance
            end_dist = centerline[cuts[i + 1]].distance
            gap = end_dist - start_dist

            if gap > self.straight_fill_distance * 1.5:
                # Add intermediate cuts - at least 1 in the middle
                num_fills = max(1, int(gap / self.straight_fill_distance))
                for j in range(1, num_fills + 1):
                    target_dist = start_dist + j * (gap / (num_fills + 1))
                    idx = self._find_index_at_distance(centerline, target_dist)
                    if idx is not None and idx not in new_cuts:
                        new_cuts.append(idx)

        # Check gap from start to first cut
        if cuts:
            first_dist = centerline[cuts[0]].distance
            if first_dist > self.straight_fill_distance * 1.5:
                num_fills = max(1, int(first_dist / self.straight_fill_distance))
                for j in range(1, num_fills + 1):
                    target_dist = j * (first_dist / (num_fills + 1))
                    idx = self._find_index_at_distance(centerline, target_dist)
                    if idx is not None and idx not in new_cuts:
                        new_cuts.append(idx)

        # Check gap from last cut to end
        if cuts:
            last_dist = centerline[cuts[-1]].distance
            total_dist = centerline[-1].distance
            gap = total_dist - last_dist
            if gap > self.straight_fill_distance * 1.5:
                num_fills = max(1, int(gap / self.straight_fill_distance))
                for j in range(1, num_fills + 1):
                    target_dist = last_dist + j * (gap / (num_fills + 1))
                    idx = self._find_index_at_distance(centerline, target_dist)
                    if idx is not None and idx not in new_cuts:
                        new_cuts.append(idx)

        return sorted(set(new_cuts))

    def _phase4_sign_changes(
        self,
        cuts: List[int],
        centerline: List[TrackPoint],
        curvatures: List[float]
    ) -> List[int]:
        """
        Phase 4: Add cuts where curvature sign changes.

        Sign changes indicate transitions between left and right turns,
        which are natural segment boundaries.
        """
        cuts = sorted(cuts, key=lambda i: centerline[i].distance)
        new_cuts = list(cuts)

        # Find all sign change points
        for i in range(1, len(curvatures)):
            prev_sign = 1 if curvatures[i - 1] > 0 else -1
            curr_sign = 1 if curvatures[i] > 0 else -1

            # Skip near-zero curvatures (straight sections have noisy signs)
            if abs(curvatures[i - 1]) < 0.001 or abs(curvatures[i]) < 0.001:
                continue

            if prev_sign != curr_sign:
                # Check if this point falls between existing cuts
                dist = centerline[i].distance

                # Find surrounding cuts
                prev_cut_dist = 0
                next_cut_dist = centerline[-1].distance

                for cut in cuts:
                    cut_dist = centerline[cut].distance
                    if cut_dist < dist:
                        prev_cut_dist = max(prev_cut_dist, cut_dist)
                    else:
                        next_cut_dist = min(next_cut_dist, cut_dist)

                # Only add if not too close to existing cuts
                if (dist - prev_cut_dist > self.min_cut_distance and
                    next_cut_dist - dist > self.min_cut_distance):
                    if i not in new_cuts:
                        new_cuts.append(i)

        return sorted(set(new_cuts))

    def _phase5_final_filtering(
        self,
        cuts: List[int],
        centerline: List[TrackPoint]
    ) -> List[int]:
        """
        Phase 5: Final pass to remove any remaining close cuts.
        """
        return self._phase2_redundancy_reduction(cuts, centerline)

    def _find_index_at_distance(
        self,
        centerline: List[TrackPoint],
        target_distance: float
    ) -> Optional[int]:
        """Find centerline index closest to target distance."""
        best_idx = None
        best_diff = float('inf')

        for i, pt in enumerate(centerline):
            diff = abs(pt.distance - target_distance)
            if diff < best_diff:
                best_diff = diff
                best_idx = i

        return best_idx

    def _create_segments(
        self,
        cuts: List[int],
        centerline: List[TrackPoint],
        curvatures: List[float]
    ) -> List[TrackSegment]:
        """
        Create track segments from cut points.

        Each segment is classified as 'corner' or 'straight' based on
        average curvature and total angle.
        """
        if not cuts:
            # Entire track is one segment
            return [self._analyze_segment(0, len(centerline) - 1, centerline, curvatures)]

        cuts = sorted(cuts)
        segments = []

        # Segment from start to first cut
        if cuts[0] > 0:
            seg = self._analyze_segment(0, cuts[0], centerline, curvatures)
            segments.append(seg)

        # Segments between cuts
        for i in range(len(cuts) - 1):
            seg = self._analyze_segment(cuts[i], cuts[i + 1], centerline, curvatures)
            segments.append(seg)

        # Segment from last cut to end
        if cuts[-1] < len(centerline) - 1:
            seg = self._analyze_segment(cuts[-1], len(centerline) - 1, centerline, curvatures)
            segments.append(seg)

        return segments

    def _analyze_segment(
        self,
        start_idx: int,
        end_idx: int,
        centerline: List[TrackPoint],
        curvatures: List[float]
    ) -> TrackSegment:
        """Analyze a segment and classify as corner or straight."""
        if start_idx >= end_idx:
            end_idx = start_idx + 1
            if end_idx >= len(centerline):
                end_idx = len(centerline) - 1
                start_idx = end_idx - 1

        # Calculate segment properties
        segment_curvatures = curvatures[start_idx:end_idx + 1]

        if not segment_curvatures:
            avg_curvature = 0.0
            max_curvature = 0.0
        else:
            avg_curvature = sum(segment_curvatures) / len(segment_curvatures)
            max_curvature = max(abs(c) for c in segment_curvatures)

        # Calculate total angle
        total_angle = 0.0
        for i in range(start_idx, min(end_idx, len(centerline) - 1)):
            arc_length = abs(centerline[i + 1].distance - centerline[i].distance)
            total_angle += abs(curvatures[i]) * arc_length
        total_angle = math.degrees(total_angle)

        # Determine direction
        if avg_curvature > 0.001:
            direction = "left"
        elif avg_curvature < -0.001:
            direction = "right"
        else:
            direction = None

        # Classify as corner or straight
        # Use min_radius (from max_curvature) for classification - matches original detector behavior
        min_radius = 1.0 / max_curvature if max_curvature > 0.0001 else float('inf')

        if total_angle >= self.min_corner_angle and min_radius <= self.min_corner_radius:
            segment_type = "corner"
        else:
            segment_type = "straight"

        return TrackSegment(
            start_index=start_idx,
            end_index=end_idx,
            start_distance=centerline[start_idx].distance,
            end_distance=centerline[end_idx].distance,
            segment_type=segment_type,
            avg_curvature=avg_curvature,
            max_curvature=max_curvature,
            direction=direction
        )

    def _merge_corner_segments(
        self,
        segments: List[TrackSegment],
        centerline: List[TrackPoint],
        curvatures: List[float],
        max_straight_gap: float = 30.0,
        max_corner_span: float = 80.0
    ) -> List[TrackSegment]:
        """
        Merge consecutive corner segments that turn the same direction.

        This consolidates over-segmented corners into single logical corners.
        Short straight sections between same-direction corners are absorbed.

        Args:
            segments: List of track segments
            centerline: Track centerline
            curvatures: Curvature at each point
            max_straight_gap: Max straight length to absorb between corners (meters)
            max_corner_span: Maximum total span for a merged corner (meters)
        """
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

            # Try to merge with following segments
            merge_end_idx = current.end_index
            merge_end_distance = current.end_distance

            j = i + 1
            while j < len(segments):
                next_seg = segments[j]

                if next_seg.segment_type == "corner":
                    # Same direction - merge consecutive corners unconditionally
                    # (they're part of the same turn if no straight between them)
                    if next_seg.direction == current.direction:
                        merge_end_idx = next_seg.end_index
                        merge_end_distance = next_seg.end_distance
                        j += 1
                        continue
                    else:
                        # Different direction - stop merging
                        break

                elif next_seg.segment_type == "straight":
                    # Short straight between same-direction corners - absorb if short enough
                    straight_length = next_seg.end_distance - next_seg.start_distance

                    if straight_length <= max_straight_gap and j + 1 < len(segments):
                        following = segments[j + 1]
                        if (following.segment_type == "corner" and
                            following.direction == current.direction):
                            # Check span limit before absorbing across a straight
                            potential_span = following.end_distance - current.start_distance
                            if potential_span <= max_corner_span:
                                # Absorb the straight and continue
                                j += 1
                                continue

                    # Too long, would exceed span, or no matching corner follows - stop
                    break
                else:
                    break

            # Create merged segment
            if j > i + 1:
                # Actually merged something - re-analyze the combined region
                merged_seg = self._analyze_segment(
                    current.start_index,
                    merge_end_idx,
                    centerline,
                    curvatures
                )
                # Force it to be a corner since we're merging corners
                merged_seg = TrackSegment(
                    start_index=merged_seg.start_index,
                    end_index=merged_seg.end_index,
                    start_distance=merged_seg.start_distance,
                    end_distance=merged_seg.end_distance,
                    segment_type="corner",
                    avg_curvature=merged_seg.avg_curvature,
                    max_curvature=merged_seg.max_curvature,
                    direction=current.direction
                )
                merged.append(merged_seg)
            else:
                merged.append(current)

            i = j

        return merged

    def _segments_to_corners(
        self,
        segments: List[TrackSegment],
        centerline: List[TrackPoint],
        curvatures: List[float]
    ) -> List[Corner]:
        """Convert corner segments to Corner objects."""
        corners = []
        corner_id = 1

        for seg in segments:
            if seg.segment_type != "corner":
                continue

            # Find apex (max curvature point)
            apex_idx = seg.start_index
            max_curv = 0.0
            for i in range(seg.start_index, seg.end_index + 1):
                if i < len(curvatures) and abs(curvatures[i]) > max_curv:
                    max_curv = abs(curvatures[i])
                    apex_idx = i

            # Calculate radii
            min_radius = 1.0 / max_curv if max_curv > 0 else float('inf')
            avg_radius = 1.0 / abs(seg.avg_curvature) if abs(seg.avg_curvature) > 0 else float('inf')

            # Calculate total angle
            total_angle = 0.0
            for i in range(seg.start_index, min(seg.end_index, len(centerline) - 1)):
                arc_length = abs(centerline[i + 1].distance - centerline[i].distance)
                total_angle += abs(curvatures[i]) * arc_length
            total_angle = math.degrees(total_angle)

            corner = Corner(
                id=corner_id,
                name=f"Corner {corner_id}",
                entry_distance=seg.start_distance,
                apex_distance=centerline[apex_idx].distance,
                exit_distance=seg.end_distance,
                entry_index=seg.start_index,
                apex_index=apex_idx,
                exit_index=seg.end_index,
                min_radius=min_radius,
                avg_radius=avg_radius,
                total_angle=total_angle,
                direction=seg.direction or "left"
            )
            corners.append(corner)
            corner_id += 1

        return corners
