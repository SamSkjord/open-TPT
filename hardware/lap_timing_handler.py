"""
Lap Timing Handler for openTPT.

Integrates lap-timing-system components with BoundedQueueHardwareHandler pattern.
Consumes GPS data via lock-free snapshots and publishes lap timing data for display.
"""

import time
import os
from typing import Optional, List, Dict, Any

from utils.hardware_base import BoundedQueueHardwareHandler
from utils.config import (
    LAP_TIMING_ENABLED,
    TRACK_AUTO_DETECT,
    TRACK_SEARCH_RADIUS_KM,
    LAP_TIMING_DATA_DIR,
)
from utils.lap_timing_store import get_lap_timing_store, LapRecord

# Import lap timing components
try:
    from lap_timing.core.lap_detector import LapDetector, LapCrossing
    from lap_timing.core.position_tracker import PositionTracker
    from lap_timing.core.delta_calculator import DeltaCalculator
    from lap_timing.data.models import GPSPoint, Lap, Delta, TrackPosition
    from lap_timing.data.track_loader import Track
    from lap_timing.data.track_selector import TrackSelector
    LAP_TIMING_AVAILABLE = True
except ImportError as e:
    print(f"Lap timing modules not available: {e}")
    LAP_TIMING_AVAILABLE = False


class LapTimingHandler(BoundedQueueHardwareHandler):
    """
    Lap timing handler integrating GPS with lap detection and delta calculation.

    Follows BoundedQueueHardwareHandler pattern:
    - Consumes GPS snapshots (lock-free)
    - Processes lap timing in worker thread
    - Publishes results for lock-free render access
    """

    def __init__(self, gps_handler):
        """
        Initialise lap timing handler.

        Args:
            gps_handler: GPSHandler instance to consume GPS data from
        """
        super().__init__(queue_depth=2)
        self.gps_handler = gps_handler
        self.enabled = LAP_TIMING_ENABLED and LAP_TIMING_AVAILABLE

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

        # Track auto-detection
        self.track_detected = False
        self.auto_detect_enabled = TRACK_AUTO_DETECT

        # Error tracking
        self.consecutive_errors = 0
        self.max_consecutive_errors = 10

        if self.enabled:
            self._initialise()

    def _initialise(self):
        """Initialise lap timing components."""
        if not LAP_TIMING_AVAILABLE:
            print("Lap timing: Modules not available")
            return

        try:
            # Initialise track selector for auto-detection
            tracks_db_path = os.path.join(LAP_TIMING_DATA_DIR, "tracks", "tracks.db")
            racelogic_db_path = os.path.join(LAP_TIMING_DATA_DIR, "tracks", "racelogic.db")

            if os.path.exists(tracks_db_path) or os.path.exists(racelogic_db_path):
                self.track_selector = TrackSelector()
                print("Lap timing: Track selector initialised")
            else:
                print(f"Lap timing: Track databases not found at {LAP_TIMING_DATA_DIR}")

        except Exception as e:
            print(f"Lap timing: Initialisation error: {e}")

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

        # Reset lap state
        self.current_lap_number = 0
        self.current_lap_start_time = None
        self.current_lap_points = []
        self.current_sector = 0
        self.sector_times = [None] * self.sector_count
        self.sector_start_time = None

        self.track_detected = True
        print(f"Lap timing: Track set to '{track.name}' ({track.length:.0f}m)")

        # Load stored best lap for this track
        self._load_best_lap_from_store()

    def _worker_loop(self):
        """Background thread for lap timing calculations."""
        while self.running:
            try:
                # Get latest GPS snapshot (lock-free)
                gps_snapshot = self.gps_handler.get_snapshot()

                if gps_snapshot and gps_snapshot.data.get('has_fix'):
                    # Convert to lap timing GPSPoint
                    gps_point = self._convert_gps_point(gps_snapshot)

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
                    print(f"Lap timing: Error: {e}")
                elif self.consecutive_errors >= self.max_consecutive_errors:
                    print("Lap timing: Too many errors, resetting...")
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
                print(f"Lap timing: Found {len(nearby)} nearby track(s), selecting closest: {track_info.name}")

                if track_info.kmz_path:
                    from lap_timing.data.track_loader import load_track_from_kmz
                    track = load_track_from_kmz(track_info.kmz_path)
                    if track:
                        self.set_track(track)
                        print(f"Lap timing: Auto-detected track: {track.name}")
                else:
                    print(f"Lap timing: KMZ file not found for {track_info.name}")
        except Exception as e:
            print(f"Lap timing: Auto-detect error: {e}")
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

        # Add point to current lap
        if self.current_lap_start_time is not None:
            self.current_lap_points.append(gps_point)

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
                is_valid=True,
            )

            # Calculate max/avg speed
            if lap.gps_points:
                speeds = [p.speed for p in lap.gps_points]
                lap.max_speed = max(speeds)
                lap.avg_speed = sum(speeds) / len(speeds)

            self.laps.append(lap)
            self.last_lap = lap

            # Check if this is the best lap
            if self.best_lap is None or lap.duration < self.best_lap.duration:
                self.best_lap = lap
                self.delta_calculator.set_reference_lap(lap)
                print(f"Lap timing: New best lap: {self._format_time(lap.duration)}")

            # Update best sector times
            for i, sector_time in enumerate(self.sector_times):
                if sector_time is not None:
                    if self.best_sector_times[i] is None or sector_time < self.best_sector_times[i]:
                        self.best_sector_times[i] = sector_time

            print(f"Lap timing: Lap {self.current_lap_number} - {self._format_time(lap.duration)}")

            # Record lap to persistent store
            self._record_lap_to_store(lap)

        # Start new lap
        self.current_lap_number += 1
        self.current_lap_start_time = crossing_time
        self.current_lap_points = []
        self.current_sector = 0
        self.sector_times = [None] * self.sector_count
        self.sector_start_time = crossing_time

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
            print(f"Lap timing: Error recording lap to store: {e}")

    def _load_best_lap_from_store(self):
        """Load best lap from persistent store for current track."""
        if not self.track:
            return

        try:
            store = get_lap_timing_store()
            best_record = store.get_best_lap(self.track.name)
            if best_record:
                self.stored_best_lap_time = best_record.lap_time
                print(f"Lap timing: Loaded stored best lap for {self.track.name}: {best_record.format_time()}")
        except Exception as e:
            print(f"Lap timing: Error loading best lap from store: {e}")

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
        print("Lap timing: Laps cleared")

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
            print(f"Lap timing: Error getting nearby tracks: {e}")
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
                            print(f"Lap timing: Selected track: {track.name}")
                            return True
                    except Exception as e:
                        print(f"Lap timing: Error loading track: {e}")
                        return False
        return False
