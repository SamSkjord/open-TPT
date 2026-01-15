"""
Track loader for lap timing system.

Loads track data from KMZ files (RaceLogic converted tracks).
"""

import os
import zipfile
import xml.etree.ElementTree as ET
from typing import List, Tuple, Optional
from dataclasses import dataclass
from lap_timing.data.models import StartFinishLine
from lap_timing.utils.geometry import haversine_distance
from lap_timing import config


@dataclass
class TrackPoint:
    """Single point on track boundary or centerline."""
    lat: float
    lon: float
    distance: float = 0.0  # Cumulative distance from start


@dataclass
class Track:
    """Complete track definition."""
    name: str
    outer_boundary: List[TrackPoint]
    inner_boundary: List[TrackPoint]
    centerline: List[TrackPoint]
    sf_line: StartFinishLine
    length: float  # Total track length in meters


def parse_kml_coordinates(coord_text: str) -> List[Tuple[float, float]]:
    """
    Parse KML coordinate string into list of (lat, lon) tuples.

    Handles both formats:
    - Newline-separated: "lon,lat,alt\\nlon,lat,alt\\n..."
    - Space-separated: "lon,lat,alt lon,lat,alt ..."

    Args:
        coord_text: Coordinate string from KML (lon,lat,alt format)

    Returns:
        List of (lat, lon) tuples
    """
    points = []

    # Normalize whitespace - replace newlines with spaces, then split
    coord_text = coord_text.strip().replace('\n', ' ').replace('\t', ' ')

    # Split by whitespace to get individual coordinate tuples
    for coord in coord_text.split():
        coord = coord.strip()
        if not coord:
            continue

        parts = coord.split(',')
        if len(parts) >= 2:
            try:
                lon = float(parts[0])
                lat = float(parts[1])
                points.append((lat, lon))
            except ValueError:
                continue

    return points


def calculate_cumulative_distances(points: List[Tuple[float, float]]) -> List[TrackPoint]:
    """
    Convert coordinate list to TrackPoint list with cumulative distances.

    Args:
        points: List of (lat, lon) tuples

    Returns:
        List of TrackPoint objects with distance calculated
    """
    if not points:
        return []

    track_points = []
    cumulative_distance = 0.0

    # First point
    track_points.append(TrackPoint(
        lat=points[0][0],
        lon=points[0][1],
        distance=0.0
    ))

    # Calculate cumulative distances
    for i in range(1, len(points)):
        prev_lat, prev_lon = points[i-1]
        curr_lat, curr_lon = points[i]

        segment_distance = haversine_distance(prev_lat, prev_lon, curr_lat, curr_lon)
        cumulative_distance += segment_distance

        track_points.append(TrackPoint(
            lat=curr_lat,
            lon=curr_lon,
            distance=cumulative_distance
        ))

    return track_points


def interpolate_coordinates(coords: List[Tuple[float, float]], target_spacing: float = 5.0) -> List[Tuple[float, float]]:
    """
    Interpolate coordinates to achieve consistent spacing.

    Args:
        coords: List of (lat, lon) tuples
        target_spacing: Target distance between points in meters

    Returns:
        Interpolated coordinates with consistent spacing
    """
    if len(coords) < 2:
        return coords

    interpolated = [coords[0]]
    accumulated = 0.0

    for i in range(1, len(coords)):
        prev_lat, prev_lon = coords[i-1]
        curr_lat, curr_lon = coords[i]

        segment_dist = haversine_distance(prev_lat, prev_lon, curr_lat, curr_lon)

        if segment_dist < 0.001:  # Skip duplicate points
            continue

        # Interpolate points along this segment
        remaining = target_spacing - accumulated
        dist_along = remaining

        while dist_along <= segment_dist:
            # Linear interpolation
            t = dist_along / segment_dist
            new_lat = prev_lat + t * (curr_lat - prev_lat)
            new_lon = prev_lon + t * (curr_lon - prev_lon)
            interpolated.append((new_lat, new_lon))
            dist_along += target_spacing

        accumulated = segment_dist - (dist_along - target_spacing)

    # Always include the last point
    if interpolated[-1] != coords[-1]:
        interpolated.append(coords[-1])

    return interpolated


