import pygame
import time

pygame.init()
screen = pygame.display.set_mode((1920, 1080), pygame.FULLSCREEN)
pygame.mouse.set_visible(False)

screen.fill((255, 0, 0))  # Red
pygame.display.update()
time.sleep(2)

screen.fill((0, 255, 0))  # Green
pygame.display.update()
time.sleep(2)

screen.fill((0, 0, 255))  # Blue
pygame.display.update()
time.sleep(2)
