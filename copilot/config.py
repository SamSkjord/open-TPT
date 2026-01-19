"""
CoPilot configuration.

These settings are tuned for road driving with OSM map data.
Different from lap_timing config which is optimised for track use.
"""

# Lookahead and navigation
LOOKAHEAD_DISTANCE_M = 1000  # How far ahead to analyse (metres)
ROAD_FETCH_RADIUS_M = 2000   # Radius to cache roads around current position
REFETCH_DISTANCE_M = 500     # Refetch roads when moved this far from last fetch
UPDATE_INTERVAL_S = 0.5      # Main loop update rate

# Corner detection (tuned for road driving - larger radii than track)
CORNER_MIN_RADIUS_M = 300.0   # Minimum radius to consider a corner (metres)
CORNER_MIN_ANGLE_DEG = 10.0   # Minimum total angle to consider a corner (degrees)

# Junction detection
JUNCTION_WARN_DISTANCE_M = 200  # Warn about T-junctions this far ahead
HEADING_TOLERANCE_DEG = 30.0    # Roads within this angle of heading are "straight on"

# Audio
TTS_VOICE = "Daniel"  # British male voice (macOS), falls back to en-gb on Linux
TTS_SPEED = 210       # Words per minute (faster for rally style)
