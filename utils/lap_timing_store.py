"""
Persistent storage for lap timing data.

Stores best lap times, session history, and reference lap GPS traces
in SQLite database for persistence across restarts.
"""

import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# Default data directory
LAP_TIMING_DATA_DIR = os.path.expanduser("~/.opentpt/lap_timing")
DATABASE_FILE = os.path.join(LAP_TIMING_DATA_DIR, "lap_timing.db")


@dataclass
class LapRecord:
    """A recorded lap time."""
    track_name: str
    lap_time: float  # seconds
    timestamp: float  # Unix timestamp when lap was recorded
    sectors: Optional[List[float]] = None  # sector times in seconds
    session_id: Optional[str] = None
    conditions: Optional[str] = None  # e.g. "dry", "wet"

    def format_time(self) -> str:
        """Format lap time as M:SS.mmm."""
        minutes = int(self.lap_time // 60)
        seconds = self.lap_time % 60
        return f"{minutes}:{seconds:06.3f}"


@dataclass
class ReferenceLap:
    """A reference lap with full GPS trace for delta calculations."""
    track_name: str
    lap_time: float
    timestamp: float
    gps_trace: List[Dict[str, Any]]  # List of {lat, lon, elapsed_time, track_position}


class LapTimingStore:
    """
    Manages persistent storage of lap timing data.

    Thread-safe singleton for concurrent access from multiple handlers.
    """

    _instance: Optional['LapTimingStore'] = None
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
        """Initialise the lap timing store."""
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
            os.makedirs(LAP_TIMING_DATA_DIR, exist_ok=True)
            print(f"Lap timing data directory: {LAP_TIMING_DATA_DIR}")
        except Exception as e:
            print(f"Warning: Could not create lap timing data directory: {e}")

    def _init_database(self):
        """Initialise the SQLite database with required tables."""
        with self._db_lock:
            try:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.cursor()

                # Lap records table - all recorded laps
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS lap_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        track_name TEXT NOT NULL,
                        lap_time REAL NOT NULL,
                        timestamp REAL NOT NULL,
                        sectors TEXT,
                        session_id TEXT,
                        conditions TEXT
                    )
                ''')

                # Best laps table - best lap per track (quick lookup)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS best_laps (
                        track_name TEXT PRIMARY KEY,
                        lap_time REAL NOT NULL,
                        timestamp REAL NOT NULL,
                        sectors TEXT
                    )
                ''')

                # Reference laps table - full GPS traces for delta calculation
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS reference_laps (
                        track_name TEXT PRIMARY KEY,
                        lap_time REAL NOT NULL,
                        timestamp REAL NOT NULL,
                        gps_trace TEXT NOT NULL
                    )
                ''')

                # Sessions table - session metadata
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id TEXT PRIMARY KEY,
                        track_name TEXT NOT NULL,
                        start_time REAL NOT NULL,
                        end_time REAL,
                        total_laps INTEGER DEFAULT 0,
                        best_lap_time REAL
                    )
                ''')

                # Index for faster queries
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_lap_records_track
                    ON lap_records(track_name)
                ''')

                conn.commit()
                conn.close()
                print(f"Lap timing database initialised: {self._db_path}")

            except Exception as e:
                print(f"Warning: Could not initialise lap timing database: {e}")

    def record_lap(self, lap: LapRecord) -> bool:
        """
        Record a completed lap.

        Args:
            lap: The lap record to store

        Returns:
            True if this was a new best lap for the track
        """
        is_new_best = False

        with self._db_lock:
            try:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.cursor()

                # Store in lap records
                sectors_json = json.dumps(lap.sectors) if lap.sectors else None
                cursor.execute('''
                    INSERT INTO lap_records
                    (track_name, lap_time, timestamp, sectors, session_id, conditions)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    lap.track_name,
                    lap.lap_time,
                    lap.timestamp,
                    sectors_json,
                    lap.session_id,
                    lap.conditions
                ))

                # Check if this is a new best
                cursor.execute('''
                    SELECT lap_time FROM best_laps WHERE track_name = ?
                ''', (lap.track_name,))
                row = cursor.fetchone()

                if row is None or lap.lap_time < row[0]:
                    # New best lap
                    cursor.execute('''
                        INSERT OR REPLACE INTO best_laps
                        (track_name, lap_time, timestamp, sectors)
                        VALUES (?, ?, ?, ?)
                    ''', (lap.track_name, lap.lap_time, lap.timestamp, sectors_json))
                    is_new_best = True
                    print(f"New best lap for {lap.track_name}: {lap.format_time()}")

                conn.commit()
                conn.close()

            except Exception as e:
                print(f"Warning: Could not record lap: {e}")

        return is_new_best

    def get_best_lap(self, track_name: str) -> Optional[LapRecord]:
        """
        Get the best lap for a track.

        Args:
            track_name: Name of the track

        Returns:
            Best lap record or None if no laps recorded
        """
        with self._db_lock:
            try:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.cursor()

                cursor.execute('''
                    SELECT lap_time, timestamp, sectors
                    FROM best_laps WHERE track_name = ?
                ''', (track_name,))
                row = cursor.fetchone()
                conn.close()

                if row:
                    sectors = json.loads(row[2]) if row[2] else None
                    return LapRecord(
                        track_name=track_name,
                        lap_time=row[0],
                        timestamp=row[1],
                        sectors=sectors
                    )

            except Exception as e:
                print(f"Warning: Could not get best lap: {e}")

        return None

    def get_all_best_laps(self) -> Dict[str, LapRecord]:
        """
        Get all best laps indexed by track name.

        Returns:
            Dict mapping track name to best lap record
        """
        result = {}

        with self._db_lock:
            try:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.cursor()

                cursor.execute('''
                    SELECT track_name, lap_time, timestamp, sectors
                    FROM best_laps
                ''')

                for row in cursor.fetchall():
                    sectors = json.loads(row[3]) if row[3] else None
                    result[row[0]] = LapRecord(
                        track_name=row[0],
                        lap_time=row[1],
                        timestamp=row[2],
                        sectors=sectors
                    )

                conn.close()

            except Exception as e:
                print(f"Warning: Could not get best laps: {e}")

        return result

    def clear_best_lap(self, track_name: str) -> bool:
        """
        Clear the best lap for a specific track.

        Args:
            track_name: Name of the track

        Returns:
            True if a record was deleted
        """
        with self._db_lock:
            try:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.cursor()

                cursor.execute('''
                    DELETE FROM best_laps WHERE track_name = ?
                ''', (track_name,))

                deleted = cursor.rowcount > 0
                conn.commit()
                conn.close()

                if deleted:
                    print(f"Cleared best lap for {track_name}")

                return deleted

            except Exception as e:
                print(f"Warning: Could not clear best lap: {e}")
                return False

    def clear_all_best_laps(self) -> int:
        """
        Clear all best laps.

        Returns:
            Number of records deleted
        """
        with self._db_lock:
            try:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.cursor()

                cursor.execute('DELETE FROM best_laps')
                deleted = cursor.rowcount
                conn.commit()
                conn.close()

                print(f"Cleared {deleted} best lap records")
                return deleted

            except Exception as e:
                print(f"Warning: Could not clear best laps: {e}")
                return 0

    def save_reference_lap(
        self,
        track_name: str,
        lap_time: float,
        gps_trace: List[Dict[str, Any]]
    ) -> bool:
        """
        Save a reference lap with full GPS trace for delta calculation.

        Args:
            track_name: Name of the track
            lap_time: Lap time in seconds
            gps_trace: List of GPS points with elapsed_time and track_position

        Returns:
            True if saved successfully
        """
        with self._db_lock:
            try:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.cursor()

                cursor.execute('''
                    INSERT OR REPLACE INTO reference_laps
                    (track_name, lap_time, timestamp, gps_trace)
                    VALUES (?, ?, ?, ?)
                ''', (
                    track_name,
                    lap_time,
                    time.time(),
                    json.dumps(gps_trace)
                ))

                conn.commit()
                conn.close()
                print(f"Saved reference lap for {track_name}: {len(gps_trace)} points")
                return True

            except Exception as e:
                print(f"Warning: Could not save reference lap: {e}")
                return False

    def get_reference_lap(self, track_name: str) -> Optional[ReferenceLap]:
        """
        Get the reference lap for a track.

        Args:
            track_name: Name of the track

        Returns:
            Reference lap with GPS trace or None
        """
        with self._db_lock:
            try:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.cursor()

                cursor.execute('''
                    SELECT lap_time, timestamp, gps_trace
                    FROM reference_laps WHERE track_name = ?
                ''', (track_name,))
                row = cursor.fetchone()
                conn.close()

                if row:
                    return ReferenceLap(
                        track_name=track_name,
                        lap_time=row[0],
                        timestamp=row[1],
                        gps_trace=json.loads(row[2])
                    )

            except Exception as e:
                print(f"Warning: Could not get reference lap: {e}")

        return None

    def get_recent_laps(
        self,
        track_name: str,
        limit: int = 10
    ) -> List[LapRecord]:
        """
        Get recent laps for a track.

        Args:
            track_name: Name of the track
            limit: Maximum number of laps to return

        Returns:
            List of recent lap records, newest first
        """
        result = []

        with self._db_lock:
            try:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.cursor()

                cursor.execute('''
                    SELECT lap_time, timestamp, sectors, session_id, conditions
                    FROM lap_records
                    WHERE track_name = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (track_name, limit))

                for row in cursor.fetchall():
                    sectors = json.loads(row[2]) if row[2] else None
                    result.append(LapRecord(
                        track_name=track_name,
                        lap_time=row[0],
                        timestamp=row[1],
                        sectors=sectors,
                        session_id=row[3],
                        conditions=row[4]
                    ))

                conn.close()

            except Exception as e:
                print(f"Warning: Could not get recent laps: {e}")

        return result

    def get_track_stats(self, track_name: str) -> Dict[str, Any]:
        """
        Get statistics for a track.

        Args:
            track_name: Name of the track

        Returns:
            Dict with total_laps, best_time, average_time, etc.
        """
        stats = {
            'total_laps': 0,
            'best_time': None,
            'average_time': None,
            'last_lap': None,
        }

        with self._db_lock:
            try:
                conn = sqlite3.connect(self._db_path)
                cursor = conn.cursor()

                # Count and average
                cursor.execute('''
                    SELECT COUNT(*), AVG(lap_time), MIN(lap_time), MAX(timestamp)
                    FROM lap_records
                    WHERE track_name = ?
                ''', (track_name,))
                row = cursor.fetchone()

                if row and row[0] > 0:
                    stats['total_laps'] = row[0]
                    stats['average_time'] = row[1]
                    stats['best_time'] = row[2]
                    stats['last_lap'] = row[3]

                conn.close()

            except Exception as e:
                print(f"Warning: Could not get track stats: {e}")

        return stats


# Convenience function to get the singleton instance
def get_lap_timing_store() -> LapTimingStore:
    """Get the lap timing store singleton."""
    return LapTimingStore()
