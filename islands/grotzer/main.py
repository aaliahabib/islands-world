"""RHYTHM ISLAND — your island's game.

Four lane circles sit at the bottom. Notes fall down each lane — hit D, F, J or
K right as a note reaches its circle. The closer to dead-center you hit it, the
more points you get. Miss 20 notes and it's game over.

    D / F / J / K   hit the matching lane
    R               restart after game over

This is YOUR game now. The fastest way to make it yours is the CUSTOMIZE block
just below — change the colours, make notes fall faster, change how forgiving
the hit window is. Then run it and see what happened. After that, ask Claude
for bigger changes.

Two rules that keep your island working inside Islands World:
  1. keep `async def main()` and the `await asyncio.sleep(0)` at the end of the
     game loop — that's what lets the game run in a browser.
  2. keep calling `submit_score(...)` and `game_over(...)` — that's what puts
     your score on the world scoreboard.
"""

import asyncio
import random

import pygame

from islands_sdk import game_over, reset as reset_score, submit_score

# ─────────────────────────────────────────────────────────────────────────────
#  CUSTOMIZE ME — change these numbers and colours first. Nothing here can
#  break the game; the worst that happens is it gets silly.
# ─────────────────────────────────────────────────────────────────────────────

TITLE = "Rhythm Island"

WIDTH = 900                      # size of the game window
HEIGHT = 700

BACKGROUND = (10, 10, 18)
LINE_COLOR = (255, 255, 255)
FONT_NAME = None                 # None = pygame's built-in font

LANES = [
    {"key": pygame.K_d, "label": "D", "color": (255, 90, 90)},
    {"key": pygame.K_f, "label": "F", "color": (255, 210, 80)},
    {"key": pygame.K_j, "label": "J", "color": (100, 220, 140)},
    {"key": pygame.K_k, "label": "K", "color": (110, 170, 255)},
]

TARGET_Y = HEIGHT - 110          # height of the fixed circles
TARGET_RADIUS = 36
NOTE_RADIUS = 26

NOTE_SPEED = 380                 # pixels per second, falling down
NOTE_SPAWN_INTERVAL = 0.55       # seconds between new notes, steady pace

HIT_WINDOW = 55                  # how far (in pixels) from dead-center still counts as a hit
MAX_HIT_POINTS = 100             # points for a perfect, dead-center hit
MISS_PENALTY = 15                # points lost for letting a note go by
MAX_MISSES = 20                  # game over once you've missed this many

FPS = 60

# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

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


def lane_x(lane_index):
    """The x position of a lane, evenly spaced across the screen."""
    spacing = WIDTH / (len(LANES) + 1)
    return spacing * (lane_index + 1)


# ─────────────────────────────────────────────────────────────────────────────
#  Things in the game
# ─────────────────────────────────────────────────────────────────────────────


class Note:
    def __init__(self, lane_index):
        self.lane = lane_index
        self.x = lane_x(lane_index)
        self.y = -NOTE_RADIUS

    def update(self, dt):
        self.y += NOTE_SPEED * dt

    def distance_to_target(self):
        return abs(self.y - TARGET_Y)

    def draw(self, surface):
        color = LANES[self.lane]["color"]
        pygame.draw.circle(surface, color, (int(self.x), int(self.y)), NOTE_RADIUS)


class Popup:
    """A little floating score number, like "+87" or "MISS"."""

    def __init__(self, x, y, text, color):
        self.x = x
        self.y = y
        self.text = text
        self.color = color
        self.life = 0.6

    def update(self, dt):
        self.y -= 60 * dt
        self.life -= dt

    def draw(self, surface):
        alpha_size = 26
        draw_text(surface, self.text, (self.x, self.y), size=alpha_size,
                  color=self.color, align="center")


# ─────────────────────────────────────────────────────────────────────────────
#  The game
# ─────────────────────────────────────────────────────────────────────────────


