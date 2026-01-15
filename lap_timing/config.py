"""
Configuration file for lap timing system.

Contains settings for GPS filtering, track detection, visualization, etc.
"""

# =============================================================================
# GPS Kalman Filter Settings
# =============================================================================

# Enable Kalman filter by default (set to False for pre-filtered data like VBO files)
KALMAN_FILTER_ENABLED = False

# Kalman filter parameters
KALMAN_PROCESS_NOISE = 0.5      # Vehicle dynamics uncertainty (m/s²)
                                 # Lower = smoother but slower response
                                 # Higher = faster response but more noise
                                 # Typical: 0.1-1.0 for motorsport

KALMAN_MEASUREMENT_NOISE = 5.0  # GPS measurement uncertainty (meters)
                                 # Should match your GPS accuracy (±5m typical)
                                 # Lower = trust GPS more
                                 # Higher = trust prediction more

KALMAN_INITIAL_UNCERTAINTY = 10.0  # Initial position uncertainty (meters)
                                    # How uncertain we are about first position
                                    # Converges quickly, so not critical


# =============================================================================
# Track Database Settings
# =============================================================================

import os

# Root directory for track assets (relative to this file)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRACKS_ROOT = os.path.join(_BASE_DIR, 'assets', 'tracks')

# Database paths
TRACKS_DB_PATH = os.path.join(TRACKS_ROOT, 'tracks.db')         # Custom tracks
RACELOGIC_DB_PATH = os.path.join(TRACKS_ROOT, 'racelogic.db')   # RaceLogic tracks

# KMZ file directories
CUSTOM_TRACKS_DIR = os.path.join(TRACKS_ROOT, 'maps')           # Custom KMZ files
RACELOGIC_TRACKS_DIR = os.path.join(TRACKS_ROOT, 'racelogic')   # RaceLogic KMZ by country


# =============================================================================
# Track Detection Settings
# =============================================================================

TRACK_SEARCH_RADIUS_KM = 10.0   # Maximum distance to search for tracks (km)


# =============================================================================
# Corner Detection Settings
# =============================================================================

CORNER_MIN_RADIUS = 100.0       # Maximum radius to classify as corner (meters)
                                 # Smaller = detect tighter corners only
                                 # Larger = include gentler sweeps

CORNER_MIN_ANGLE = 15.0          # Minimum angle to consider a corner (degrees)
                                 # Filters out slight kinks in track
                                 # Typical: 10-20 degrees

# Chicane detection settings
CHICANE_MERGE_ENABLED = True     # Merge consecutive opposite-direction corners
CHICANE_MAX_GAP = 30.0           # Maximum gap between corners to merge (meters)
                                 # Smaller = stricter chicane detection
                                 # Larger = merge corners further apart
CHICANE_MAX_LENGTH = 200.0       # Maximum total chicane span (meters)
                                 # Prevents merging separate corner complexes


# =============================================================================
# Lap Detection Settings
# =============================================================================

MIN_LAP_TIME = 30.0             # Minimum valid lap time (seconds)
                                 # Prevents false S/F crossings
                                 # Set based on your shortest expected lap

MIN_LAP_DISTANCE_RATIO = 0.9    # Minimum distance ratio for valid lap
                                 # 0.9 = lap must cover 90% of track length
                                 # Filters out partial laps


# =============================================================================
# Visualization Settings
# =============================================================================

PLAYBACK_SPEED_DEFAULT = 3.0    # Default playback speed multiplier

# Display colors (matplotlib format)
COLOR_FASTER = '#00ff00'        # Bright green
COLOR_SLOWER = '#ff3333'        # Bright red
COLOR_ACTIVE = '#00ffff'        # Cyan
COLOR_NEW = '#ffff00'           # Yellow
COLOR_BEST = '#888888'          # Gray
COLOR_NO_DATA = '#666666'       # Dark gray