def smooth_coordinates(coords: List[Tuple[float, float]], window: int = 3) -> List[Tuple[float, float]]:
    """
    Apply moving average smoothing to coordinates.

    Args:
        coords: List of (lat, lon) tuples
        window: Smoothing window size (must be odd)

    Returns:
        Smoothed coordinates
    """
    if len(coords) < window:
        return coords

    # Ensure window is odd
    if window % 2 == 0:
        window += 1

    half_window = window // 2
    smoothed = []

    for i in range(len(coords)):
        # Get window bounds (handle edges)
        start = max(0, i - half_window)
        end = min(len(coords), i + half_window + 1)

        # Average within window
        avg_lat = sum(c[0] for c in coords[start:end]) / (end - start)
        avg_lon = sum(c[1] for c in coords[start:end]) / (end - start)
        smoothed.append((avg_lat, avg_lon))

    return smoothed


def upsample_boundary(points: List[TrackPoint], target_spacing: float = 2.0) -> List[TrackPoint]:
    """
    Upsample boundary to consistent point spacing.

    Args:
        points: Boundary points
        target_spacing: Target distance between points in meters

    Returns:
        Upsampled boundary points with consistent spacing
    """
    if len(points) < 2:
        return points

    coords = [(p.lat, p.lon) for p in points]
    upsampled = interpolate_coordinates(coords, target_spacing)
    return calculate_cumulative_distances(upsampled)


def align_boundaries(
    outer: List[TrackPoint],
    inner: List[TrackPoint]
) -> Tuple[List[TrackPoint], List[TrackPoint]]:
    """
    Align inner boundary to start at same position as outer boundary and go same direction.

    For loop tracks, boundaries may start at different positions around the track
    and may go in opposite directions. This function:
    1. Rotates the inner boundary so both start at the same position
    2. Reverses the inner boundary if it's going the opposite direction

    Args:
        outer: Outer boundary points
        inner: Inner boundary points

    Returns:
        Tuple of (outer, aligned_inner) where inner starts at same position and goes same direction
    """
    if len(inner) < 3 or len(outer) < 3:
        return outer, inner

    # First, check if boundaries are going in opposite directions
    # Compare the direction of travel from start: which way does each boundary go?
    # Use the second point to determine initial direction
    outer_dir_lat = outer[1].lat - outer[0].lat
    outer_dir_lon = outer[1].lon - outer[0].lon

    inner_dir_lat = inner[1].lat - inner[0].lat
    inner_dir_lon = inner[1].lon - inner[0].lon

    # Calculate dot product to see if directions are aligned or opposite
    # Positive dot product = same general direction, Negative = opposite
    dot_product = outer_dir_lat * inner_dir_lat + outer_dir_lon * inner_dir_lon

    # Check if inner boundary is going opposite direction (negative dot product)
    inner_reversed = False
    if dot_product < 0:
        # Boundaries are going opposite directions - reverse inner
        inner_is_closed = (inner[0].lat == inner[-1].lat and inner[0].lon == inner[-1].lon)
        if inner_is_closed:
            # For closed boundary, reverse the core and re-close
            inner_core = inner[:-1]
            inner = list(reversed(inner_core))
            inner.append(inner[0])
        else:
            inner = list(reversed(inner))

        # Recalculate cumulative distances after reversing
        inner_coords = [(p.lat, p.lon) for p in inner]
        inner = calculate_cumulative_distances(inner_coords)
        inner_reversed = True

    # Now find inner point closest to outer's start and rotate to align
    outer_start = outer[0]
    min_dist = float('inf')
    align_idx = 0

    for i, p in enumerate(inner):
        dist = haversine_distance(outer_start.lat, outer_start.lon, p.lat, p.lon)
        if dist < min_dist:
            min_dist = dist
            align_idx = i

    # Rotate inner boundary to start at aligned point
    inner_is_closed = (inner[0].lat == inner[-1].lat and inner[0].lon == inner[-1].lon)

    if inner_is_closed:
        # Exclude duplicate last point, rotate, then re-close
        inner_core = inner[:-1]
        rotated = inner_core[align_idx:] + inner_core[:align_idx]
        rotated.append(rotated[0])  # Re-close
    else:
        rotated = inner[align_idx:] + inner[:align_idx]

    # Recalculate cumulative distances for rotated inner
    rotated_coords = [(p.lat, p.lon) for p in rotated]
    aligned_inner = calculate_cumulative_distances(rotated_coords)

    return outer, aligned_inner


