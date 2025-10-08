import time
import pygame
import board
import busio
import adafruit_mlx90640

pygame.init()
screen = pygame.display.set_mode((1920, 1080), pygame.FULLSCREEN)
pygame.mouse.set_visible(False)
screen.fill((32, 32, 32))
pygame.display.update()
i2c = busio.I2C(board.SCL, board.SDA)
mlx = adafruit_mlx90640.MLX90640(i2c)
mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_2_HZ
frame = [0] * 768

while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            exit(0)
    try:
        mlx.getFrame(frame)
    except Exception:
        continue

    screen.fill((0, 0, 0))  # Just clear to black every frame
    pygame.display.update()
    time.sleep(0.1)
