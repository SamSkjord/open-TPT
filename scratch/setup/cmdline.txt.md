# Optimised cmdline.txt for sub-7-second boot
# NOTE: Replace PARTUUID with your actual partition UUID (run: blkid)

# Production (fastest boot):
console=tty1 root=PARTUUID=XXXXXXXX-02 rootfstype=ext4 rootwait quiet loglevel=0 logo.nologo vt.global_cursor_default=0 systemd.show_status=0 rd.udev.log_priority=3 fsck.mode=skip

# Debug (with serial console, slower):
# console=serial0,115200 console=tty1 root=PARTUUID=XXXXXXXX-02 rootfstype=ext4 fsck.repair=yes rootwait loglevel=3 logo.nologo vt.global_cursor_default=0

# Key optimisations:
# - Removed serial console (saves ~0.5s)
# - fsck.mode=skip (skip filesystem check - assumes clean shutdown)
# - systemd.show_status=0 (hide boot messages)
# - rd.udev.log_priority=3 (reduce udev logging)
# - quiet loglevel=0 (minimal kernel messages)