"""
Performance monitoring mixin for openTPT.

Provides power status checking, memory statistics collection,
and periodic performance monitoring.
"""

import gc
import logging
import subprocess
import time

import pygame

logger = logging.getLogger('openTPT.performance')


def check_power_status():
    """
    Check Raspberry Pi power status for undervoltage and throttling.

    Logs warnings if power issues are detected that could cause system instability.

    Returns:
        tuple: (throttled_value, has_issues, warning_message)
    """
    try:
        result = subprocess.run(
            ['vcgencmd', 'get_throttled'],
            capture_output=True,
            text=True,
            timeout=2.0
        )

        if result.returncode != 0:
            return (None, False, "Could not read throttle status")

        # Parse throttled value (format: "throttled=0x50000")
        throttled_str = result.stdout.strip().split('=')[1]
        throttled = int(throttled_str, 16)

        # Decode throttle bits
        # Bits 0-3: Current status
        # Bits 16-19: Has occurred since boot
        issues = []
        has_critical = False

        # Current status bits
        if throttled & 0x1:
            issues.append("[CRITICAL] Undervoltage detected NOW")
            has_critical = True
        if throttled & 0x2:
            issues.append("[CRITICAL] Arm frequency capped NOW")
            has_critical = True
        if throttled & 0x4:
            issues.append("[WARNING] Currently throttled")
            has_critical = True
        if throttled & 0x8:
            issues.append("[WARNING] Soft temperature limit active")

        # Historical bits (since boot)
        if throttled & 0x10000:
            issues.append("[INFO] Undervoltage has occurred since boot")
        if throttled & 0x20000:
            issues.append("[INFO] Arm frequency capping has occurred")
        if throttled & 0x40000:
            issues.append("[INFO] Throttling has occurred")
        if throttled & 0x80000:
            issues.append("[INFO] Soft temperature limit has been reached")

        if throttled == 0:
            return (throttled, False, "Power status: OK")

        warning = f"\n{'='*60}\n"
        warning += f"POWER ISSUES DETECTED (throttled={throttled_str})\n"
        warning += f"{'='*60}\n"
        for issue in issues:
            warning += f"{issue}\n"

        if has_critical or (throttled & 0x50000):  # Undervoltage or frequency capping occurred
            warning += "\n[CRITICAL] System experiencing power problems!\n"
            warning += "   - Use official Raspberry Pi power supply (5V/5A)\n"
            warning += "   - Check USB-C cable quality (use thick, short cable)\n"
            warning += "   - Reduce connected hardware load if problem persists\n"
            warning += "   - System may crash or behave erratically\n"

        warning += f"{'='*60}\n"

        return (throttled, True, warning)

    except FileNotFoundError:
        return (None, False, "vcgencmd not available (not running on Pi?)")
    except (subprocess.SubprocessError, OSError, ValueError) as e:
        return (None, False, f"Error checking power status: {e}")


