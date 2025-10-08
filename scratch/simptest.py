import time
import board
import busio
import adafruit_mlx90640

print("Simple MLX90640 test starting...")

# Init I2C
i2c = busio.I2C(board.SCL, board.SDA)
print("I2C initialized")

# Init MLX90640
mlx = adafruit_mlx90640.MLX90640(i2c)
print("MLX90640 initialized")

# Set refresh rate
mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_2_HZ
print("Refresh rate set")

# Wait for sensor
print("Waiting 3 seconds...")
time.sleep(3)

# Try to read frame
frame = [0] * 768
print("About to call getFrame()...")

try:
    mlx.getFrame(frame)
    print("SUCCESS! First few temps:", frame[:5])
    print("Frame length:", len(frame))
    print("Min temp:", min(frame))
    print("Max temp:", max(frame))
    print("Avg temp:", sum(frame)/len(frame))
except Exception as e:
    print("ERROR:", e)

print("Test complete")
