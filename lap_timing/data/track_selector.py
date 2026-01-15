"""
Track selection based on GPS location.

Automatically detects nearby tracks from SQLite databases with spatial indexing
and selects the appropriate one based on current GPS position.
"""

import os
import sqlite3
from typing import List, Optional
from dataclasses import dataclass
from lap_timing.data.track_loader import Track, load_track_from_kmz
from lap_timing.utils.geometry import haversine_distance
from lap_timing import config


# =============================================================================
# Geohash Implementation (for spatial queries)
# =============================================================================

GEOHASH_BASE32 = '0123456789bcdefghjkmnpqrstuvwxyz'


def encode_geohash(lat: float, lon: float, precision: int = 6) -> str:
    """Encode latitude/longitude to geohash string."""
    lat_range = (-90.0, 90.0)
    lon_range = (-180.0, 180.0)

    geohash = []
    bits = [16, 8, 4, 2, 1]
    bit = 0
    ch = 0
    is_lon = True

    while len(geohash) < precision:
        if is_lon:
            mid = (lon_range[0] + lon_range[1]) / 2
            if lon >= mid:
                ch |= bits[bit]
                lon_range = (mid, lon_range[1])
            else:
                lon_range = (lon_range[0], mid)
        else:
            mid = (lat_range[0] + lat_range[1]) / 2
            if lat >= mid:
                ch |= bits[bit]
                lat_range = (mid, lat_range[1])
            else:
                lat_range = (lat_range[0], mid)

        is_lon = not is_lon

        if bit < 4:
            bit += 1
        else:
            geohash.append(GEOHASH_BASE32[ch])
            bit = 0
            ch = 0

    return ''.join(geohash)


def decode_geohash_bounds(geohash: str) -> tuple:
    """Decode geohash to bounding box (min_lat, max_lat, min_lon, max_lon)."""
    lat_range = [-90.0, 90.0]
    lon_range = [-180.0, 180.0]

    is_lon = True

    for char in geohash.lower():
        idx = GEOHASH_BASE32.index(char)
        for bit in [16, 8, 4, 2, 1]:
            if is_lon:
                mid = (lon_range[0] + lon_range[1]) / 2
                if idx & bit:
                    lon_range[0] = mid
                else:
                    lon_range[1] = mid
            else:
                mid = (lat_range[0] + lat_range[1]) / 2
                if idx & bit:
                    lat_range[0] = mid
                else:
                    lat_range[1] = mid
            is_lon = not is_lon

    return (lat_range[0], lat_range[1], lon_range[0], lon_range[1])


def geohash_neighbors(geohash: str) -> List[str]:
    """Get the 8 neighboring geohash cells (plus self = 9 cells)."""
    min_lat, max_lat, min_lon, max_lon = decode_geohash_bounds(geohash)

    lat_delta = (max_lat - min_lat) / 2
    lon_delta = (max_lon - min_lon) / 2
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2

    precision = len(geohash)
    neighbors = []

    for dlat in [-1, 0, 1]:
        for dlon in [-1, 0, 1]:
            nlat = center_lat + dlat * lat_delta * 2
            nlon = center_lon + dlon * lon_delta * 2
            if -90 <= nlat <= 90 and -180 <= nlon <= 180:
                neighbors.append(encode_geohash(nlat, nlon, precision))

    return list(set(neighbors))


# =============================================================================
# Track Info
# =============================================================================

@dataclass
class TrackInfo:
    """Information about an available track."""
    name: str
    country: Optional[str]
    kmz_path: Optional[str]
    distance_to_sf: float      # Distance from GPS point to S/F line (meters)
    sf_lat: float              # S/F line latitude (decimal degrees)
    sf_lon: float              # S/F line longitude (decimal degrees)
    length: Optional[float] = None
    source: str = 'racelogic'  # 'racelogic' or 'custom'


# =============================================================================
# Track Selector
# =============================================================================