class Game:
    def __init__(self):
        self.start_new_game()

    def start_new_game(self):
        self.notes = []
        self.popups = []
        self.score = 0
        self.misses = 0
        self.spawn_timer = 0.0
        self.over = False
        reset_score()
        submit_score(0)

    def add_score(self, delta):
        self.score = max(0, self.score + delta)
        submit_score(self.score)

    def register_miss(self, lane_index):
        self.add_score(-MISS_PENALTY)
        self.misses += 1
        x = lane_x(lane_index)
        self.popups.append(Popup(x, TARGET_Y - TARGET_RADIUS - 10, "MISS", (255, 90, 90)))
        if self.misses >= MAX_MISSES:
            self.over = True
            game_over(self.score)

    def try_hit(self, lane_index):
        # Find the closest not-yet-hit note in this lane.
        candidates = [n for n in self.notes if n.lane == lane_index]
        if not candidates:
            return
        closest = min(candidates, key=Note.distance_to_target)
        distance = closest.distance_to_target()
        if distance > HIT_WINDOW:
            return

        points = round(MAX_HIT_POINTS * (1 - distance / HIT_WINDOW))
        self.notes.remove(closest)
        self.add_score(points)
        color = LANES[lane_index]["color"]
        self.popups.append(Popup(closest.x, TARGET_Y - TARGET_RADIUS - 10, f"+{points}", color))

    def update(self, dt, pressed_keys):
        if self.over:
            for popup in self.popups:
                popup.update(dt)
            self.popups = [p for p in self.popups if p.life > 0]
            return

        for lane_index, lane in enumerate(LANES):
            if lane["key"] in pressed_keys:
                self.try_hit(lane_index)

        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            self.notes.append(Note(random.randrange(len(LANES))))
            self.spawn_timer = NOTE_SPAWN_INTERVAL

        for note in self.notes:
            note.update(dt)

        surviving = []
        for note in self.notes:
            if note.y - TARGET_Y > HIT_WINDOW:
                self.register_miss(note.lane)
            else:
                surviving.append(note)
        self.notes = surviving

        for popup in self.popups:
            popup.update(dt)
        self.popups = [p for p in self.popups if p.life > 0]

    def draw(self, surface):
        surface.fill(BACKGROUND)

        for lane_index, lane in enumerate(LANES):
            x = lane_x(lane_index)
            pygame.draw.circle(surface, lane["color"], (int(x), TARGET_Y), TARGET_RADIUS, 3)
            draw_text(surface, lane["label"], (x, TARGET_Y + TARGET_RADIUS + 8),
                      size=22, color=lane["color"], align="center")

        for note in self.notes:
            note.draw(surface)
        for popup in self.popups:
            popup.draw(surface)

        self.draw_hud(surface)

        if self.over:
            draw_text(surface, "GAME OVER", (WIDTH / 2, HEIGHT / 2 - 70), size=64, align="center")
            draw_text(surface, f"SCORE {self.score}", (WIDTH / 2, HEIGHT / 2 + 10),
                      size=34, align="center")
            draw_text(surface, "PRESS R TO PLAY AGAIN", (WIDTH / 2, HEIGHT / 2 + 60),
                      size=24, align="center")

    def draw_hud(self, surface):
        draw_text(surface, str(self.score), (28, 22), size=48)
        draw_text(surface, f"MISSES {self.misses}/{MAX_MISSES}", (WIDTH - 28, 26),
                  size=24, align="right")


async def main():
    pygame.init()
    pygame.display.set_caption(TITLE)
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()

    game = Game()
    running = True

    while running:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)   # cap dt so lag can't skip things

        pressed_this_frame = set()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                pressed_this_frame.add(event.key)
                if event.key == pygame.K_r and game.over:
                    game.start_new_game()
                # ESC is not handled here on purpose — in Islands World it means
                # "leave this island", and the world itself takes care of that.

        game.update(dt, pressed_this_frame)
        game.draw(screen)
        pygame.display.flip()

        # Required for the browser build — hands control back to the page each
        # frame. Do not remove this line.
        await asyncio.sleep(0)

    pygame.quit()


# pygbag needs the program to start with asyncio.run(main()) at the top level.
asyncio.run(main())
