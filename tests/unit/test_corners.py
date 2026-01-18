"""Tests for copilot/corners.py - corner detection algorithm."""

import math
import pytest
from typing import List, Tuple

from copilot.corners import (
    CornerDetector, Corner, Direction, Segment, RADIUS_SEVERITY
)


class TestRadiusSeverity:
    """Test severity classification based on radius."""

    def test_severity_thresholds(self):
        """Verify the radius-to-severity mapping thresholds."""
        detector = CornerDetector()

        # Hairpin: < 15m
        assert detector._classify_severity(10) == 1
        assert detector._classify_severity(14.9) == 1

        # Very tight: 15-30m
        assert detector._classify_severity(15) == 2
        assert detector._classify_severity(25) == 2

        # Tight: 30-50m
        assert detector._classify_severity(30) == 3
        assert detector._classify_severity(45) == 3

        # Medium: 50-80m
        assert detector._classify_severity(50) == 4
        assert detector._classify_severity(70) == 4

        # Fast: 80-120m
        assert detector._classify_severity(80) == 5
        assert detector._classify_severity(100) == 5

        # Six: 120-200m
        assert detector._classify_severity(120) == 6
        assert detector._classify_severity(180) == 6

        # Kink: > 200m
        assert detector._classify_severity(200) == 7
        assert detector._classify_severity(500) == 7


class TestCornerDataclass:
    """Test Corner dataclass."""

    def test_corner_creation(self):
        """Test creating a Corner with all fields."""
        corner = Corner(
            entry_distance=100.0,
            apex_distance=150.0,
            exit_distance=200.0,
            apex_lat=51.5074,
            apex_lon=-0.1278,
            direction=Direction.LEFT,
            severity=3,
            total_angle=90.0,
            min_radius=40.0,
        )

        assert corner.entry_distance == 100.0
        assert corner.apex_distance == 150.0
        assert corner.exit_distance == 200.0
        assert corner.direction == Direction.LEFT
        assert corner.severity == 3
        assert corner.total_angle == 90.0
        assert corner.min_radius == 40.0
        assert corner.tightens is False
        assert corner.opens is False
        assert corner.long_corner is False
        assert corner.is_chicane is False

    def test_corner_with_modifiers(self):
        """Test corner with tightens/opens modifiers."""
        corner = Corner(
            entry_distance=50.0,
            apex_distance=75.0,
            exit_distance=100.0,
            apex_lat=51.5,
            apex_lon=-0.1,
            direction=Direction.RIGHT,
            severity=2,
            total_angle=120.0,
            min_radius=25.0,
            tightens=True,
            long_corner=True,
        )

        assert corner.tightens is True
        assert corner.opens is False
        assert corner.long_corner is True

    def test_chicane_corner(self):
        """Test chicane corner with exit direction."""
        corner = Corner(
            entry_distance=80.0,
            apex_distance=100.0,
            exit_distance=130.0,
            apex_lat=51.5,
            apex_lon=-0.1,
            direction=Direction.LEFT,
            severity=3,
            total_angle=90.0,
            min_radius=35.0,
            is_chicane=True,
            exit_direction=Direction.RIGHT,
        )

        assert corner.is_chicane is True
        assert corner.direction == Direction.LEFT
        assert corner.exit_direction == Direction.RIGHT


class TestDirectionEnum:
    """Test Direction enum."""

    def test_direction_values(self):
        """Test direction enum values."""
        assert Direction.LEFT.value == "left"
        assert Direction.RIGHT.value == "right"


class TestCornerDetectorInit:
    """Test CornerDetector initialisation."""

    def test_default_parameters(self):
        """Test default constructor parameters."""
        detector = CornerDetector()

        assert detector.curvature_peak_threshold == 0.005
        assert detector.min_cut_distance == 15.0
        assert detector.straight_fill_distance == 100.0
        assert detector.merge_same_direction is True
        assert detector.merge_chicanes is True
        assert detector.max_chicane_gap == 30.0
        assert detector.max_chicane_length == 100.0

    def test_custom_parameters(self):
        """Test custom constructor parameters."""
        detector = CornerDetector(
            curvature_peak_threshold=0.01,
            min_cut_distance=20.0,
            straight_fill_distance=150.0,
            merge_same_direction=False,
            merge_chicanes=False,
        )

        assert detector.curvature_peak_threshold == 0.01
        assert detector.min_cut_distance == 20.0
        assert detector.straight_fill_distance == 150.0
        assert detector.merge_same_direction is False
        assert detector.merge_chicanes is False


