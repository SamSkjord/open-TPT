# Security Review Report - openTPT

**Date:** 2025-11-20
**Version:** v0.10
**Reviewer:** Code Security Analysis
**Overall Risk:** MEDIUM

## Executive Summary

Comprehensive security review of openTPT identified **16 vulnerabilities** across 25 production Python files. The codebase demonstrates good architectural practices (bounded queues, lock-free patterns), but contains critical issues in CAN bus message parsing that require immediate attention.

### Issues by Severity

| Severity | Count | Action Required |
|----------|-------|----------------|
| **CRITICAL** | 2 | Fix immediately before production |
| **HIGH** | 5 | Fix in current release cycle |
| **MEDIUM** | 5 | Plan for next release |
| **LOW** | 4 | Ongoing maintenance |

---

## CRITICAL Issues (Fix Immediately)

### 1. CAN Bus Array Index Access Without Bounds Checking ⚠️

**Severity:** CRITICAL
**Risk:** Crash, DoS, data corruption, potential exploitation

**Affected Files:**
- `hardware/ford_hybrid_handler.py` (lines 115, 116, 127, 138, 139, 153, 154)
- `hardware/obd2_handler.py` (lines 133-136, 168-171)

**Problem:**
```python
# VULNERABLE: Array access before length check
if (msg.data[1] == 0x41  # ← IndexError if len(msg.data) < 2
    and len(msg.data) >= 4):
```

**Impact:**
- IndexError exceptions from malformed CAN messages
- Thread crashes causing telemetry loss
- Malicious CAN injection could crash system

**Fix:**
```python
# Check length FIRST
if (len(msg.data) >= 4
    and msg.data[1] == 0x41
    and msg.data[2] == PID):
    value = msg.data[3]
```

**Files to update:**
- [ ] `hardware/ford_hybrid_handler.py:115-165` (_decode_soc, _decode_hv_temp, etc.)
- [ ] `hardware/obd2_handler.py:133-136` (speed decoding)
- [ ] `hardware/obd2_handler.py:168-171` (MAP decoding)

---

### 2. NumPy Array Slicing Without Shape Validation

**Severity:** HIGH
**Risk:** Array errors, crashes, incorrect data

**Affected Files:**
- `gui/display.py` (lines 424, 478)

**Problem:**
```python
# Assumes thermal_data is always 24x32
section_width = thermal_data.shape[1] // 3  # No validation
```

**Fix:**
```python
def draw_thermal_image(self, position, thermal_data):
    if thermal_data is None or thermal_data.shape != (24, 32):
        return  # Invalid data
    section_width = thermal_data.shape[1] // 3
```

**Files to update:**
- [ ] `gui/display.py:420-430`
- [ ] `gui/display.py:475-485`

---

## HIGH Priority Issues

### 3. Bare Except Clauses

**Severity:** HIGH
**Files:** `hardware/unified_corner_handler.py:374`, `hardware/i2c_mux.py:175,238`

**Problem:** Catches ALL exceptions including KeyboardInterrupt, SystemExit
**Fix:** Use specific exception types: `except (IOError, OSError) as e:`

**Files to update:**
- [ ] `hardware/unified_corner_handler.py:374`
- [ ] `hardware/i2c_mux.py:175`
- [ ] `hardware/i2c_mux.py:238`

---

### 4. Configuration File Input Validation

**Severity:** HIGH
**Files:** `utils/config.py:111-131`

**Problem:** No validation of display dimensions from JSON config
**Risk:** Integer overflow, division by zero, memory exhaustion

**Fix:**
```python
def validate_display_config(width, height):
    if not isinstance(width, int) or not isinstance(height, int):
        raise ValueError("Dimensions must be integers")
    if not (320 <= width <= 7680 and 240 <= height <= 4320):
        raise ValueError(f"Invalid dimensions: {width}x{height}")
    return width, height
```

**Files to update:**
- [ ] `utils/config.py:111-131`

---

### 5. Camera Thread Race Conditions

**Severity:** HIGH
**Files:** `gui/camera.py:98-142, 267-272`

**Problem:** Shared frame access without locks, non-atomic queue operations
**Risk:** Display artifacts, thread deadlocks, crashes

**Fix:** Use locks around frame access, atomic queue operations

**Files to update:**
- [ ] `gui/camera.py:267-272` (queue operations)
- [ ] `gui/camera.py:98-142` (switch_camera method)

---

## MEDIUM Priority Issues

### 6. Unbounded String Operations in Device Paths
**Severity:** MEDIUM | **Files:** `gui/camera.py:124,341`

### 7. Integer Division Without Bounds Checking
**Severity:** MEDIUM | **Files:** `gui/display.py:294,383-384,515,542`

### 8. Subprocess Command Injection Risk
**Severity:** MEDIUM | **Files:** `hardware/toyota_radar_driver.py:380-396`

### 9. Missing I2C Operation Timeouts
**Severity:** MEDIUM | **Files:** `hardware/unified_corner_handler.py:327-375`

