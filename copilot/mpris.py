"""
MPRIS D-Bus interface for CoPilot audio metadata.

Provides "Now Playing" information to Bluetooth car head units via AVRCP.
Shows callout text, artist (Skjord Motorsport), and album art on the car display.
"""

import logging
import os
import pwd
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger('openTPT.copilot.mpris')


def _get_session_bus_user() -> tuple[int, str]:
    """
    Get the UID and bus path for the session bus user.

    Returns the first non-root user with an active session bus,
    or falls back to user 'pi' if available.
    """
    # Check for existing session buses
    run_user = Path('/run/user')
    if run_user.exists():
        for uid_dir in sorted(run_user.iterdir()):
            try:
                uid = int(uid_dir.name)
                if uid == 0:
                    continue  # Skip root
                bus_path = uid_dir / 'bus'
                if bus_path.exists():
                    return uid, str(bus_path)
            except (ValueError, PermissionError):
                continue

    # Fall back to 'pi' user if no active session found
    try:
        pi_user = pwd.getpwnam('pi')
        return pi_user.pw_uid, f'/run/user/{pi_user.pw_uid}/bus'
    except KeyError:
        pass

    # Last resort: first non-root user
    for pw in pwd.getpwall():
        if pw.pw_uid >= 1000:
            return pw.pw_uid, f'/run/user/{pw.pw_uid}/bus'

    raise RuntimeError("No suitable user found for session bus")


# Set session bus address for root processes BEFORE importing dbus
# This allows systemd services to connect to the user's session bus
if os.getuid() == 0 and 'DBUS_SESSION_BUS_ADDRESS' not in os.environ:
    try:
        _uid, _bus_path = _get_session_bus_user()
        if os.path.exists(_bus_path):
            os.environ['DBUS_SESSION_BUS_ADDRESS'] = f'unix:path={_bus_path}'
            logger.debug("Set DBUS_SESSION_BUS_ADDRESS for root process: %s", _bus_path)
    except Exception as e:
        logger.debug("Could not determine session bus user: %s", e)

# Try to import D-Bus bindings
try:
    import dbus
    import dbus.service
    import dbus.mainloop.glib
    from gi.repository import GLib
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False
    logger.debug("D-Bus not available - MPRIS metadata disabled")


# MPRIS D-Bus interface names
MPRIS_INTERFACE = "org.mpris.MediaPlayer2"
MPRIS_PLAYER_INTERFACE = "org.mpris.MediaPlayer2.Player"
DBUS_PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"


