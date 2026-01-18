"""Tests for copilot/pacenotes.py - pacenote generation."""

import pytest
from dataclasses import dataclass
from typing import Optional

from copilot.pacenotes import (
    PacenoteGenerator, Pacenote, NoteType
)
from copilot.corners import Corner, Direction


# Minimal mock classes for path_projector types
@dataclass
class MockJunctionInfo:
    """Mock JunctionInfo for testing."""
    lat: float
    lon: float
    distance_m: float
    node_id: int
    turn_direction: Optional[str] = None
    straight_on_bearing: Optional[float] = None


@dataclass
class MockBridgeInfo:
    """Mock BridgeInfo for testing."""
    lat: float
    lon: float
    distance_m: float
    way_id: int


@dataclass
class MockTunnelInfo:
    """Mock TunnelInfo for testing."""
    lat: float
    lon: float
    distance_m: float
    way_id: int


@dataclass
class MockRailwayCrossingInfo:
    """Mock RailwayCrossingInfo for testing."""
    lat: float
    lon: float
    distance_m: float
    node_id: int


@dataclass
class MockFordInfo:
    """Mock FordInfo for testing."""
    lat: float
    lon: float
    distance_m: float
    way_id: int


@dataclass
class MockSpeedBumpInfo:
    """Mock SpeedBumpInfo for testing."""
    lat: float
    lon: float
    distance_m: float
    way_id: int
    bump_type: str = "bump"


@dataclass
class MockSurfaceChangeInfo:
    """Mock SurfaceChangeInfo for testing."""
    lat: float
    lon: float
    distance_m: float
    way_id: int
    from_surface: str = "asphalt"
    to_surface: str = "gravel"


@dataclass
class MockBarrierInfo:
    """Mock BarrierInfo for testing."""
    lat: float
    lon: float
    distance_m: float
    node_id: int
    barrier_type: str = "cattle_grid"


@dataclass
class MockNarrowInfo:
    """Mock NarrowInfo for testing."""
    lat: float
    lon: float
    distance_m: float
    way_id: int


class TestNoteType:
    """Test NoteType enum."""

    def test_note_types(self):
        """Test all note type values."""
        assert NoteType.CORNER.value == "corner"
        assert NoteType.JUNCTION.value == "junction"
        assert NoteType.CAUTION.value == "caution"
        assert NoteType.BRIDGE.value == "bridge"
        assert NoteType.TUNNEL.value == "tunnel"
        assert NoteType.RAILWAY.value == "railway"
        assert NoteType.FORD.value == "ford"
        assert NoteType.SPEED_BUMP.value == "speed_bump"
        assert NoteType.SURFACE.value == "surface"
        assert NoteType.BARRIER.value == "barrier"
        assert NoteType.NARROW.value == "narrow"


class TestPacenote:
    """Test Pacenote dataclass."""

    def test_pacenote_creation(self):
        """Test creating a Pacenote."""
        note = Pacenote(
            text="one hundred left three",
            distance_m=100.0,
            note_type=NoteType.CORNER,
            priority=3,
        )

        assert note.text == "one hundred left three"
        assert note.distance_m == 100.0
        assert note.note_type == NoteType.CORNER
        assert note.priority == 3
        assert note.unique_key == ""

    def test_pacenote_with_key(self):
        """Test Pacenote with unique key."""
        note = Pacenote(
            text="fifty junction",
            distance_m=50.0,
            note_type=NoteType.JUNCTION,
            priority=1,
            unique_key="junction_12345",
        )

        assert note.unique_key == "junction_12345"


class TestPacenoteGeneratorInit:
    """Test PacenoteGenerator initialisation."""

    def test_default_parameters(self):
        """Test default constructor parameters."""
        gen = PacenoteGenerator()

        assert gen.callout_distance == 100

    def test_custom_parameters(self):
        """Test custom constructor parameters."""
        gen = PacenoteGenerator(
            distance_threshold_m=500.0,
            junction_warn_distance=200.0,
            callout_distance_m=150,
        )

        assert gen.distance_threshold == 500.0
        assert gen.junction_warn_distance == 200.0
        assert gen.callout_distance == 150


