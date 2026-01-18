"""
Unit tests for GPS geometry calculations.
Tests pure functions from copilot/geometry.py with no mocking required.
"""

import pytest
import math
from copilot.geometry import (
    haversine_distance,
    bearing,
    angle_difference,
    point_along_bearing,
    closest_point_on_segment,
    calculate_curvature,
    cumulative_distances,
)


class TestHaversineDistance:
    """Tests for great circle distance calculation."""

    @pytest.mark.unit
    def test_same_point_zero_distance(self):
        """Test that distance from a point to itself is zero."""
        lat, lon = 51.5074, -0.1278  # London
        result = haversine_distance(lat, lon, lat, lon)
        assert result == 0

    @pytest.mark.unit
    def test_london_to_paris(self):
        """Test distance from London to Paris (~344 km)."""
        # London
        lat1, lon1 = 51.5074, -0.1278
        # Paris
        lat2, lon2 = 48.8566, 2.3522

        result = haversine_distance(lat1, lon1, lat2, lon2)
        # Should be approximately 344 km
        assert 340_000 < result < 350_000

    @pytest.mark.unit
    def test_short_distance(self):
        """Test a short distance (~100 metres)."""
        # Two points approximately 100m apart
        lat1, lon1 = 51.5074, -0.1278
        lat2, lon2 = 51.5083, -0.1278  # ~100m north

        result = haversine_distance(lat1, lon1, lat2, lon2)
        assert 95 < result < 105

    @pytest.mark.unit
    def test_symmetry(self):
        """Test that distance A->B equals distance B->A."""
        lat1, lon1 = 51.5074, -0.1278
        lat2, lon2 = 48.8566, 2.3522

        dist_ab = haversine_distance(lat1, lon1, lat2, lon2)
        dist_ba = haversine_distance(lat2, lon2, lat1, lon1)
        assert pytest.approx(dist_ab, rel=1e-9) == dist_ba

    @pytest.mark.unit
    def test_equator_crossing(self):
        """Test distance crossing the equator."""
        # Quito, Ecuador (near equator)
        lat1, lon1 = 0.1807, -78.4678
        # Bogota, Colombia
        lat2, lon2 = 4.7110, -74.0721

        result = haversine_distance(lat1, lon1, lat2, lon2)
        # Should be approximately 700 km
        assert 690_000 < result < 710_000

    @pytest.mark.unit
    def test_longitude_180(self):
        """Test distance across the international date line."""
        # Points on either side of 180 longitude
        lat1, lon1 = 0, 179
        lat2, lon2 = 0, -179

        result = haversine_distance(lat1, lon1, lat2, lon2)
        # Should be approximately 222 km (2 degrees at equator)
        assert 200_000 < result < 250_000


class TestBearing:
    """Tests for bearing calculation."""

    @pytest.mark.unit
    def test_bearing_north(self):
        """Test bearing due north is approximately 0 degrees."""
        lat1, lon1 = 51.5074, -0.1278
        lat2, lon2 = 51.6074, -0.1278  # Due north

        result = bearing(lat1, lon1, lat2, lon2)
        assert pytest.approx(result, abs=0.1) == 0

    @pytest.mark.unit
    def test_bearing_east(self):
        """Test bearing due east is approximately 90 degrees."""
        lat1, lon1 = 51.5074, -0.1278
        lat2, lon2 = 51.5074, -0.0278  # Due east

        result = bearing(lat1, lon1, lat2, lon2)
        assert pytest.approx(result, abs=0.1) == 90

    @pytest.mark.unit
    def test_bearing_south(self):
        """Test bearing due south is approximately 180 degrees."""
        lat1, lon1 = 51.5074, -0.1278
        lat2, lon2 = 51.4074, -0.1278  # Due south

        result = bearing(lat1, lon1, lat2, lon2)
        assert pytest.approx(result, abs=0.1) == 180

    @pytest.mark.unit
    def test_bearing_west(self):
        """Test bearing due west is approximately 270 degrees."""
        lat1, lon1 = 51.5074, -0.1278
        lat2, lon2 = 51.5074, -0.2278  # Due west

        result = bearing(lat1, lon1, lat2, lon2)
        assert pytest.approx(result, abs=0.1) == 270

    @pytest.mark.unit
    def test_bearing_range(self):
        """Test that bearing is always in range [0, 360)."""
        test_cases = [
            (51.5074, -0.1278, 51.6074, -0.0278),  # NE
            (51.5074, -0.1278, 51.4074, -0.0278),  # SE
            (51.5074, -0.1278, 51.4074, -0.2278),  # SW
            (51.5074, -0.1278, 51.6074, -0.2278),  # NW
        ]
        for lat1, lon1, lat2, lon2 in test_cases:
            result = bearing(lat1, lon1, lat2, lon2)
            assert 0 <= result < 360


