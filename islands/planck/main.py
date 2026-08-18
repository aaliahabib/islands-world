"""ZOO BREAKOUT — your island's game.

You're the security guard. Animals escape their pens one at a time and come
for you — dodge or jump their attacks, then hit them with the right weapon
(it switches automatically) until they're down. Get hit once and it's over.

    LEFT / RIGHT  (or A / D)   move
    UP / SPACE                 jump
    R                          dodge
    E                          attack
    R (after game over)        restart

This is YOUR game now. The fastest way to make it yours is the CUSTOMIZE block
just below — change the colours, make the guard faster, give the animals more
health. Then run it and see what happened. After that, ask Claude for bigger
changes.

Two rules that keep your island working inside Islands World:
  1. keep `async def main()` and the `await asyncio.sleep(0)` at the end of the
     game loop — that's what lets the game run in a browser.
  2. keep calling `submit_score(...)` and `game_over(...)` — that's what puts
     your score on the world scoreboard.
"""

import asyncio
import math
import random

import pygame

from islands_sdk import game_over, reset as reset_score, submit_score

# ─────────────────────────────────────────────────────────────────────────────
#  CUSTOMIZE ME — change these numbers and colours first. Nothing here can
#  break the game; the worst that happens is it gets silly.
# ─────────────────────────────────────────────────────────────────────────────

TITLE = "Zoo Breakout"

WIDTH = 900                      # size of the game window
HEIGHT = 700

SKY_COLOR = (135, 206, 235)      # daytime sky
GROUND_COLOR = (110, 90, 60)     # dirt floor of the empty enclosure
CAGE_WALL_COLOR = (170, 165, 150)   # back wall of the empty cage, behind the guard
CAGE_BAR_COLOR = (60, 60, 60)       # bars across the cage wall — pure background, no collision
CAGE_WIDTH = 480                    # how wide the cage is — make it smaller or bigger
CAGE_SIGN_COLOR = (200, 60, 40)     # the "ZOO" sign on the cage
LINE_COLOR = (255, 255, 255)     # the guard and UI are drawn in this colour
LINE_WIDTH = 2
FONT_NAME = None                 # None = pygame's built-in font

GROUND_Y = HEIGHT - 120          # the ground the guard stands on

GUARD_SIZE = 34                  # how big the guard is
GUARD_SPEED = 260                # how fast he walks, pixels/second
GUARD_JUMP_SPEED = 620           # how strong the jump is
GUARD_GRAVITY = 1500             # how fast he falls back down
GUARD_DODGE_SPEED = 620          # how fast the dodge burst is
GUARD_DODGE_TIME = 0.22          # seconds the dodge burst lasts
GUARD_DODGE_COOLDOWN = 0.6       # seconds before you can dodge again

FPS = 60

# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────


def draw_shape(surface, points, color=None, width=None, closed=True):
    """Draw an outline through `points`."""
    pygame.draw.lines(
        surface,
        color or LINE_COLOR,
        closed,
        points,
        width or LINE_WIDTH,
    )


_fonts = {}


def draw_text(surface, text, pos, size=24, color=None, align="left"):
    """Draw some text. `align` is "left", "center" or "right", and `pos` is the
    top corner (or top middle, if centred)."""
    if size not in _fonts:
        _fonts[size] = pygame.font.Font(FONT_NAME, size)
    image = _fonts[size].render(str(text).upper(), True, color or LINE_COLOR)
    rect = image.get_rect()
    setattr(rect, {"left": "topleft", "center": "midtop", "right": "topright"}[align], pos)
    surface.blit(image, rect)


# ─────────────────────────────────────────────────────────────────────────────
#  Things in the game
# ─────────────────────────────────────────────────────────────────────────────