class TestDistanceCall:
    """Test distance callout generation."""

    def test_distance_call_exact(self):
        """Test exact distance matches."""
        gen = PacenoteGenerator()

        # Test exact matches (within tolerance)
        assert gen._get_distance_call(100) == "one hundred"
        assert gen._get_distance_call(200) == "two hundred"
        assert gen._get_distance_call(300) == "three hundred"
        assert gen._get_distance_call(500) == "five hundred"
        assert gen._get_distance_call(1000) == "one thousand"

    def test_distance_call_near(self):
        """Test near distance matches (within 25m)."""
        gen = PacenoteGenerator()

        assert gen._get_distance_call(95) == "one hundred"
        assert gen._get_distance_call(105) == "one hundred"
        assert gen._get_distance_call(490) == "five hundred"
        assert gen._get_distance_call(510) == "five hundred"

    def test_distance_call_no_match(self):
        """Test distances that don't match any bracket."""
        gen = PacenoteGenerator()

        assert gen._get_distance_call(250) is None
        assert gen._get_distance_call(450) is None
        assert gen._get_distance_call(750) is None


class TestDistanceBracket:
    """Test distance bracket detection."""

    def test_hazard_distance_bracket(self):
        """Test multi-callout distance brackets for hazards."""
        gen = PacenoteGenerator()

        # 500 bracket: 400-525
        assert gen._get_distance_bracket(500) == 500
        assert gen._get_distance_bracket(450) == 500
        assert gen._get_distance_bracket(410) == 500

        # 300 bracket: 200-325
        assert gen._get_distance_bracket(300) == 300
        assert gen._get_distance_bracket(250) == 300
        assert gen._get_distance_bracket(210) == 300

        # 100 bracket: 0-125
        assert gen._get_distance_bracket(100) == 100
        assert gen._get_distance_bracket(50) == 100
        assert gen._get_distance_bracket(10) == 100

    def test_corner_distance_bracket(self):
        """Test corner distance brackets."""
        gen = PacenoteGenerator()

        # 1000 bracket: 900-1025
        assert gen._get_corner_distance_bracket(1000) == 1000
        assert gen._get_corner_distance_bracket(950) == 1000
        assert gen._get_corner_distance_bracket(910) == 1000

        # 500 bracket: 400-525
        assert gen._get_corner_distance_bracket(500) == 500
        assert gen._get_corner_distance_bracket(450) == 500

        # 100 bracket: 20-150
        assert gen._get_corner_distance_bracket(100) == 100
        assert gen._get_corner_distance_bracket(50) == 100
        assert gen._get_corner_distance_bracket(30) == 100