def generate_centerline_from_boundaries(
    outer: List[TrackPoint],
    inner: List[TrackPoint],
    num_points: int = 500,
    smooth: bool = True
) -> List[TrackPoint]:
    """
    Generate centerline from outer and inner boundaries.

    Uses closest-point matching: for each outer point, find nearest inner point
    and average them to create centerline point. Optionally applies smoothing to
    reduce kinks from imperfect boundary matching.

    Args:
        outer: Outer boundary points
        inner: Inner boundary points
        num_points: Number of points to resample to
        smooth: Whether to apply smoothing (disable for point-to-point tracks)

    Returns:
        Centerline points with cumulative distances
    """
    # Resample outer boundary to desired number of points
    if len(outer) > num_points:
        # Simple resampling - take every nth point
        step = len(outer) / num_points
        outer_resampled = [outer[int(i * step)] for i in range(num_points)]
    else:
        outer_resampled = outer

    # Generate centerline by finding closest inner point for each outer point
    centerline_coords = []

    for o in outer_resampled:
        # Find closest point on inner boundary
        min_dist = float('inf')
        closest_inner = None

        for i in inner:
            dist = haversine_distance(o.lat, o.lon, i.lat, i.lon)
            if dist < min_dist:
                min_dist = dist
                closest_inner = i

        if closest_inner:
            # Average the two points
            avg_lat = (o.lat + closest_inner.lat) / 2
            avg_lon = (o.lon + closest_inner.lon) / 2
            centerline_coords.append((avg_lat, avg_lon))

    # Optionally smooth the centerline to reduce kinks from boundary misalignment
    if smooth:
        centerline_coords = smooth_coordinates(centerline_coords, window=5)

    # Calculate cumulative distances for centerline
    return calculate_cumulative_distances(centerline_coords)


def _interpolate_point_at_distance(
    points: List[TrackPoint],
    target_distance: float
) -> Optional[Tuple[float, float]]:
    """
    Find point at specific distance along boundary using linear interpolation.

    Args:
        points: Boundary points with cumulative distances
        target_distance: Target distance in meters

    Returns:
        (lat, lon) tuple at target distance, or None if not found
    """
    if not points:
        return None

    # Handle edge cases
    if target_distance <= 0:
        return (points[0].lat, points[0].lon)
    if target_distance >= points[-1].distance:
        return (points[-1].lat, points[-1].lon)

    # Find segment containing target distance
    for i in range(len(points) - 1):
        if points[i].distance <= target_distance <= points[i + 1].distance:
            # Linear interpolation within segment
            segment_length = points[i + 1].distance - points[i].distance
            if segment_length == 0:
                return (points[i].lat, points[i].lon)

            t = (target_distance - points[i].distance) / segment_length
            lat = points[i].lat + t * (points[i + 1].lat - points[i].lat)
            lon = points[i].lon + t * (points[i + 1].lon - points[i].lon)
            return (lat, lon)

    return (points[-1].lat, points[-1].lon)


