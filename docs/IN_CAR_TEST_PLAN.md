# In-Car Test Plan: Lap Timing & CoPilot

**Version:** 1.0 | **Date:** 2026-01-18

This test plan covers in-vehicle testing of the lap timing and CoPilot systems. Tests should be performed at a known track or route.

---

## Pre-Test Checklist

### Hardware
- [ ] Pi powered and display visible
- [ ] GPS antenna has clear sky view (dash mount or roof)
- [ ] Audio output connected (Bluetooth speaker or aux)
- [ ] All cables secured (no interference with controls)

### Software
- [ ] Latest code deployed (`./tools/quick_sync.sh`)
- [ ] Service running (`sudo systemctl status openTPT.service`)
- [ ] No errors in logs (`sudo journalctl -u openTPT.service --since "5 min ago"`)

### Data
- [ ] Track file loaded (KMZ) or auto-detect enabled
- [ ] CoPilot map data available for region (`/mnt/usb/.opentpt/copilot/maps/`)
- [ ] Audio samples installed (if using Janne samples)

---

## Test 1: GPS Acquisition

**Location:** Stationary in paddock/car park with sky view

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 1.1 | Power on system | Boot splash, then main display | |
| 1.2 | Navigate to System > GPS Status | GPS page shows | |
| 1.3 | Wait for fix | "Fix: 3D" within 60s cold, 15s warm | |
| 1.4 | Check satellite count | 6+ satellites visible | |
| 1.5 | Check position | Lat/Lon matches actual location | |
| 1.6 | Check speed | 0 km/h when stationary | |

**Notes:**
```
Time to first fix: _____ seconds
Satellite count: _____
Fix type: 2D / 3D
```

---

## Test 2: Track Detection

**Location:** Within 5km of known track

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 2.1 | Enable auto-detect (Menu > Lap Timing > Auto-Detect: Yes) | Setting saved | |
| 2.2 | Drive towards track | Track detected and loaded automatically | |
| 2.3 | Check track name | Correct track shown in status bar | |
| 2.4 | Alternative: Manual selection | Menu > Lap Timing > Select Track | |
| 2.5 | Verify start/finish shown | S/F marker on display (if applicable) | |

**Notes:**
```
Auto-detect distance: _____ km
Track detected: _____
Detection time: _____ seconds
```

---

## Test 3: Lap Timing - Circuit

**Location:** On track, ready to start lap

### 3.1 First Lap (Out Lap)

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 3.1.1 | Cross start/finish line | Lap timing starts, lap counter = 1 | |
| 3.1.2 | Check live timer | Timer counting up accurately | |
| 3.1.3 | Cross sector markers | Sector times recorded | |
| 3.1.4 | Complete lap, cross S/F | Lap time recorded, lap counter = 2 | |

### 3.2 Flying Laps

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 3.2.1 | Complete second lap | Lap time displayed | |
| 3.2.2 | Check delta display | Delta vs previous lap shown | |
| 3.2.3 | Set fastest lap | Best lap updated, delta reference changes | |
| 3.2.4 | Slower lap | Delta shows positive (red) | |
| 3.2.5 | Faster lap | Delta shows negative (green) | |

### 3.3 Timing Accuracy

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 3.3.1 | Compare to official timing | Within +/- 0.5s of transponder | |
| 3.3.2 | Consistent S/F detection | Same trigger point each lap | |
| 3.3.3 | No missed laps | All laps recorded | |

**Notes:**
```
Official lap time: _____
openTPT lap time: _____
Difference: _____ seconds

Laps completed: _____
Laps missed: _____
```

---

## Test 4: Lap Timing - Point-to-Point (Stage)

**Location:** Start of GPX stage route

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 4.1 | Load GPX route (Menu > Lap Timing > Load Route) | Route loaded, stage name shown | |
| 4.2 | Drive to start point | "At Start" indicator | |
| 4.3 | Cross start line | Timer starts | |
| 4.4 | Drive stage | Progress indicator updates | |
| 4.5 | Cross finish line | Stage time recorded | |
| 4.6 | Check persistence | Time saved to database | |

**Notes:**
```
Stage name: _____
Stage time: _____
Distance: _____ km
```

---

## Test 5: CoPilot - Just Drive Mode

**Location:** Public road or track with mapped roads

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 5.1 | Enable CoPilot (Menu > CoPilot > Enabled: Yes) | CoPilot active | |
| 5.2 | Set mode to "Just Drive" | Mode confirmed | |
| 5.3 | Set lookahead (e.g., 150m) | Lookahead saved | |
| 5.4 | Drive on mapped road | Road detected, callouts begin | |
| 5.5 | Approach corner | Corner callout heard (e.g., "3 left") | |
| 5.6 | Check timing | Callout ~3-5s before corner | |
| 5.7 | Check severity | Matches actual corner difficulty | |