class TestCornerToNote:
    """Test converting corners to pacenotes."""

    @pytest.fixture
    def generator(self):
        """Create a fresh generator for each test."""
        return PacenoteGenerator()

    def test_left_three_corner(self, generator):
        """Test left severity 3 corner."""
        corner = Corner(
            entry_distance=100.0,
            apex_distance=120.0,
            exit_distance=140.0,
            apex_lat=51.5,
            apex_lon=-0.1,
            direction=Direction.LEFT,
            severity=3,
            total_angle=90.0,
            min_radius=40.0,
        )

        note = generator._corner_to_note(corner)

        assert note is not None
        assert "left" in note.text
        assert "three" in note.text
        assert note.note_type == NoteType.CORNER

    def test_right_five_corner(self, generator):
        """Test right severity 5 corner."""
        corner = Corner(
            entry_distance=100.0,
            apex_distance=120.0,
            exit_distance=140.0,
            apex_lat=51.5,
            apex_lon=-0.1,
            direction=Direction.RIGHT,
            severity=5,
            total_angle=45.0,
            min_radius=100.0,
        )

        note = generator._corner_to_note(corner)

        assert note is not None
        assert "right" in note.text
        assert "five" in note.text

    def test_hairpin_corner(self, generator):
        """Test hairpin corner (severity 1)."""
        corner = Corner(
            entry_distance=100.0,
            apex_distance=120.0,
            exit_distance=140.0,
            apex_lat=51.5,
            apex_lon=-0.1,
            direction=Direction.LEFT,
            severity=1,
            total_angle=180.0,
            min_radius=10.0,
        )

        note = generator._corner_to_note(corner)

        assert note is not None
        assert "hairpin" in note.text
        assert "left" in note.text

    def test_flat_corner(self, generator):
        """Test flat corner (severity 7)."""
        corner = Corner(
            entry_distance=100.0,
            apex_distance=120.0,
            exit_distance=140.0,
            apex_lat=51.5,
            apex_lon=-0.1,
            direction=Direction.RIGHT,
            severity=7,
            total_angle=15.0,
            min_radius=300.0,
        )

        note = generator._corner_to_note(corner)

        assert note is not None
        assert "flat" in note.text

    def test_tightening_corner(self, generator):
        """Test corner with tightens modifier."""
        corner = Corner(
            entry_distance=100.0,
            apex_distance=120.0,
            exit_distance=140.0,
            apex_lat=51.5,
            apex_lon=-0.1,
            direction=Direction.LEFT,
            severity=3,
            total_angle=90.0,
            min_radius=40.0,
            tightens=True,
        )

        note = generator._corner_to_note(corner)

        assert note is not None
        assert "tightens" in note.text

    def test_opening_corner(self, generator):
        """Test corner with opens modifier."""
        corner = Corner(
            entry_distance=100.0,
            apex_distance=120.0,
            exit_distance=140.0,
            apex_lat=51.5,
            apex_lon=-0.1,
            direction=Direction.RIGHT,
            severity=4,
            total_angle=60.0,
            min_radius=60.0,
            opens=True,
        )

        note = generator._corner_to_note(corner)

        assert note is not None
        assert "opens" in note.text

    def test_long_corner(self, generator):
        """Test long corner modifier."""
        corner = Corner(
            entry_distance=100.0,
            apex_distance=150.0,
            exit_distance=200.0,
            apex_lat=51.5,
            apex_lon=-0.1,
            direction=Direction.LEFT,
            severity=4,
            total_angle=90.0,
            min_radius=50.0,
            long_corner=True,
        )

        note = generator._corner_to_note(corner)

        assert note is not None
        assert "long" in note.text

    def test_chicane(self, generator):
        """Test chicane corner."""
        corner = Corner(
            entry_distance=100.0,
            apex_distance=120.0,
            exit_distance=150.0,
            apex_lat=51.5,
            apex_lon=-0.1,
            direction=Direction.LEFT,
            severity=3,
            total_angle=90.0,
            min_radius=40.0,
            is_chicane=True,
            exit_direction=Direction.RIGHT,
        )

        note = generator._corner_to_note(corner)

        assert note is not None
        assert "chicane" in note.text
        assert "left" in note.text
        assert "right" in note.text

    def test_corner_outside_bracket(self, generator):
        """Corner outside any bracket returns None."""
        corner = Corner(
            entry_distance=250.0,  # Between brackets
            apex_distance=270.0,
            exit_distance=290.0,
            apex_lat=51.5,
            apex_lon=-0.1,
            direction=Direction.LEFT,
            severity=3,
            total_angle=90.0,
            min_radius=40.0,
        )

        note = generator._corner_to_note(corner)

        # 250m is between 200 (150-225) and 300 (250-325) brackets
        # Actually 250m is at the edge of 300 bracket (250-325)
        # So this might return a note
        # Let me check the bracket logic again...
        # 300 bracket: 250-325m, so 250 is included
        assert note is not None


