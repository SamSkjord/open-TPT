"""Tests for utils/lap_timing_store.py - lap time persistence."""

import json
import os
import sqlite3
import tempfile
import time
import pytest

from utils.lap_timing_store import (
    LapRecord, ReferenceLap, LapTimingStore, get_lap_timing_store
)


class TestLapRecord:
    """Test LapRecord dataclass."""

    def test_lap_record_creation(self):
        """Test creating a LapRecord with required fields."""
        record = LapRecord(
            track_name="Silverstone",
            lap_time=92.456,
            timestamp=1704067200.0,
        )

        assert record.track_name == "Silverstone"
        assert record.lap_time == 92.456
        assert record.timestamp == 1704067200.0
        assert record.sectors is None
        assert record.session_id is None
        assert record.conditions is None

    def test_lap_record_with_sectors(self):
        """Test LapRecord with sector times."""
        record = LapRecord(
            track_name="Brands Hatch",
            lap_time=85.123,
            timestamp=1704067200.0,
            sectors=[28.5, 30.2, 26.423],
        )

        assert record.sectors == [28.5, 30.2, 26.423]

    def test_lap_record_with_all_fields(self):
        """Test LapRecord with all optional fields."""
        record = LapRecord(
            track_name="Donington",
            lap_time=78.900,
            timestamp=1704067200.0,
            sectors=[25.1, 27.3, 26.5],
            session_id="session_001",
            conditions="dry",
        )

        assert record.session_id == "session_001"
        assert record.conditions == "dry"

    def test_format_time_under_minute(self):
        """Test formatting time under one minute."""
        record = LapRecord(
            track_name="Test",
            lap_time=45.678,
            timestamp=0,
        )

        assert record.format_time() == "0:45.678"

    def test_format_time_over_minute(self):
        """Test formatting time over one minute."""
        record = LapRecord(
            track_name="Test",
            lap_time=92.456,
            timestamp=0,
        )

        assert record.format_time() == "1:32.456"

    def test_format_time_multiple_minutes(self):
        """Test formatting time of multiple minutes."""
        record = LapRecord(
            track_name="Test",
            lap_time=185.123,
            timestamp=0,
        )

        assert record.format_time() == "3:05.123"

    def test_format_time_exact_minute(self):
        """Test formatting exact minute."""
        record = LapRecord(
            track_name="Test",
            lap_time=60.000,
            timestamp=0,
        )

        assert record.format_time() == "1:00.000"


class TestReferenceLap:
    """Test ReferenceLap dataclass."""

    def test_reference_lap_creation(self):
        """Test creating a ReferenceLap."""
        gps_trace = [
            {"lat": 51.5, "lon": -0.1, "elapsed_time": 0.0, "track_position": 0.0},
            {"lat": 51.501, "lon": -0.1, "elapsed_time": 1.5, "track_position": 0.1},
        ]

        ref = ReferenceLap(
            track_name="Silverstone",
            lap_time=92.456,
            timestamp=1704067200.0,
            gps_trace=gps_trace,
        )

        assert ref.track_name == "Silverstone"
        assert ref.lap_time == 92.456
        assert len(ref.gps_trace) == 2


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_lap_timing.db")
        yield db_path


@pytest.fixture
def store(temp_db, monkeypatch):
    """Create a LapTimingStore with temporary database."""
    # Reset singleton
    LapTimingStore._instance = None

    # Patch the database path
    monkeypatch.setattr('utils.lap_timing_store.DATABASE_FILE', temp_db)
    monkeypatch.setattr('utils.lap_timing_store.LAP_TIMING_DATA_DIR',
                       os.path.dirname(temp_db))

    store = LapTimingStore()
    store._db_path = temp_db

    yield store

    # Clean up singleton
    LapTimingStore._instance = None


