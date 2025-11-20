#!/bin/bash
# CAN interface setup script for openTPT
# Brings up all CAN interfaces with standard 500kbps bitrate

set -e

BITRATE=500000

# Bring up all CAN interfaces
for iface in can_b1_0 can_b1_1 can_b2_0 can_b2_1; do
    if [ -d "/sys/class/net/$iface" ]; then
        echo "Bringing up $iface at ${BITRATE} bps..."
        ip link set "$iface" down 2>/dev/null || true
        ip link set "$iface" up type can bitrate "$BITRATE" restart-ms 100
        echo "$iface: UP"
    else
        echo "$iface: not found (skipping)"
    fi
done

echo "CAN interfaces ready"