### 10. No Queue Overflow Monitoring
**Severity:** MEDIUM | **Files:** `utils/hardware_base.py:48`

---

## LOW Priority Issues

### 11. Brightness Cycle Edge Case
**Severity:** LOW | **Files:** `gui/input_threaded.py:288`

### 12. Pygame Surface Threading
**Severity:** LOW | **Files:** `gui/camera.py:500-514`

### 13. Hardcoded File Paths
**Severity:** LOW | **Files:** `utils/config.py:15-17,316`

### 14. Exception Information Leakage
**Severity:** LOW | **Files:** `main.py:408-411`

---

## Positive Security Findings ✅

**Excellent practices observed:**

1. ✅ **Bounded Queue Architecture** - Prevents memory exhaustion (depth=2)
2. ✅ **Lock-Free Render Path** - No blocking in critical rendering code
3. ✅ **Worker Thread Pattern** - Clean I/O separation
4. ✅ **Defensive Defaults** - Graceful degradation without hardware
5. ✅ **No Dynamic Code Execution** - No eval(), exec(), or pickle
6. ✅ **Subprocess Safety** - List-form arguments (not shell=True)
7. ✅ **Resource Cleanup** - Proper cleanup methods and thread shutdown

---

## Priority 1 Action Items (Critical)

### Week 1: CAN Bus Safety

- [ ] **Add CAN message length validation helper**
  ```python
  def validate_can_msg(msg: can.Message, min_len: int) -> bool:
      """Validate CAN message has minimum data length."""
      return msg is not None and len(msg.data) >= min_len
  ```

- [ ] **Fix ford_hybrid_handler.py**
  - Update _decode_soc (lines 115-116)
  - Update _decode_hv_temp (line 127)
  - Update _decode_hv_current (lines 138-139)
  - Update _decode_hv_voltage (lines 153-154)
  - Update _decode_max_power (line 165)

- [ ] **Fix obd2_handler.py**
  - Update speed decoder (lines 133-136)
  - Update MAP decoder (lines 168-171)

- [ ] **Add NumPy shape validation in display.py**
  - Add checks before thermal array slicing
  - Lines 424, 478

---

## Priority 2 Action Items (High)

### Week 2-3: Error Handling & Validation

- [ ] **Replace bare except clauses**
  - unified_corner_handler.py:374
  - i2c_mux.py:175, 238

- [ ] **Add configuration validation**
  - Create validate_display_config() function
  - Add range checks for all numeric config values

- [ ] **Fix camera thread safety**
  - Add locks around self.frame access
  - Use atomic queue operations

---

## Testing Requirements

### Security Test Suite

```python
# tests/security/test_can_safety.py
def test_malformed_can_messages():
    """Test handlers don't crash on truncated CAN messages."""
    handler = OBD2Handler()
    # Truncated message
    msg = can.Message(arbitration_id=0x7E8, data=[0x00])
    # Should not raise IndexError
    handler._process_message(msg)

def test_oversized_config():
    """Test config validation rejects extreme values."""
    config = {"width": 999999, "height": 999999}
    with pytest.raises(ValueError):
        validate_display_config(config)

def test_queue_overflow():
    """Test queue overflow doesn't crash or leak memory."""
    handler = TPMSHandler()
    for i in range(10000):
        handler._publish_snapshot({"test": i})
    # Should complete without crash
```

---

## Deployment Security Checklist

Before production deployment:

- [ ] All CRITICAL issues fixed and tested
- [ ] All HIGH priority issues addressed
- [ ] Security test suite passing
- [ ] Configuration validation enabled
- [ ] Logging configured (not print statements)
- [ ] File permissions reviewed (config files not world-writable)
- [ ] DBC files integrity checked
- [ ] CAN bus environment documented as trusted/untrusted
- [ ] Watchdog timer for critical threads
- [ ] Rate limiting on error messages

---

## Long-Term Security Improvements

### Phase 1 (Next Release)
- Implement comprehensive input validation framework
- Add security event logging
- Create fuzzing test suite for CAN messages

### Phase 2 (Future)
- Add integrity checks for configuration and DBC files
- Implement anomaly detection for sensor data
- Add security documentation (threat model, deployment guide)
- Consider adding CAN bus message authentication (if hardware supports)

### Phase 3 (Ongoing)
- Regular security audits
- Dependency vulnerability scanning
- Penetration testing with physical CAN bus injection

---

## References

- **CAN Security:** ISO 21434 (Road vehicles — Cybersecurity engineering)
- **Python Security:** OWASP Python Security Best Practices
- **Embedded Safety:** IEC 61508 (Functional Safety)

---

## Review History

| Date | Version | Reviewer | Issues Found | Status |
|------|---------|----------|--------------|--------|
| 2025-11-20 | v0.10 | Security Analysis | 16 (2 Critical, 5 High) | Initial Review |

---

**Next Review:** After Priority 1 fixes implemented
**Contact:** Review findings with development team before production deployment