class TestLapTimingStoreInit:
    """Test LapTimingStore initialisation."""

    def test_singleton_pattern(self, store):
        """Test that LapTimingStore is a singleton."""
        store2 = LapTimingStore()
        assert store is store2

    def test_database_created(self, store, temp_db):
        """Test that database file is created."""
        assert os.path.exists(temp_db)

    def test_tables_created(self, store, temp_db):
        """Test that required tables are created."""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        # Check tables exist
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name IN
            ('lap_records', 'best_laps', 'reference_laps', 'sessions')
        """)
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert 'lap_records' in tables
        assert 'best_laps' in tables
        assert 'reference_laps' in tables
        assert 'sessions' in tables


class TestRecordLap:
    """Test recording laps."""

    def test_record_first_lap(self, store):
        """First lap should be best lap."""
        lap = LapRecord(
            track_name="Silverstone",
            lap_time=92.456,
            timestamp=time.time(),
        )

        is_new_best = store.record_lap(lap)

        assert is_new_best is True

    def test_record_faster_lap(self, store):
        """Faster lap should become new best."""
        lap1 = LapRecord(
            track_name="Silverstone",
            lap_time=95.000,
            timestamp=time.time(),
        )
        lap2 = LapRecord(
            track_name="Silverstone",
            lap_time=92.456,
            timestamp=time.time(),
        )

        store.record_lap(lap1)
        is_new_best = store.record_lap(lap2)

        assert is_new_best is True

    def test_record_slower_lap(self, store):
        """Slower lap should not become best."""
        lap1 = LapRecord(
            track_name="Silverstone",
            lap_time=92.456,
            timestamp=time.time(),
        )
        lap2 = LapRecord(
            track_name="Silverstone",
            lap_time=95.000,
            timestamp=time.time(),
        )

        store.record_lap(lap1)
        is_new_best = store.record_lap(lap2)

        assert is_new_best is False

    def test_record_lap_with_sectors(self, store):
        """Lap with sectors should be stored correctly."""
        lap = LapRecord(
            track_name="Brands Hatch",
            lap_time=85.123,
            timestamp=time.time(),
            sectors=[28.5, 30.2, 26.423],
        )

        store.record_lap(lap)
        best = store.get_best_lap("Brands Hatch")

        assert best is not None
        assert best.sectors == [28.5, 30.2, 26.423]


class TestGetBestLap:
    """Test getting best laps."""

    def test_get_best_lap_exists(self, store):
        """Get best lap that exists."""
        lap = LapRecord(
            track_name="Silverstone",
            lap_time=92.456,
            timestamp=1704067200.0,
        )
        store.record_lap(lap)

        best = store.get_best_lap("Silverstone")

        assert best is not None
        assert best.track_name == "Silverstone"
        assert best.lap_time == 92.456

    def test_get_best_lap_not_exists(self, store):
        """Get best lap for track with no laps."""
        best = store.get_best_lap("Unknown Track")

        assert best is None

    def test_get_best_after_multiple_laps(self, store):
        """Best lap is correct after multiple laps."""
        laps = [
            LapRecord("Silverstone", 95.0, time.time()),
            LapRecord("Silverstone", 92.5, time.time()),
            LapRecord("Silverstone", 93.0, time.time()),
            LapRecord("Silverstone", 91.8, time.time()),
        ]

        for lap in laps:
            store.record_lap(lap)

        best = store.get_best_lap("Silverstone")

        assert best is not None
        assert best.lap_time == 91.8


class TestGetAllBestLaps:
    """Test getting all best laps."""

    def test_get_all_best_laps_empty(self, store):
        """Get all best laps when none recorded."""
        result = store.get_all_best_laps()

        assert result == {}

    def test_get_all_best_laps_multiple_tracks(self, store):
        """Get all best laps for multiple tracks."""
        store.record_lap(LapRecord("Silverstone", 92.0, time.time()))
        store.record_lap(LapRecord("Brands Hatch", 85.0, time.time()))
        store.record_lap(LapRecord("Donington", 78.0, time.time()))

        result = store.get_all_best_laps()

        assert len(result) == 3
        assert "Silverstone" in result
        assert "Brands Hatch" in result
        assert "Donington" in result
        assert result["Silverstone"].lap_time == 92.0


class TestClearBestLap:
    """Test clearing best laps."""

    def test_clear_existing_best_lap(self, store):
        """Clear an existing best lap."""
        store.record_lap(LapRecord("Silverstone", 92.0, time.time()))

        deleted = store.clear_best_lap("Silverstone")

        assert deleted is True
        assert store.get_best_lap("Silverstone") is None

    def test_clear_nonexistent_best_lap(self, store):
        """Clear a nonexistent best lap."""
        deleted = store.clear_best_lap("Unknown Track")

        assert deleted is False

    def test_clear_all_best_laps(self, store):
        """Clear all best laps."""
        store.record_lap(LapRecord("Silverstone", 92.0, time.time()))
        store.record_lap(LapRecord("Brands Hatch", 85.0, time.time()))

        count = store.clear_all_best_laps()

        assert count == 2
        assert store.get_all_best_laps() == {}


class TestReferenceLapOperations:
    """Test reference lap operations."""

    def test_save_reference_lap(self, store):
        """Save a reference lap."""
        gps_trace = [
            {"lat": 51.5, "lon": -0.1, "elapsed_time": 0.0},
            {"lat": 51.501, "lon": -0.1, "elapsed_time": 1.5},
        ]

        success = store.save_reference_lap("Silverstone", 92.0, gps_trace)

        assert success is True

    def test_get_reference_lap(self, store):
        """Get a saved reference lap."""
        gps_trace = [
            {"lat": 51.5, "lon": -0.1, "elapsed_time": 0.0},
            {"lat": 51.501, "lon": -0.1, "elapsed_time": 1.5},
        ]
        store.save_reference_lap("Silverstone", 92.0, gps_trace)

        ref = store.get_reference_lap("Silverstone")

        assert ref is not None
        assert ref.track_name == "Silverstone"
        assert ref.lap_time == 92.0
        assert len(ref.gps_trace) == 2

    def test_get_nonexistent_reference_lap(self, store):
        """Get nonexistent reference lap."""
        ref = store.get_reference_lap("Unknown Track")

        assert ref is None

    def test_replace_reference_lap(self, store):
        """Replace an existing reference lap."""
        trace1 = [{"lat": 51.5, "lon": -0.1, "elapsed_time": 0.0}]
        trace2 = [{"lat": 51.6, "lon": -0.2, "elapsed_time": 0.0}]

        store.save_reference_lap("Silverstone", 95.0, trace1)
        store.save_reference_lap("Silverstone", 92.0, trace2)

        ref = store.get_reference_lap("Silverstone")

        assert ref.lap_time == 92.0
        assert ref.gps_trace[0]["lat"] == 51.6


class TestGetRecentLaps:
    """Test getting recent laps."""

    def test_get_recent_laps_empty(self, store):
        """Get recent laps when none recorded."""
        result = store.get_recent_laps("Silverstone")

        assert result == []

    def test_get_recent_laps_ordered(self, store):
        """Recent laps should be ordered newest first."""
        base_time = time.time()
        store.record_lap(LapRecord("Silverstone", 95.0, base_time))
        store.record_lap(LapRecord("Silverstone", 93.0, base_time + 60))
        store.record_lap(LapRecord("Silverstone", 91.0, base_time + 120))

        result = store.get_recent_laps("Silverstone")

        assert len(result) == 3
        assert result[0].lap_time == 91.0  # Newest first
        assert result[2].lap_time == 95.0  # Oldest last

    def test_get_recent_laps_limit(self, store):
        """Recent laps should respect limit."""
        base_time = time.time()
        for i in range(15):
            store.record_lap(LapRecord("Silverstone", 90.0 + i, base_time + i))

        result = store.get_recent_laps("Silverstone", limit=5)

        assert len(result) == 5

    def test_get_recent_laps_different_tracks(self, store):
        """Recent laps should be filtered by track."""
        store.record_lap(LapRecord("Silverstone", 92.0, time.time()))
        store.record_lap(LapRecord("Brands Hatch", 85.0, time.time()))
        store.record_lap(LapRecord("Silverstone", 93.0, time.time()))

        result = store.get_recent_laps("Silverstone")

        assert len(result) == 2
        for lap in result:
            assert lap.track_name == "Silverstone"


class TestGetTrackStats:
    """Test getting track statistics."""

    def test_get_track_stats_empty(self, store):
        """Get stats for track with no laps."""
        stats = store.get_track_stats("Unknown Track")

        assert stats['total_laps'] == 0
        assert stats['best_time'] is None
        assert stats['average_time'] is None

    def test_get_track_stats(self, store):
        """Get stats for track with laps."""
        base_time = time.time()
        store.record_lap(LapRecord("Silverstone", 95.0, base_time))
        store.record_lap(LapRecord("Silverstone", 90.0, base_time + 60))
        store.record_lap(LapRecord("Silverstone", 92.0, base_time + 120))

        stats = store.get_track_stats("Silverstone")

        assert stats['total_laps'] == 3
        assert stats['best_time'] == 90.0
        assert stats['average_time'] == pytest.approx(92.333, rel=0.01)
        assert stats['last_lap'] == pytest.approx(base_time + 120, rel=1)


class TestGetLapTimingStore:
    """Test convenience function."""

    def test_get_lap_timing_store(self, store):
        """Test get_lap_timing_store returns singleton."""
        store2 = get_lap_timing_store()

        assert store2 is store
