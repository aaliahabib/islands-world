"""RHYTHM ISLAND — your island's game.

Four lane circles sit at the bottom. Notes fall down each lane — hit D, F, J or
K right as a note reaches its circle. The closer to dead-center you hit it, the
more points you get. After 10 seconds, some notes grow a tail — hold the key
down until the tail finishes for a big bonus. Miss 20 notes and it's game over.

    D / F / J / K   hit the matching lane (hold for tailed notes)
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

CHORD_FREE_TIME = 60.0           # seconds before two notes are allowed to need hitting at once

HOLD_NOTES_START_AT = 10.0       # seconds into the game before hold notes appear
HOLD_NOTE_CHANCE = 0.2           # chance a note spawns as a hold note, once unlocked
HOLD_MIN_DURATION = 0.5          # shortest hold, in seconds
HOLD_MAX_DURATION = 5.0          # longest hold, in seconds
HOLD_PRESS_SHARE = 0.5           # fraction of the normal hit points awarded on press
HOLD_COMPLETE_BONUS = 1.2        # full-hold total, as a multiple of a normal hit

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


def format_time(seconds):
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes}:{secs:02d}"


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


class HoldNote(Note):
    def __init__(self, lane_index, duration):
        super().__init__(lane_index)
        self.duration = duration
        self.started = False     # key pressed while in the hit window yet?
        self.finished = False    # released early or completed
        self.held_elapsed = 0.0
        self.press_points = 0    # timing points earned the moment it was pressed

    def draw(self, surface):
        color = LANES[self.lane]["color"]
        remaining = self.duration - self.held_elapsed
        tail_length = remaining * NOTE_SPEED
        pygame.draw.line(
            surface, color, (self.x, self.y), (self.x, self.y - tail_length), NOTE_RADIUS
        )
        super().draw(surface)


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
        self.time_alive = 0.0
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
        candidates = [n for n in self.notes if n.lane == lane_index and not getattr(n, "started", False)]
        if not candidates:
            return
        closest = min(candidates, key=Note.distance_to_target)
        distance = closest.distance_to_target()
        if distance > HIT_WINDOW:
            return

        timing_points = round(MAX_HIT_POINTS * (1 - distance / HIT_WINDOW))
        color = LANES[lane_index]["color"]

        if isinstance(closest, HoldNote):
            closest.started = True
            closest.y = TARGET_Y
            closest.press_points = timing_points
            press_award = round(timing_points * HOLD_PRESS_SHARE)
            self.add_score(press_award)
            self.popups.append(Popup(closest.x, TARGET_Y - TARGET_RADIUS - 10, f"+{press_award}", color))
        else:
            self.notes.remove(closest)
            self.add_score(timing_points)
            self.popups.append(Popup(closest.x, TARGET_Y - TARGET_RADIUS - 10, f"+{timing_points}", color))

    def lane_blocked(self, lane_index, spawn_y):
        """True if a new note at spawn_y would land inside a hold note's tail."""
        for note in self.notes:
            if note.lane != lane_index or not isinstance(note, HoldNote) or note.finished:
                continue
            remaining = note.duration - note.held_elapsed
            tail_top = note.y - remaining * NOTE_SPEED - NOTE_RADIUS
            tail_bottom = note.y + NOTE_RADIUS
            if tail_top <= spawn_y <= tail_bottom:
                return True
        return False

    def hit_window_interval(self, note):
        """When (relative to right now, in seconds) a note needs the player's
        attention — the span during which it can be pressed, or a hold that's
        already started and still needs holding."""
        if isinstance(note, HoldNote) and note.started:
            return 0.0, note.duration - note.held_elapsed
        entry_time = (TARGET_Y - HIT_WINDOW - note.y) / NOTE_SPEED
        exit_time = (TARGET_Y + HIT_WINDOW - note.y) / NOTE_SPEED
        return entry_time, exit_time

    def update_holds(self, dt, held_down):
        surviving = []
        for note in self.notes:
            if isinstance(note, HoldNote) and note.started and not note.finished:
                if not held_down[LANES[note.lane]["key"]]:
                    note.finished = True
                    continue
                note.held_elapsed += dt
                if note.held_elapsed >= note.duration:
                    full_value = round(note.press_points * HOLD_COMPLETE_BONUS)
                    press_award = round(note.press_points * HOLD_PRESS_SHARE)
                    bonus = full_value - press_award
                    color = LANES[note.lane]["color"]
                    self.add_score(bonus)
                    self.popups.append(Popup(note.x, TARGET_Y - TARGET_RADIUS - 34, f"+{bonus} HELD!", color))
                    note.finished = True
                    continue
            surviving.append(note)
        self.notes = surviving

    def update(self, dt, pressed_keys, held_down):
        if self.over:
            for popup in self.popups:
                popup.update(dt)
            self.popups = [p for p in self.popups if p.life > 0]
            return

        self.time_alive += dt

        for lane_index, lane in enumerate(LANES):
            if lane["key"] in pressed_keys:
                self.try_hit(lane_index)

        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            spawn_y = -NOTE_RADIUS
            new_start = (TARGET_Y - HIT_WINDOW - spawn_y) / NOTE_SPEED
            new_end = (TARGET_Y + HIT_WINDOW - spawn_y) / NOTE_SPEED

            chords_locked = self.time_alive < CHORD_FREE_TIME
            would_overlap = chords_locked and any(
                new_start <= end and start <= new_end
                for start, end in (self.hit_window_interval(n) for n in self.notes)
            )

            if not would_overlap:
                lane_order = list(range(len(LANES)))
                random.shuffle(lane_order)
                lane_index = next((l for l in lane_order if not self.lane_blocked(l, spawn_y)), None)

                if lane_index is not None:
                    if self.time_alive >= HOLD_NOTES_START_AT and random.random() < HOLD_NOTE_CHANCE:
                        duration = random.uniform(HOLD_MIN_DURATION, HOLD_MAX_DURATION)
                        self.notes.append(HoldNote(lane_index, duration))
                    else:
                        self.notes.append(Note(lane_index))
            self.spawn_timer = NOTE_SPAWN_INTERVAL

        for note in self.notes:
            if not (isinstance(note, HoldNote) and note.started):
                note.update(dt)

        self.update_holds(dt, held_down)

        surviving = []
        for note in self.notes:
            if isinstance(note, HoldNote) and note.started:
                surviving.append(note)
                continue
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
        draw_text(surface, format_time(self.time_alive), (28, 22), size=32)
        draw_text(surface, str(self.score), (28, 62), size=48)
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

        held_down = pygame.key.get_pressed()
        game.update(dt, pressed_this_frame, held_down)
        game.draw(screen)
        pygame.display.flip()

        # Required for the browser build — hands control back to the page each
        # frame. Do not remove this line.
        await asyncio.sleep(0)

    pygame.quit()


# pygbag needs the program to start with asyncio.run(main()) at the top level.
asyncio.run(main())
