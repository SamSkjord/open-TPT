# CM4-POE-UPS-BASE RTC Setup (PCF85063A) on Debian Trixie

This enables the onboard RTC and makes `hwclock` functional.

## 1. Install Required Packages

```bash
sudo apt update
sudo apt install util-linux-extra i2c-tools
```

## 2. Enable the Correct I²C Bus and RTC Overlay

The RTC is on **I²C-10** (CSI/DSI bus), not I²C-1.

```bash
CFG=/boot/firmware/config.txt
[ -f /boot/config.txt ] && CFG=/boot/config.txt

sudo sed -i -e '/^dtparam=i2c_vc=/d' -e '/^dtoverlay=i2c-rtc/d' "$CFG"
echo 'dtparam=i2c_vc=on' | sudo tee -a "$CFG"
echo 'dtoverlay=i2c-rtc,pcf85063a,i2c_csi_dsi' | sudo tee -a "$CFG"
```

Reboot:

```bash
sudo reboot
```

## 3. Confirm RTC is Detected

```bash
sudo i2cdetect -y 10
```

Expected output should show: `0x51` present.

## 4. Verify RTC Driver and Ticking

```bash
cat /sys/class/rtc/rtc0/name
cat /sys/class/rtc/rtc0/time
sleep 3
cat /sys/class/rtc/rtc0/time
```

The second call should show time increasing.  
Expected name output:

```
rtc-pcf85063 10-0051
```

## 5. Set and Write RTC Time (UTC)

```bash
sudo hwclock --rtc=/dev/rtc0 --set --date="$(date -u '+%Y-%m-%d %H:%M:%S')" --utc
sudo hwclock --systohc --utc
```

Read RTC → System time (manual restore if needed):

```bash
sudo hwclock --hctosys --utc
```

## 6. Optional: Restore Time from RTC on Boot

```bash
sudo tee /etc/systemd/system/rtc-hctosys.service >/dev/null <<'EOF'
[Unit]
Description=Set system time from PCF85063A RTC
After=dev-rtc.device
Wants=dev-rtc.device

[Service]
Type=oneshot
ExecStart=/usr/sbin/hwclock --hctosys --utc

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable rtc-hctosys.service
```

## Done

The RTC now:
- Uses the correct driver (`pcf85063a`)
- Updates correctly
- Survives power loss
- Can set time before network sync
