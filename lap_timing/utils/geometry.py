"""
Shared geometry functions for GPS calculations.
"""

import math


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate great circle distance between two GPS points in meters.
    
    Args:
        lat1, lon1: First point (decimal degrees)
        lat2, lon2: Second point (decimal degrees)
    
    Returns:
        Distance in meters
    """
    R = 6371000  # Earth's radius in meters
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c


def point_side_of_line(lat: float, lon: float, 
                       line_p1: tuple, line_p2: tuple) -> int:
    """
    Determine which side of a line a point is on.
    
    Args:
        lat, lon: Point coordinates
        line_p1, line_p2: Line endpoints (lat, lon)
    
    Returns:
        +1 if point is on left, -1 if on right
    """
    # Vector from line.p1 to line.p2
    line_vec = (line_p2[0] - line_p1[0], line_p2[1] - line_p1[1])
    
    # Vector from line.p1 to point
    point_vec = (lat - line_p1[0], lon - line_p1[1])
    
    # Cross product (2D)
    cross = line_vec[0] * point_vec[1] - line_vec[1] * point_vec[0]
    
    return 1 if cross > 0 else -1


def distance_to_line(lat: float, lon: float,
                    line_p1: tuple, line_p2: tuple) -> float:
    """
    Calculate perpendicular distance from point to line.
    
    Returns:
        Distance in meters
    """
    # Approximate using haversine for small distances
    # Project point onto line segment
    
    # For now, simple distance to midpoint
    midpoint = ((line_p1[0] + line_p2[0]) / 2, 
                (line_p1[1] + line_p2[1]) / 2)
    
    return haversine_distance(lat, lon, midpoint[0], midpoint[1])
