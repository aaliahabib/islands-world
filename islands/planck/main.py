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
GUARD_HAT_COLOR = (30, 40, 110)  # colour of the guard's security hat
GUARD_WALK_SPEED = 9.0           # how fast his legs swing while walking
GUARD_ATTACK_REACH = GUARD_SIZE * 1.4     # how far the weapon hits
GUARD_ATTACK_COOLDOWN = 0.3               # seconds between attacks

ANIMAL_ORDER = ["lion", "gorilla", "crocodile", "elephant", "bull"]   # fight order
ANIMAL_ICON_COLOR = (255, 255, 255)
ANIMAL_ICON_SIZE = 22            # radius of each icon in the top-right roster

LION_COLOR = (200, 140, 40)
LION_SIZE = 40                   # how big the lion is
LION_HEALTH = 4                  # how many hits it takes to beat it
LION_SPEED = 320                 # how fast it chases the guard — faster than him
LION_STOP_RANGE = GUARD_SIZE * 1.9        # how close it gets before it stops to bite
LION_WINDUP_TIME = 1.0           # seconds it pauses before biting
LION_RECOVER_TIME = 0.5          # seconds it waits after a bite before chasing again
LION_HIT_POINTS = 25             # score for landing one hit on it

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


def draw_animal_icon(surface, name, cx, cy, r, color=None):
    """A simple line-icon for one of the five animals, centred at (cx, cy)."""
    color = color or ANIMAL_ICON_COLOR

    if name == "lion":
        # A jagged ring of fur around a round face — reads as a mane.
        spikes = 12
        points = []
        for i in range(spikes * 2):
            theta = math.tau * i / (spikes * 2)
            radius = r if i % 2 == 0 else r * 0.68
            points.append((cx + math.cos(theta) * radius, cy + math.sin(theta) * radius))
        pygame.draw.polygon(surface, color, points, 2)
        pygame.draw.circle(surface, color, (int(cx), int(cy)), int(r * 0.42), 2)
        pygame.draw.circle(surface, color, (int(cx - r * 0.15), int(cy - r * 0.08)), 2, 0)
        pygame.draw.circle(surface, color, (int(cx + r * 0.15), int(cy - r * 0.08)), 2, 0)

    elif name == "gorilla":
        pygame.draw.circle(surface, color, (int(cx), int(cy - r * 0.55)), int(r * 0.4), 2)
        pygame.draw.polygon(surface, color, [
            (cx - r * 0.45, cy - r * 0.2), (cx + r * 0.45, cy - r * 0.2),
            (cx + r * 0.65, cy + r * 0.55), (cx - r * 0.65, cy + r * 0.55),
        ], 2)
        pygame.draw.line(surface, color, (cx - r * 0.5, cy - r * 0.1), (cx - r * 0.85, cy + r * 0.7), 3)
        pygame.draw.line(surface, color, (cx + r * 0.5, cy - r * 0.1), (cx + r * 0.85, cy + r * 0.7), 3)

    elif name == "crocodile":
        pygame.draw.ellipse(surface, color, (cx - r, cy - r * 0.28, r * 1.5, r * 0.56), 2)
        pygame.draw.polygon(surface, color, [
            (cx + r * 0.45, cy - r * 0.16), (cx + r * 1.1, cy), (cx + r * 0.45, cy + r * 0.16),
        ], 2)
        for i in range(3):
            x = cx + r * 0.55 + i * r * 0.18
            pygame.draw.line(surface, color, (x, cy - r * 0.05), (x + r * 0.09, cy + r * 0.1), 2)
        pygame.draw.circle(surface, color, (int(cx - r * 0.25), int(cy - r * 0.28)), 2, 0)

    elif name == "elephant":
        pygame.draw.circle(surface, color, (int(cx - r * 0.05), int(cy - r * 0.1)), int(r * 0.42), 2)
        pygame.draw.circle(surface, color, (int(cx - r * 0.55), int(cy - r * 0.15)), int(r * 0.4), 2)
        pygame.draw.lines(surface, color, False, [
            (cx + r * 0.28, cy + r * 0.15), (cx + r * 0.38, cy + r * 0.5),
            (cx + r * 0.15, cy + r * 0.7), (cx - r * 0.05, cy + r * 0.55),
        ], 3)

    elif name == "bull":
        pygame.draw.circle(surface, color, (int(cx), int(cy + r * 0.1)), int(r * 0.45), 2)
        pygame.draw.arc(surface, color, (cx - r * 1.1, cy - r * 0.9, r * 1.0, r * 1.0), 0.3, 2.6, 3)
        pygame.draw.arc(surface, color, (cx + r * 0.1, cy - r * 0.9, r * 1.0, r * 1.0), 0.5, 2.8, 3)
        pygame.draw.circle(surface, color, (int(cx - r * 0.18), int(cy)), 2, 0)
        pygame.draw.circle(surface, color, (int(cx + r * 0.18), int(cy)), 2, 0)