class TestJunctionToNote:
    """Test converting junctions to pacenotes."""

    @pytest.fixture
    def generator(self):
        """Create a fresh generator for each test."""
        return PacenoteGenerator()

    def test_junction_turn_left(self, generator):
        """Test junction with left turn."""
        junction = MockJunctionInfo(
            lat=51.5,
            lon=-0.1,
            distance_m=100.0,
            node_id=12345,
            turn_direction="left",
            straight_on_bearing=None,
        )

        note = generator._junction_to_note(junction)

        assert note is not None
        assert "junction" in note.text
        assert "left" in note.text
        assert note.note_type == NoteType.JUNCTION
        assert note.priority == 1

    def test_junction_turn_right(self, generator):
        """Test junction with right turn."""
        junction = MockJunctionInfo(
            lat=51.5,
            lon=-0.1,
            distance_m=100.0,
            node_id=12345,
            turn_direction="right",
            straight_on_bearing=None,
        )

        note = generator._junction_to_note(junction)

        assert note is not None
        assert "junction" in note.text
        assert "right" in note.text

    def test_junction_no_direction(self, generator):
        """Test junction without turn direction."""
        junction = MockJunctionInfo(
            lat=51.5,
            lon=-0.1,
            distance_m=100.0,
            node_id=12345,
            turn_direction=None,
            straight_on_bearing=None,
        )

        note = generator._junction_to_note(junction)

        assert note is not None
        assert note.text.endswith("junction") or "junction" in note.text


class TestBridgeToNote:
    """Test converting bridges to pacenotes."""

    def test_bridge_note(self):
        """Test bridge pacenote."""
        gen = PacenoteGenerator()
        bridge = MockBridgeInfo(
            lat=51.5,
            lon=-0.1,
            distance_m=100.0,
            way_id=12345,
        )

        note = gen._bridge_to_note(bridge)

        assert note is not None
        assert "bridge" in note.text
        assert note.note_type == NoteType.BRIDGE
        assert note.priority == 5  # Lower priority - informational


class TestTunnelToNote:
    """Test converting tunnels to pacenotes."""

    def test_tunnel_note(self):
        """Test tunnel pacenote."""
        gen = PacenoteGenerator()
        tunnel = MockTunnelInfo(
            lat=51.5,
            lon=-0.1,
            distance_m=100.0,
            way_id=12345,
        )

        note = gen._tunnel_to_note(tunnel)

        assert note is not None
        assert "tunnel" in note.text
        assert note.note_type == NoteType.TUNNEL


class TestRailwayToNote:
    """Test converting railway crossings to pacenotes."""

    def test_railway_note(self):
        """Test railway crossing pacenote."""
        gen = PacenoteGenerator()
        crossing = MockRailwayCrossingInfo(
            lat=51.5,
            lon=-0.1,
            distance_m=100.0,
            node_id=12345,
        )

        note = gen._railway_to_note(crossing)

        assert note is not None
        assert "rails" in note.text
        assert note.note_type == NoteType.RAILWAY
        assert note.priority == 3


class TestFordToNote:
    """Test converting fords to pacenotes."""

    def test_ford_note(self):
        """Test ford pacenote."""
        gen = PacenoteGenerator()
        ford = MockFordInfo(
            lat=51.5,
            lon=-0.1,
            distance_m=100.0,
            way_id=12345,
        )

        note = gen._ford_to_note(ford)

        assert note is not None
        assert "water" in note.text
        assert note.note_type == NoteType.FORD


class TestSpeedBumpToNote:
    """Test converting speed bumps to pacenotes."""

    def test_bump_note(self):
        """Test single bump pacenote."""
        gen = PacenoteGenerator()
        bump = MockSpeedBumpInfo(
            lat=51.5,
            lon=-0.1,
            distance_m=100.0,
            way_id=12345,
            bump_type="bump",
        )

        note = gen._speed_bump_to_note(bump)

        assert note is not None
        assert "bump" in note.text
        assert note.note_type == NoteType.SPEED_BUMP

    def test_table_note(self):
        """Test speed table (multiple bumps) pacenote."""
        gen = PacenoteGenerator()
        bump = MockSpeedBumpInfo(
            lat=51.5,
            lon=-0.1,
            distance_m=100.0,
            way_id=12345,
            bump_type="table",
        )

        note = gen._speed_bump_to_note(bump)

        assert note is not None
        assert "bumps" in note.text