def collect_memory_stats():
    """
    Collect comprehensive memory statistics for long-runtime monitoring.

    Returns GPU memory (malloc/reloc), system RAM, Python process memory,
    and pygame surface count.

    Returns:
        dict: Memory statistics or None if collection fails
    """
    try:
        stats = {}

        # GPU memory allocation (vcgencmd)
        try:
            # GPU malloc heap
            result = subprocess.run(
                ['vcgencmd', 'get_mem', 'malloc'],
                capture_output=True,
                text=True,
                timeout=1.0
            )
            if result.returncode == 0:
                # Format: "malloc=14M\n"
                stats['gpu_malloc'] = result.stdout.strip().split('=')[1]

            # GPU reloc heap
            result = subprocess.run(
                ['vcgencmd', 'get_mem', 'reloc'],
                capture_output=True,
                text=True,
                timeout=1.0
            )
            if result.returncode == 0:
                stats['gpu_reloc'] = result.stdout.strip().split('=')[1]

            # Total GPU
            result = subprocess.run(
                ['vcgencmd', 'get_mem', 'gpu'],
                capture_output=True,
                text=True,
                timeout=1.0
            )
            if result.returncode == 0:
                stats['gpu_total'] = result.stdout.strip().split('=')[1]

        except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError, ValueError) as e:
            stats['gpu_error'] = str(e)

        # System memory (free -m)
        try:
            result = subprocess.run(
                ['free', '-m'],
                capture_output=True,
                text=True,
                timeout=1.0
            )
            if result.returncode == 0:
                # Parse second line (Mem:)
                lines = result.stdout.strip().split('\n')
                if len(lines) >= 2:
                    mem_line = lines[1].split()
                    stats['ram_total'] = f"{mem_line[1]}M"
                    stats['ram_used'] = f"{mem_line[2]}M"
                    stats['ram_free'] = f"{mem_line[3]}M"
                    stats['ram_available'] = f"{mem_line[6]}M" if len(mem_line) > 6 else "N/A"
        except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError, IndexError, ValueError) as e:
            stats['ram_error'] = str(e)

        # Python process memory (from /proc/self/status)
        try:
            with open('/proc/self/status', 'r') as f:
                for line in f:
                    if line.startswith('VmRSS:'):
                        # Resident Set Size (physical RAM used)
                        rss_kb = int(line.split()[1])
                        stats['process_rss'] = f"{rss_kb // 1024}M"
                    elif line.startswith('VmSize:'):
                        # Virtual Memory Size
                        vm_kb = int(line.split()[1])
                        stats['process_vms'] = f"{vm_kb // 1024}M"
        except (FileNotFoundError, IOError, OSError, IndexError, ValueError) as e:
            stats['process_error'] = str(e)

        # Pygame surface count (if available)
        try:
            # Count active pygame surfaces using gc
            surface_count = sum(1 for obj in gc.get_objects()
                              if isinstance(obj, pygame.Surface))
            stats['pygame_surfaces'] = surface_count
        except (TypeError, RuntimeError) as e:
            stats['surface_error'] = str(e)

        # CPU temperature
        try:
            result = subprocess.run(
                ['vcgencmd', 'measure_temp'],
                capture_output=True,
                text=True,
                timeout=1.0
            )
            if result.returncode == 0:
                # Format: "temp=51.1'C\n"
                stats['cpu_temp'] = result.stdout.strip().split('=')[1]
        except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError, IndexError, ValueError) as e:
            stats['temp_error'] = str(e)

        # Object type profiling (identify memory leaks)
        try:
            from collections import Counter
            all_objects = gc.get_objects()
            stats['total_objects'] = len(all_objects)

            # Count objects by type
            type_counts = Counter(type(obj).__name__ for obj in all_objects)

            # Get top 10 object types
            stats['top_object_types'] = type_counts.most_common(10)
        except (TypeError, RuntimeError) as e:
            stats['profiling_error'] = str(e)

        return stats

    except (RuntimeError, MemoryError) as e:
        return {'error': str(e)}


