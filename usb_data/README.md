# USB Drive Data

This folder contains the data structure for the openTPT USB drive.

## Setup

Copy the `.opentpt` folder to the root of a USB drive:

```bash
# Format USB drive as ext4 (recommended) or FAT32
# Mount USB drive (e.g., /mnt/usb or /media/pi/USB)

# Copy data to USB
cp -r usb_data/.opentpt /mnt/usb/
```

## Directory Structure

```
/mnt/usb/.opentpt/
├── settings.json              # User preferences (created at runtime)
├── lap_timing/
│   ├── lap_timing.db          # Lap times database (created at runtime)
│   └── tracks/
│       ├── tracks.db          # Track database
│       ├── racelogic.db       # Racelogic track database
│       ├── maps/              # Custom track files (.kmz)
│       └── racelogic/         # Racelogic track files by country
├── routes/                    # Lap timing GPX/KMZ route files
├── copilot/
│   ├── maps/                  # OSM .roads.db files (large, download separately)
│   ├── routes/                # CoPilot GPX route files
│   └── cache/                 # Road data cache (created at runtime)
├── pit_timer/
│   └── pit_waypoints.db       # Pit lane GPS waypoints (created at runtime)
└── logs/                      # Service logs (created by usb-log-sync)
```

## Adding Tracks

### Racelogic Tracks (Required)
Racelogic track data is copyrighted and must be obtained separately:

1. Download from [racelogic.co.uk](https://www.racelogic.co.uk/support/vbox-tools/tools-software/circuit-database)
2. Place `racelogic.db` in `lap_timing/tracks/`
3. Extract country folders to `lap_timing/tracks/racelogic/`

### Custom Tracks (KMZ)
Place `.kmz` files in `lap_timing/tracks/maps/`

### GPX Routes
- Lap timing routes: `routes/`
- CoPilot routes: `copilot/routes/`

## CoPilot Maps

CoPilot requires OSM map data (`.roads.db` files). These are large (6+ GB for UK) and must be downloaded separately:

1. Download regional PBF from [Geofabrik](https://download.geofabrik.de/)
2. Convert to `.roads.db` using the CoPilot tools
3. Place in `copilot/maps/`

## Notes

- USB should be mounted at `/mnt/usb` on the Pi
- If USB is not available, openTPT falls back to `~/.opentpt/` (won't persist on read-only rootfs)
- The Pi shows a warning on splash screen if USB is not mounted