# ─────────────────────────────────────────────────────────────────────────────
#  Things in the game
# ─────────────────────────────────────────────────────────────────────────────


class Guard:
    # Proportions of the stickman, as a fraction of GUARD_SIZE. self.y is
    # where his feet touch the ground.
    HEAD_RADIUS = 0.26
    LEG_LENGTH = 0.9
    TORSO_LENGTH = 0.7

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
        self.attack_cooldown = 0.0
        self.r_was_down = False
        self.e_was_down = False
        self.did_attack = False
        self.walk_phase = 0.0
        self.walking = False

    @property
    def dodging(self):
        return self.dodge_timer > 0

    def update(self, dt, keys):
        self.dodge_cooldown = max(0.0, self.dodge_cooldown - dt)
        self.attack_timer = max(0.0, self.attack_timer - dt)
        self.attack_cooldown = max(0.0, self.attack_cooldown - dt)

        self.did_attack = False
        e_down = keys[pygame.K_e]
        if e_down and not self.e_was_down and self.attack_cooldown <= 0:
            self.attack_timer = 0.18
            self.attack_cooldown = GUARD_ATTACK_COOLDOWN
            self.did_attack = True
        self.e_was_down = e_down

        r_down = keys[pygame.K_r]
        if r_down and not self.r_was_down and self.dodge_cooldown <= 0:
            self.dodge_timer = GUARD_DODGE_TIME
            self.dodge_cooldown = GUARD_DODGE_COOLDOWN
            self.dodge_vx = GUARD_DODGE_SPEED * self.facing
        self.r_was_down = r_down

        if self.dodging:
            self.dodge_timer = max(0.0, self.dodge_timer - dt)
            self.x += self.dodge_vx * dt
            self.walking = False
        else:
            move = 0
            if keys[pygame.K_LEFT] or keys[pygame.K_a]:
                move -= 1
            if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
                move += 1
            if move:
                self.facing = move
            self.x += move * GUARD_SPEED * dt

            self.walking = move != 0 and self.on_ground
            if self.walking:
                self.walk_phase += dt * GUARD_WALK_SPEED

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

    def draw(self, surface):
        color = (255, 255, 120) if self.dodging else LINE_COLOR
        flip = self.facing

        feet_y = self.y
        hip_y = feet_y - GUARD_SIZE * self.LEG_LENGTH
        shoulder_y = hip_y - GUARD_SIZE * self.TORSO_LENGTH
        head_r = GUARD_SIZE * self.HEAD_RADIUS
        head_cx, head_cy = self.x, shoulder_y - head_r

        # Legs swing opposite each other while walking; standing still, they
        # rest in a neutral V.
        swing = math.sin(self.walk_phase) * GUARD_SIZE * 0.34 if self.walking else 0.0

        # Legs, torso and arms — all lines through the same body points.
        pygame.draw.line(surface, color, (self.x, hip_y), (self.x - GUARD_SIZE * 0.28 + swing, feet_y), 4)
        pygame.draw.line(surface, color, (self.x, hip_y), (self.x + GUARD_SIZE * 0.28 - swing, feet_y), 4)
        pygame.draw.line(surface, color, (self.x, hip_y), (self.x, shoulder_y), 4)
        pygame.draw.line(surface, color, (self.x, shoulder_y),
                          (self.x - GUARD_SIZE * 0.3 * flip, shoulder_y + GUARD_SIZE * 0.3), 4)

        # Front arm swings out on attack, otherwise rests at his side.
        arm_x = self.x + GUARD_SIZE * (0.75 if self.attack_timer > 0 else 0.3) * flip
        arm_y = shoulder_y + (GUARD_SIZE * 0.05 if self.attack_timer > 0 else GUARD_SIZE * 0.3)
        pygame.draw.line(surface, color, (self.x, shoulder_y), (arm_x, arm_y), 4)

        pygame.draw.circle(surface, color, (int(head_cx), int(head_cy)), int(head_r), 3)

        # The security hat: a brim across the forehead and a flat top.
        brim_y = head_cy - head_r * 0.15
        pygame.draw.line(surface, GUARD_HAT_COLOR,
                          (head_cx - head_r * 1.3, brim_y), (head_cx + head_r * 1.3, brim_y), 5)
        pygame.draw.rect(surface, GUARD_HAT_COLOR,
                          (head_cx - head_r * 0.85, head_cy - head_r * 1.35, head_r * 1.7, head_r * 0.8))

        if self.attack_timer > 0:
            tip_x = self.x + self.facing * GUARD_ATTACK_REACH
            pygame.draw.line(
                surface, (255, 210, 90),
                (arm_x, arm_y), (tip_x, arm_y), 4,
            )