if DBUS_AVAILABLE:
    class MPRISService(dbus.service.Object):
        """
        MPRIS D-Bus service for CoPilot.

        Implements the MediaPlayer2 and MediaPlayer2.Player interfaces
        to expose "Now Playing" metadata over Bluetooth AVRCP.
        """

        def __init__(self, bus, art_path: Optional[Path] = None):
            """
            Initialise the MPRIS service.

            Args:
                bus: D-Bus bus connection
                art_path: Path to album art image (PNG/JPEG)

            Raises:
                RuntimeError: If bus name acquisition fails
            """
            self._bus = bus
            self._lock = threading.RLock()  # Protect metadata access

            # Request the well-known name on the bus
            name = "org.mpris.MediaPlayer2.openTPT"
            try:
                # Try BusName first (works with SessionBus)
                self._bus_name = dbus.service.BusName(name, bus=bus)
                logger.debug("Acquired bus name via BusName: %s", name)
            except (TypeError, dbus.exceptions.DBusException) as e:
                logger.debug("BusName failed (%s), trying request_name", e)
                # For BusConnection, request name directly
                result = bus.request_name(name, dbus.bus.NAME_FLAG_DO_NOT_QUEUE)
                if result == dbus.bus.REQUEST_NAME_REPLY_PRIMARY_OWNER:
                    logger.debug("Acquired bus name via request_name: %s", name)
                elif result == dbus.bus.REQUEST_NAME_REPLY_ALREADY_OWNER:
                    logger.debug("Already own bus name: %s", name)
                else:
                    raise RuntimeError(f"Failed to acquire bus name {name} (result={result})")
                self._bus_name = None

            dbus.service.Object.__init__(self, bus, "/org/mpris/MediaPlayer2")

            # Album art URL
            if art_path and art_path.exists():
                self._art_url = f"file://{art_path.resolve()}"
            else:
                self._art_url = ""

            # Current metadata (protected by self._lock)
            self._title = ""
            self._playback_status = "Stopped"
            self._track_id = "/org/mpris/MediaPlayer2/TrackList/NoTrack"

        def update_metadata(self, title: str, playing: bool = True) -> None:
            """
            Update the current track metadata.

            Args:
                title: Callout text to display
                playing: Whether audio is currently playing
            """
            with self._lock:
                self._title = title
                self._playback_status = "Playing" if playing else "Stopped"
                self._track_id = f"/org/mpris/MediaPlayer2/Track/{hash(title) & 0xFFFFFFFF}"

                # Emit PropertiesChanged signal
                changed_props = {
                    "Metadata": self._get_metadata(),
                    "PlaybackStatus": self._playback_status,
                }

            self.PropertiesChanged(
                MPRIS_PLAYER_INTERFACE,
                changed_props,
                []
            )

        def set_stopped(self) -> None:
            """Set playback status to stopped."""
            with self._lock:
                self._playback_status = "Stopped"

            self.PropertiesChanged(
                MPRIS_PLAYER_INTERFACE,
                {"PlaybackStatus": "Stopped"},
                []
            )

        def _get_metadata(self) -> dbus.Dictionary:
            """Build metadata dictionary. Must be called with lock held."""
            metadata = dbus.Dictionary({
                "mpris:trackid": dbus.ObjectPath(self._track_id),
                "xesam:title": self._title or "CoPilot Ready",
                "xesam:artist": dbus.Array(["Skjord Motorsport"], signature="s"),
                "xesam:album": "CoPilot",
            }, signature="sv")

            if self._art_url:
                metadata["mpris:artUrl"] = self._art_url

            return metadata

        # =====================================================================
        # org.mpris.MediaPlayer2 interface
        # =====================================================================

        @dbus.service.method(MPRIS_INTERFACE)
        def Raise(self) -> None:
            """Bring the player to the front (no-op for embedded)."""
            pass

        @dbus.service.method(MPRIS_INTERFACE)
        def Quit(self) -> None:
            """Quit the player (no-op for embedded)."""
            pass

        # =====================================================================
        # org.mpris.MediaPlayer2.Player interface
        # =====================================================================

        @dbus.service.method(MPRIS_PLAYER_INTERFACE)
        def Next(self) -> None:
            """Skip to next track (no-op)."""
            pass

        @dbus.service.method(MPRIS_PLAYER_INTERFACE)
        def Previous(self) -> None:
            """Skip to previous track (no-op)."""
            pass

        @dbus.service.method(MPRIS_PLAYER_INTERFACE)
        def Pause(self) -> None:
            """Pause playback (no-op)."""
            pass

        @dbus.service.method(MPRIS_PLAYER_INTERFACE)
        def PlayPause(self) -> None:
            """Toggle play/pause (no-op)."""
            pass

        @dbus.service.method(MPRIS_PLAYER_INTERFACE)
        def Stop(self) -> None:
            """Stop playback (no-op)."""
            pass

        @dbus.service.method(MPRIS_PLAYER_INTERFACE)
        def Play(self) -> None:
            """Start playback (no-op)."""
            pass

        @dbus.service.method(MPRIS_PLAYER_INTERFACE, in_signature="x")
        def Seek(self, offset: int) -> None:
            """Seek by offset (no-op)."""
            pass

        @dbus.service.method(MPRIS_PLAYER_INTERFACE, in_signature="ox")
        def SetPosition(self, track_id: str, position: int) -> None:
            """Set position (no-op)."""
            pass

        @dbus.service.method(MPRIS_PLAYER_INTERFACE, in_signature="s")
        def OpenUri(self, uri: str) -> None:
            """Open URI (no-op)."""
            pass

        # =====================================================================
        # org.freedesktop.DBus.Properties interface
        # =====================================================================

        @dbus.service.method(DBUS_PROPERTIES_INTERFACE, in_signature="ss", out_signature="v")
        def Get(self, interface: str, prop: str):
            """Get a property value."""
            return self.GetAll(interface).get(prop)

        @dbus.service.method(DBUS_PROPERTIES_INTERFACE, in_signature="s", out_signature="a{sv}")
        def GetAll(self, interface: str) -> dbus.Dictionary:
            """Get all properties for an interface."""
            if interface == MPRIS_INTERFACE:
                return dbus.Dictionary({
                    "CanQuit": False,
                    "CanRaise": False,
                    "HasTrackList": False,
                    "Identity": "openTPT CoPilot",
                    "DesktopEntry": "opentpt",
                    "SupportedUriSchemes": dbus.Array([], signature="s"),
                    "SupportedMimeTypes": dbus.Array([], signature="s"),
                }, signature="sv")

            elif interface == MPRIS_PLAYER_INTERFACE:
                with self._lock:
                    return dbus.Dictionary({
                        "PlaybackStatus": self._playback_status,
                        "LoopStatus": "None",
                        "Rate": 1.0,
                        "Shuffle": False,
                        "Metadata": self._get_metadata(),
                        "Volume": 1.0,
                        "Position": dbus.Int64(0),
                        "MinimumRate": 1.0,
                        "MaximumRate": 1.0,
                        "CanGoNext": False,
                        "CanGoPrevious": False,
                        "CanPlay": False,
                        "CanPause": False,
                        "CanSeek": False,
                        "CanControl": False,
                    }, signature="sv")

            return dbus.Dictionary({}, signature="sv")

        @dbus.service.method(DBUS_PROPERTIES_INTERFACE, in_signature="ssv")
        def Set(self, interface: str, prop: str, value) -> None:
            """Set a property value (no-op, all props are read-only)."""
            pass

        @dbus.service.signal(DBUS_PROPERTIES_INTERFACE, signature="sa{sv}as")
        def PropertiesChanged(
            self,
            interface: str,
            changed: dict,
            invalidated: list
        ) -> None:
            """Signal property changes to listeners."""
            pass


