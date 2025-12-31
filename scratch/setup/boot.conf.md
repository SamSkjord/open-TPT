# For more options and information see
# http://rptl.io/configtxt
# Some settings may impact device functionality. See link above for details

# ============================================================================
# Boot Speed Optimisations
# ============================================================================
disable_splash=1
boot_delay=0              # Remove 1-second boot delay
initial_turbo=60          # Turbo mode for first 60 seconds of boot
force_eeprom_read=0       # Skip EEPROM read delay

# ============================================================================
# Hardware Interface Configuration
# ============================================================================
dtparam=i2c_arm=on
dtparam=i2s=off        # Disabled to free GPIO19 for SPI1_MISO
dtparam=spi=on

# Enable audio (loads snd_bcm2835)
#dtparam=audio=on

# ============================================================================
# System Configuration
# ============================================================================
# Automatically load overlays for detected cameras
camera_auto_detect=0

# Automatically load overlays for detected DSI displays
display_auto_detect=0

# Automatically load initramfs files, if found
auto_initramfs=1

# Enable DRM VC4 V3D driver
dtoverlay=vc4-kms-v3d
max_framebuffers=2

# Don't have the firmware create an initial video= setting in cmdline.txt.
# Use the kernel's default instead.
disable_fw_kms_setup=1

# Run in 64-bit mode
arm_64bit=1

# Disable compensation for displays with overscan
disable_overscan=1

# Run as fast as firmware / board allows
arm_boost=1

# ============================================================================
# Platform-Specific Configuration
# ============================================================================
[cm4]
# Enable host mode on the 2711 built-in XHCI USB controller.
# This line should be removed if the legacy DWC2 controller is required
# (e.g. for USB device mode) or if USB support is not required.
otg_mode=1

[cm5]
dtoverlay=dwc2,dr_mode=host

# ============================================================================
# Common Configuration (all platforms)
# ============================================================================
[all]

# Waveshare CM4-POE-UPS-BASE peripherals
dtparam=i2c_vc=on
dtoverlay=i2c-rtc,pcf85063a,i2c_csi_dsi              # RTC clock
dtoverlay=i2c-fan,emc2301,i2c_csi_dsi,midtemp=45000,maxtemp=65000  # Fan control

# ============================================================================
# Dual Waveshare 2-CH CAN HAT+ Configuration
# ============================================================================
# NOTE: Interface names (can0-can3) are determined by hardware probe order,
#       NOT by the declaration order below. This mapping is fixed:
#
# Board 1 (bottom) - SPI1 bus
#   can0: CAN_1 connector, SPI1 CE2 (GPIO16), interrupt GPIO13
#   can1: CAN_0 connector, SPI1 CE1 (GPIO7),  interrupt GPIO22
#
# Board 2 (top) - SPI0 bus  
#   can2: CAN_1 connector, SPI0 CE1 (GPIO7),  interrupt GPIO25 
#   can3: CAN_0 connector, SPI0 CE0 (GPIO8),  interrupt GPIO23

# Board 1 configuration (SPI1)
dtoverlay=spi1-3cs
dtoverlay=mcp2515,spi1-1,oscillator=16000000,interrupt=22  # can1 (CAN_0)
dtoverlay=mcp2515,spi1-2,oscillator=16000000,interrupt=13  # can0 (CAN_1)

# Board 2 configuration (SPI0)
dtoverlay=spi0-2cs
dtoverlay=mcp2515,spi0-0,oscillator=16000000,interrupt=23  # can3 (CAN_0)
dtoverlay=mcp2515,spi0-1,oscillator=16000000,interrupt=25  # can2 (CAN_1)