class TestAngleDifference:
    """Tests for angle difference calculation."""

    @pytest.mark.unit
    @pytest.mark.parametrize("angle1,angle2,expected", [
        (0, 90, 90),       # Quarter turn right
        (90, 0, -90),      # Quarter turn left
        (0, 180, 180),     # Half turn (or -180)
        (0, 270, -90),     # Three-quarter turn = -90
        (350, 10, 20),     # Across 0/360 boundary
        (10, 350, -20),    # Across 0/360 boundary, other direction
        (45, 45, 0),       # Same angle
        (0, 359, -1),      # Just before 360
    ])
    def test_angle_difference(self, angle1, angle2, expected):
        """Test angle difference returns smallest signed difference."""
        result = angle_difference(angle1, angle2)
        # Handle the special case of 180/-180
        if expected == 180:
            assert abs(result) == 180
        else:
            assert pytest.approx(result, abs=0.01) == expected

    @pytest.mark.unit
    def test_angle_difference_range(self):
        """Test that result is always in range [-180, 180]."""
        for angle1 in range(0, 360, 30):
            for angle2 in range(0, 360, 30):
                result = angle_difference(angle1, angle2)
                assert -180 <= result <= 180


class TestPointAlongBearing:
    """Tests for calculating points at distance and bearing."""

    @pytest.mark.unit
    def test_point_north_1km(self):
        """Test calculating a point 1km due north."""
        lat, lon = 51.5074, -0.1278
        result_lat, result_lon = point_along_bearing(lat, lon, 0, 1000)

        # Should be approximately 0.009 degrees north
        assert result_lat > lat
        assert pytest.approx(result_lon, abs=0.0001) == lon

    @pytest.mark.unit
    def test_point_east_1km(self):
        """Test calculating a point 1km due east."""
        lat, lon = 51.5074, -0.1278
        result_lat, result_lon = point_along_bearing(lat, lon, 90, 1000)

        # Should be approximately same latitude, further east
        assert pytest.approx(result_lat, abs=0.0001) == lat
        assert result_lon > lon

    @pytest.mark.unit
    def test_round_trip(self):
        """Test that going forward then calculating distance gives same distance."""
        lat, lon = 51.5074, -0.1278
        distance = 5000  # 5 km
        bearing_deg = 45

        # Calculate point at distance
        new_lat, new_lon = point_along_bearing(lat, lon, bearing_deg, distance)

        # Calculate distance back
        result_distance = haversine_distance(lat, lon, new_lat, new_lon)
        assert pytest.approx(result_distance, rel=0.001) == distance

    @pytest.mark.unit
    def test_zero_distance(self):
        """Test that zero distance returns same point."""
        lat, lon = 51.5074, -0.1278
        result_lat, result_lon = point_along_bearing(lat, lon, 45, 0)

        assert pytest.approx(result_lat, rel=1e-9) == lat
        assert pytest.approx(result_lon, rel=1e-9) == lon


class TestClosestPointOnSegment:
    """Tests for finding closest point on a line segment."""

    @pytest.mark.unit
    def test_point_on_segment(self):
        """Test when query point projects onto the segment."""
        point = (51.5074, -0.1278)
        seg_start = (51.5074, -0.1378)
        seg_end = (51.5074, -0.1178)

        closest, t = closest_point_on_segment(point, seg_start, seg_end)

        # Point should be approximately at t=0.5 (middle of segment)
        assert pytest.approx(t, abs=0.1) == 0.5
        # Closest point should be very close to query point
        dist = haversine_distance(point[0], point[1], closest[0], closest[1])
        assert dist < 10  # Within 10 metres

    @pytest.mark.unit
    def test_closest_to_start(self):
        """Test when closest point is the start of segment."""
        point = (51.5174, -0.1378)  # Northwest of segment
        seg_start = (51.5074, -0.1278)
        seg_end = (51.5074, -0.1178)

        closest, t = closest_point_on_segment(point, seg_start, seg_end)

        # Should be clamped to start (t=0)
        assert t == 0
        assert closest == seg_start

    @pytest.mark.unit
    def test_closest_to_end(self):
        """Test when closest point is the end of segment."""
        point = (51.5174, -0.1078)  # Northeast of segment end
        seg_start = (51.5074, -0.1278)
        seg_end = (51.5074, -0.1178)

        closest, t = closest_point_on_segment(point, seg_start, seg_end)

        # Should be clamped to end (t=1)
        assert t == 1
        assert closest == seg_end

    @pytest.mark.unit
    def test_degenerate_segment(self):
        """Test when segment has zero length (start == end)."""
        point = (51.5174, -0.1278)
        seg_start = (51.5074, -0.1278)
        seg_end = (51.5074, -0.1278)  # Same as start

        closest, t = closest_point_on_segment(point, seg_start, seg_end)

        assert t == 0
        assert closest == seg_start


