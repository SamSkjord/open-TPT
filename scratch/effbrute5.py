import can
import time
from datetime import datetime

interface = "can0"
bitrate = 500000

# Set up the bus
bus = can.interface.Bus(channel=interface, bustype="socketcan")

# Log format: [time] (trigger ID) → recv ID: data
log = []

def send_trigger(trigger_id):
    msg = can.Message(arbitration_id=trigger_id, data=[0x00]*8, is_extended_id=False)
    try:
        bus.send(msg)
        print(f"→ Sent to 0x{trigger_id:03X}")
        return True
    except can.CanError as e:
        print(f"✖ {trigger_id:03X} send failed: {e}")
        return False

def listen_responses(trigger_id, duration=0.3):
    start_time = time.time()
    while time.time() - start_time < duration:
        msg = bus.recv(timeout=0.1)
        if msg:
            timestamp = datetime.now().isoformat(timespec='milliseconds')
            entry = {
                "timestamp": timestamp,
                "trigger_id": f"{trigger_id:03X}",
                "recv_id": f"{msg.arbitration_id:03X}",
                "data": msg.data.hex(" ").upper()
            }
            log.append(entry)
            print(f"[{timestamp}] ← (0x{trigger_id:03X}) ID: {msg.arbitration_id:03X} Data: {entry['data']}")

# Main brute loop
for trigger_id in range(0x100, 0x200):  # shrink range while testing
    if send_trigger(trigger_id):
        listen_responses(trigger_id)
    time.sleep(0.05)

# Optionally save log
with open("can_trigger_log.txt", "w") as f:
    for entry in log:
        f.write(f"[{entry['timestamp']}] Trigger: 0x{entry['trigger_id']} → ID: 0x{entry['recv_id']} Data: {entry['data']}\n")