class PerformanceMixin:
    """Mixin providing performance monitoring and maintenance methods."""

    def _do_periodic_maintenance(self):
        """
        Perform periodic maintenance tasks.

        Called from _update_hardware() to handle:
        - Garbage collection every 60 seconds
        - Surface clearing every 10 minutes
        - Voltage monitoring every 60 seconds
        """
        current_time = time.time()

        # Periodic garbage collection for long runtime stability (every 60 seconds)
        if current_time - self.last_gc_time >= self.gc_interval:
            self.last_gc_time = current_time

            # Count objects before GC
            obj_count_before = len(gc.get_objects())

            # Force garbage collection
            collected = gc.collect()

            # Count objects after GC
            obj_count_after = len(gc.get_objects())

            logger.debug("GC: Collected %d objects, %d -> %d objects (%d freed)",
                         collected, obj_count_before, obj_count_after,
                         obj_count_before - obj_count_after)

        # Clear cached pygame surfaces periodically (every 10 minutes)
        # This prevents GPU memory buildup from cached surfaces
        if current_time - self.last_surface_clear >= self.surface_clear_interval:
            self.last_surface_clear = current_time
            self.cached_ui_surface = None
            self.cached_brightness_surface = None
            logger.debug("Memory: Cleared cached pygame surfaces (frame %d)", self.frame_count)

        # Periodic voltage monitoring (every 60 seconds)
        if current_time - self.last_voltage_check >= self.voltage_check_interval:
            self.last_voltage_check = current_time
            throttled, has_issues, message = check_power_status()

            # Only log if there are new issues or critical issues
            if has_issues and (throttled & 0xF):  # Current issues (bits 0-3)
                logger.warning(message)
            elif has_issues and not self.voltage_warning_shown:
                # Historical issues only - log once
                logger.info(message)
                self.voltage_warning_shown = True

            # Collect and log detailed memory statistics if enabled
            self._log_memory_stats()

    def _log_memory_stats(self):
        """Log detailed memory statistics if monitoring is enabled."""
        from utils.config import MEMORY_MONITORING_ENABLED

        if not MEMORY_MONITORING_ENABLED:
            return

        stats = collect_memory_stats()
        if stats and 'error' not in stats:
            # Format compact log message with key metrics
            mem_msg = f"MEMORY: frame={self.frame_count}"

            # GPU memory
            if 'gpu_malloc' in stats and 'gpu_reloc' in stats and 'gpu_total' in stats:
                mem_msg += f" | GPU: {stats['gpu_total']} (malloc={stats['gpu_malloc']} reloc={stats['gpu_reloc']})"

            # System RAM
            if 'ram_used' in stats and 'ram_available' in stats:
                mem_msg += f" | RAM: used={stats['ram_used']} avail={stats['ram_available']}"

            # Python process
            if 'process_rss' in stats:
                mem_msg += f" | Process: RSS={stats['process_rss']}"
                if 'process_vms' in stats:
                    mem_msg += f" VMS={stats['process_vms']}"

            # Pygame surfaces
            if 'pygame_surfaces' in stats:
                mem_msg += f" | Surfaces={stats['pygame_surfaces']}"

            # CPU temperature
            if 'cpu_temp' in stats:
                mem_msg += f" | Temp={stats['cpu_temp']}"

            # Total object count with delta
            if 'total_objects' in stats:
                current_count = stats['total_objects']
                delta = current_count - self.last_object_count if self.last_object_count > 0 else 0
                if delta > 0:
                    mem_msg += f" | Objects={current_count} (+{delta})"
                else:
                    mem_msg += f" | Objects={current_count}"
                self.last_object_count = current_count

            logger.debug(mem_msg)

            # Log object type profiling on separate line for easy grepping
            if 'top_object_types' in stats:
                top_types = ', '.join([f"{name}:{count}" for name, count in stats['top_object_types']])
                logger.debug("PROFILE: Top objects: %s", top_types)

                # Show which types are growing the most
                if self.last_top_types:
                    growing_types = []
                    for name, count in stats['top_object_types'][:5]:  # Top 5
                        prev_count = self.last_top_types.get(name, 0)
                        delta = count - prev_count
                        if delta > 100:  # Only show significant growth
                            growing_types.append(f"{name}:+{delta}")

                    if growing_types:
                        logger.debug("PROFILE: Growing: %s", ', '.join(growing_types))

                # Update last_top_types
                self.last_top_types = dict(stats['top_object_types'])

        elif stats and 'error' in stats:
            logger.warning("MEMORY: Collection error: %s", stats['error'])

    def _calculate_fps(self):
        """Calculate and update the FPS value."""
        self.frame_count += 1
        current_time = time.time()
        elapsed = current_time - self.last_time

        # Update FPS every second
        if elapsed >= 1.0:
            self.fps = self.frame_count / elapsed
            self.frame_count = 0
            self.last_time = current_time

    def _update_performance_metrics(self):
        """Update and optionally print performance metrics."""
        if not self.perf_monitor:
            return

        current_time = time.time()

        # Update hardware update rates
        self.perf_monitor.update_hardware_rate("TPMS", self.tpms.get_update_rate())
        self.perf_monitor.update_hardware_rate("Corners", self.corner_sensors.get_update_rate())

        # Print performance summary periodically
        if current_time - self.last_perf_summary >= self.perf_summary_interval:
            self.last_perf_summary = current_time
            logger.debug(self.perf_monitor.get_performance_summary())

            # Print brake temps (useful for thermocouple debugging)
            brake_temps = self.brakes.get_temps()
            brake_lines = []
            for pos in ["FL", "FR", "RL", "RR"]:
                data = brake_temps.get(pos, {})
                inner = data.get("inner")
                outer = data.get("outer")
                temp = data.get("temp")
                if inner is not None or outer is not None:
                    parts = []
                    if inner is not None:
                        parts.append(f"inner={inner:.1f}C")
                    if outer is not None:
                        parts.append(f"outer={outer:.1f}C")
                    brake_lines.append(f"  {pos}: {', '.join(parts)}")
                elif temp is not None:
                    brake_lines.append(f"  {pos}: {temp:.1f}C")
            if brake_lines:
                logger.debug("Brake temps:\n%s", "\n".join(brake_lines))