class Guard:
    # The guard outline, drawn facing right. Change these to reshape him.
    SHAPE = [
        (-0.35, 1.0), (-0.35, 0.15), (-0.55, -0.15), (-0.35, -0.45),
        (0.0, -0.6), (0.35, -0.45), (0.55, -0.15), (0.35, 0.15), (0.35, 1.0),
    ]

    def __init__(self):
        self.reset()

    def reset(self):
        self.x = WIDTH / 2
        self.y = GROUND_Y
        self.vy = 0.0
        self.on_ground = True
        self.facing = 1
        self.dodge_timer = 0.0
        self.dodge_cooldown = 0.0
        self.dodge_vx = 0.0
        self.attack_timer = 0.0
        self.r_was_down = False

    @property
    def dodging(self):
        return self.dodge_timer > 0

    def update(self, dt, keys):
        self.dodge_cooldown = max(0.0, self.dodge_cooldown - dt)
        self.attack_timer = max(0.0, self.attack_timer - dt)

        r_down = keys[pygame.K_r]
        if r_down and not self.r_was_down and self.dodge_cooldown <= 0:
            self.dodge_timer = GUARD_DODGE_TIME
            self.dodge_cooldown = GUARD_DODGE_COOLDOWN
            self.dodge_vx = GUARD_DODGE_SPEED * self.facing
        self.r_was_down = r_down

        if self.dodging:
            self.dodge_timer = max(0.0, self.dodge_timer - dt)
            self.x += self.dodge_vx * dt
        else:
            move = 0
            if keys[pygame.K_LEFT] or keys[pygame.K_a]:
                move -= 1
            if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
                move += 1
            if move:
                self.facing = move
            self.x += move * GUARD_SPEED * dt

        half = GUARD_SIZE * 0.4
        self.x = max(half, min(WIDTH - half, self.x))

        if self.on_ground and (keys[pygame.K_UP] or keys[pygame.K_SPACE] or keys[pygame.K_w]):
            self.vy = -GUARD_JUMP_SPEED
            self.on_ground = False

        self.vy += GUARD_GRAVITY * dt
        self.y += self.vy * dt
        if self.y >= GROUND_Y:
            self.y = GROUND_Y
            self.vy = 0.0
            self.on_ground = True

    def attack(self):
        self.attack_timer = 0.18

    def points(self):
        flip = -1 if self.facing < 0 else 1
        return [
            (self.x + px * flip * GUARD_SIZE, self.y + py * GUARD_SIZE)
            for px, py in self.SHAPE
        ]

    def draw(self, surface):
        color = (255, 255, 120) if self.dodging else None
        draw_shape(surface, self.points(), color=color)
        if self.attack_timer > 0:
            tip_x = self.x + self.facing * GUARD_SIZE * 1.4
            pygame.draw.line(
                surface, (255, 210, 90),
                (self.x, self.y - GUARD_SIZE * 0.2), (tip_x, self.y - GUARD_SIZE * 0.2), 4,
            )


def draw_cage_background(surface):
    """The empty enclosure behind the guard — pure scenery, nothing to hit."""
    wall_top = GROUND_Y - 260
    wall_left = (WIDTH - CAGE_WIDTH) / 2
    pygame.draw.rect(surface, CAGE_WALL_COLOR, (wall_left, wall_top, CAGE_WIDTH, GROUND_Y - wall_top))
    for x in range(int(wall_left) + 20, int(wall_left + CAGE_WIDTH), 40):
        pygame.draw.line(surface, CAGE_BAR_COLOR, (x, wall_top), (x, GROUND_Y), 4)

    sign_width, sign_height = 150, 44
    sign_rect = (WIDTH / 2 - sign_width / 2, wall_top - sign_height - 10, sign_width, sign_height)
    pygame.draw.rect(surface, CAGE_SIGN_COLOR, sign_rect)
    draw_text(surface, "ZOO", (WIDTH / 2, sign_rect[1] + 8), size=28, color=LINE_COLOR, align="center")


# ─────────────────────────────────────────────────────────────────────────────
#  The game
# ─────────────────────────────────────────────────────────────────────────────


class Game:
    def __init__(self):
        self.start_new_game()

    def start_new_game(self):
        self.guard = Guard()
        self.score = 0
        self.over = False
        reset_score()
        submit_score(0)

    def update(self, dt, keys):
        if self.over:
            return
        self.guard.update(dt, keys)
        if keys[pygame.K_e]:
            self.guard.attack()

    def draw(self, surface):
        surface.fill(SKY_COLOR)
        draw_cage_background(surface)
        pygame.draw.rect(surface, GROUND_COLOR, (0, GROUND_Y, WIDTH, HEIGHT - GROUND_Y))

        self.guard.draw(surface)
        self.draw_hud(surface)

        if self.over:
            draw_text(surface, "GAME OVER", (WIDTH / 2, HEIGHT / 2 - 40), size=64, align="center")
            draw_text(surface, "PRESS R TO PLAY AGAIN", (WIDTH / 2, HEIGHT / 2 + 30),
                      size=24, align="center")

    def draw_hud(self, surface):
        draw_text(surface, str(self.score), (28, 22), size=48)


async def main():
    pygame.init()
    pygame.display.set_caption(TITLE)
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()

    game = Game()
    running = True

    while running:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)   # cap dt so lag can't teleport things

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r and game.over:
                    game.start_new_game()
                # ESC is not handled here on purpose — in Islands World it means
                # "leave this island", and the world itself takes care of that.

        game.update(dt, pygame.key.get_pressed())
        game.draw(screen)
        pygame.display.flip()

        # Required for the browser build — hands control back to the page each
        # frame. Do not remove this line.
        await asyncio.sleep(0)

    pygame.quit()


# pygbag needs the program to start with asyncio.run(main()) at the top level.
asyncio.run(main())
