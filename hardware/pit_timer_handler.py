"""
Pit Timer Handler for openTPT.

VBOX-style pit lane timer with GPS-based entry/exit detection,
countdown timing, and speed monitoring.

Features:
- Two timing modes: Entrance-to-Exit vs Stationary-only
- GPS waypoint marking for pit entry/exit lines
- Crossing detection using cross-product algorithm
- Countdown timer for minimum stop time
- Speed monitoring with warning when approaching limit
- Per-track storage of pit waypoints
"""

import logging
import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from utils.hardware_base import BoundedQueueHardwareHandler
from utils.settings import get_settings
from utils.pit_lane_store import (
    get_pit_lane_store,
    PitLine,
    PitWaypoints,
    PitSession,
)
from config import (
    PIT_TIMER_ENABLED,
    PIT_SPEED_LIMIT_DEFAULT_KMH,
    PIT_SPEED_WARNING_MARGIN_KMH,
    PIT_TIMER_DEFAULT_MODE,
    PIT_LINE_WIDTH_M,
    PIT_STATIONARY_SPEED_KMH,
    PIT_STATIONARY_DURATION_S,
    PIT_MIN_STOP_TIME_DEFAULT_S,
)

logger = logging.getLogger('openTPT.pit_timer')


class PitState(Enum):
    """Pit timer state machine states."""
    ON_TRACK = "on_track"        # Normal driving
    IN_PIT_LANE = "in_pit_lane"  # Moving in pit lane
    STATIONARY = "stationary"    # Stopped in pit box


@dataclass(frozen=True)
class PitTimerSnapshot:
    """Lock-free snapshot of pit timer state for rendering."""
    state: PitState
    pit_entry_time: Optional[float]
    stationary_start_time: Optional[float]
    elapsed_pit_time_s: float
    elapsed_stationary_time_s: float
    speed_kmh: float
    speed_limit_kmh: float
    speed_warning: bool          # approaching limit
    speed_violation: bool        # over limit
    countdown_remaining_s: Optional[float]
    safe_to_leave: bool
    has_entry_line: bool
    has_exit_line: bool
    mode: str                    # "entrance_to_exit" or "stationary_only"
    track_name: Optional[str]
    last_pit_time: Optional[float]