class TrackSelector:
    """Select appropriate track based on GPS location using SQLite databases."""

    def __init__(
        self,
        tracks_db_path: str = None,
        racelogic_db_path: str = None,
        custom_tracks_dir: str = None,
        racelogic_tracks_dir: str = None
    ):
        """
        Initialise track selector.

        Args:
            tracks_db_path: Path to custom tracks SQLite database
            racelogic_db_path: Path to RaceLogic tracks SQLite database
            custom_tracks_dir: Directory containing custom KMZ files
            racelogic_tracks_dir: Directory containing RaceLogic KMZ files (by country)
        """
        self.tracks_db_path = tracks_db_path or config.TRACKS_DB_PATH
        self.racelogic_db_path = racelogic_db_path or config.RACELOGIC_DB_PATH
        self.custom_tracks_dir = custom_tracks_dir or config.CUSTOM_TRACKS_DIR
        self.racelogic_tracks_dir = racelogic_tracks_dir or config.RACELOGIC_TRACKS_DIR

        # Verify databases exist
        self._check_databases()

    def _check_databases(self):
        """Check which databases are available."""
        self.has_custom_db = os.path.exists(self.tracks_db_path)
        self.has_racelogic_db = os.path.exists(self.racelogic_db_path)

        if not self.has_custom_db and not self.has_racelogic_db:
            print(f"Warning: No track databases found")
            print(f"  Custom: {self.tracks_db_path}")
            print(f"  RaceLogic: {self.racelogic_db_path}")

    def _query_database(
        self,
        db_path: str,
        lat: float,
        lon: float,
        radius_km: float,
        source: str
    ) -> List[TrackInfo]:
        """
        Query a single database for nearby tracks.

        Uses geohash prefix filtering followed by haversine distance calculation.
        """
        if not os.path.exists(db_path):
            return []

        radius_m = radius_km * 1000

        # Choose geohash precision based on search radius
        if radius_km >= 30:
            precision = 4
            geohash_col = 'geohash_4'
        elif radius_km >= 5:
            precision = 5
            geohash_col = 'geohash_5'
        else:
            precision = 6
            geohash_col = 'geohash_6'

        # Get geohash of search center and neighbors
        center_geohash = encode_geohash(lat, lon, precision)
        search_hashes = geohash_neighbors(center_geohash)

        results = []

        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row

            placeholders = ','.join(['?' for _ in search_hashes])
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT name, country, start_lat, start_lon, length_meters, source_file
                FROM tracks
                WHERE {geohash_col} IN ({placeholders})
            """, search_hashes)

            for row in cursor.fetchall():
                dist = haversine_distance(lat, lon, row['start_lat'], row['start_lon'])
                if dist <= radius_m:
                    # Resolve KMZ path
                    kmz_path = self._find_kmz_file(
                        row['name'],
                        row['country'],
                        source
                    )

                    results.append(TrackInfo(
                        name=row['name'],
                        country=row['country'],
                        kmz_path=kmz_path,
                        distance_to_sf=dist,
                        sf_lat=row['start_lat'],
                        sf_lon=row['start_lon'],
                        length=row['length_meters'],
                        source=source
                    ))

            conn.close()

        except (sqlite3.Error, IOError, OSError) as e:
            print(f"Warning: Error querying {db_path}: {e}")

        return results

    def _find_kmz_file(
        self,
        track_name: str,
        country: Optional[str],
        source: str
    ) -> Optional[str]:
        """Find KMZ file for a track."""
        if source == 'custom':
            # Custom tracks: assets/tracks/maps/{name}.kmz
            kmz_path = os.path.join(self.custom_tracks_dir, f"{track_name}.kmz")
            if os.path.exists(kmz_path):
                return kmz_path
        else:
            # RaceLogic tracks: assets/tracks/racelogic/{country}/{name}.kmz
            if country:
                kmz_path = os.path.join(
                    self.racelogic_tracks_dir,
                    country,
                    f"{track_name}.kmz"
                )
                if os.path.exists(kmz_path):
                    return kmz_path

        return None

    def find_nearby_tracks(
        self,
        lat: float,
        lon: float,
        max_distance_km: float = None
    ) -> List[TrackInfo]:
        """
        Find tracks within specified distance of GPS position.

        Searches both custom and RaceLogic databases.

        Args:
            lat, lon: GPS coordinates (decimal degrees)
            max_distance_km: Maximum distance to search (km)

        Returns:
            List of TrackInfo, sorted by distance (nearest first)
        """
        if max_distance_km is None:
            max_distance_km = config.TRACK_SEARCH_RADIUS_KM

        nearby = []

        # Query custom tracks database
        if self.has_custom_db:
            custom_tracks = self._query_database(
                self.tracks_db_path, lat, lon, max_distance_km, 'custom'
            )
            nearby.extend(custom_tracks)

        # Query RaceLogic database
        if self.has_racelogic_db:
            racelogic_tracks = self._query_database(
                self.racelogic_db_path, lat, lon, max_distance_km, 'racelogic'
            )
            nearby.extend(racelogic_tracks)

        # Sort by distance (nearest first)
        nearby.sort(key=lambda t: t.distance_to_sf)

        return nearby

    def select_track(
        self,
        lat: float,
        lon: float,
        max_distance_km: float = None,
        auto_select: bool = True
    ) -> Optional[Track]:
        """
        Select track based on GPS position.

        Args:
            lat, lon: GPS coordinates
            max_distance_km: Maximum distance to search (km)
            auto_select: If True and only one track found, auto-select it

        Returns:
            Selected Track object, or None if no selection made
        """
        nearby = self.find_nearby_tracks(lat, lon, max_distance_km)

        if len(nearby) == 0:
            print(f"No tracks found within {max_distance_km or config.TRACK_SEARCH_RADIUS_KM}km "
                  f"of position ({lat:.6f}, {lon:.6f})")
            return None

        if len(nearby) == 1 and auto_select:
            track_info = nearby[0]
            print(f"Auto-selected: {track_info.name}")
            if track_info.country:
                print(f"  Country: {track_info.country}")
            print(f"  Distance: {track_info.distance_to_sf/1000:.2f}km from S/F line")

            if track_info.kmz_path:
                return load_track_from_kmz(track_info.kmz_path)
            else:
                print(f"  Warning: KMZ file not found for {track_info.name}")
                return None

        # Multiple tracks found - ask user to select
        print(f"\nFound {len(nearby)} tracks within "
              f"{max_distance_km or config.TRACK_SEARCH_RADIUS_KM}km:\n")

        for i, track_info in enumerate(nearby, 1):
            source_tag = f"[{track_info.source}]"
            country_str = f" ({track_info.country})" if track_info.country else ""
            print(f"{i}. {track_info.name}{country_str} {source_tag}")
            print(f"   Distance: {track_info.distance_to_sf/1000:.2f}km")
            if track_info.length:
                print(f"   Length: {track_info.length}m")
            print()

        # Get user selection
        while True:
            try:
                choice = input(f"Select track (1-{len(nearby)}, or 0 to cancel): ").strip()

                if choice == "0":
                    print("Track selection cancelled")
                    return None

                idx = int(choice) - 1
                if 0 <= idx < len(nearby):
                    selected = nearby[idx]
                    print(f"\nSelected: {selected.name}")

                    if selected.kmz_path:
                        return load_track_from_kmz(selected.kmz_path)
                    else:
                        print(f"Warning: KMZ file not found for {selected.name}")
                        return None
                else:
                    print(f"Please enter a number between 1 and {len(nearby)}")

            except ValueError:
                print("Please enter a valid number")
            except KeyboardInterrupt:
                print("\nTrack selection cancelled")
                return None

    def get_track_by_name(self, track_name: str) -> Optional[Track]:
        """
        Get track by name (searches both databases).

        Args:
            track_name: Track name to search for

        Returns:
            Track object or None if not found
        """
        track_name_lower = track_name.lower()

        # Search custom database first
        for db_path, source in [
            (self.tracks_db_path, 'custom'),
            (self.racelogic_db_path, 'racelogic')
        ]:
            if not os.path.exists(db_path):
                continue

            try:
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Try exact match
                cursor.execute(
                    "SELECT name, country FROM tracks WHERE LOWER(name) = ?",
                    (track_name_lower,)
                )
                row = cursor.fetchone()

                if row:
                    kmz_path = self._find_kmz_file(row['name'], row['country'], source)
                    if kmz_path:
                        print(f"Loading: {row['name']}")
                        conn.close()
                        return load_track_from_kmz(kmz_path)

                # Try partial match
                cursor.execute(
                    "SELECT name, country FROM tracks WHERE LOWER(name) LIKE ?",
                    (f'%{track_name_lower}%',)
                )
                matches = cursor.fetchall()
                conn.close()

                if len(matches) == 1:
                    kmz_path = self._find_kmz_file(
                        matches[0]['name'],
                        matches[0]['country'],
                        source
                    )
                    if kmz_path:
                        print(f"Loading: {matches[0]['name']}")
                        return load_track_from_kmz(kmz_path)
                elif len(matches) > 1:
                    print(f"Multiple tracks match '{track_name}':")
                    for m in matches[:10]:
                        country_str = f" ({m['country']})" if m['country'] else ""
                        print(f"  - {m['name']}{country_str}")
                    if len(matches) > 10:
                        print(f"  ... and {len(matches) - 10} more")
                    print("\nPlease be more specific")
                    return None

            except (sqlite3.Error, IOError, OSError) as e:
                print(f"Warning: Error searching {db_path}: {e}")

        print(f"No track found matching '{track_name}'")
        return None

    def list_all_tracks(self, country: str = None):
        """List all available tracks."""
        total = 0

        for db_path, source in [
            (self.tracks_db_path, 'custom'),
            (self.racelogic_db_path, 'racelogic')
        ]:
            if not os.path.exists(db_path):
                continue

            try:
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                if country:
                    cursor.execute(
                        "SELECT name, country FROM tracks WHERE country = ? ORDER BY name",
                        (country,)
                    )
                else:
                    cursor.execute(
                        "SELECT name, country FROM tracks ORDER BY country, name"
                    )

                tracks = cursor.fetchall()
                conn.close()

                if tracks:
                    print(f"\n{source.upper()} Tracks ({len(tracks)}):")
                    current_country = None
                    for t in tracks:
                        if t['country'] != current_country:
                            current_country = t['country']
                            print(f"\n  {current_country or 'Unknown'}:")
                        print(f"    - {t['name']}")

                total += len(tracks)

            except (sqlite3.Error, IOError, OSError) as e:
                print(f"Warning: Error listing tracks from {db_path}: {e}")

        print(f"\nTotal: {total} tracks")

    def get_database_stats(self) -> dict:
        """Get statistics about the track databases."""
        stats = {
            'custom_tracks': 0,
            'racelogic_tracks': 0,
            'custom_countries': [],
            'racelogic_countries': []
        }

        for db_path, key_prefix in [
            (self.tracks_db_path, 'custom'),
            (self.racelogic_db_path, 'racelogic')
        ]:
            if not os.path.exists(db_path):
                continue

            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                cursor.execute("SELECT COUNT(*) FROM tracks")
                stats[f'{key_prefix}_tracks'] = cursor.fetchone()[0]

                cursor.execute(
                    "SELECT DISTINCT country FROM tracks WHERE country IS NOT NULL"
                )
                stats[f'{key_prefix}_countries'] = [r[0] for r in cursor.fetchall()]

                conn.close()

            except (sqlite3.Error, IOError, OSError) as e:
                print(f"Warning: Error getting stats from {db_path}: {e}")

        return stats