class TestCalculateCurvature:
    """Tests for curvature calculation using three points."""

    @pytest.mark.unit
    def test_straight_line_zero_curvature(self):
        """Test that three collinear points have zero curvature."""
        p1 = (51.5074, -0.1378)
        p2 = (51.5074, -0.1278)
        p3 = (51.5074, -0.1178)

        result = calculate_curvature(p1, p2, p3)
        assert pytest.approx(result, abs=1e-6) == 0

    @pytest.mark.unit
    def test_left_turn_nonzero(self):
        """Test that a left turn produces non-zero curvature."""
        # Going east, then turning left (north)
        p1 = (51.5074, -0.1378)  # Start
        p2 = (51.5074, -0.1278)  # East
        p3 = (51.5174, -0.1278)  # Turn north (left)

        result = calculate_curvature(p1, p2, p3)
        assert result != 0

    @pytest.mark.unit
    def test_right_turn_opposite_sign(self):
        """Test that a right turn has opposite sign to left turn."""
        # Going east, then turning left (north)
        p1 = (51.5074, -0.1378)  # Start
        p2 = (51.5074, -0.1278)  # East
        p3_left = (51.5174, -0.1278)  # Turn north (left)

        # Going east, then turning right (south)
        p3_right = (51.4974, -0.1278)  # Turn south (right)

        left_curvature = calculate_curvature(p1, p2, p3_left)
        right_curvature = calculate_curvature(p1, p2, p3_right)

        # Left and right turns should have opposite signs
        assert left_curvature * right_curvature < 0

    @pytest.mark.unit
    def test_tighter_turn_higher_curvature(self):
        """Test that tighter turns have higher absolute curvature."""
        # Start and middle point the same
        p1 = (51.5074, -0.1378)
        p2 = (51.5074, -0.1278)

        # Gentle left turn
        p3_gentle = (51.5084, -0.1178)
        curvature_gentle = abs(calculate_curvature(p1, p2, p3_gentle))

        # Sharp left turn
        p3_sharp = (51.5174, -0.1278)
        curvature_sharp = abs(calculate_curvature(p1, p2, p3_sharp))

        assert curvature_sharp > curvature_gentle

    @pytest.mark.unit
    def test_curvature_with_tuple_points(self):
        """Test that curvature works with tuple points."""
        p1 = (51.5074, -0.1378)
        p2 = (51.5074, -0.1278)
        p3 = (51.5174, -0.1278)

        # Should not raise
        result = calculate_curvature(p1, p2, p3)
        assert isinstance(result, float)


class TestCumulativeDistances:
    """Tests for cumulative distance calculation along a path."""

    @pytest.mark.unit
    def test_single_point(self):
        """Test cumulative distance for single point is [0]."""
        points = [(51.5074, -0.1278)]
        result = cumulative_distances(points)
        assert result == [0.0]

    @pytest.mark.unit
    def test_two_points(self):
        """Test cumulative distance for two points."""
        points = [
            (51.5074, -0.1278),
            (51.5174, -0.1278),  # ~1.1 km north
        ]
        result = cumulative_distances(points)

        assert len(result) == 2
        assert result[0] == 0.0
        assert result[1] > 1000  # More than 1 km

    @pytest.mark.unit
    def test_rectangular_path(self, sample_gps_path):
        """Test cumulative distances along a rectangular path."""
        result = cumulative_distances(sample_gps_path)

        assert len(result) == len(sample_gps_path)
        assert result[0] == 0.0
        # Each subsequent distance should be greater
        for i in range(1, len(result)):
            assert result[i] > result[i - 1]

    @pytest.mark.unit
    def test_cumulative_monotonic(self):
        """Test that cumulative distances are monotonically increasing."""
        # Random path
        points = [
            (51.5074, -0.1278),
            (51.5084, -0.1268),
            (51.5094, -0.1258),
            (51.5104, -0.1248),
        ]
        result = cumulative_distances(points)

        for i in range(1, len(result)):
            assert result[i] >= result[i - 1]

    @pytest.mark.unit
    def test_return_to_start(self):
        """Test path that returns to start has expected total distance."""
        # Square path, each side ~700m
        points = [
            (51.5074, -0.1278),
            (51.5074, -0.1178),  # East
            (51.5134, -0.1178),  # North
            (51.5134, -0.1278),  # West
            (51.5074, -0.1278),  # South (back to start)
        ]
        result = cumulative_distances(points)

        # Total should be approximately 4 * 700m = 2800m
        total = result[-1]
        assert 2500 < total < 3500
