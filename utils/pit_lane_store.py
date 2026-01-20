"""
Persistent storage for pit lane timer data.

Stores pit lane waypoints (entry/exit lines) and pit session history
in SQLite database for persistence across restarts.
"""

import logging
import math
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

from config import PIT_TIMER_DATA_DIR

logger = logging.getLogger('openTPT.pit_timer')


# Default data directory and database file
DATABASE_FILE = os.path.join(PIT_TIMER_DATA_DIR, "pit_waypoints.db")


@dataclass
class PitLine:
    """Defines a pit lane entry or exit crossing line."""
    point1: Tuple[float, float]  # (lat, lon) - one end
    point2: Tuple[float, float]  # (lat, lon) - other end
    centre: Tuple[float, float]  # midpoint
    heading: float               # perpendicular direction (degrees)
    width: float                 # line width in metres


@dataclass
class PitWaypoints:
    """Pit lane waypoints for a specific track."""
    track_name: str
    entry_line: Optional[PitLine] = None
    exit_line: Optional[PitLine] = None
    speed_limit_kmh: float = 60.0
    min_stop_time_s: float = 0.0  # countdown target


@dataclass
class PitSession:
    """A recorded pit stop session."""
    track_name: str
    entry_time: float          # Unix timestamp
    exit_time: float           # Unix timestamp
    stationary_time: float     # Seconds spent stationary
    total_time: float          # Total pit time in seconds
    speed_violations: int = 0  # Number of speed limit violations
    timestamp: float = 0.0     # When this was recorded