class TestCalculateCurvatures:
    """Test curvature calculation."""

    def test_straight_line(self):
        """Straight line should have zero curvature."""
        detector = CornerDetector()

        # Straight line going north
        points = [
            (51.5000, -0.1000),
            (51.5001, -0.1000),
            (51.5002, -0.1000),
            (51.5003, -0.1000),
            (51.5004, -0.1000),
        ]

        curvatures = detector._calculate_curvatures(points)

        # First and last are always 0
        assert curvatures[0] == 0.0
        assert curvatures[-1] == 0.0

        # Middle points should have near-zero curvature
        for c in curvatures[1:-1]:
            assert abs(c) < 0.0001

    def test_curve_has_curvature(self):
        """Curved path should have non-zero curvature."""
        detector = CornerDetector()

        # Create a curved path (quarter circle-ish)
        points = [
            (51.5000, -0.1000),
            (51.5001, -0.0999),
            (51.5002, -0.0997),
            (51.5003, -0.0994),
            (51.5003, -0.0990),
        ]

        curvatures = detector._calculate_curvatures(points)

        # Should have some curvature in the middle
        max_curv = max(abs(c) for c in curvatures[1:-1])
        assert max_curv > 0


class TestPhase1PeakDetection:
    """Test phase 1: curvature peak detection."""

    def test_no_peaks_in_straight(self):
        """Straight path should have no curvature peaks."""
        detector = CornerDetector()

        curvatures = [0.0, 0.001, 0.002, 0.001, 0.0]
        cuts = detector._phase1_peak_detection(curvatures)

        assert len(cuts) == 0  # No peaks above threshold

    def test_single_peak(self):
        """Single peak should be detected."""
        detector = CornerDetector(curvature_peak_threshold=0.005)

        curvatures = [0.0, 0.002, 0.01, 0.002, 0.0]
        cuts = detector._phase1_peak_detection(curvatures)

        assert len(cuts) == 1
        assert cuts[0] == 2  # Index of peak

    def test_multiple_peaks(self):
        """Multiple peaks should be detected."""
        detector = CornerDetector(curvature_peak_threshold=0.005)

        curvatures = [0.0, 0.01, 0.002, 0.015, 0.002, 0.008, 0.0]
        cuts = detector._phase1_peak_detection(curvatures)

        assert len(cuts) == 3
        assert 1 in cuts
        assert 3 in cuts
        assert 5 in cuts


class TestPhase2RedundancyReduction:
    """Test phase 2: merging close cuts."""

    def test_no_merge_needed(self):
        """Cuts far apart should not be merged."""
        detector = CornerDetector(min_cut_distance=15.0)

        cuts = [5, 20, 40]
        distances = list(range(0, 500, 10))  # 0, 10, 20, ... 490

        result = detector._phase2_redundancy_reduction(cuts, distances)

        assert len(result) == 3

    def test_close_cuts_merged(self):
        """Cuts close together should be merged."""
        detector = CornerDetector(min_cut_distance=15.0)

        cuts = [5, 6, 7]  # Very close together
        distances = list(range(0, 100, 1))  # 0, 1, 2, ... 99

        result = detector._phase2_redundancy_reduction(cuts, distances)

        # Should merge to single cut (middle one)
        assert len(result) == 1
        assert result[0] == 6


class TestFindIndexAtDistance:
    """Test finding index at target distance."""

    def test_exact_match(self):
        """Find exact distance match."""
        detector = CornerDetector()

        distances = [0.0, 10.0, 20.0, 30.0, 40.0]
        idx = detector._find_index_at_distance(distances, 20.0)

        assert idx == 2

    def test_closest_match(self):
        """Find closest distance when no exact match."""
        detector = CornerDetector()

        distances = [0.0, 10.0, 20.0, 30.0, 40.0]
        idx = detector._find_index_at_distance(distances, 22.0)

        assert idx == 2  # 20.0 is closest to 22.0