class PitTimerHandler(BoundedQueueHardwareHandler):
    """
    Pit timer handler with GPS-based pit lane detection.

    Uses cross-product algorithm (same as lap timing) to detect
    when the car crosses entry/exit lines.

    State Machine:
    - ON_TRACK: Normal driving on circuit
    - IN_PIT_LANE: Between entry line and pit box
    - STATIONARY: Stopped in pit box (speed < threshold)
    """

    def __init__(self, gps_handler, lap_timing_handler=None):
        """
        Initialise pit timer handler.

        Args:
            gps_handler: GPSHandler instance for GPS data
            lap_timing_handler: Optional LapTimingHandler for track info
        """
        super().__init__(queue_depth=2)
        self.gps_handler = gps_handler
        self.lap_timing_handler = lap_timing_handler
        self._settings = get_settings()

        # Check settings for enabled state
        settings_enabled = self._settings.get("pit_timer.enabled", PIT_TIMER_ENABLED)
        self.enabled = settings_enabled

        # Current track
        self.track_name: Optional[str] = None

        # Pit waypoints for current track
        self.waypoints: Optional[PitWaypoints] = None

        # State machine
        self.state = PitState.ON_TRACK

        # Timing state
        self.pit_entry_time: Optional[float] = None
        self.stationary_start_time: Optional[float] = None
        self.last_pit_time: Optional[float] = None
        self.speed_violation_count = 0

        # Crossing detection state (previous GPS point)
        self._prev_gps_lat: Optional[float] = None
        self._prev_gps_lon: Optional[float] = None

        # Speed monitoring
        self.current_speed_kmh = 0.0

        # Timing mode
        self.mode = self._settings.get("pit_timer.mode", PIT_TIMER_DEFAULT_MODE)

        # Speed limit (can be overridden per track)
        self.speed_limit_kmh = PIT_SPEED_LIMIT_DEFAULT_KMH

        # Minimum stop time (countdown target)
        self.min_stop_time_s = PIT_MIN_STOP_TIME_DEFAULT_S

        # Error tracking
        self.consecutive_errors = 0
        self.max_consecutive_errors = 10

    def _worker_loop(self):
        """Background thread for pit timer processing."""
        while self.running:
            try:
                # Get latest GPS snapshot
                gps_snapshot = self.gps_handler.get_snapshot()

                if gps_snapshot and gps_snapshot.data.get('has_fix'):
                    self._process_gps(gps_snapshot)
                    self.consecutive_errors = 0
                else:
                    # No GPS fix, publish current state
                    self._publish_state()

                # Poll at ~10Hz (matching GPS rate)
                time.sleep(0.1)

            except Exception as e:
                self.consecutive_errors += 1
                if self.consecutive_errors == 3:
                    logger.warning("Pit timer: Error: %s", e)
                elif self.consecutive_errors >= self.max_consecutive_errors:
                    logger.warning("Pit timer: Too many errors, continuing...")
                    self.consecutive_errors = 0
                time.sleep(0.1)

    def _process_gps(self, gps_snapshot):
        """Process GPS data for pit timing."""
        data = gps_snapshot.data
        lat = data.get('latitude', 0.0)
        lon = data.get('longitude', 0.0)
        self.current_speed_kmh = data.get('speed_kmh', 0.0)

        # Check for track change (via lap timing handler)
        self._check_track_change()

        # Process based on current state
        if self.state == PitState.ON_TRACK:
            self._process_on_track(lat, lon)
        elif self.state == PitState.IN_PIT_LANE:
            self._process_in_pit_lane(lat, lon)
        elif self.state == PitState.STATIONARY:
            self._process_stationary(lat, lon)

        # Store previous position for crossing detection
        self._prev_gps_lat = lat
        self._prev_gps_lon = lon

        # Publish updated state
        self._publish_state()

    def _check_track_change(self):
        """Check if track has changed via lap timing handler."""
        if not self.lap_timing_handler:
            return

        lap_data = self.lap_timing_handler.get_data()
        if not lap_data:
            return

        new_track_name = lap_data.get('track_name')
        if new_track_name and new_track_name != self.track_name:
            self._on_track_changed(new_track_name)

    def _on_track_changed(self, new_track_name: str):
        """Handle track change - load pit waypoints."""
        self.track_name = new_track_name

        # Reset state
        self.state = PitState.ON_TRACK
        self.pit_entry_time = None
        self.stationary_start_time = None
        self.speed_violation_count = 0

        # Load waypoints for this track
        store = get_pit_lane_store()
        self.waypoints = store.get_waypoints(new_track_name)

        if self.waypoints:
            self.speed_limit_kmh = self.waypoints.speed_limit_kmh
            self.min_stop_time_s = self.waypoints.min_stop_time_s
            logger.info("Pit timer: Loaded waypoints for %s (entry=%s, exit=%s)",
                       new_track_name,
                       "SET" if self.waypoints.entry_line else "NOT SET",
                       "SET" if self.waypoints.exit_line else "NOT SET")
        else:
            # Use defaults
            self.speed_limit_kmh = PIT_SPEED_LIMIT_DEFAULT_KMH
            self.min_stop_time_s = PIT_MIN_STOP_TIME_DEFAULT_S
            logger.info("Pit timer: No waypoints for %s, using defaults", new_track_name)

    def _process_on_track(self, lat: float, lon: float):
        """Process GPS when on track."""
        if not self.waypoints or not self.waypoints.entry_line:
            return

        # Check for entry line crossing
        if self._check_crossing(lat, lon, self.waypoints.entry_line):
            self._enter_pit_lane()

    def _process_in_pit_lane(self, lat: float, lon: float):
        """Process GPS when in pit lane."""
        # Check for stationary (speed below threshold for duration)
        if self.current_speed_kmh < PIT_STATIONARY_SPEED_KMH:
            if self.stationary_start_time is None:
                self.stationary_start_time = time.time()
            elif time.time() - self.stationary_start_time >= PIT_STATIONARY_DURATION_S:
                self._become_stationary()
        else:
            # Moving - reset stationary timer
            self.stationary_start_time = None

        # Check for exit line crossing
        if self.waypoints and self.waypoints.exit_line:
            if self._check_crossing(lat, lon, self.waypoints.exit_line):
                self._exit_pit_lane()

        # Check speed violation
        if self.current_speed_kmh > self.speed_limit_kmh:
            self.speed_violation_count += 1

    def _process_stationary(self, lat: float, lon: float):
        """Process GPS when stationary."""
        # Check if started moving
        if self.current_speed_kmh >= PIT_STATIONARY_SPEED_KMH:
            self.state = PitState.IN_PIT_LANE
            logger.debug("Pit timer: Started moving in pit lane")

        # Check for exit line crossing (in case car moves directly out)
        if self.waypoints and self.waypoints.exit_line:
            if self._check_crossing(lat, lon, self.waypoints.exit_line):
                self._exit_pit_lane()

    def _enter_pit_lane(self):
        """Handle entry into pit lane."""
        self.state = PitState.IN_PIT_LANE
        self.pit_entry_time = time.time()
        self.stationary_start_time = None
        self.speed_violation_count = 0
        logger.info("Pit timer: Entered pit lane")

    def _become_stationary(self):
        """Handle becoming stationary in pit box."""
        self.state = PitState.STATIONARY
        # Keep the existing stationary_start_time from when speed first dropped
        # (don't reset it here - it was set in _process_in_pit_lane)
        logger.info("Pit timer: Stationary in pit box")

    def _exit_pit_lane(self):
        """Handle exit from pit lane."""
        # Record pit session
        if self.pit_entry_time:
            exit_time = time.time()
            total_time = exit_time - self.pit_entry_time
            stationary_time = 0.0

            if self.stationary_start_time:
                stationary_time = exit_time - self.stationary_start_time

            self.last_pit_time = total_time

            # Record to store
            if self.track_name:
                session = PitSession(
                    track_name=self.track_name,
                    entry_time=self.pit_entry_time,
                    exit_time=exit_time,
                    stationary_time=stationary_time,
                    total_time=total_time,
                    speed_violations=self.speed_violation_count,
                    timestamp=time.time()
                )
                store = get_pit_lane_store()
                store.record_session(session)

            logger.info("Pit timer: Exited pit lane - total %.1fs, stationary %.1fs, violations %d",
                       total_time, stationary_time, self.speed_violation_count)

        # Reset state
        self.state = PitState.ON_TRACK
        self.pit_entry_time = None
        self.stationary_start_time = None
        self.speed_violation_count = 0

    def _check_crossing(self, lat: float, lon: float, line: PitLine) -> bool:
        """
        Check if the car has crossed a line using cross-product algorithm.

        Same algorithm as lap timing S/F line detection.

        Args:
            lat: Current latitude
            lon: Current longitude
            line: PitLine to check crossing against

        Returns:
            True if line was crossed
        """
        if self._prev_gps_lat is None or self._prev_gps_lon is None:
            return False

        # Line segment endpoints
        ax, ay = line.point1[1], line.point1[0]  # lon, lat
        bx, by = line.point2[1], line.point2[0]

        # Previous and current position
        px, py = self._prev_gps_lon, self._prev_gps_lat
        cx, cy = lon, lat

        # Cross products to determine which side of line each point is on
        def cross_product(ax, ay, bx, by, px, py):
            return (bx - ax) * (py - ay) - (by - ay) * (px - ax)

        cross_prev = cross_product(ax, ay, bx, by, px, py)
        cross_curr = cross_product(ax, ay, bx, by, cx, cy)

        # Crossing occurs if signs are different (one positive, one negative)
        if cross_prev * cross_curr < 0:
            # Also check that the segment crosses the line (not just the infinite line)
            # Using bounding box check for efficiency
            min_lat = min(line.point1[0], line.point2[0])
            max_lat = max(line.point1[0], line.point2[0])
            min_lon = min(line.point1[1], line.point2[1])
            max_lon = max(line.point1[1], line.point2[1])

            # Add small tolerance for crossing detection
            tolerance = 0.0001  # ~11 metres
            if (min_lat - tolerance <= lat <= max_lat + tolerance and
                min_lon - tolerance <= lon <= max_lon + tolerance):
                return True

        return False

    def _publish_state(self):
        """Publish current pit timer state."""
        now = time.time()

        # Calculate elapsed times
        elapsed_pit_time = 0.0
        elapsed_stationary_time = 0.0

        if self.pit_entry_time:
            elapsed_pit_time = now - self.pit_entry_time

        if self.stationary_start_time:
            elapsed_stationary_time = now - self.stationary_start_time

        # In stationary_only mode, use stationary time as main timer
        if self.mode == "stationary_only" and self.state == PitState.STATIONARY:
            elapsed_pit_time = elapsed_stationary_time

        # Calculate countdown
        countdown_remaining = None
        safe_to_leave = False

        if self.state == PitState.STATIONARY and self.min_stop_time_s > 0:
            countdown_remaining = max(0, self.min_stop_time_s - elapsed_stationary_time)
            safe_to_leave = countdown_remaining <= 0
        elif self.state == PitState.STATIONARY:
            safe_to_leave = True

        # Speed warning/violation
        speed_warning = (
            self.state != PitState.ON_TRACK and
            self.current_speed_kmh > (self.speed_limit_kmh - PIT_SPEED_WARNING_MARGIN_KMH)
        )
        speed_violation = (
            self.state != PitState.ON_TRACK and
            self.current_speed_kmh > self.speed_limit_kmh
        )

        # Check waypoint status
        has_entry = self.waypoints and self.waypoints.entry_line is not None
        has_exit = self.waypoints and self.waypoints.exit_line is not None

        data = {
            'state': self.state.value,
            'pit_entry_time': self.pit_entry_time,
            'stationary_start_time': self.stationary_start_time,
            'elapsed_pit_time_s': elapsed_pit_time,
            'elapsed_stationary_time_s': elapsed_stationary_time,
            'speed_kmh': self.current_speed_kmh,
            'speed_limit_kmh': self.speed_limit_kmh,
            'speed_warning': speed_warning,
            'speed_violation': speed_violation,
            'countdown_remaining_s': countdown_remaining,
            'safe_to_leave': safe_to_leave,
            'has_entry_line': has_entry,
            'has_exit_line': has_exit,
            'mode': self.mode,
            'track_name': self.track_name,
            'last_pit_time': self.last_pit_time,
            'min_stop_time_s': self.min_stop_time_s,
        }

        self._publish_snapshot(data)

    # Public API

    def mark_entry_line(self) -> bool:
        """
        Mark current GPS position as pit entry line.

        Creates a line perpendicular to current heading.

        Returns:
            True if entry line was marked successfully
        """
        gps_snapshot = self.gps_handler.get_snapshot()
        if not gps_snapshot or not gps_snapshot.data.get('has_fix'):
            logger.warning("Pit timer: Cannot mark entry - no GPS fix")
            return False

        if not self.track_name:
            logger.warning("Pit timer: Cannot mark entry - no track selected")
            return False

        data = gps_snapshot.data
        lat = data.get('latitude', 0.0)
        lon = data.get('longitude', 0.0)
        heading = data.get('heading', 0.0)

        entry_line = self._create_pit_line(lat, lon, heading)

        # Update waypoints
        if not self.waypoints:
            self.waypoints = PitWaypoints(
                track_name=self.track_name,
                entry_line=entry_line,
                speed_limit_kmh=self.speed_limit_kmh,
                min_stop_time_s=self.min_stop_time_s
            )
        else:
            self.waypoints = PitWaypoints(
                track_name=self.track_name,
                entry_line=entry_line,
                exit_line=self.waypoints.exit_line,
                speed_limit_kmh=self.waypoints.speed_limit_kmh,
                min_stop_time_s=self.waypoints.min_stop_time_s
            )

        # Save to store
        store = get_pit_lane_store()
        store.save_waypoints(self.waypoints)

        logger.info("Pit timer: Marked entry line at %.6f, %.6f (heading %.1f)",
                   lat, lon, heading)
        return True

    def mark_exit_line(self) -> bool:
        """
        Mark current GPS position as pit exit line.

        Creates a line perpendicular to current heading.

        Returns:
            True if exit line was marked successfully
        """
        gps_snapshot = self.gps_handler.get_snapshot()
        if not gps_snapshot or not gps_snapshot.data.get('has_fix'):
            logger.warning("Pit timer: Cannot mark exit - no GPS fix")
            return False

        if not self.track_name:
            logger.warning("Pit timer: Cannot mark exit - no track selected")
            return False

        data = gps_snapshot.data
        lat = data.get('latitude', 0.0)
        lon = data.get('longitude', 0.0)
        heading = data.get('heading', 0.0)

        exit_line = self._create_pit_line(lat, lon, heading)

        # Update waypoints
        if not self.waypoints:
            self.waypoints = PitWaypoints(
                track_name=self.track_name,
                exit_line=exit_line,
                speed_limit_kmh=self.speed_limit_kmh,
                min_stop_time_s=self.min_stop_time_s
            )
        else:
            self.waypoints = PitWaypoints(
                track_name=self.track_name,
                entry_line=self.waypoints.entry_line,
                exit_line=exit_line,
                speed_limit_kmh=self.waypoints.speed_limit_kmh,
                min_stop_time_s=self.waypoints.min_stop_time_s
            )

        # Save to store
        store = get_pit_lane_store()
        store.save_waypoints(self.waypoints)

        logger.info("Pit timer: Marked exit line at %.6f, %.6f (heading %.1f)",
                   lat, lon, heading)
        return True

    def _create_pit_line(self, lat: float, lon: float, heading: float) -> PitLine:
        """
        Create a pit line perpendicular to heading at given position.

        Args:
            lat: Latitude of line centre
            lon: Longitude of line centre
            heading: Direction of travel (degrees, 0=N, 90=E)

        Returns:
            PitLine object
        """
        # Convert to radians
        heading_rad = math.radians(heading)

        # Perpendicular direction (90 degrees offset)
        perp_rad = heading_rad + math.pi / 2

        # Calculate half-width in degrees (approximate)
        # 1 degree latitude ~= 111km
        # 1 degree longitude ~= 111km * cos(lat)
        half_width_m = PIT_LINE_WIDTH_M / 2
        dlat = (half_width_m / 111000) * math.cos(perp_rad)
        dlon = (half_width_m / (111000 * math.cos(math.radians(lat)))) * math.sin(perp_rad)

        # Line endpoints
        p1 = (lat + dlat, lon + dlon)
        p2 = (lat - dlat, lon - dlon)

        return PitLine(
            point1=p1,
            point2=p2,
            centre=(lat, lon),
            heading=heading,
            width=PIT_LINE_WIDTH_M
        )

    def toggle_mode(self):
        """Toggle between timing modes."""
        if self.mode == "entrance_to_exit":
            self.mode = "stationary_only"
        else:
            self.mode = "entrance_to_exit"

        # Save preference
        self._settings.set("pit_timer.mode", self.mode)
        logger.info("Pit timer: Mode changed to %s", self.mode)

    def set_speed_limit(self, speed_kmh: float):
        """Set pit lane speed limit."""
        self.speed_limit_kmh = speed_kmh

        # Update waypoints and save
        if self.waypoints:
            self.waypoints = PitWaypoints(
                track_name=self.waypoints.track_name,
                entry_line=self.waypoints.entry_line,
                exit_line=self.waypoints.exit_line,
                speed_limit_kmh=speed_kmh,
                min_stop_time_s=self.waypoints.min_stop_time_s
            )
            store = get_pit_lane_store()
            store.save_waypoints(self.waypoints)

        logger.info("Pit timer: Speed limit set to %.0f km/h", speed_kmh)

    def set_min_stop_time(self, seconds: float):
        """Set minimum stop time (countdown target)."""
        self.min_stop_time_s = seconds

        # Update waypoints and save
        if self.waypoints:
            self.waypoints = PitWaypoints(
                track_name=self.waypoints.track_name,
                entry_line=self.waypoints.entry_line,
                exit_line=self.waypoints.exit_line,
                speed_limit_kmh=self.waypoints.speed_limit_kmh,
                min_stop_time_s=seconds
            )
            store = get_pit_lane_store()
            store.save_waypoints(self.waypoints)

        logger.info("Pit timer: Min stop time set to %.1f s", seconds)

    def clear_waypoints(self) -> bool:
        """Clear pit waypoints for current track."""
        if not self.track_name:
            return False

        store = get_pit_lane_store()
        result = store.clear_waypoints(self.track_name)

        if result:
            self.waypoints = None

        return result

    def get_state(self) -> PitState:
        """Get current pit timer state."""
        return self.state

    def is_in_pit(self) -> bool:
        """Check if currently in pit lane."""
        return self.state != PitState.ON_TRACK
