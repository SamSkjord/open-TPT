"""
Lap Timing Handler for openTPT.

Integrates lap-timing-system components with BoundedQueueHardwareHandler pattern.
Consumes GPS data via lock-free snapshots and publishes lap timing data for display.
"""

import logging
import time
import os
from typing import Optional, List, Dict, Any

from utils.hardware_base import BoundedQueueHardwareHandler

logger = logging.getLogger('openTPT.lap_timing')
from config import (
    LAP_TIMING_ENABLED,
    TRACK_AUTO_DETECT,
    TRACK_SEARCH_RADIUS_KM,
    LAP_TIMING_DATA_DIR,
    LAP_TIMING_CORNER_DETECTOR,
    LAP_TIMING_CORNER_MIN_RADIUS_M,
    LAP_TIMING_CORNER_MIN_ANGLE_DEG,
    LAP_TIMING_CORNER_MIN_CUT_DISTANCE_M,
    LAP_TIMING_CORNER_STRAIGHT_FILL_M,
    LAP_TIMING_CORNER_MERGE_CHICANES,
)
from utils.settings import get_settings
from utils.lap_timing_store import get_lap_timing_store, LapRecord

# Import lap timing components
try:
    from lap_timing.core.lap_detector import LapDetector, LapCrossing
    from lap_timing.core.position_tracker import PositionTracker
    from lap_timing.core.delta_calculator import DeltaCalculator
    from lap_timing.data.models import GPSPoint, Lap, Delta, TrackPosition, Corner, CornerSpeedRecord
    from lap_timing.data.track_loader import Track
    from lap_timing.data.track_selector import TrackSelector
    from lap_timing.analysis.corner_analyzer import CornerAnalyzer
    from lap_timing.analysis.hybrid_corner_detector import HybridCornerDetector
    from lap_timing.analysis.asc_corner_detector import ASCCornerDetector
    from lap_timing.analysis.corner_detector import CornerDetector
    from lap_timing.analysis.curvefinder_detector import CurveFinderDetector
    LAP_TIMING_AVAILABLE = True
except ImportError as e:
    logger.warning("Lap timing modules not available: %s", e)
    LAP_TIMING_AVAILABLE = False


