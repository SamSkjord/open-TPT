"""
GPS test data fixtures for geometry tests.
Contains known GPS coordinates and expected calculations for testing.
"""

# Major cities with known approximate distances
CITY_COORDINATES = {
    'london': (51.5074, -0.1278),
    'paris': (48.8566, 2.3522),
    'berlin': (52.5200, 13.4050),
    'madrid': (40.4168, -3.7038),
    'rome': (41.9028, 12.4964),
    'amsterdam': (52.3676, 4.9041),
    'brussels': (50.8503, 4.3517),
    'vienna': (48.2082, 16.3738),
    'tokyo': (35.6762, 139.6503),
    'new_york': (40.7128, -74.0060),
    'sydney': (-33.8688, 151.2093),
    'quito': (-0.1807, -78.4678),  # Near equator
}

# Known distances between cities (in metres, approximate)
CITY_DISTANCES = {
    ('london', 'paris'): 344_000,       # ~344 km
    ('london', 'amsterdam'): 358_000,   # ~358 km
    ('london', 'brussels'): 322_000,    # ~322 km
    ('paris', 'berlin'): 878_000,       # ~878 km
    ('paris', 'madrid'): 1054_000,      # ~1054 km
    ('london', 'new_york'): 5_570_000,  # ~5570 km (transatlantic)
    ('sydney', 'tokyo'): 7_820_000,     # ~7820 km
}

# Test tracks - simplified circuit layouts
TEST_TRACKS = {
    # Simple oval track (approx 2km)
    'oval': [
        (51.5074, -0.1278),   # Start/finish
        (51.5074, -0.1178),   # First straight end
        (51.5134, -0.1178),   # First corner
        (51.5134, -0.1278),   # Second straight end
        (51.5074, -0.1278),   # Back to start
    ],
    # Figure-8 track
    'figure8': [
        (51.5074, -0.1278),   # Centre point
        (51.5124, -0.1228),   # NE
        (51.5124, -0.1328),   # NW
        (51.5074, -0.1278),   # Centre (crossing)
        (51.5024, -0.1328),   # SW
        (51.5024, -0.1228),   # SE
        (51.5074, -0.1278),   # Back to centre
    ],
    # S-curve section
    's_curve': [
        (51.5074, -0.1378),   # Entry
        (51.5074, -0.1328),   # Approach first turn
        (51.5094, -0.1278),   # Apex first turn (left)
        (51.5094, -0.1228),   # Transition
        (51.5074, -0.1178),   # Apex second turn (right)
        (51.5074, -0.1128),   # Exit
    ],
    # Hairpin turn
    'hairpin': [
        (51.5074, -0.1278),   # Approach
        (51.5074, -0.1228),   # Braking zone
        (51.5084, -0.1208),   # Turn-in
        (51.5094, -0.1208),   # Apex
        (51.5104, -0.1208),   # Exit
        (51.5104, -0.1228),   # Acceleration
        (51.5104, -0.1278),   # Full throttle
    ],
    # Chicane
    'chicane': [
        (51.5074, -0.1378),   # Entry
        (51.5084, -0.1328),   # Left kink
        (51.5074, -0.1278),   # Centre
        (51.5064, -0.1228),   # Right kink
        (51.5074, -0.1178),   # Exit
    ],
}

# Cardinal direction test points
# Used for bearing calculations
CARDINAL_POINTS = {
    'origin': (51.5074, -0.1278),
    # Points approximately 1km in each cardinal direction
    'north': (51.5164, -0.1278),   # ~1km north
    'east': (51.5074, -0.1134),    # ~1km east (adjusted for latitude)
    'south': (51.4984, -0.1278),   # ~1km south
    'west': (51.5074, -0.1422),    # ~1km west (adjusted for latitude)
}

# Expected bearings from origin to cardinal points
EXPECTED_BEARINGS = {
    'north': 0,
    'east': 90,
    'south': 180,
    'west': 270,
}

# Curvature test paths
CURVATURE_PATHS = {
    # Straight line - zero curvature
    'straight': [
        (51.5074, -0.1378),
        (51.5074, -0.1278),
        (51.5074, -0.1178),
    ],
    # Gentle left turn - positive curvature
    'gentle_left': [
        (51.5074, -0.1378),
        (51.5074, -0.1278),
        (51.5094, -0.1178),
    ],
    # Sharp left turn (90 degrees) - higher positive curvature
    'sharp_left': [
        (51.5074, -0.1378),
        (51.5074, -0.1278),
        (51.5174, -0.1278),
    ],
    # Gentle right turn - negative curvature
    'gentle_right': [
        (51.5074, -0.1378),
        (51.5074, -0.1278),
        (51.5054, -0.1178),
    ],
    # Sharp right turn (90 degrees) - higher negative curvature
    'sharp_right': [
        (51.5074, -0.1378),
        (51.5074, -0.1278),
        (51.4974, -0.1278),
    ],
}

# Rally stage segments with corner severities (ASC 1-6 scale)
# 1 = flat, 6 = hairpin
RALLY_CORNERS = {
    'flat': {
        'path': [
            (51.5074, -0.1378),
            (51.5074, -0.1278),
            (51.5074, -0.1178),
        ],
        'expected_severity': 1,
    },
    'easy': {
        'path': [
            (51.5074, -0.1378),
            (51.5074, -0.1278),
            (51.5084, -0.1178),
        ],
        'expected_severity': 2,
    },
    'medium': {
        'path': [
            (51.5074, -0.1378),
            (51.5074, -0.1278),
            (51.5104, -0.1208),
        ],
        'expected_severity': 3,
    },
    'tight': {
        'path': [
            (51.5074, -0.1378),
            (51.5074, -0.1278),
            (51.5134, -0.1258),
        ],
        'expected_severity': 4,
    },
    'very_tight': {
        'path': [
            (51.5074, -0.1378),
            (51.5074, -0.1278),
            (51.5154, -0.1278),
        ],
        'expected_severity': 5,
    },
    'hairpin': {
        'path': [
            (51.5074, -0.1378),
            (51.5074, -0.1278),
            (51.5074, -0.1378),  # U-turn
        ],
        'expected_severity': 6,
    },
}

# Segment projection test cases
SEGMENT_PROJECTION = {
    'on_segment': {
        'point': (51.5074, -0.1278),
        'seg_start': (51.5074, -0.1378),
        'seg_end': (51.5074, -0.1178),
        'expected_t': 0.5,  # Middle of segment
    },
    'before_segment': {
        'point': (51.5074, -0.1478),
        'seg_start': (51.5074, -0.1378),
        'seg_end': (51.5074, -0.1178),
        'expected_t': 0.0,  # Clamped to start
    },
    'after_segment': {
        'point': (51.5074, -0.1078),
        'seg_start': (51.5074, -0.1378),
        'seg_end': (51.5074, -0.1178),
        'expected_t': 1.0,  # Clamped to end
    },
}