class PitLaneStore:
    """
    Manages persistent storage of pit lane data.

    Thread-safe singleton for concurrent access from multiple handlers.
    """

    _instance: Optional['PitLaneStore'] = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern - only one store instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialised = False
        return cls._instance

    def __init__(self):
        """Initialise the pit lane store."""
        if self._initialised:
            return

        self._db_path = DATABASE_FILE
        self._db_lock = threading.Lock()
        self._ensure_data_dir()
        self._init_database()
        self._initialised = True

    def _ensure_data_dir(self):
        """Create data directory if it doesn't exist."""
        try:
            os.makedirs(PIT_TIMER_DATA_DIR, exist_ok=True)
            logger.info("Pit timer data directory: %s", PIT_TIMER_DATA_DIR)
        except Exception as e:
            logger.warning("Could not create pit timer data directory: %s", e)

    def _init_database(self):
        """Initialise the SQLite database with required tables."""
        with self._db_lock:
            try:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.cursor()

                # Pit waypoints table - entry/exit lines per track
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS pit_waypoints (
                        track_name TEXT PRIMARY KEY,
                        entry_lat1 REAL, entry_lon1 REAL,
                        entry_lat2 REAL, entry_lon2 REAL,
                        exit_lat1 REAL, exit_lon1 REAL,
                        exit_lat2 REAL, exit_lon2 REAL,
                        speed_limit_kmh REAL DEFAULT 60.0,
                        min_stop_time_s REAL DEFAULT 0.0,
                        updated_at REAL
                    )
                ''')

                # Pit sessions table - history of pit stops
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS pit_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        track_name TEXT,
                        entry_time REAL,
                        exit_time REAL,
                        stationary_time REAL,
                        total_time REAL,
                        speed_violations INTEGER DEFAULT 0,
                        timestamp REAL
                    )
                ''')

                # Index for faster queries
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_pit_sessions_track
                    ON pit_sessions(track_name)
                ''')

                conn.commit()
                conn.close()
                logger.info("Pit timer database initialised: %s", self._db_path)

            except Exception as e:
                logger.warning("Could not initialise pit timer database: %s", e)

    def save_waypoints(self, waypoints: PitWaypoints) -> bool:
        """
        Save pit waypoints for a track.

        Args:
            waypoints: PitWaypoints object to save

        Returns:
            True if saved successfully
        """
        with self._db_lock:
            try:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.cursor()

                # Extract line coordinates
                entry_lat1, entry_lon1 = waypoints.entry_line.point1 if waypoints.entry_line else (None, None)
                entry_lat2, entry_lon2 = waypoints.entry_line.point2 if waypoints.entry_line else (None, None)
                exit_lat1, exit_lon1 = waypoints.exit_line.point1 if waypoints.exit_line else (None, None)
                exit_lat2, exit_lon2 = waypoints.exit_line.point2 if waypoints.exit_line else (None, None)

                cursor.execute('''
                    INSERT OR REPLACE INTO pit_waypoints
                    (track_name, entry_lat1, entry_lon1, entry_lat2, entry_lon2,
                     exit_lat1, exit_lon1, exit_lat2, exit_lon2,
                     speed_limit_kmh, min_stop_time_s, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    waypoints.track_name,
                    entry_lat1, entry_lon1, entry_lat2, entry_lon2,
                    exit_lat1, exit_lon1, exit_lat2, exit_lon2,
                    waypoints.speed_limit_kmh,
                    waypoints.min_stop_time_s,
                    time.time()
                ))

                conn.commit()
                conn.close()
                logger.info("Saved pit waypoints for %s", waypoints.track_name)
                return True

            except Exception as e:
                logger.warning("Could not save pit waypoints: %s", e)
                return False

    def get_waypoints(self, track_name: str) -> Optional[PitWaypoints]:
        """
        Get pit waypoints for a track.

        Args:
            track_name: Name of the track

        Returns:
            PitWaypoints object or None if not found
        """
        with self._db_lock:
            try:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.cursor()

                cursor.execute('''
                    SELECT entry_lat1, entry_lon1, entry_lat2, entry_lon2,
                           exit_lat1, exit_lon1, exit_lat2, exit_lon2,
                           speed_limit_kmh, min_stop_time_s
                    FROM pit_waypoints WHERE track_name = ?
                ''', (track_name,))
                row = cursor.fetchone()
                conn.close()

                if row:
                    entry_line = None
                    exit_line = None

                    # Reconstruct entry line if coordinates exist
                    if row[0] is not None and row[1] is not None:
                        p1 = (row[0], row[1])
                        p2 = (row[2], row[3])
                        centre = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
                        entry_line = PitLine(
                            point1=p1,
                            point2=p2,
                            centre=centre,
                            heading=0.0,  # Recalculated when used
                            width=self._calculate_line_width(p1, p2)
                        )

                    # Reconstruct exit line if coordinates exist
                    if row[4] is not None and row[5] is not None:
                        p1 = (row[4], row[5])
                        p2 = (row[6], row[7])
                        centre = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
                        exit_line = PitLine(
                            point1=p1,
                            point2=p2,
                            centre=centre,
                            heading=0.0,  # Recalculated when used
                            width=self._calculate_line_width(p1, p2)
                        )

                    return PitWaypoints(
                        track_name=track_name,
                        entry_line=entry_line,
                        exit_line=exit_line,
                        speed_limit_kmh=row[8] or 60.0,
                        min_stop_time_s=row[9] or 0.0
                    )

            except Exception as e:
                logger.warning("Could not get pit waypoints: %s", e)

        return None

    def _calculate_line_width(self, p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        """Calculate approximate width of a line in metres from lat/lon points."""
        # Haversine formula for distance
        lat1, lon1 = math.radians(p1[0]), math.radians(p1[1])
        lat2, lon2 = math.radians(p2[0]), math.radians(p2[1])

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))

        # Earth radius in metres
        r = 6371000
        return r * c

    def record_session(self, session: PitSession) -> bool:
        """
        Record a completed pit session.

        Args:
            session: PitSession object to record

        Returns:
            True if recorded successfully
        """
        with self._db_lock:
            try:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.cursor()

                cursor.execute('''
                    INSERT INTO pit_sessions
                    (track_name, entry_time, exit_time, stationary_time,
                     total_time, speed_violations, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    session.track_name,
                    session.entry_time,
                    session.exit_time,
                    session.stationary_time,
                    session.total_time,
                    session.speed_violations,
                    time.time()
                ))

                conn.commit()
                conn.close()
                logger.info("Recorded pit session for %s: %.1fs total, %.1fs stationary",
                           session.track_name, session.total_time, session.stationary_time)
                return True

            except Exception as e:
                logger.warning("Could not record pit session: %s", e)
                return False

    def get_recent_sessions(
        self,
        track_name: str,
        limit: int = 10
    ) -> List[PitSession]:
        """
        Get recent pit sessions for a track.

        Args:
            track_name: Name of the track
            limit: Maximum number of sessions to return

        Returns:
            List of PitSession objects, newest first
        """
        result = []

        with self._db_lock:
            try:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.cursor()

                cursor.execute('''
                    SELECT entry_time, exit_time, stationary_time,
                           total_time, speed_violations, timestamp
                    FROM pit_sessions
                    WHERE track_name = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (track_name, limit))

                for row in cursor.fetchall():
                    result.append(PitSession(
                        track_name=track_name,
                        entry_time=row[0],
                        exit_time=row[1],
                        stationary_time=row[2],
                        total_time=row[3],
                        speed_violations=row[4],
                        timestamp=row[5]
                    ))

                conn.close()

            except Exception as e:
                logger.warning("Could not get recent pit sessions: %s", e)

        return result

    def get_best_pit_time(self, track_name: str) -> Optional[float]:
        """
        Get the best (fastest) pit time for a track.

        Args:
            track_name: Name of the track

        Returns:
            Best pit time in seconds, or None if no sessions
        """
        with self._db_lock:
            try:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.cursor()

                cursor.execute('''
                    SELECT MIN(total_time)
                    FROM pit_sessions
                    WHERE track_name = ?
                ''', (track_name,))
                row = cursor.fetchone()
                conn.close()

                if row and row[0] is not None:
                    return row[0]

            except Exception as e:
                logger.warning("Could not get best pit time: %s", e)

        return None

    def clear_waypoints(self, track_name: str) -> bool:
        """
        Clear pit waypoints for a track.

        Args:
            track_name: Name of the track

        Returns:
            True if waypoints were deleted
        """
        with self._db_lock:
            try:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.cursor()

                cursor.execute('''
                    DELETE FROM pit_waypoints WHERE track_name = ?
                ''', (track_name,))

                deleted = cursor.rowcount > 0
                conn.commit()
                conn.close()

                if deleted:
                    logger.info("Cleared pit waypoints for %s", track_name)

                return deleted

            except Exception as e:
                logger.warning("Could not clear pit waypoints: %s", e)
                return False


# Convenience function to get the singleton instance
def get_pit_lane_store() -> PitLaneStore:
    """Get the pit lane store singleton."""
    return PitLaneStore()