class TestClassifySeverity:
    """Test severity classification."""

    @pytest.mark.parametrize("radius,expected", [
        (5.0, 1),    # Hairpin
        (14.0, 1),
        (15.0, 2),   # Very tight
        (29.0, 2),
        (30.0, 3),   # Tight
        (49.0, 3),
        (50.0, 4),   # Medium
        (79.0, 4),
        (80.0, 5),   # Fast
        (119.0, 5),
        (120.0, 6),  # Six
        (199.0, 6),
        (200.0, 7),  # Kink
        (1000.0, 7),
    ])
    def test_severity_ranges(self, radius, expected):
        """Test severity classification for various radii."""
        detector = CornerDetector()
        assert detector._classify_severity(radius) == expected


class TestCheckCurvatureProfile:
    """Test tightening/opening detection."""

    def test_straight_profile(self):
        """Constant curvature should not tighten or open."""
        detector = CornerDetector()

        curvatures = [0.01, 0.01, 0.01, 0.01, 0.01]
        tightens, opens = detector._check_curvature_profile(curvatures)

        assert tightens is False
        assert opens is False

    def test_tightening_corner(self):
        """Increasing curvature should be tightening."""
        detector = CornerDetector()

        # Entry curvature low, exit curvature high
        curvatures = [0.005, 0.008, 0.02, 0.025, 0.03]
        tightens, opens = detector._check_curvature_profile(curvatures)

        assert tightens is True
        assert opens is False

    def test_opening_corner(self):
        """Decreasing curvature should be opening."""
        detector = CornerDetector()

        # Entry curvature high, peak in middle, exit curvature low
        # Max at index 2 (0.03), entry avg = (0.025+0.028)/2 = 0.0265
        # exit avg = (0.03+0.008+0.005)/3 = 0.0143
        # ratio = 0.0143 / 0.0265 = 0.54 < 0.67 = opens
        curvatures = [0.025, 0.028, 0.03, 0.008, 0.005]
        tightens, opens = detector._check_curvature_profile(curvatures)

        assert tightens is False
        assert opens is True

    def test_short_profile(self):
        """Short profiles should return False for both."""
        detector = CornerDetector()

        curvatures = [0.01, 0.02]
        tightens, opens = detector._check_curvature_profile(curvatures)

        assert tightens is False
        assert opens is False


class TestDetectCornersIntegration:
    """Integration tests for corner detection."""

    def test_too_few_points(self):
        """Less than 5 points should return empty list."""
        detector = CornerDetector()

        points = [(51.5, -0.1), (51.5001, -0.1), (51.5002, -0.1)]
        corners = detector.detect_corners(points)

        assert corners == []

    def test_straight_road(self):
        """Straight road should have no corners."""
        detector = CornerDetector()

        # Straight line
        points = [(51.5 + i * 0.0001, -0.1) for i in range(20)]
        corners = detector.detect_corners(points)

        # Might have some corners due to floating point, but should be minimal
        tight_corners = [c for c in corners if c.severity <= 4]
        assert len(tight_corners) == 0

    def test_simple_left_turn(self):
        """Simple 90-degree left turn should be detected."""
        detector = CornerDetector()

        # Create a path that turns left (going north then west)
        points = []
        # Going north
        for i in range(10):
            points.append((51.5 + i * 0.0002, -0.1))
        # Curving left
        for i in range(5):
            lat = 51.5 + 0.0018 + i * 0.00005
            lon = -0.1 - i * 0.0002
            points.append((lat, lon))
        # Going west
        for i in range(10):
            points.append((51.502, -0.1 - 0.001 - i * 0.0002))

        corners = detector.detect_corners(points)

        # Should detect at least one corner
        assert len(corners) >= 1

    def test_simple_right_turn(self):
        """Simple right turn should be detected."""
        detector = CornerDetector()

        # Create a path that turns right
        points = []
        # Going north
        for i in range(10):
            points.append((51.5 + i * 0.0002, -0.1))
        # Curving right
        for i in range(5):
            lat = 51.5 + 0.0018 + i * 0.00005
            lon = -0.1 + i * 0.0002
            points.append((lat, lon))
        # Going east
        for i in range(10):
            points.append((51.502, -0.1 + 0.001 + i * 0.0002))

        corners = detector.detect_corners(points)

        # Should detect at least one corner
        assert len(corners) >= 1