def load_track_from_kmz(kmz_path: str) -> Track:
    """
    Load track from KMZ file.

    Args:
        kmz_path: Path to KMZ file

    Returns:
        Track object with boundaries, centerline, and S/F line
    """
    # Extract KML from KMZ
    with zipfile.ZipFile(kmz_path, 'r') as kmz:
        # KMZ files contain a doc.kml file
        kml_content = kmz.read('doc.kml').decode('utf-8')

    # Parse KML
    root = ET.fromstring(kml_content)

    # Define namespace
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}

    # Extract track name
    track_name = root.find('.//kml:Document/kml:name', ns)
    if track_name is not None:
        track_name = track_name.text
    else:
        track_name = os.path.basename(kmz_path).replace('.kmz', '')

    # Find placemarks
    outer_boundary = None
    inner_boundary = None
    track_path = None  # For simple KMZ format (single path, no boundaries)
    sf_line = None
    sf_point = None  # For simple KMZ format (point marker instead of line)
    finish_point = None  # For point-to-point tracks

    for placemark in root.findall('.//kml:Placemark', ns):
        name_elem = placemark.find('kml:name', ns)
        if name_elem is None:
            continue

        name = name_elem.text

        if name == 'Outer Boundary':
            coords_elem = placemark.find('.//kml:coordinates', ns)
            if coords_elem is not None:
                outer_boundary = parse_kml_coordinates(coords_elem.text)

        elif name == 'Inner Boundary':
            coords_elem = placemark.find('.//kml:coordinates', ns)
            if coords_elem is not None:
                inner_boundary = parse_kml_coordinates(coords_elem.text)

        elif name == 'Track Path':
            # Simple format: single path representing the track
            coords_elem = placemark.find('.//kml:coordinates', ns)
            if coords_elem is not None:
                track_path = parse_kml_coordinates(coords_elem.text)

        elif name == 'Start / Finish Line':
            coords_elem = placemark.find('.//kml:coordinates', ns)
            if coords_elem is not None:
                sf_coords = parse_kml_coordinates(coords_elem.text)
                if len(sf_coords) >= 2:
                    point1 = sf_coords[0]
                    point2 = sf_coords[1]
                    center = (
                        (point1[0] + point2[0]) / 2,
                        (point1[1] + point2[1]) / 2
                    )

                    # Calculate heading
                    import math
                    dx = point2[1] - point1[1]
                    dy = point2[0] - point1[0]
                    heading = math.degrees(math.atan2(dy, dx))

                    # Calculate width
                    width = haversine_distance(
                        point1[0], point1[1],
                        point2[0], point2[1]
                    )

                    sf_line = StartFinishLine(
                        point1=point1,
                        point2=point2,
                        center=center,
                        heading=heading,
                        width=width
                    )

        elif name in ('Start / Finish', 'Start', 'Start/Finish'):
            # Simple format: point marker for S/F
            point_elem = placemark.find('.//kml:Point/kml:coordinates', ns)
            if point_elem is not None:
                coords = point_elem.text.strip().split(',')
                if len(coords) >= 2:
                    sf_point = (float(coords[1]), float(coords[0]))  # (lat, lon)

        elif name == 'Finish':
            # Point-to-point: separate finish waypoint
            point_elem = placemark.find('.//kml:Point/kml:coordinates', ns)
            if point_elem is not None:
                coords = point_elem.text.strip().split(',')
                if len(coords) >= 2:
                    finish_point = (float(coords[1]), float(coords[0]))  # (lat, lon)

    # Handle simple format: Track Path without boundaries
    if outer_boundary is None and track_path is not None:
        # Check if this is a point-to-point track (separate Start and Finish waypoints)
        if sf_point and finish_point and len(track_path) > 10:
            # Point-to-point: track_path is a closed boundary loop
            # Find the boundary points closest to Start and Finish
            start_lat, start_lon = sf_point
            finish_lat, finish_lon = finish_point

            # Find closest boundary point to Start
            min_start_dist = float('inf')
            start_idx = 0
            for i, (lat, lon) in enumerate(track_path):
                dist = haversine_distance(lat, lon, start_lat, start_lon)
                if dist < min_start_dist:
                    min_start_dist = dist
                    start_idx = i

            # Find closest boundary point to Finish
            min_finish_dist = float('inf')
            finish_idx = 0
            for i, (lat, lon) in enumerate(track_path):
                dist = haversine_distance(lat, lon, finish_lat, finish_lon)
                if dist < min_finish_dist:
                    min_finish_dist = dist
                    finish_idx = i

            # Split boundary into two halves at start and finish points
            # Ensure start_idx < finish_idx for consistent splitting
            if start_idx > finish_idx:
                start_idx, finish_idx = finish_idx, start_idx
                # Swap start/finish points too
                sf_point, finish_point = finish_point, sf_point

            # Path 1: from start to finish (one side of track)
            path1 = track_path[start_idx:finish_idx + 1]

            # Path 2: from finish back to start (other side, via wrap-around)
            path2 = track_path[finish_idx:] + track_path[:start_idx + 1]
            path2 = list(reversed(path2))  # Reverse so it goes same direction

            # Use path1 as outer, path2 as inner
            outer_boundary = path1
            inner_boundary = path2

        # Check if this is a combined inner/outer boundary path (loop track)
        # (path that goes around twice, crossing over at S/F)
        elif sf_point and not finish_point and len(track_path) > 10:
            # Find where the path comes closest to S/F point (excluding start/end)
            sf_lat, sf_lon = sf_point
            min_dist = float('inf')
            crossover_idx = None

            # Search middle portion of path for crossover point
            search_start = len(track_path) // 4
            search_end = 3 * len(track_path) // 4

            for i in range(search_start, search_end):
                dist = haversine_distance(track_path[i][0], track_path[i][1], sf_lat, sf_lon)
                if dist < min_dist:
                    min_dist = dist
                    crossover_idx = i

            # If crossover point is close to S/F (within 50m), split the path
            if crossover_idx and min_dist < 50:
                # Split into two boundaries
                outer_boundary = track_path[:crossover_idx + 1]
                inner_boundary = track_path[crossover_idx:]
                # Reverse inner so both go the same direction around the track
                inner_boundary = list(reversed(inner_boundary))

                # Close the boundaries by adding the start point if needed
                # Outer should close back to its start
                if outer_boundary[0] != outer_boundary[-1]:
                    outer_boundary.append(outer_boundary[0])
                # Inner should also close back to its start
                if inner_boundary[0] != inner_boundary[-1]:
                    inner_boundary.append(inner_boundary[0])
            else:
                # No crossover found - use path as centerline
                outer_boundary = track_path
                inner_boundary = track_path
        else:
            # Use track path as centerline, generate synthetic boundaries
            outer_boundary = track_path
            inner_boundary = track_path

    # Handle simple format: S/F point instead of line
    if sf_line is None and sf_point is not None:
        import math
        # Create S/F line perpendicular to track at S/F point
        # Find closest point on track to get direction
        sf_lat, sf_lon = sf_point

        # Default width (10 meters in degrees, approximately)
        width_deg = 0.0001  # ~10m

        # Find track direction at S/F point
        if track_path and len(track_path) >= 2:
            # Find closest segment
            min_dist = float('inf')
            closest_idx = 0
            for i, (lat, lon) in enumerate(track_path):
                dist = (lat - sf_lat)**2 + (lon - sf_lon)**2
                if dist < min_dist:
                    min_dist = dist
                    closest_idx = i

            # Get direction from neighboring points
            n = len(track_path)
            prev_idx = max(0, closest_idx - 1)
            next_idx = min(n - 1, closest_idx + 1)

            dx = track_path[next_idx][1] - track_path[prev_idx][1]  # lon diff
            dy = track_path[next_idx][0] - track_path[prev_idx][0]  # lat diff
            length = math.sqrt(dx*dx + dy*dy)

            if length > 0:
                # Perpendicular direction
                perp_dx = -dy / length * width_deg
                perp_dy = dx / length * width_deg
            else:
                perp_dx, perp_dy = width_deg, 0
        else:
            perp_dx, perp_dy = width_deg, 0

        point1 = (sf_lat - perp_dy, sf_lon - perp_dx)
        point2 = (sf_lat + perp_dy, sf_lon + perp_dx)

        sf_line = StartFinishLine(
            point1=point1,
            point2=point2,
            center=sf_point,
            heading=math.degrees(math.atan2(perp_dy, perp_dx)),
            width=haversine_distance(point1[0], point1[1], point2[0], point2[1])
        )

    # Validate we got the required data
    if outer_boundary is None or inner_boundary is None:
        raise ValueError(f"Track boundaries not found in {kmz_path}")

    if sf_line is None:
        raise ValueError(f"Start/Finish line not found in {kmz_path}")

    # Convert to TrackPoint objects with cumulative distances
    outer_points = calculate_cumulative_distances(outer_boundary)
    inner_points = calculate_cumulative_distances(inner_boundary)

    # Determine if this is a point-to-point track (needs different processing)
    is_point_to_point = finish_point is not None and sf_point is not None

    # Generate centerline - disable smoothing for point-to-point to preserve sharp corners
    centerline_points = generate_centerline_from_boundaries(
        outer_points,
        inner_points,
        num_points=500,
        smooth=not is_point_to_point  # Don't smooth point-to-point tracks
    )

    # For point-to-point tracks, trim centerline to actual start/finish waypoints
    if is_point_to_point and centerline_points:
        start_lat, start_lon = sf_point
        finish_lat, finish_lon = finish_point

        # Find centerline point closest to start
        min_start_dist = float('inf')
        start_cl_idx = 0
        for i, p in enumerate(centerline_points):
            dist = haversine_distance(p.lat, p.lon, start_lat, start_lon)
            if dist < min_start_dist:
                min_start_dist = dist
                start_cl_idx = i

        # Find FIRST centerline point within threshold of finish (not closest overall)
        # This prevents including loops that pass finish and come back
        finish_threshold = 50.0  # meters
        finish_cl_idx = len(centerline_points) - 1
        for i, p in enumerate(centerline_points):
            if i <= start_cl_idx:  # Must be after start
                continue
            dist = haversine_distance(p.lat, p.lon, finish_lat, finish_lon)
            if dist < finish_threshold:
                finish_cl_idx = i
                break

        # If no point within threshold, fall back to closest point (but after start)
        if finish_cl_idx == len(centerline_points) - 1:
            min_finish_dist = float('inf')
            for i, p in enumerate(centerline_points):
                if i <= start_cl_idx:
                    continue
                dist = haversine_distance(p.lat, p.lon, finish_lat, finish_lon)
                if dist < min_finish_dist:
                    min_finish_dist = dist
                    finish_cl_idx = i

        # Trim centerline to start-finish section
        if start_cl_idx < finish_cl_idx:
            trimmed = centerline_points[start_cl_idx:finish_cl_idx + 1]
        else:
            trimmed = centerline_points[finish_cl_idx:start_cl_idx + 1]
            trimmed = list(reversed(trimmed))

        # Replace endpoints with actual waypoint coordinates for accuracy
        if trimmed:
            trimmed_coords = [(p.lat, p.lon) for p in trimmed]
            # Replace first point with actual start waypoint
            trimmed_coords[0] = sf_point
            # Replace last point with actual finish waypoint
            trimmed_coords[-1] = finish_point

            # Interpolate to 5m spacing to preserve sharp corners
            interpolated_coords = interpolate_coordinates(trimmed_coords, target_spacing=5.0)
            centerline_points = calculate_cumulative_distances(interpolated_coords)

    # For loop tracks (not point-to-point), reorder centerline to start at S/F and close the loop
    if not is_point_to_point and centerline_points and len(centerline_points) >= 2:
        # First, reorder centerline to start at the point closest to S/F line
        if sf_line is not None:
            sf_lat, sf_lon = sf_line.center
            min_dist = float('inf')
            sf_idx = 0
            for i, p in enumerate(centerline_points):
                dist = haversine_distance(p.lat, p.lon, sf_lat, sf_lon)
                if dist < min_dist:
                    min_dist = dist
                    sf_idx = i

            # Reorder: points from sf_idx to end, then points from 0 to sf_idx
            if sf_idx > 0:
                reordered = centerline_points[sf_idx:] + centerline_points[:sf_idx]
                # Recalculate cumulative distances from new start
                reordered_coords = [(p.lat, p.lon) for p in reordered]
                centerline_points = calculate_cumulative_distances(reordered_coords)

        first_pt = centerline_points[0]
        last_pt = centerline_points[-1]
        closure_distance = haversine_distance(first_pt.lat, first_pt.lon, last_pt.lat, last_pt.lon)

        # If first/last points are close but not the same, close the loop
        if closure_distance > 1.0 and closure_distance < 100.0:
            # Add first point at end to close the loop
            final_distance = last_pt.distance + closure_distance
            centerline_points.append(TrackPoint(
                lat=first_pt.lat,
                lon=first_pt.lon,
                distance=final_distance
            ))

    # Track length is the centerline length
    track_length = centerline_points[-1].distance if centerline_points else 0.0

    return Track(
        name=track_name,
        outer_boundary=outer_points,
        inner_boundary=inner_points,
        centerline=centerline_points,
        sf_line=sf_line,
        length=track_length
    )


def get_donington_track() -> Track:
    """
    Convenience function to load Donington National track.

    Returns:
        Track object for Donington National
    """
    kmz_path = os.path.join(
        config.RACELOGIC_TRACKS_DIR,
        'United Kingdom',
        'Donington National.kmz'
    )

    if not os.path.exists(kmz_path):
        raise FileNotFoundError(
            f"Donington National KMZ not found at {kmz_path}"
        )

    return load_track_from_kmz(kmz_path)
