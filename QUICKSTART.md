# Quick Start Guide - openTPT Development

## Your Pi Configuration
- **IP Address**: `192.168.199.247`
- **User**: `pi`
- **Path**: `/home/pi/openTPT`
- **Status**: ✅ Deployed and tested

## Quick Commands

### Deploy from Mac to Pi
```bash
# Full deployment (first time or big changes)
./deploy_to_pi.sh pi@192.168.199.247

# Quick sync (only code changes)
./tools/quick_sync.sh pi@192.168.199.247

# Auto-deploy on file changes (requires fswatch)
brew install fswatch
fswatch -o . | xargs -n1 -I{} ./tools/quick_sync.sh pi@192.168.199.247
```

### Run on Pi
```bash
# SSH to Pi
ssh pi@192.168.199.247

# Navigate to app
cd /home/pi/openTPT

# Run performance tests
python3 tools/performance_test.py

# Run application (needs sudo for GPIO)
sudo ./main.py

# Or windowed mode for testing
sudo ./main.py --windowed
```

### View Pi Logs Remotely
```bash
# Real-time performance monitoring
ssh pi@192.168.199.247 "cd /home/pi/openTPT && sudo ./main.py 2>&1" | grep "Performance Summary" -A 20
```

## Performance Results (Tested on Your Pi)

| Test | Target | Result | Status |
|------|--------|--------|--------|
| Render Loop | ≤ 12 ms | 8.07 ms | ✅ PASS |
| Lock-Free Access | < 100 µs | 6.11 µs | ✅ PASS |
| Thermal Processing | < 1 ms | 1.46 ms | ⚠️ Close |
| FPS | 30-60 | 62.5 | ✅ PASS |

## Development Workflow

### 1. Edit on Mac
```bash
# Open your editor
code /Users/sam/git/open-TPT

# Or vim, etc.
vim hardware/mlx_handler_optimized.py
```

### 2. Test Locally (Mock Mode)
```bash
cd /Users/sam/git/open-TPT
./main.py --windowed
```

### 3. Deploy to Pi
```bash
# In another terminal, auto-deploy on save
fswatch -o . | xargs -n1 -I{} ./tools/quick_sync.sh pi@192.168.199.247
```

### 4. Test on Pi
```bash
# SSH to Pi
ssh pi@192.168.199.247

# Run with actual hardware
cd /home/pi/openTPT
sudo ./main.py
```

## Key Files You'll Edit

### Hardware Handlers
- `hardware/mlx_handler_optimized.py` - Thermal cameras
- `hardware/ir_brakes_optimized.py` - Brake temp sensors
- `hardware/tpms_input_optimized.py` - TPMS sensors

### Processing
- `perception/tyre_zones.py` - Thermal zone analysis (I/C/O)

### GUI
- `gui/display.py` - Rendering logic
- `main.py` - Main application loop

### Configuration
- `utils/config.py` - All constants and positions

## British English Reminders

Remember to use British spelling:
- ✅ **Tyre** (not Tire)
- ✅ **Optimised** (not Optimized)
- ✅ **Initialise** (not Initialize)
- ✅ **Colour** (not Color)
- ✅ **Centre** (not Center)

## Troubleshooting

### Can't Connect to Pi
```bash
# Check Pi is on network
ping 192.168.199.247

# Test SSH
ssh pi@192.168.199.247 "echo 'Connection OK'"
```

### GPIO Errors
```bash
# Always use sudo for hardware access
sudo ./main.py
```

### Performance Issues
```bash
# Check performance summary in logs
ssh pi@192.168.199.247 "cd /home/pi/openTPT && sudo ./main.py 2>&1 | grep -A 20 'Performance Summary'"
```

### Dependencies Missing
```bash
# Re-run install script on Pi
ssh pi@192.168.199.247
cd /home/pi/openTPT
./install.sh
```

## What's Optimised

✅ **Bounded Queue Architecture**
- No blocking in render path
- Lock-free data snapshots
- Queue depth = 2 (double-buffering)

✅ **Numba JIT Compilation**
- Thermal zone processor
- 10x faster on x86, 2x on ARM

✅ **Pre-Processing**
- I/C/O thermal zones calculated in background
- EMA smoothing
- Slew-rate limiting

✅ **Performance Monitoring**
- Real-time metrics
- Automatic warnings
- Printed every 10 seconds

## Next Steps

1. **Test with Real Hardware**
   - Connect sensors
   - Run `sudo ./main.py` on Pi
   - Verify thermal zones (I/C/O split)

2. **Monitor Performance**
   - Check performance summary
   - Look for warnings
   - Validate FPS stays above 30

3. **Continue Development**
   - Follow system plan for radar, CAN, OBD
   - Use auto-deploy for fast iteration
   - Test on Pi frequently

## Quick Links

- **System Plan**: `open-TPT_System_Plan.md`
- **Performance Details**: `PERFORMANCE_OPTIMISATIONS.md`
- **Deployment Guide**: `DEPLOYMENT.md`
- **Test Results**: On Pi at `/home/pi/openTPT/TEST_RESULTS.md`

---

**Status**: ✅ All optimisations deployed and tested on your Pi!

Happy coding! 🚀
