"""Main CoPilot application loop."""

import threading
import time
from typing import Optional, Protocol

from .gps import GPSReader, Position
from .map_loader import MapLoader, RoadNetwork
from .path_projector import PathProjector, ProjectedPath
from .corners import CornerDetector
from .pacenotes import PacenoteGenerator
from .audio import AudioPlayer
from .geometry import haversine_distance
from . import config


class GPSInterface(Protocol):
    """Protocol for GPS data sources."""
    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def read_position(self) -> Optional[Position]: ...


class CoPilot:
    """
    Main CoPilot application coordinating GPS, maps, and audio callouts.

    This class orchestrates all CoPilot components to provide rally-style
    pacenote callouts while driving. It reads GPS position, projects the
    road ahead from OSM map data, detects corners, and generates audio
    callouts for upcoming hazards.

    Architecture
    ------------
    The CoPilot runs a main loop that executes update cycles at a fixed
    interval (default 0.2s = 5Hz). Each cycle:

    1. Read GPS position
    2. Check/apply pending background map loads
    3. Fetch new road data if moved far from last load centre
    4. Project path ahead using road network topology
    5. Detect corners in projected path
    6. Generate pacenotes for detected features
    7. Filter and speak new callouts via audio system
    8. Update visualisation (if enabled)

    Asynchronous Map Loading
    ------------------------
    Road data loading can be slow (100-500ms for dense areas). To avoid
    blocking the update loop:

    - First load is synchronous (must have data to start)
    - Subsequent loads happen in a background daemon thread
    - _pending_network stores loaded data for main thread pickup
    - _apply_pending_network() atomically swaps in new data

    State Machine
    -------------
    The map loading state machine has three states:

    1. NO_DATA: _network is None, needs initial sync load
    2. LOADING: _loading_thread is alive, async load in progress
    3. READY: _network is set, normal operation

    Transitions:
    - NO_DATA -> READY: via _fetch_roads_sync()
    - READY -> LOADING: via _fetch_roads_async() when moved far enough
    - LOADING -> READY: via _apply_pending_network() on next update

    Thread Safety
    -------------
    - Main loop runs in calling thread (typically main thread)
    - Background loads use daemon thread (dies with main)
    - _pending_network/pos set atomically from background thread
    - Audio playback runs in separate thread via AudioPlayer

    GPS Sources
    -----------
    Supports multiple GPS interfaces via GPSInterface protocol:
    - GPSReader: Real serial GPS (PA1616S at 10Hz)
    - GPSSimulator: Simulated GPS at fixed heading
    - VBOSimulator: Replay from VBO log file
    - GPXSimulator: Follow GPX route file
    """

    def __init__(
        self,
        gps: GPSInterface,
        map_loader: MapLoader,
        lookahead_m: float = config.LOOKAHEAD_DISTANCE_M,
        update_interval: float = config.UPDATE_INTERVAL_S,
        audio_enabled: bool = True,
        visualize: bool = False,
        simulation_mode: bool = False,
    ):
        self.gps = gps
        self.map_loader = map_loader
        # Tune corner detection for better square/chicane detection
        self.corner_detector = CornerDetector(
            merge_same_direction=False,  # Don't merge consecutive same-direction turns
            min_cut_distance=10.0,        # More precise cuts (was 15)
            max_chicane_gap=15.0,         # Tighter chicane merging (was 30)
        )
        self.pacenote_gen = PacenoteGenerator(distance_threshold_m=lookahead_m)
        self.visualize = visualize
        self.simulation_mode = simulation_mode

        if audio_enabled:
            self.audio = AudioPlayer()
        else:
            self.audio = None

        self.lookahead = lookahead_m
        self.update_interval = update_interval

        self._network: Optional[RoadNetwork] = None
        self._projector: Optional[PathProjector] = None
        self._last_fetch_pos: Optional[Position] = None
        self._visualizer = None
        self._loading_thread: Optional[threading.Thread] = None
        self._pending_network: Optional[RoadNetwork] = None
        self._pending_pos: Optional[Position] = None

    def run(self) -> None:
        """Main application loop."""
        print("CoPilot starting...")
        print(f"Lookahead: {self.lookahead}m")

        self.gps.connect()
        if self.audio:
            self.audio.start()
            time.sleep(0.1)  # Let audio thread fully initialise

        print("GPS ready, starting navigation...")

        try:
            while True:
                self._update_cycle()
                time.sleep(self.update_interval)
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            if self.audio:
                self.audio.stop()
            self.gps.disconnect()

    def _update_cycle(self) -> None:
        """
        Execute a single update cycle of the CoPilot main loop.

        This method performs the complete pipeline from GPS reading to audio
        callout. It is called repeatedly by run() at the configured update
        interval (typically 5Hz).

        Pipeline Steps:
            1. Read GPS position - skip cycle if no fix available
            2. Apply pending network - swap in background-loaded map data
            3. Refetch roads if needed - async load when far from last centre
            4. Project path - use road topology to predict path ahead
            5. Detect corners - ASC algorithm on projected geometry
            6. Generate pacenotes - convert corners/features to callouts
            7. Filter and speak - deduplicate and send to audio system
            8. Update visualisation - refresh map display if enabled
            9. Clear old callouts - prevent memory growth

        Note:
            This method is designed to complete quickly (< 50ms typical).
            Expensive operations like map loading are delegated to background
            threads. If GPS has no fix, the cycle returns immediately.
        """
        pos = self.gps.read_position()
        if not pos:
            return

        # Check if background load completed
        if self._pending_network is not None:
            self._apply_pending_network()

        # Fetch road data if needed
        if self._should_refetch(pos):
            if self._network is None:
                # First load - block so we have data to start with
                self._fetch_roads_sync(pos)
            else:
                # Subsequent loads - async to avoid blocking visualiser
                self._fetch_roads_async(pos)

        if not self._network or not self._projector:
            return

        # Get path ahead - use road network projection with optional GPX route guidance
        route_waypoints = None
        if hasattr(self.gps, 'get_upcoming_path'):
            # GPX mode: get route waypoints to guide junction decisions
            route_waypoints = self.gps.get_upcoming_path(self.lookahead)

        # Project path from road network (optionally guided by GPX route)
        path = self._projector.project_path(
            pos.lat, pos.lon, pos.heading, self.lookahead,
            route_waypoints=route_waypoints
        )
        if not path or len(path.points) < 5:
            return
        # Extract geometry from path
        points = [(p.lat, p.lon) for p in path.points]

        # Detect corners
        corners = self.corner_detector.detect_corners(points)

        # Generate pacenotes
        notes = self.pacenote_gen.generate(
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

        # Speak/print notes that haven't been called yet
        # Pass speed for speed-scaled callout timing
        for note in notes:
            should_call, filtered_note = self.pacenote_gen.should_call(
                note, speed_mps=pos.speed
            )
            if should_call and filtered_note:
                if self.audio:
                    self.audio.say(filtered_note.text, filtered_note.priority)
                print(f"  >>> [{filtered_note.distance_m:.0f}m] {filtered_note.text}")

        # Update visualisation
        if self._visualizer:
            self._visualizer.update(pos.lat, pos.lon, pos.heading, path, corners)

        # Periodically clear old called notes
        self.pacenote_gen.clear_called()

    def _should_refetch(self, pos: Position) -> bool:
        """Check if we need to fetch new road data."""
        # Don't start new load if one is already in progress
        if self._loading_thread is not None and self._loading_thread.is_alive():
            return False

        if not self._last_fetch_pos or not self._network:
            return True

        distance = haversine_distance(
            self._last_fetch_pos.lat, self._last_fetch_pos.lon,
            pos.lat, pos.lon,
        )

        # In simulation mode, use larger threshold (half the load radius)
        # to avoid frequent reloads while still covering long routes
        if self.simulation_mode:
            return distance > 2500  # Refetch when 2.5km from last load centre

        return distance > config.REFETCH_DISTANCE_M

    def _fetch_roads_sync(self, pos: Position) -> None:
        """Fetch road data synchronously (blocks until complete)."""
        radius = 5000 if self.simulation_mode else config.ROAD_FETCH_RADIUS_M

        try:
            print(f"Loading roads near {pos.lat:.4f}, {pos.lon:.4f}...")
            self._network = self.map_loader.load_around(pos.lat, pos.lon, radius)
            self._projector = PathProjector(self._network)
            self._last_fetch_pos = pos

            print(f"Loaded {len(self._network.ways)} roads, "
                  f"{len(self._network.junctions)} junctions")

            if hasattr(self.gps, 'set_network'):
                self.gps.set_network(self._network)

            if self.visualize and not self._visualizer:
                try:
                    from .visualizer import MapVisualizer
                    route_bounds = None
                    if hasattr(self.gps, 'get_route_bounds'):
                        route_bounds = self.gps.get_route_bounds()
                    self._visualizer = MapVisualizer(self._network, route_bounds)
                    print("Visualisation window opened")
                except ImportError as e:
                    print(f"Visualisation unavailable: {e}")
                    self.visualize = False
        except Exception as e:
            print(f"Error loading roads: {e}")

    def _fetch_roads_async(self, pos: Position) -> None:
        """Start background thread to fetch road data."""
        radius = 5000 if self.simulation_mode else config.ROAD_FETCH_RADIUS_M

        def load_in_background():
            try:
                print(f"Loading roads near {pos.lat:.4f}, {pos.lon:.4f}...")
                network = self.map_loader.load_around(pos.lat, pos.lon, radius)
                # Store for main thread to pick up
                self._pending_network = network
                self._pending_pos = pos
            except Exception as e:
                print(f"Error loading roads: {e}")

        self._loading_thread = threading.Thread(target=load_in_background, daemon=True)
        self._loading_thread.start()

    def _apply_pending_network(self) -> None:
        """Apply network loaded by background thread."""
        if self._pending_network is None:
            return

        self._network = self._pending_network
        self._projector = PathProjector(self._network)
        self._last_fetch_pos = self._pending_pos

        print(f"Loaded {len(self._network.ways)} roads, "
              f"{len(self._network.junctions)} junctions")

        # Share network with simulator if it needs it for route building
        if hasattr(self.gps, 'set_network'):
            self.gps.set_network(self._network)

        # Initialise visualiser if enabled (only on first load)
        if self.visualize and not self._visualizer:
            try:
                from .visualizer import MapVisualizer
                route_bounds = None
                if hasattr(self.gps, 'get_route_bounds'):
                    route_bounds = self.gps.get_route_bounds()
                self._visualizer = MapVisualizer(self._network, route_bounds)
                print("Visualisation window opened")
            except ImportError as e:
                print(f"Visualisation unavailable: {e}")
                self.visualize = False

        # Clear pending
        self._pending_network = None
        self._pending_pos = None