class LapTimingHandler(BoundedQueueHardwareHandler):
    """
    Lap timing handler integrating GPS with lap detection and delta calculation.

    Follows BoundedQueueHardwareHandler pattern:
    - Consumes GPS snapshots (lock-free)
    - Processes lap timing in worker thread
    - Publishes results for lock-free render access
    """

    def __init__(self, gps_handler, fuel_tracker=None):
        """
        Initialise lap timing handler.

        Args:
            gps_handler: GPSHandler instance to consume GPS data from
            fuel_tracker: Optional FuelTracker instance for fuel consumption tracking
        """
        super().__init__(queue_depth=2)
        self.gps_handler = gps_handler
        self.fuel_tracker = fuel_tracker
        self._settings = get_settings()

        # Check settings for enabled state, fallback to config
        settings_enabled = self._settings.get("lap_timing.enabled", LAP_TIMING_ENABLED)
        self.enabled = settings_enabled and LAP_TIMING_AVAILABLE

        # Track and timing state
        self.track: Optional[Track] = None
        self.track_selector: Optional[TrackSelector] = None
        self.lap_detector: Optional[LapDetector] = None
        self.position_tracker: Optional[PositionTracker] = None
        self.delta_calculator: Optional[DeltaCalculator] = None

        # Lap state
        self.current_lap_number = 0
        self.current_lap_start_time: Optional[float] = None
        self.current_lap_points: List[GPSPoint] = []
        self.laps: List[Lap] = []
        self.best_lap: Optional[Lap] = None  # Best lap in current session
        self.last_lap: Optional[Lap] = None
        self.stored_best_lap_time: Optional[float] = None  # Persisted best lap time

        # Sector state (3 sectors by default)
        self.sector_count = 3
        self.sector_boundaries: List[float] = []  # Distances from S/F
        self.current_sector = 0
        self.sector_times: List[Optional[float]] = [None] * self.sector_count
        self.sector_start_time: Optional[float] = None
        self.best_sector_times: List[Optional[float]] = [None] * self.sector_count

        # Current delta
        self.current_delta: Optional[Delta] = None
        self.current_position: Optional[TrackPosition] = None

        # Current GPS position (for map view)
        self.current_gps_point: Optional[GPSPoint] = None

        # Fuel tracking state
        self._lap_start_fuel_percent: Optional[float] = None

        # Corner detection and analysis state
        self.corners: List[Any] = []  # Detected corners on track
        self.corner_analyzer: Optional[Any] = None  # CornerAnalyzer instance
        self.current_lap_positions: List[TrackPosition] = []  # Positions during current lap
        self.last_lap_corner_speeds: List[Any] = []  # Corner speeds from last lap
        self.best_corner_speeds: Dict[int, Any] = {}  # Best speed per corner

        # Track auto-detection - read from settings, fallback to config
        self.track_detected = False
        self.auto_detect_enabled = self._settings.get("lap_timing.auto_detect", TRACK_AUTO_DETECT)

        # Error tracking
        self.consecutive_errors = 0
        self.max_consecutive_errors = 10

        if self.enabled:
            self._initialise()

    def _initialise(self):
        """Initialise lap timing components."""
        if not LAP_TIMING_AVAILABLE:
            logger.warning("Lap timing: Modules not available")
            return

        try:
            # Initialise track selector for auto-detection
            tracks_dir = os.path.join(LAP_TIMING_DATA_DIR, "tracks")
            tracks_db_path = os.path.join(tracks_dir, "tracks.db")
            racelogic_db_path = os.path.join(tracks_dir, "racelogic.db")
            custom_tracks_dir = os.path.join(tracks_dir, "maps")
            racelogic_tracks_dir = os.path.join(tracks_dir, "racelogic")

            if os.path.exists(tracks_db_path) or os.path.exists(racelogic_db_path):
                self.track_selector = TrackSelector(
                    tracks_db_path=tracks_db_path,
                    racelogic_db_path=racelogic_db_path,
                    custom_tracks_dir=custom_tracks_dir,
                    racelogic_tracks_dir=racelogic_tracks_dir,
                )
                logger.info("Lap timing: Track selector initialised")
            else:
                logger.warning("Lap timing: Track databases not found at %s", tracks_dir)

        except Exception as e:
            logger.warning("Lap timing: Initialisation error: %s", e)

    def set_track(self, track: Track):
        """
        Set the active track for lap timing.

        Args:
            track: Track object with centerline and S/F line
        """
        self.track = track
        self.lap_detector = LapDetector(track.sf_line)
        self.position_tracker = PositionTracker(track)
        self.delta_calculator = DeltaCalculator(track.length)

        # Calculate sector boundaries (equal thirds)
        self.sector_boundaries = [
            track.length * (i + 1) / self.sector_count
            for i in range(self.sector_count - 1)
        ]

        # Detect corners on track
        self._detect_corners(track)

        # Reset lap state
        self.current_lap_number = 0
        self.current_lap_start_time = None
        self.current_lap_points = []
        self.current_lap_positions = []
        self.current_sector = 0
        self.sector_times = [None] * self.sector_count
        self.sector_start_time = None

        self.track_detected = True
        logger.info("Lap timing: Track set to '%s' (%.0fm, %d corners)",
                    track.name, track.length, len(self.corners))

        # Load stored best lap for this track
        self._load_best_lap_from_store()

    def clear_track(self):
        """Clear the current track and reset lap timing state."""
        self.track = None
        self.lap_detector = None
        self.position_tracker = None
        self.delta_calculator = None
        self.track_detected = False

        # Reset lap state
        self.current_lap_number = 0
        self.current_lap_start_time = None
        self.current_lap_points = []
        self.current_lap_positions = []
        self.laps = []
        self.best_lap = None
        self.last_lap = None
        self.stored_best_lap_time = None
        self.current_sector = 0
        self.sector_times = [None] * self.sector_count
        self.sector_start_time = None
        self.best_sector_times = [None] * self.sector_count
        self.current_delta = None
        self.current_position = None

        # Reset corner state
        self.corners = []
        self.corner_analyzer = None
        self.last_lap_corner_speeds = []
        self.best_corner_speeds = {}

        logger.info("Lap timing: Track cleared")

    def _detect_corners(self, track: Track):
        """
        Detect corners on the track and initialise corner analyzer.

        Args:
            track: Track with centerline for corner detection
        """
        try:
            # Select detector based on config
            detector_type = LAP_TIMING_CORNER_DETECTOR.lower()

            if detector_type == "hybrid":
                detector = HybridCornerDetector(
                    min_corner_radius=LAP_TIMING_CORNER_MIN_RADIUS_M,
                    min_corner_angle=LAP_TIMING_CORNER_MIN_ANGLE_DEG,
                    min_cut_distance=LAP_TIMING_CORNER_MIN_CUT_DISTANCE_M,
                    straight_fill_distance=LAP_TIMING_CORNER_STRAIGHT_FILL_M,
                    merge_chicanes=LAP_TIMING_CORNER_MERGE_CHICANES,
                )
            elif detector_type == "asc":
                # Note: ASCCornerDetector's merge_same_direction controls merging
                # consecutive corners of the same direction, not chicanes.
                # Let it use the default (True) as chicane merging is HybridCornerDetector only.
                detector = ASCCornerDetector(
                    min_corner_radius=LAP_TIMING_CORNER_MIN_RADIUS_M,
                    min_corner_angle=LAP_TIMING_CORNER_MIN_ANGLE_DEG,
                    min_cut_distance=LAP_TIMING_CORNER_MIN_CUT_DISTANCE_M,
                    straight_fill_distance=LAP_TIMING_CORNER_STRAIGHT_FILL_M,
                )
            elif detector_type == "curvefinder":
                detector = CurveFinderDetector(
                    min_corner_radius=LAP_TIMING_CORNER_MIN_RADIUS_M,
                    min_corner_angle=LAP_TIMING_CORNER_MIN_ANGLE_DEG,
                )
            else:  # threshold
                detector = CornerDetector(
                    min_radius=LAP_TIMING_CORNER_MIN_RADIUS_M,
                    min_angle=LAP_TIMING_CORNER_MIN_ANGLE_DEG,
                )

            # Detect corners
            self.corners = detector.detect_corners(track)

            # Initialise corner analyzer if corners found
            if self.corners:
                self.corner_analyzer = CornerAnalyzer(self.corners)
                logger.info("Lap timing: Detected %d corners using %s detector",
                           len(self.corners), detector_type)
            else:
                self.corner_analyzer = None
                logger.info("Lap timing: No corners detected on track")

        except Exception as e:
            logger.warning("Lap timing: Corner detection failed: %s", e)
            self.corners = []
            self.corner_analyzer = None

    def _worker_loop(self):
        """Background thread for lap timing calculations."""
        while self.running:
            try:
                # Get latest GPS snapshot (lock-free)
                gps_snapshot = self.gps_handler.get_snapshot()

                if gps_snapshot and gps_snapshot.data.get('has_fix'):
                    # Convert to lap timing GPSPoint
                    gps_point = self._convert_gps_point(gps_snapshot)

                    # Check settings for auto-detect (allows live toggle)
                    self.auto_detect_enabled = self._settings.get(
                        "lap_timing.auto_detect", TRACK_AUTO_DETECT
                    )

                    # Auto-detect track if enabled and not yet detected
                    if self.auto_detect_enabled and not self.track_detected:
                        self._auto_detect_track(gps_point)

                    # Process lap timing if track is set
                    if self.track:
                        self._process_gps_point(gps_point)

                    self.consecutive_errors = 0
                else:
                    # No GPS fix, publish empty state
                    self._publish_state()

                # Poll at ~10Hz (matching GPS rate)
                time.sleep(0.1)

            except Exception as e:
                self.consecutive_errors += 1
                if self.consecutive_errors == 3:
                    logger.warning("Lap timing: Error: %s", e)
                elif self.consecutive_errors >= self.max_consecutive_errors:
                    logger.warning("Lap timing: Too many errors, resetting...")
                    self.consecutive_errors = 0
                time.sleep(0.1)

    def _convert_gps_point(self, gps_snapshot) -> GPSPoint:
        """Convert openTPT GPS snapshot to lap timing GPSPoint."""
        data = gps_snapshot.data
        return GPSPoint(
            timestamp=gps_snapshot.timestamp,
            lat=data.get('latitude', 0.0),
            lon=data.get('longitude', 0.0),
            speed=data.get('speed_kmh', 0.0) / 3.6,  # km/h to m/s
            heading=data.get('heading', 0.0),
            accuracy=5.0,  # Default accuracy
        )

    def _auto_detect_track(self, gps_point: GPSPoint):
        """Attempt to auto-detect track from GPS position."""
        if not self.track_selector:
            return

        try:
            nearby = self.track_selector.find_nearby_tracks(
                gps_point.lat,
                gps_point.lon,
                max_distance_km=TRACK_SEARCH_RADIUS_KM
            )
            if nearby:
                # Load the closest track directly (already sorted by distance)
                track_info = nearby[0]
                logger.info("Lap timing: Found %d nearby track(s), selecting closest: %s", len(nearby), track_info.name)

                if track_info.kmz_path:
                    from lap_timing.data.track_loader import load_track_from_kmz
                    track = load_track_from_kmz(track_info.kmz_path)
                    if track:
                        self.set_track(track)
                        logger.info("Lap timing: Auto-detected track: %s", track.name)
                else:
                    logger.warning("Lap timing: KMZ file not found for %s", track_info.name)
        except Exception as e:
            logger.warning("Lap timing: Auto-detect error: %s", e)
            self.auto_detect_enabled = False  # Disable after error

    def _process_gps_point(self, gps_point: GPSPoint):
        """Process a GPS point for lap timing."""
        # Store current GPS point for map view
        self.current_gps_point = gps_point

        # Get track position
        self.current_position = self.position_tracker.get_track_position(gps_point)

        # Check for S/F line crossing
        crossing = self.lap_detector.check_crossing(gps_point)
        if crossing:
            self._handle_lap_crossing(crossing, gps_point)

        # Update sector
        self._update_sector(gps_point)

        # Calculate delta if we have a reference lap
        if self.best_lap and self.current_position:
            self.current_delta = self.delta_calculator.calculate_delta(
                self.current_position
            )

        # Add point and position to current lap (needed for corner analysis)
        # Only add when both GPS point and position are valid to keep arrays in sync
        if self.current_lap_start_time is not None and self.current_position:
            self.current_lap_points.append(gps_point)
            self.current_lap_positions.append(self.current_position)

        # Publish current state
        self._publish_state()

    def _handle_lap_crossing(self, crossing: LapCrossing, gps_point: GPSPoint):
        """Handle a detected S/F line crossing."""
        crossing_time = crossing.timestamp

        if self.current_lap_start_time is not None:
            # Complete the current lap
            lap_duration = crossing_time - self.current_lap_start_time
            lap = Lap(
                lap_number=self.current_lap_number,
                start_time=self.current_lap_start_time,
                end_time=crossing_time,
                duration=lap_duration,
                gps_points=self.current_lap_points.copy(),
                positions=self.current_lap_positions.copy(),  # For corner analysis
                is_valid=True,
            )

            # Calculate max/avg speed
            if lap.gps_points:
                speeds = [p.speed for p in lap.gps_points]
                lap.max_speed = max(speeds)
                lap.avg_speed = sum(speeds) / len(speeds)

            # Track fuel consumption if fuel tracker is available
            if self.fuel_tracker:
                fuel_state = self.fuel_tracker.get_state()
                lap.fuel_at_start_percent = self._lap_start_fuel_percent
                lap.fuel_at_end_percent = fuel_state.get('fuel_level_percent')

                # Calculate fuel used this lap
                fuel_used = self.fuel_tracker.on_lap_complete(
                    lap_number=lap.lap_number,
                    lap_time=lap.duration,
                    avg_speed_kmh=lap.avg_speed * 3.6  # m/s to km/h
                )
                lap.fuel_used_litres = fuel_used

            self.laps.append(lap)
            self.last_lap = lap

            # Analyze corner speeds if corner analyzer is available
            if self.corner_analyzer and lap.positions:
                try:
                    corner_speeds = self.corner_analyzer.analyze_lap(lap)
                    self.last_lap_corner_speeds = corner_speeds

                    # Update best corner speeds
                    for record in corner_speeds:
                        corner_id = record.corner_id
                        if corner_id not in self.best_corner_speeds:
                            self.best_corner_speeds[corner_id] = record
                        elif record.min_speed > self.best_corner_speeds[corner_id].min_speed:
                            self.best_corner_speeds[corner_id] = record

                    logger.debug("Lap timing: Analyzed %d corner speeds", len(corner_speeds))
                except Exception as e:
                    logger.warning("Lap timing: Corner analysis failed: %s", e)
                    self.last_lap_corner_speeds = []

            # Check if this is the best lap
            if self.best_lap is None or lap.duration < self.best_lap.duration:
                self.best_lap = lap
                self.delta_calculator.set_reference_lap(lap)
                logger.info("Lap timing: New best lap: %s", self._format_time(lap.duration))

            # Update best sector times
            for i, sector_time in enumerate(self.sector_times):
                if sector_time is not None:
                    if self.best_sector_times[i] is None or sector_time < self.best_sector_times[i]:
                        self.best_sector_times[i] = sector_time

            logger.info("Lap timing: Lap %d - %s", self.current_lap_number, self._format_time(lap.duration))

            # Record lap to persistent store
            self._record_lap_to_store(lap)

        # Start new lap
        self.current_lap_number += 1
        self.current_lap_start_time = crossing_time
        self.current_lap_points = []
        self.current_lap_positions = []
        self.current_sector = 0
        self.sector_times = [None] * self.sector_count
        self.sector_start_time = crossing_time

        # Notify fuel tracker of new lap start
        if self.fuel_tracker:
            fuel_state = self.fuel_tracker.get_state()
            # Store the fuel at start for the next lap's record
            self._lap_start_fuel_percent = fuel_state.get('fuel_level_percent')
            self.fuel_tracker.on_lap_start()

    def _update_sector(self, gps_point: GPSPoint):
        """Update sector timing based on current position."""
        if not self.current_position or self.current_lap_start_time is None:
            return

        current_distance = self.current_position.distance_along_track

        # Check if we've crossed into a new sector
        for i, boundary in enumerate(self.sector_boundaries):
            if self.current_sector == i and current_distance >= boundary:
                # Crossed into next sector
                if self.sector_start_time is not None:
                    self.sector_times[i] = gps_point.timestamp - self.sector_start_time
                self.sector_start_time = gps_point.timestamp
                self.current_sector = i + 1

    def _publish_state(self):
        """Publish current lap timing state."""
        current_time = time.time()

        # Calculate current lap time
        current_lap_time = None
        if self.current_lap_start_time is not None:
            current_lap_time = current_time - self.current_lap_start_time

        # Calculate delta seconds
        delta_seconds = 0.0
        predicted_time = None
        if self.current_delta:
            delta_seconds = self.current_delta.time_delta
            predicted_time = self.current_delta.predicted_lap_time

        # Build sector data
        sector_data = []
        for i in range(self.sector_count):
            sector_info = {
                'time': self.sector_times[i],
                'best': self.best_sector_times[i],
                'is_current': (i == self.current_sector),
            }
            if self.sector_times[i] and self.best_sector_times[i]:
                sector_info['delta'] = self.sector_times[i] - self.best_sector_times[i]
            sector_data.append(sector_info)

        data = {
            # Track info
            'track_name': self.track.name if self.track else None,
            'track_length': self.track.length if self.track else None,
            'track_detected': self.track_detected,
            'track': self.track,  # Full track object for map view

            # Current lap
            'lap_number': self.current_lap_number,
            'current_lap_time': current_lap_time,
            'current_sector': self.current_sector,

            # Delta
            'delta_seconds': delta_seconds,
            'predicted_time': predicted_time,

            # Position
            'track_position': self.current_position.distance_along_track if self.current_position else None,
            'progress_fraction': self.current_position.progress_fraction if self.current_position else 0.0,

            # Current GPS position (for map view)
            'current_lat': self.current_gps_point.lat if self.current_gps_point else None,
            'current_lon': self.current_gps_point.lon if self.current_gps_point else None,

            # Best/last lap - use overall best (stored or session)
            'best_lap_time': self._get_overall_best_lap_time(),
            'session_best_lap_time': self.best_lap.duration if self.best_lap else None,
            'stored_best_lap_time': self.stored_best_lap_time,
            'last_lap_time': self.last_lap.duration if self.last_lap else None,
            'last_lap_delta': self._get_last_lap_delta(),

            # Sectors
            'sectors': sector_data,
            'sector_times': self.sector_times,
            'best_sector_times': self.best_sector_times,

            # Corner data
            'corners': self.corners,
            'corner_count': len(self.corners),
            'last_lap_corner_speeds': self.last_lap_corner_speeds,
            'best_corner_speeds': self.best_corner_speeds,

            # Stats
            'total_laps': len(self.laps),
        }

        self._publish_snapshot(data)

    def _format_time(self, seconds: float) -> str:
        """Format time as M:SS.mmm."""
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}:{secs:06.3f}"

    def _get_overall_best_lap_time(self) -> Optional[float]:
        """Get the overall best lap time (stored or session, whichever is faster)."""
        session_best = self.best_lap.duration if self.best_lap else None
        stored_best = self.stored_best_lap_time

        if session_best is not None and stored_best is not None:
            return min(session_best, stored_best)
        return session_best or stored_best

    def _get_last_lap_delta(self) -> Optional[float]:
        """Get delta between last lap and overall best."""
        if not self.last_lap:
            return None

        overall_best = self._get_overall_best_lap_time()
        if overall_best is None:
            return None

        # Don't show delta if last lap IS the best
        if abs(self.last_lap.duration - overall_best) < 0.001:
            return None

        return self.last_lap.duration - overall_best

    def _record_lap_to_store(self, lap: 'Lap'):
        """Record a completed lap to the persistent store."""
        try:
            store = get_lap_timing_store()
            record = LapRecord(
                track_name=self.track.name if self.track else "Unknown",
                lap_time=lap.duration,
                timestamp=time.time(),
                sectors=self.sector_times.copy() if any(self.sector_times) else None,
            )
            is_new_best = store.record_lap(record)
            if is_new_best:
                # Save reference lap with GPS trace for future delta calculations
                if lap.gps_points:
                    gps_trace = [
                        {
                            'lat': p.lat,
                            'lon': p.lon,
                            'timestamp': p.timestamp,
                            'speed': p.speed,
                        }
                        for p in lap.gps_points
                    ]
                    store.save_reference_lap(
                        self.track.name if self.track else "Unknown",
                        lap.duration,
                        gps_trace
                    )
        except Exception as e:
            logger.warning("Lap timing: Error recording lap to store: %s", e)

    def _load_best_lap_from_store(self):
        """Load best lap from persistent store for current track."""
        if not self.track:
            return

        try:
            store = get_lap_timing_store()
            best_record = store.get_best_lap(self.track.name)
            if best_record:
                self.stored_best_lap_time = best_record.lap_time
                logger.info("Lap timing: Loaded stored best lap for %s: %s", self.track.name, best_record.format_time())
        except Exception as e:
            logger.warning("Lap timing: Error loading best lap from store: %s", e)

    # Convenience methods for display
    def get_current_lap_time(self) -> Optional[float]:
        """Get current lap elapsed time in seconds."""
        data = self.get_data()
        return data.get('current_lap_time')

    def get_best_lap_time(self) -> Optional[float]:
        """Get best lap time in seconds."""
        data = self.get_data()
        return data.get('best_lap_time')

    def get_last_lap_time(self) -> Optional[float]:
        """Get last lap time in seconds."""
        data = self.get_data()
        return data.get('last_lap_time')

    def get_delta(self) -> float:
        """Get current delta to best lap in seconds."""
        data = self.get_data()
        return data.get('delta_seconds', 0.0)

    def get_track_name(self) -> Optional[str]:
        """Get current track name."""
        data = self.get_data()
        return data.get('track_name')

    def has_track(self) -> bool:
        """Check if a track is loaded."""
        return self.track is not None

    def clear_laps(self):
        """Clear all lap data (for new session)."""
        self.laps = []
        self.best_lap = None
        self.last_lap = None
        self.current_lap_number = 0
        self.current_lap_start_time = None
        self.current_lap_points = []
        self.best_sector_times = [None] * self.sector_count
        if self.delta_calculator:
            self.delta_calculator.clear_reference()
        logger.info("Lap timing: Laps cleared")

    def get_nearby_tracks(self) -> List[Dict[str, Any]]:
        """
        Get list of nearby tracks sorted by distance.

        Returns:
            List of dicts with name, distance_km, country, source
        """
        if not self.track_selector:
            return []

        # Get current GPS position
        gps_snapshot = self.gps_handler.get_snapshot()
        if not gps_snapshot or not gps_snapshot.data.get('has_fix'):
            return []

        lat = gps_snapshot.data.get('latitude', 0.0)
        lon = gps_snapshot.data.get('longitude', 0.0)

        try:
            nearby = self.track_selector.find_nearby_tracks(
                lat, lon, max_distance_km=TRACK_SEARCH_RADIUS_KM
            )
            return [
                {
                    'name': t.name,
                    'distance_km': t.distance_to_sf / 1000.0,
                    'country': t.country,
                    'source': t.source,
                    'kmz_path': t.kmz_path,
                }
                for t in nearby
            ]
        except Exception as e:
            logger.warning("Lap timing: Error getting nearby tracks: %s", e)
            return []

    def select_track_by_name(self, track_name: str) -> bool:
        """
        Select a specific track by name.

        Args:
            track_name: Name of the track to select

        Returns:
            True if track was loaded successfully
        """
        nearby = self.get_nearby_tracks()
        for track_info in nearby:
            if track_info['name'] == track_name:
                if track_info['kmz_path']:
                    try:
                        from lap_timing.data.track_loader import load_track_from_kmz
                        track = load_track_from_kmz(track_info['kmz_path'])
                        if track:
                            self.set_track(track)
                            logger.info("Lap timing: Selected track: %s", track.name)
                            return True
                    except Exception as e:
                        logger.warning("Lap timing: Error loading track: %s", e)
                        return False
        return False

    def load_track_from_file(self, file_path: str) -> bool:
        """
        Load a track from a file (KMZ or GPX).

        Args:
            file_path: Path to .kmz or .gpx file

        Returns:
            True if track was loaded successfully
        """
        try:
            from lap_timing.data.track_loader import load_track
            track = load_track(file_path)
            if track:
                self.set_track(track)
                return True
        except Exception as e:
            logger.warning("Lap timing: Error loading track from %s: %s", file_path, e)
        return False

    def get_route_waypoints(self, max_distance: float = 0) -> List[tuple]:
        """
        Get the current track centerline as route waypoints.

        Used by CoPilot for route following mode when a track is loaded.

        Args:
            max_distance: Maximum distance ahead to return (0 = all)

        Returns:
            List of (lat, lon) tuples representing the route
        """
        if not self.track or not self.track.centerline:
            return []

        waypoints = [(p.lat, p.lon) for p in self.track.centerline]

        if max_distance > 0 and self.current_position:
            # Filter to waypoints within max_distance of current position
            current_dist = self.current_position.distance_along_track
            filtered = []
            for p in self.track.centerline:
                if p.distance >= current_dist and p.distance <= current_dist + max_distance:
                    filtered.append((p.lat, p.lon))
            return filtered

        return waypoints

    def get_route_bounds(self) -> Optional[tuple]:
        """
        Get bounds of the current track route.

        Returns:
            (min_lat, max_lat, min_lon, max_lon) or None if no track
        """
        if not self.track or not self.track.centerline:
            return None

        lats = [p.lat for p in self.track.centerline]
        lons = [p.lon for p in self.track.centerline]
        return (min(lats), max(lats), min(lons), max(lons))

    def is_point_to_point(self) -> bool:
        """Check if current track is a point-to-point stage."""
        return self.track is not None and self.track.is_point_to_point