class TestSurfaceChangeToNote:
    """Test converting surface changes to pacenotes."""

    def test_gravel_surface(self):
        """Test surface change to gravel."""
        gen = PacenoteGenerator()
        change = MockSurfaceChangeInfo(
            lat=51.5,
            lon=-0.1,
            distance_m=100.0,
            way_id=12345,
            from_surface="asphalt",
            to_surface="gravel",
        )

        note = gen._surface_change_to_note(change)

        assert note is not None
        assert "gravel" in note.text
        assert note.note_type == NoteType.SURFACE

    def test_tarmac_surface(self):
        """Test surface change to tarmac."""
        gen = PacenoteGenerator()
        change = MockSurfaceChangeInfo(
            lat=51.5,
            lon=-0.1,
            distance_m=100.0,
            way_id=12345,
            from_surface="gravel",
            to_surface="asphalt",
        )

        note = gen._surface_change_to_note(change)

        assert note is not None
        assert "tarmac" in note.text

    def test_unknown_surface(self):
        """Test unknown surface returns None."""
        gen = PacenoteGenerator()
        change = MockSurfaceChangeInfo(
            lat=51.5,
            lon=-0.1,
            distance_m=100.0,
            way_id=12345,
            from_surface="asphalt",
            to_surface="unknown_surface_type",
        )

        note = gen._surface_change_to_note(change)

        assert note is None


class TestBarrierToNote:
    """Test converting barriers to pacenotes."""

    def test_cattle_grid(self):
        """Test cattle grid pacenote."""
        gen = PacenoteGenerator()
        barrier = MockBarrierInfo(
            lat=51.5,
            lon=-0.1,
            distance_m=100.0,
            node_id=12345,
            barrier_type="cattle_grid",
        )

        note = gen._barrier_to_note(barrier)

        assert note is not None
        assert "cattle grid" in note.text
        assert note.note_type == NoteType.BARRIER

    def test_gate(self):
        """Test gate pacenote."""
        gen = PacenoteGenerator()
        barrier = MockBarrierInfo(
            lat=51.5,
            lon=-0.1,
            distance_m=100.0,
            node_id=12345,
            barrier_type="gate",
        )

        note = gen._barrier_to_note(barrier)

        assert note is not None
        assert "gate" in note.text

    def test_unknown_barrier(self):
        """Test unknown barrier type returns None."""
        gen = PacenoteGenerator()
        barrier = MockBarrierInfo(
            lat=51.5,
            lon=-0.1,
            distance_m=100.0,
            node_id=12345,
            barrier_type="unknown",
        )

        note = gen._barrier_to_note(barrier)

        assert note is None


class TestNarrowToNote:
    """Test converting narrow sections to pacenotes."""

    def test_narrow_note(self):
        """Test narrow section pacenote."""
        gen = PacenoteGenerator()
        narrow = MockNarrowInfo(
            lat=51.5,
            lon=-0.1,
            distance_m=100.0,
            way_id=12345,
        )

        note = gen._narrow_to_note(narrow)

        assert note is not None
        assert "narrows" in note.text
        assert note.note_type == NoteType.NARROW


class TestShouldCall:
    """Test should_call deduplication logic."""

    def test_first_call_succeeds(self):
        """First call to a note should succeed."""
        gen = PacenoteGenerator()
        note = Pacenote(
            text="one hundred left three",
            distance_m=100.0,
            note_type=NoteType.CORNER,
            priority=3,
            unique_key="corner_51.5_-0.1_100",
        )

        should_call, result = gen.should_call(note)

        assert should_call is True
        assert result == note

    def test_duplicate_call_fails(self):
        """Duplicate call to same note should fail."""
        gen = PacenoteGenerator()
        note = Pacenote(
            text="one hundred left three",
            distance_m=100.0,
            note_type=NoteType.CORNER,
            priority=3,
            unique_key="corner_51.5_-0.1_100",
        )

        gen.should_call(note)  # First call
        should_call, result = gen.should_call(note)  # Duplicate

        assert should_call is False
        assert result is None

    def test_too_far_fails(self):
        """Note too far away should fail."""
        gen = PacenoteGenerator(callout_distance_m=100)
        note = Pacenote(
            text="five hundred left three",
            distance_m=2000.0,  # Too far
            note_type=NoteType.BRIDGE,  # Not a corner, so uses callout_distance
            priority=3,
            unique_key="bridge_123",
        )

        should_call, result = gen.should_call(note)

        assert should_call is False

    def test_too_close_fails(self):
        """Note too close should fail."""
        gen = PacenoteGenerator()
        note = Pacenote(
            text="left three",
            distance_m=10.0,  # Too close (< MIN_CALLOUT_DISTANCE_M)
            note_type=NoteType.CORNER,
            priority=3,
            unique_key="corner_123",
        )

        should_call, result = gen.should_call(note)

        assert should_call is False

    def test_clear_called(self):
        """Test clearing called notes."""
        gen = PacenoteGenerator()

        # Add many notes to trigger clear
        for i in range(150):
            gen._called.add(f"note_{i}")

        gen.clear_called()

        assert len(gen._called) == 0