### Corner Severity Reference (ASC Scale)
| Grade | Description | Example |
|-------|-------------|---------|
| 1 | Flat out / slight kink | High-speed sweeper |
| 2 | Lift or small brake | Fast bend |
| 3 | Medium corner | Standard 90-degree |
| 4 | Slow corner | Tight hairpin approach |
| 5 | Very slow | Hairpin |
| 6 | Acute hairpin | Switchback |

**Notes:**
```
Road detection: Yes / No
Callout timing: Early / Good / Late
Severity accuracy: ___ / 10 corners correct
Audio clarity: Clear / Muffled / Too quiet
```

---

## Test 6: CoPilot - Route Follow Mode

**Location:** Start of loaded GPX/KMZ route

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 6.1 | Load route (Menu > CoPilot > Routes) | Route loaded | |
| 6.2 | Set mode to "Route Follow" | Mode confirmed | |
| 6.3 | Drive to route start | "On Route" indicator | |
| 6.4 | Follow route | Callouts match route corners | |
| 6.5 | Deviate from route | "Off Route" warning | |
| 6.6 | Return to route | Callouts resume | |

**Notes:**
```
Route name: _____
On-route detection: Accurate / Delayed / Missed
Off-route detection: Yes / No
```

---

## Test 7: CoPilot Audio

**Location:** Stationary or low-speed test area

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 7.1 | Test espeak-ng voice | Clear TTS output | |
| 7.2 | Test Janne samples (if installed) | Natural rally voice | |
| 7.3 | Adjust volume (Menu > Bluetooth > Volume) | Volume changes | |
| 7.4 | Test at speed with wind/engine noise | Still audible | |
| 7.5 | Test Bluetooth latency | Callouts not delayed | |

**Notes:**
```
Audio source: espeak-ng / Janne samples
Volume level: _____%
Audibility at speed: Good / Marginal / Poor
Bluetooth latency: _____ ms (estimated)
```

---

## Test 8: Integration - Lap Timing + CoPilot

**Location:** On track with both systems active

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 8.1 | Load track for lap timing | Track active | |
| 8.2 | Use lap timing track for CoPilot (Menu > CoPilot > Routes > Use Track) | CoPilot uses track centreline | |
| 8.3 | Complete lap with callouts | Both systems work together | |
| 8.4 | Check lap time accuracy | Not affected by CoPilot | |
| 8.5 | Check callout timing | Consistent with standalone CoPilot | |

**Notes:**
```
Systems conflict: Yes / No
Performance impact: None / Minor / Significant
```

---

## Test 9: System Stability

**Location:** Full session (20+ minutes continuous use)

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 9.1 | Run full session | No crashes or freezes | |
| 9.2 | Check FPS | Maintains 60 FPS | |
| 9.3 | Check memory | No significant growth | |
| 9.4 | Check GPS | Fix maintained throughout | |
| 9.5 | Check logs after session | No errors or warnings | |

**Notes:**
```
Session duration: _____ minutes
Crashes: _____
GPS dropouts: _____
Display issues: _____
```

---

## Test 10: Edge Cases

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 10.1 | Pit lane entry/exit | Lap correctly invalidated or handled | |
| 10.2 | GPS momentary loss (tunnel/bridge) | Recovers gracefully | |
| 10.3 | Very slow lap (traffic/red flag) | Still records correctly | |
| 10.4 | Aborted lap (off track) | Handles without crash | |
| 10.5 | Track limits (off racing line) | CoPilot still works | |
| 10.6 | Multiple quick laps | All recorded accurately | |

---

## Post-Test Checklist

- [ ] Download logs: `scp pi@192.168.199.246:/home/pi/open-TPT/logs/* ./`
- [ ] Export lap times: Check `/mnt/usb/.opentpt/lap_timing/lap_timing.db`
- [ ] Note any issues for bug reports
- [ ] Check for throttling: `vcgencmd get_throttled` (0x0 = OK)
- [ ] Back up telemetry recordings if enabled

---

## Test Results Summary

| Test | Result | Notes |
|------|--------|-------|
| 1. GPS Acquisition | | |
| 2. Track Detection | | |
| 3. Lap Timing - Circuit | | |
| 4. Lap Timing - P2P | | |
| 5. CoPilot - Just Drive | | |
| 6. CoPilot - Route Follow | | |
| 7. CoPilot Audio | | |
| 8. Integration | | |
| 9. Stability | | |
| 10. Edge Cases | | |

**Overall Result:** PASS / FAIL

**Tester:** _______________
**Date:** _______________
**Track/Location:** _______________
**Software Version:** _______________

---

## Known Limitations

1. GPS accuracy is typically 2-3m CEP, affecting S/F line precision
2. CoPilot requires pre-loaded OSM map data for the region
3. First GPS fix after cold start may take 60+ seconds
4. Bluetooth audio has ~100-200ms latency
5. Point-to-point stages require GPX file with accurate waypoints
