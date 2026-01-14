#!/bin/bash
# Configure GPS for 10Hz RMC-only output
#
# At 9600 baud, 10Hz is only possible with RMC-only output.
# PMTK314 disables all sentences except RMC.
# PMTK220,100 sets 100ms (10Hz) update rate.
#
# This script stops gpsd, configures GPS, then restarts gpsd.

GPS_PORT="/dev/ttyS0"
GPS_BAUD=9600

# Stop gpsd if running (it locks the serial port)
systemctl stop gpsd.socket gpsd.service 2>/dev/null || true

# Wait for GPS port
for i in {1..10}; do
    [ -c "$GPS_PORT" ] && break
    sleep 0.5
done

if [ ! -c "$GPS_PORT" ]; then
    echo "GPS port $GPS_PORT not found"
    exit 1
fi

stty -F "$GPS_PORT" $GPS_BAUD raw -echo

# Set RMC-only output (PMTK314)
# Format: GLL,RMC,VTG,GGA,GSA,GSV... - only RMC enabled (position 2)
echo -ne "\$PMTK314,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0*29\r\n" > "$GPS_PORT"
sleep 0.2

# Set 10Hz update rate (PMTK220,100 = 100ms interval)
echo -ne "\$PMTK220,100*2F\r\n" > "$GPS_PORT"
sleep 0.2

echo "GPS configured for 10Hz RMC-only output"

# Restart gpsd
systemctl start gpsd.socket gpsd.service 2>/dev/null || true