class MPRISProvider:
    """
    High-level MPRIS provider for CoPilot.

    Manages the D-Bus mainloop and service lifecycle.
    Thread-safe - can be called from any thread.
    """

    def __init__(self, art_path: Optional[Path] = None):
        """
        Initialise the MPRIS provider.

        Args:
            art_path: Path to album art image
        """
        self._art_path = art_path
        self._service: Optional["MPRISService"] = None
        self._mainloop: Optional["GLib.MainLoop"] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._init_event = threading.Event()  # Signals when initialisation completes
        self._init_error: Optional[str] = None  # Stores initialisation error message

    @property
    def available(self) -> bool:
        """Check if MPRIS is available."""
        return DBUS_AVAILABLE

    def start(self, timeout: float = 5.0) -> bool:
        """
        Start the MPRIS service.

        Args:
            timeout: Maximum seconds to wait for initialisation

        Returns:
            True if started successfully
        """
        if not DBUS_AVAILABLE:
            logger.info("MPRIS not available (D-Bus bindings not installed)")
            return False

        if self._running:
            return True

        try:
            self._running = True
            self._init_event.clear()
            self._init_error = None
            self._thread = threading.Thread(target=self._run_mainloop, daemon=True)
            self._thread.start()

            # Wait for initialisation to complete
            if not self._init_event.wait(timeout=timeout):
                logger.warning("MPRIS service initialisation timed out")
                self._running = False
                return False

            if self._init_error:
                logger.warning("MPRIS service failed: %s", self._init_error)
                self._running = False
                return False

            if self._service:
                logger.info("MPRIS service started: org.mpris.MediaPlayer2.openTPT")
                return True
            else:
                logger.warning("MPRIS service failed to initialise")
                self._running = False
                return False

        except Exception as e:
            logger.warning("Failed to start MPRIS service: %s", e)
            self._running = False
            return False

    def stop(self) -> None:
        """Stop the MPRIS service."""
        self._running = False

        if self._mainloop:
            self._mainloop.quit()

        if self._thread:
            self._thread.join(timeout=1)

        self._service = None
        self._mainloop = None
        self._init_event.clear()
        logger.info("MPRIS service stopped")

    def update_now_playing(self, title: str) -> None:
        """
        Update the "Now Playing" metadata.

        Thread-safe - can be called from any thread.

        Args:
            title: Callout text to display on head unit
        """
        # Store local references to avoid TOCTOU race
        service = self._service
        mainloop = self._mainloop

        if service and self._running and mainloop:
            GLib.idle_add(service.update_metadata, title, True)

    def set_stopped(self) -> None:
        """Set playback status to stopped."""
        # Store local references to avoid TOCTOU race
        service = self._service
        mainloop = self._mainloop

        if service and self._running and mainloop:
            GLib.idle_add(service.set_stopped)

    def _run_mainloop(self) -> None:
        """Run the GLib mainloop (called in background thread)."""
        try:
            # Initialise D-Bus mainloop integration FIRST
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

            # Determine session bus address
            session_address = os.environ.get('DBUS_SESSION_BUS_ADDRESS')
            if not session_address:
                # For root/systemd services, find the user's session bus
                try:
                    uid, bus_path = _get_session_bus_user()
                    session_address = f'unix:path={bus_path}'
                except Exception as e:
                    raise RuntimeError(f"Could not determine session bus: {e}")

            # Wait for socket to appear (may not exist at boot before user login)
            socket_path = session_address.replace('unix:path=', '')
            max_wait = 60  # Wait up to 60 seconds for session bus
            waited = 0
            while not os.path.exists(socket_path) and waited < max_wait:
                if not self._running:
                    self._init_event.set()
                    return  # Cancelled during wait
                time.sleep(2)
                waited += 2
                if waited % 10 == 0:
                    logger.debug("Waiting for session bus socket: %s (%ds)", socket_path, waited)

            if not os.path.exists(socket_path):
                raise RuntimeError(f"Session bus socket not found after {max_wait}s: {socket_path}")

            # Check socket permissions
            socket_stat = os.stat(socket_path)
            logger.debug(
                "Session bus socket: %s (mode=%o, uid=%d)",
                socket_path, socket_stat.st_mode & 0o777, socket_stat.st_uid
            )

            # Connect directly to the bus address
            bus = dbus.bus.BusConnection(session_address)
            logger.debug("Connected to session bus at %s", session_address)

            # Create MPRIS service (which will register the name)
            self._service = MPRISService(bus, self._art_path)

            # Verify name was acquired
            name = "org.mpris.MediaPlayer2.openTPT"
            if bus.name_has_owner(name):
                logger.info("MPRIS name acquired: %s", name)
            else:
                raise RuntimeError(f"MPRIS name not visible on bus: {name}")

            # Signal successful initialisation
            self._init_event.set()

            # Run mainloop
            self._mainloop = GLib.MainLoop()
            while self._running:
                # Run with timeout to allow checking _running flag
                context = self._mainloop.get_context()
                context.iteration(True)

        except Exception as e:
            logger.error("MPRIS mainloop error: %s", e, exc_info=True)
            self._init_error = str(e)
            self._service = None
            self._mainloop = None
            self._running = False
            self._init_event.set()  # Signal completion (with error)