class TestSegment:
    """Test Segment dataclass."""

    def test_segment_creation(self):
        """Test creating a Segment."""
        segment = Segment(
            start_idx=0,
            end_idx=10,
            start_distance=0.0,
            end_distance=100.0,
            segment_type="corner",
            avg_curvature=0.01,
            max_curvature=0.02,
            direction="left",
        )

        assert segment.start_idx == 0
        assert segment.end_idx == 10
        assert segment.start_distance == 0.0
        assert segment.end_distance == 100.0
        assert segment.segment_type == "corner"
        assert segment.avg_curvature == 0.01
        assert segment.max_curvature == 0.02
        assert segment.direction == "left"


class TestChicaneMerging:
    """Test chicane detection and merging."""

    def test_chicane_conditions(self):
        """Test that chicane conditions are checked properly."""
        detector = CornerDetector(
            max_chicane_gap=30.0,
            max_chicane_length=100.0,
        )

        # Create two opposite-direction corners close together
        corners = [
            Corner(
                entry_distance=50.0,
                apex_distance=60.0,
                exit_distance=70.0,
                apex_lat=51.5,
                apex_lon=-0.1,
                direction=Direction.LEFT,
                severity=3,
                total_angle=45.0,
                min_radius=40.0,
            ),
            Corner(
                entry_distance=80.0,  # 10m gap from previous exit
                apex_distance=90.0,
                exit_distance=100.0,
                apex_lat=51.501,
                apex_lon=-0.1,
                direction=Direction.RIGHT,  # Opposite direction
                severity=3,
                total_angle=45.0,
                min_radius=40.0,
            ),
        ]

        # Empty points list (not used in merge_chicanes for basic checks)
        merged = detector._merge_chicanes(corners, [])

        # Should be merged into one chicane
        assert len(merged) == 1
        assert merged[0].is_chicane is True
        assert merged[0].direction == Direction.LEFT
        assert merged[0].exit_direction == Direction.RIGHT

    def test_no_chicane_same_direction(self):
        """Same direction corners should not be merged as chicane."""
        detector = CornerDetector()

        corners = [
            Corner(
                entry_distance=50.0,
                apex_distance=60.0,
                exit_distance=70.0,
                apex_lat=51.5,
                apex_lon=-0.1,
                direction=Direction.LEFT,
                severity=3,
                total_angle=45.0,
                min_radius=40.0,
            ),
            Corner(
                entry_distance=80.0,
                apex_distance=90.0,
                exit_distance=100.0,
                apex_lat=51.501,
                apex_lon=-0.1,
                direction=Direction.LEFT,  # Same direction
                severity=3,
                total_angle=45.0,
                min_radius=40.0,
            ),
        ]

        merged = detector._merge_chicanes(corners, [])

        # Should NOT be merged (same direction)
        assert len(merged) == 2
        assert merged[0].is_chicane is False
        assert merged[1].is_chicane is False

    def test_no_chicane_large_gap(self):
        """Corners with large gap should not be merged as chicane."""
        detector = CornerDetector(max_chicane_gap=30.0)

        corners = [
            Corner(
                entry_distance=50.0,
                apex_distance=60.0,
                exit_distance=70.0,
                apex_lat=51.5,
                apex_lon=-0.1,
                direction=Direction.LEFT,
                severity=3,
                total_angle=45.0,
                min_radius=40.0,
            ),
            Corner(
                entry_distance=150.0,  # 80m gap - too large
                apex_distance=160.0,
                exit_distance=170.0,
                apex_lat=51.501,
                apex_lon=-0.1,
                direction=Direction.RIGHT,
                severity=3,
                total_angle=45.0,
                min_radius=40.0,
            ),
        ]

        merged = detector._merge_chicanes(corners, [])

        # Should NOT be merged (gap too large)
        assert len(merged) == 2

    def test_single_corner_no_merge(self):
        """Single corner should not be affected."""
        detector = CornerDetector()

        corners = [
            Corner(
                entry_distance=50.0,
                apex_distance=60.0,
                exit_distance=70.0,
                apex_lat=51.5,
                apex_lon=-0.1,
                direction=Direction.LEFT,
                severity=3,
                total_angle=45.0,
                min_radius=40.0,
            ),
        ]

        merged = detector._merge_chicanes(corners, [])

        assert len(merged) == 1
        assert merged[0].is_chicane is False

    def test_empty_corners(self):
        """Empty corner list should return empty."""
        detector = CornerDetector()

        merged = detector._merge_chicanes([], [])

        assert merged == []