class Lion:
    """Chases the guard, stops when it gets close, pauses, then bites."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.x = LION_SIZE * 1.5   # starts over at the edge so the chase shows
        self.y = GROUND_Y
        self.health = LION_HEALTH
        self.state = "approach"    # approach -> windup -> recover -> approach
        self.timer = 0.0
        self.facing = 1

    def update(self, dt, guard):
        """Returns True on the exact frame it bites."""
        distance = abs(guard.x - self.x)
        direction = 1 if guard.x >= self.x else -1

        if self.state == "approach":
            self.facing = direction
            if distance <= LION_STOP_RANGE:
                self.state = "windup"
                self.timer = LION_WINDUP_TIME
            else:
                self.x += direction * LION_SPEED * dt
            return False

        if self.state == "windup":
            self.timer -= dt
            if self.timer <= 0:
                self.state = "recover"
                self.timer = LION_RECOVER_TIME
                return True
            return False

        # recover
        self.timer -= dt
        if self.timer <= 0:
            self.state = "approach"
        return False

    def draw(self, surface):
        body_y = self.y - LION_SIZE * 0.5
        body_rect = (self.x - LION_SIZE * 0.9, body_y - LION_SIZE * 0.4, LION_SIZE * 1.8, LION_SIZE * 0.8)
        pygame.draw.ellipse(surface, LION_COLOR, body_rect, 3)

        for dx in (-0.6, -0.2, 0.2, 0.6):
            leg_x = self.x + dx * LION_SIZE
            pygame.draw.line(surface, LION_COLOR, (leg_x, body_y + LION_SIZE * 0.3), (leg_x, self.y), 4)

        tail_x = self.x - self.facing * LION_SIZE * 1.2
        pygame.draw.line(surface, LION_COLOR,
                          (self.x - self.facing * LION_SIZE * 0.8, body_y), (tail_x, body_y - LION_SIZE * 0.3), 3)

        face_x = self.x + self.facing * LION_SIZE * 0.65
        face_y = body_y - LION_SIZE * 0.05
        draw_animal_icon(surface, "lion", face_x, face_y, LION_SIZE * 0.75, color=LION_COLOR)

        if self.state == "windup":
            # The mouth opens wide — the warning that a bite is coming.
            mouth_x = face_x + self.facing * LION_SIZE * 0.35
            pygame.draw.polygon(surface, (200, 30, 30), [
                (mouth_x, face_y - LION_SIZE * 0.14),
                (mouth_x + self.facing * LION_SIZE * 0.32, face_y),
                (mouth_x, face_y + LION_SIZE * 0.14),
            ])

        bar_w, bar_h = LION_SIZE * 1.6, 8
        bar_x = self.x - bar_w / 2
        bar_y = body_y - LION_SIZE * 0.75
        pygame.draw.rect(surface, (60, 60, 60), (bar_x, bar_y, bar_w, bar_h))
        fraction = max(0.0, self.health / LION_HEALTH)
        pygame.draw.rect(surface, (210, 40, 40), (bar_x, bar_y, bar_w * fraction, bar_h))
        pygame.draw.rect(surface, LINE_COLOR, (bar_x, bar_y, bar_w, bar_h), 2)


def draw_cage_background(surface):
    """The empty enclosure behind the guard — pure scenery, nothing to hit."""
    wall_top = GROUND_Y - 260
    wall_left = (WIDTH - CAGE_WIDTH) / 2
    wall_right = wall_left + CAGE_WIDTH

    pygame.draw.rect(surface, CAGE_WALL_COLOR, (wall_left, wall_top, CAGE_WIDTH, GROUND_Y - wall_top))
    for x in range(int(wall_left) + 20, int(wall_right), 40):
        pygame.draw.line(surface, CAGE_BAR_COLOR, (x, wall_top), (x, GROUND_Y), 4)

    # A frame around the bars — top rail and thicker corner posts — so it
    # reads as a built structure instead of a flat rectangle.
    pygame.draw.line(surface, CAGE_BAR_COLOR, (wall_left, wall_top), (wall_right, wall_top), 10)
    pygame.draw.line(surface, CAGE_BAR_COLOR, (wall_left, wall_top), (wall_left, GROUND_Y), 10)
    pygame.draw.line(surface, CAGE_BAR_COLOR, (wall_right, wall_top), (wall_right, GROUND_Y), 10)

    # The sign sits straddling the top rail, like it's mounted on the cage.
    sign_width, sign_height = 160, 48
    sign_rect = (WIDTH / 2 - sign_width / 2, wall_top - sign_height / 2, sign_width, sign_height)
    pygame.draw.rect(surface, CAGE_SIGN_COLOR, sign_rect)
    pygame.draw.rect(surface, CAGE_BAR_COLOR, sign_rect, 3)
    draw_text(surface, "ZOO", (WIDTH / 2, sign_rect[1] + 10), size=28, color=LINE_COLOR, align="center")


# ─────────────────────────────────────────────────────────────────────────────
#  The game
# ─────────────────────────────────────────────────────────────────────────────


class Game:
    def __init__(self):
        self.start_new_game()

    def start_new_game(self):
        self.guard = Guard()
        self.lion = Lion()
        self.score = 0
        self.over = False
        self.remaining_animals = list(ANIMAL_ORDER)
        reset_score()
        submit_score(0)

    def add_score(self, points):
        self.score += points
        submit_score(self.score)

    def defeat_animal(self, name):
        """Call this once an animal is beaten — its icon drops off the roster."""
        if name in self.remaining_animals:
            self.remaining_animals.remove(name)

    def die(self):
        self.over = True
        game_over(self.score)

    def update(self, dt, keys):
        if self.over:
            return
        self.guard.update(dt, keys)

        if self.lion:
            bit_now = self.lion.update(dt, self.guard)
            if bit_now and not (self.guard.dodging or not self.guard.on_ground):
                self.die()
                return

            if self.guard.did_attack:
                dx = self.lion.x - self.guard.x
                in_front = dx * self.guard.facing >= 0
                if in_front and abs(dx) <= GUARD_ATTACK_REACH:
                    self.lion.health -= 1
                    self.add_score(LION_HIT_POINTS)
                    if self.lion.health <= 0:
                        self.defeat_animal("lion")
                        self.lion = None

    def draw(self, surface):
        surface.fill(SKY_COLOR)
        draw_cage_background(surface)
        pygame.draw.rect(surface, GROUND_COLOR, (0, GROUND_Y, WIDTH, HEIGHT - GROUND_Y))

        if self.lion:
            self.lion.draw(surface)
        self.guard.draw(surface)
        self.draw_hud(surface)

        if self.over:
            draw_text(surface, "GAME OVER", (WIDTH / 2, HEIGHT / 2 - 40), size=64, align="center")
            draw_text(surface, "PRESS R TO PLAY AGAIN", (WIDTH / 2, HEIGHT / 2 + 30),
                      size=24, align="center")

    def draw_hud(self, surface):
        draw_text(surface, str(self.score), (28, 22), size=48)

        # One icon per animal still left to fight, top right, in order.
        for i, name in enumerate(self.remaining_animals):
            cx = WIDTH - 30 - i * (ANIMAL_ICON_SIZE * 2 + 14)
            cy = 34
            draw_animal_icon(surface, name, cx, cy, ANIMAL_ICON_SIZE)


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