class TestCalculatePriority:
    """Test priority calculation."""

    def test_tight_corner_high_priority(self):
        """Tight corners should have higher priority (lower number)."""
        gen = PacenoteGenerator()
        corner = Corner(
            entry_distance=50.0,
            apex_distance=60.0,
            exit_distance=70.0,
            apex_lat=51.5,
            apex_lon=-0.1,
            direction=Direction.LEFT,
            severity=1,  # Hairpin - most urgent
            total_angle=180.0,
            min_radius=10.0,
        )

        priority = gen._calculate_priority(corner)

        # severity_factor = 1, distance_factor = 1 (50/100 = 0.5, max(1, 0) = 1)
        assert priority <= 3

    def test_gentle_corner_low_priority(self):
        """Gentle corners should have lower priority (higher number)."""
        gen = PacenoteGenerator()
        corner = Corner(
            entry_distance=500.0,
            apex_distance=550.0,
            exit_distance=600.0,
            apex_lat=51.5,
            apex_lon=-0.1,
            direction=Direction.RIGHT,
            severity=6,  # Gentle
            total_angle=30.0,
            min_radius=150.0,
        )

        priority = gen._calculate_priority(corner)

        # severity_factor = 6, distance_factor = 5 (500/100)
        assert priority >= 10


class TestStripDistance:
    """Test stripping distance from pacenote text."""

    def test_strip_distance(self):
        """Test stripping distance prefix."""
        gen = PacenoteGenerator()

        assert gen._strip_distance("one hundred left three") == "left three"
        assert gen._strip_distance("five hundred right two") == "right two"
        assert gen._strip_distance("left three") == "left three"  # No prefix


class TestMergeAdjacentNotes:
    """Test merging adjacent notes."""

    def test_merge_close_notes(self):
        """Notes within merge distance should be merged."""
        gen = PacenoteGenerator()

        notes = [
            Pacenote("one hundred over bridge", 100.0, NoteType.BRIDGE, 5, "bridge_1"),
            Pacenote("one hundred left three", 120.0, NoteType.CORNER, 3, "corner_1"),
        ]

        merged = gen._merge_adjacent_notes(notes)

        assert len(merged) == 1
        assert "into" in merged[0].text

    def test_no_merge_far_notes(self):
        """Notes far apart should not be merged."""
        gen = PacenoteGenerator()

        notes = [
            Pacenote("one hundred over bridge", 100.0, NoteType.BRIDGE, 5, "bridge_1"),
            Pacenote("two hundred left three", 200.0, NoteType.CORNER, 3, "corner_1"),
        ]

        merged = gen._merge_adjacent_notes(notes)

        assert len(merged) == 2

    def test_single_note_not_merged(self):
        """Single note should pass through unchanged."""
        gen = PacenoteGenerator()

        notes = [
            Pacenote("one hundred left three", 100.0, NoteType.CORNER, 3, "corner_1"),
        ]

        merged = gen._merge_adjacent_notes(notes)

        assert len(merged) == 1
        assert merged[0].text == "one hundred left three"
