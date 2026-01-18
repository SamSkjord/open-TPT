"""
CoPilot handler for openTPT integration.

Provides rally-style audio callouts for upcoming corners,
junctions, bridges, and hazards using OSM map data and GPS position.

Modes:
- just_drive: Follow whatever road you're on, detecting corners ahead
- route_follow: Follow a loaded GPX route, using road data for corner detection
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.hardware_base import BoundedQueueHardwareHandler

try:
    from copilot.gps import Position
    from copilot.map_loader import MapLoader, RoadNetwork
    from copilot.path_projector import PathProjector
    from copilot.corners import CornerDetector
    from copilot.pacenotes import PacenoteGenerator
    from copilot.audio import AudioPlayer
    from copilot.geometry import haversine_distance
    from copilot.simulator import GPXRouteLoader
    COPILOT_AVAILABLE = True
except ImportError:
    COPILOT_AVAILABLE = False
    Position = None
    GPXRouteLoader = None


# Operating modes
MODE_JUST_DRIVE = "just_drive"
MODE_ROUTE_FOLLOW = "route_follow"

logger = logging.getLogger('openTPT.copilot')


class OpenTPTGPSAdapter:
    """
    Adapts openTPT's GPSHandler to the CoPilot GPSInterface protocol.

    CoPilot expects a GPS interface with connect(), disconnect(),
    and read_position() methods. This adapter wraps an existing
    openTPT GPSHandler to provide that interface.
    """

    def __init__(self, gps_handler):
        """
        Initialise the GPS adapter.

        Args:
            gps_handler: openTPT GPSHandler instance
        """
        self._gps = gps_handler

    def connect(self) -> None:
        """Connect to GPS - openTPT manages this lifecycle."""
        pass  # GPS already connected via openTPT

    def disconnect(self) -> None:
        """Disconnect from GPS - openTPT manages this lifecycle."""
        pass  # GPS disconnected when openTPT shuts down

    def read_position(self) -> Optional["Position"]:
        """
        Read current position from GPS.

        Returns:
            Position dataclass or None if no fix
        """
        if not COPILOT_AVAILABLE:
            return None

        snapshot = self._gps.get_snapshot()
        if not snapshot:
            return None

        data = snapshot.data if hasattr(snapshot, 'data') else snapshot
        if not data or not data.get('has_fix'):
            return None

        return Position(
            lat=data.get('latitude', 0.0),
            lon=data.get('longitude', 0.0),
            heading=data.get('heading', 0.0),
            speed=data.get('speed_kmh', 0.0) / 3.6,  # Convert km/h to m/s
        )


class CoPilotHandler(BoundedQueueHardwareHandler):
    """
    CoPilot integration handler for openTPT.

    Runs CoPilot's corner detection and pacenote generation in a
    background thread, providing lock-free access to current callout
    state for the render path.

    Modes:
    - just_drive: Detect corners on whatever road you're currently on
    - route_follow: Follow a GPX route, using it to guide junction decisions
    """

    def __init__(
        self,
        gps_handler,
        map_path: Optional[Path] = None,
        lookahead_m: float = 1000,
        update_interval_s: float = 0.5,
        audio_enabled: bool = True,
        audio_volume: float = 0.8,
        lap_timing_handler=None,
    ):
        """
        Initialise CoPilot handler.

        Args:
            gps_handler: openTPT GPSHandler instance
            map_path: Path to map database (.roads.db) or directory
            lookahead_m: Distance to look ahead for corners (metres)
            update_interval_s: Update interval in seconds
            audio_enabled: Enable audio callouts
            audio_volume: Audio volume (0.0 - 1.0)
            lap_timing_handler: Optional LapTimingHandler for route integration
        """
        super().__init__(queue_depth=2)

        if not COPILOT_AVAILABLE:
            raise ImportError("CoPilot dependencies not available")

        self.gps_adapter = OpenTPTGPSAdapter(gps_handler)
        self.lookahead_m = lookahead_m
        self.update_interval_s = update_interval_s
        self.audio_enabled = audio_enabled
        self.lap_timing_handler = lap_timing_handler

        # Operating mode
        self._mode = MODE_JUST_DRIVE
        self._route_loader: Optional[GPXRouteLoader] = None
        self._route_name: str = ""

        # Map loading
        if map_path is None:
            # Default map path
            map_path = Path.home() / ".opentpt" / "copilot" / "maps"
        self.map_path = Path(map_path)
        self._map_loader: Optional[MapLoader] = None
        self._network: Optional[RoadNetwork] = None
        self._projector: Optional[PathProjector] = None
        self._last_fetch_pos: Optional[Position] = None

        # Corner detection and pacenote generation
        self._corner_detector = CornerDetector(
            merge_same_direction=False,
            min_cut_distance=10.0,
            max_chicane_gap=15.0,
        )
        self._pacenote_gen = PacenoteGenerator(
            distance_threshold_m=lookahead_m
        )

        # Audio
        self._audio: Optional[AudioPlayer] = None
        if audio_enabled:
            self._audio = AudioPlayer()

        # State for status display
        self._last_callout_text = ""
        self._last_callout_time = 0.0
        self._corners_ahead = 0
        self._next_corner_distance = 0.0
        self._next_corner_direction = ""
        self._next_corner_severity = 0

    @property
    def mode(self) -> str:
        """Get current operating mode."""
        return self._mode

    @property
    def route_name(self) -> str:
        """Get name of loaded route (if any)."""
        if self._route_name:
            return self._route_name
        # Check lap timing track name
        if self.lap_timing_handler and self.lap_timing_handler.has_track():
            return self.lap_timing_handler.get_track_name() or ""
        return ""

    @property
    def has_route(self) -> bool:
        """Check if a route is loaded (from GPX or lap timing track)."""
        # Check GPX route first
        if self._route_loader is not None and self._route_loader.is_loaded:
            return True
        # Check lap timing track
        if self.lap_timing_handler and self.lap_timing_handler.has_track():
            return True
        return False

    @property
    def has_gpx_route(self) -> bool:
        """Check if a GPX route (not lap timing track) is loaded."""
        return self._route_loader is not None and self._route_loader.is_loaded

    def set_mode(self, mode: str) -> bool:
        """
        Set operating mode.

        Args:
            mode: MODE_JUST_DRIVE or MODE_ROUTE_FOLLOW

        Returns:
            True if mode was set successfully
        """
        if mode not in (MODE_JUST_DRIVE, MODE_ROUTE_FOLLOW):
            logger.warning("Invalid mode: %s", mode)
            return False

        if mode == MODE_ROUTE_FOLLOW and not self.has_route:
            logger.warning("Cannot set route_follow mode: no route loaded")
            return False

        self._mode = mode
        logger.info("CoPilot mode set to: %s", mode)
        return True

    def load_route(self, gpx_path: str) -> bool:
        """
        Load a GPX route file.

        Args:
            gpx_path: Path to GPX file

        Returns:
            True if route was loaded successfully
        """
        if GPXRouteLoader is None:
            logger.error("GPX route loading not available")
            return False

        try:
            loader = GPXRouteLoader(gpx_path)
            if loader.load():
                self._route_loader = loader
                self._route_name = Path(gpx_path).stem
                logger.info(
                    "Loaded GPX route '%s' with %d points",
                    self._route_name, loader.point_count
                )
                return True
            else:
                logger.warning("Failed to load GPX route: %s", gpx_path)
                return False
        except Exception as e:
            logger.error("Error loading GPX route: %s", e)
            return False

    def clear_route(self):
        """Clear the loaded route and switch to just_drive mode."""
        self._route_loader = None
        self._route_name = ""
        self._mode = MODE_JUST_DRIVE
        logger.info("Route cleared, mode set to just_drive")

    def start(self):
        """Start the CoPilot handler."""
        # Initialise map loader
        if self.map_path.exists():
            try:
                self._map_loader = MapLoader(self.map_path)
                logger.info("CoPilot map loader initialised: %s", self.map_path)
            except Exception as e:
                logger.warning("CoPilot map load failed: %s", e)
                self._map_loader = None
        else:
            logger.warning("CoPilot map path does not exist: %s", self.map_path)

        # Start audio player
        if self._audio:
            self._audio.start()

        # Start worker thread
        super().start()

    def stop(self):
        """Stop the CoPilot handler."""
        super().stop()

        if self._audio:
            self._audio.stop()

    def _worker_loop(self):
        """Worker thread loop for CoPilot updates."""
        logger.info("CoPilot worker thread started")

        while self.running:
            try:
                self._update_cycle()
            except Exception as e:
                logger.error("CoPilot update error: %s", e, exc_info=True)

            time.sleep(self.update_interval_s)

        logger.info("CoPilot worker thread stopped")

    def _update_cycle(self):
        """Single update cycle: read GPS, project path, detect corners."""
        # Read current position
        pos = self.gps_adapter.read_position()
        if not pos:
            self._publish_snapshot({
                'status': 'no_gps',
                'last_callout': self._last_callout_text,
                'last_callout_time': self._last_callout_time,
                'mode': self._mode,
                'route_name': self._route_name,
            })
            return

        # Load map if needed
        if self._map_loader and self._should_refetch(pos):
            self._fetch_roads(pos)

        if not self._network or not self._projector:
            self._publish_snapshot({
                'status': 'no_map',
                'lat': pos.lat,
                'lon': pos.lon,
                'last_callout': self._last_callout_text,
                'last_callout_time': self._last_callout_time,
                'mode': self._mode,
                'route_name': self._route_name,
            })
            return

        # Get route waypoints if in route_follow mode
        route_waypoints = None
        if self._mode == MODE_ROUTE_FOLLOW:
            # Try GPX route first
            if self._route_loader and self._route_loader.is_loaded:
                route_waypoints = self._route_loader.get_upcoming_waypoints(
                    pos.lat, pos.lon, self.lookahead_m
                )
            # Fall back to lap timing track centerline
            elif self.lap_timing_handler and self.lap_timing_handler.has_track():
                route_waypoints = self.lap_timing_handler.get_route_waypoints(
                    max_distance=self.lookahead_m
                )

        # Project path ahead (with optional route guidance)
        path = self._projector.project_path(
            pos.lat, pos.lon, pos.heading, self.lookahead_m,
            route_waypoints=route_waypoints
        )

        if not path or len(path.points) < 5:
            self._publish_snapshot({
                'status': 'no_path',
                'lat': pos.lat,
                'lon': pos.lon,
                'last_callout': self._last_callout_text,
                'last_callout_time': self._last_callout_time,
                'mode': self._mode,
                'route_name': self._route_name,
            })
            return

        # Extract geometry
        points = [(p.lat, p.lon) for p in path.points]

        # Detect corners
        corners = self._corner_detector.detect_corners(points)

        # Generate pacenotes
        notes = self._pacenote_gen.generate(
            corners,
            path.junctions,
            bridges=path.bridges,
            tunnels=path.tunnels,
            railway_crossings=path.railway_crossings,
            fords=path.fords,
            speed_bumps=path.speed_bumps,
            surface_changes=path.surface_changes,
            barriers=path.barriers,
            narrows=path.narrows,
        )

        # Process notes for audio callouts
        for note in notes:
            should_call, filtered_note = self._pacenote_gen.should_call(
                note, speed_mps=pos.speed
            )
            if should_call and filtered_note:
                self._last_callout_text = filtered_note.text
                self._last_callout_time = time.time()

                if self._audio:
                    self._audio.say(filtered_note.text, filtered_note.priority)

                logger.debug(
                    "CoPilot callout [%dm]: %s",
                    filtered_note.distance_m,
                    filtered_note.text
                )

        # Update corner state for display
        self._corners_ahead = len(corners)
        if corners:
            next_corner = corners[0]
            self._next_corner_distance = next_corner.entry_distance
            self._next_corner_direction = next_corner.direction.value
            self._next_corner_severity = next_corner.severity
        else:
            self._next_corner_distance = 0
            self._next_corner_direction = ""
            self._next_corner_severity = 0

        # Publish snapshot
        self._publish_snapshot({
            'status': 'active',
            'lat': pos.lat,
            'lon': pos.lon,
            'speed_mps': pos.speed,
            'heading': pos.heading,
            'last_callout': self._last_callout_text,
            'last_callout_time': self._last_callout_time,
            'corners_ahead': self._corners_ahead,
            'next_corner_distance': self._next_corner_distance,
            'next_corner_direction': self._next_corner_direction,
            'next_corner_severity': self._next_corner_severity,
            'path_distance': path.total_distance if path else 0,
            'mode': self._mode,
            'route_name': self._route_name,
        })

        # Periodically clear old called notes
        self._pacenote_gen.clear_called()

    def _should_refetch(self, pos: Position) -> bool:
        """Check if we need to fetch new road data."""
        if not self._last_fetch_pos or not self._network:
            return True

        distance = haversine_distance(
            self._last_fetch_pos.lat, self._last_fetch_pos.lon,
            pos.lat, pos.lon,
        )

        return distance > 500  # Refetch when 500m from last load centre

    def _fetch_roads(self, pos: Position):
        """Fetch road data around current position."""
        try:
            logger.info(
                "CoPilot loading roads near %.4f, %.4f",
                pos.lat, pos.lon
            )
            self._network = self._map_loader.load_around(
                pos.lat, pos.lon, radius_m=2000
            )
            self._projector = PathProjector(self._network)
            self._last_fetch_pos = pos
            logger.info(
                "CoPilot loaded %d roads, %d junctions",
                len(self._network.ways),
                len(self._network.junctions)
            )
        except Exception as e:
            logger.error("CoPilot road load failed: %s", e)

    def get_last_callout(self) -> str:
        """Get the last callout text for display."""
        return self._last_callout_text

    def get_next_corner_info(self) -> Dict[str, Any]:
        """
        Get information about the next corner for overlay display.

        Returns:
            Dictionary with distance, direction, severity
        """
        return {
            'distance': self._next_corner_distance,
            'direction': self._next_corner_direction,
            'severity': self._next_corner_severity,
        }

    def set_audio_enabled(self, enabled: bool):
        """Enable or disable audio callouts."""
        self.audio_enabled = enabled
        if enabled and not self._audio:
            self._audio = AudioPlayer()
            self._audio.start()
        elif not enabled and self._audio:
            self._audio.stop()
            self._audio = None

    def set_lookahead(self, lookahead_m: float):
        """Set the lookahead distance."""
        self.lookahead_m = lookahead_m
        self._pacenote_gen = PacenoteGenerator(
            distance_threshold_m=lookahead_m
        )
