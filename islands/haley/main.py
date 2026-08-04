"""ASTEROIDS — your island's game.

Fly the ship, shoot the unicorns, don't get hit. Big unicorns split into
smaller ones.

    ARROW KEYS    (or WASD)    move — the ship faces the way you're moving
    SPACE                      shoot
    R                          restart after game over

This is YOUR game now. The fastest way to make it yours is the CUSTOMIZE block
just below — change the colours, make the ship faster, give yourself 10 lives.
Then run it and see what happened. After that, ask Claude for bigger changes.

Two rules that keep your island working inside Islands World:
  1. keep `async def main()` and the `await asyncio.sleep(0)` at the end of the
     game loop — that's what lets the game run in a browser.
  2. keep calling `submit_score(...)` and `game_over(...)` — that's what puts
     your score on the world scoreboard.
"""

import asyncio
import math
import os
import random

import pygame

from islands_sdk import game_over, reset as reset_score, submit_score

# ─────────────────────────────────────────────────────────────────────────────
#  CUSTOMIZE ME — change these numbers and colours first. Nothing here can
#  break the game; the worst that happens is it gets silly.
# ─────────────────────────────────────────────────────────────────────────────

TITLE = "Asteroid Island"

WIDTH = 900                      # size of the game window
HEIGHT = 700

BACKGROUND = (0, 0, 0)           # colours are (RED, GREEN, BLUE), 0–255
LINE_COLOR = (255, 255, 255)     # everything is drawn as lines in this colour
LINE_WIDTH = 2
FONT_NAME = None                 # None = pygame's built-in font

MUSIC_FILE = "death-duel.mp3"        # background music, loops the whole game
MUSIC_VOLUME = 0.5                   # 0.0 (silent) to 1.0 (full volume)

SHIP_SIZE = 22                   # how big the ship is
SHIP_THRUST = 340                # how hard the engine pushes
SHIP_MAX_SPEED = 430             # top speed
SHIP_DRAG = 0.45                 # how fast you coast to a stop (0 = never)
SHIP_INVULN_TIME = 2.0           # seconds of blinking safety after respawning
FREEZE_COLOR = (60, 140, 255)    # colour the ship turns while frozen

BULLET_SPEED = 560
BULLET_LIFETIME = 0.85           # seconds before a bullet fizzles out
BULLET_COOLDOWN = 0.20           # seconds between shots
MAX_BULLETS = 5

STARTING_LIVES = 3
STARTING_UNICORNS = 4            # unicorns in wave 1; each wave adds one more

# Unicorns come in 3 sizes. size 3 = big, 2 = medium, 1 = small.
UNICORN_RADIUS = {3: 54, 2: 30, 1: 16}
UNICORN_SPEED = {3: 55, 2: 90, 1: 140}
UNICORN_POINTS = {3: 20, 2: 50, 1: 100}   # points for shooting one
UNICORN_SPLIT_COUNT = 2                   # how many pieces a unicorn breaks into

# Each edge of a unicorn is drawn in the next colour from this list, so every
# unicorn is rainbow-coloured all over. Add, remove, or reorder colours.
RAINBOW_COLORS = [
    (255, 0, 0),      # red
    (255, 140, 0),    # orange
    (255, 230, 0),    # yellow
    (0, 200, 0),      # green
    (0, 120, 255),    # blue
    (130, 0, 255),    # violet
    (255, 0, 200),    # pink
]

# The enemy asteroid: solid white, doesn't split, shoots chunks at you.
ENEMY_COUNT_MIN = 2
ENEMY_COUNT_MAX = 3               # how many spawn at the start of the game
ENEMY_RADIUS = SHIP_SIZE * 2      # twice your ship's size
ENEMY_SPEED = UNICORN_SPEED[3]    # drifts at the same speed as a big rock
ENEMY_POINTS = 150                # points for shooting one down
ENEMY_FIRE_INTERVAL = 3.0         # seconds between shots, per enemy
ENEMY_SHOT_SPEED = 380            # how fast a broken-off chunk flies at you
ENEMY_SHOT_LIFETIME = 2.5         # seconds before a chunk fizzles out
ENEMY_FREEZE_TIME = 1.0           # seconds you're frozen after a chunk hits you

FPS = 60

# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────


def wrap(x, y):
    """The screen has no edges — fly off one side, come back on the other."""
    return x % WIDTH, y % HEIGHT


def draw_shape(surface, points, color=None, width=None):
    """Draw a closed outline through `points`."""
    pygame.draw.lines(
        surface,
        color or LINE_COLOR,
        True,
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


class Ship:
    # The ship outline, drawn nose-first. Change these to reshape your ship.
    SHAPE = [(1.0, 0.0), (-0.7, 0.65), (-0.4, 0.0), (-0.7, -0.65)]
    FLAME = [(-0.45, 0.28), (-1.15, 0.0), (-0.45, -0.28)]

    def __init__(self):
        self.reset()

    def reset(self):
        self.x = WIDTH / 2
        self.y = HEIGHT / 2
        self.vx = 0.0
        self.vy = 0.0
        self.angle = -90.0          # pointing up
        self.thrusting = False
        self.invuln = SHIP_INVULN_TIME
        self.radius = SHIP_SIZE * 0.7
        self.frozen = 0.0

    def freeze(self, seconds):
        self.frozen = seconds
        self.vx = 0.0
        self.vy = 0.0

    def update(self, dt, keys):
        self.invuln = max(0.0, self.invuln - dt)
        if self.frozen > 0:
            # Held completely in place — no input, no drifting.
            self.frozen = max(0.0, self.frozen - dt)
            self.thrusting = False
            return

        dx = 0
        dy = 0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            dx -= 1
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            dx += 1
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            dy -= 1
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            dy += 1

        # Face and thrust toward whatever direction is held. Diagonals are
        # normalized so holding two keys isn't faster than holding one.
        self.thrusting = dx != 0 or dy != 0
        if self.thrusting:
            self.angle = math.degrees(math.atan2(dy, dx))
            length = math.hypot(dx, dy)
            ux, uy = dx / length, dy / length
            self.vx += ux * SHIP_THRUST * dt
            self.vy += uy * SHIP_THRUST * dt

        # Drag, then speed limit.
        damping = max(0.0, 1.0 - SHIP_DRAG * dt)
        self.vx *= damping
        self.vy *= damping
        speed = math.hypot(self.vx, self.vy)
        if speed > SHIP_MAX_SPEED:
            self.vx = self.vx / speed * SHIP_MAX_SPEED
            self.vy = self.vy / speed * SHIP_MAX_SPEED

        self.x, self.y = wrap(self.x + self.vx * dt, self.y + self.vy * dt)

    def points(self, shape, scale=SHIP_SIZE):
        radians = math.radians(self.angle)
        cos_a, sin_a = math.cos(radians), math.sin(radians)
        return [
            (
                self.x + (px * cos_a - py * sin_a) * scale,
                self.y + (px * sin_a + py * cos_a) * scale,
            )
            for px, py in shape
        ]

    def draw(self, surface, time_alive):
        # Blink while invulnerable so you can tell you're safe.
        if self.invuln > 0 and int(time_alive * 12) % 2 == 0:
            return
        color = FREEZE_COLOR if self.frozen > 0 else None
        draw_shape(surface, self.points(self.SHAPE), color=color)
        if self.thrusting and random.random() < 0.7:
            draw_shape(surface, self.points(self.FLAME), color=color)

    def nose(self):
        radians = math.radians(self.angle)
        return (
            self.x + math.cos(radians) * SHIP_SIZE,
            self.y + math.sin(radians) * SHIP_SIZE,
        )


class Bullet:
    def __init__(self, x, y, angle):
        radians = math.radians(angle)
        self.x = x
        self.y = y
        self.vx = math.cos(radians) * BULLET_SPEED
        self.vy = math.sin(radians) * BULLET_SPEED
        self.life = BULLET_LIFETIME
        self.radius = 2

    def update(self, dt):
        self.x, self.y = wrap(self.x + self.vx * dt, self.y + self.vy * dt)
        self.life -= dt

    def draw(self, surface):
        pygame.draw.rect(surface, LINE_COLOR, (self.x - 1.5, self.y - 1.5, 3, 3), 0)


class Unicorn:
    # A unicorn outline, horn first. Change these points to reshape it — each
    # edge gets its own colour from RAINBOW_COLORS above, so it stays rainbow
    # no matter how you redraw it.
    SHAPE = [
        (0.10, -1.00),   # horn tip
        (0.45, -0.70),   # head
        (0.70, -0.45),   # muzzle
        (0.55, -0.25),   # chin
        (0.45, 0.60),    # front leg
        (0.15, 0.20),    # belly
        (-0.35, 0.60),   # back leg
        (-0.55, 0.10),   # rear
        (-0.90, -0.10),  # tail
        (-0.35, -0.55),  # back
        (-0.05, -0.75),  # mane
    ]

    def __init__(self, x, y, size):
        self.x = x
        self.y = y
        self.size = size
        self.radius = UNICORN_RADIUS[size]

        angle = random.uniform(0, math.tau)
        speed = UNICORN_SPEED[size] * random.uniform(0.7, 1.3)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.spin = random.uniform(-60, 60)
        self.angle = random.uniform(0, 360)

    def update(self, dt):
        self.x, self.y = wrap(self.x + self.vx * dt, self.y + self.vy * dt)
        self.angle += self.spin * dt

    def draw(self, surface):
        radians = math.radians(self.angle)
        cos_a, sin_a = math.cos(radians), math.sin(radians)
        points = [
            (
                self.x + (px * cos_a - py * sin_a) * self.radius,
                self.y + (px * sin_a + py * cos_a) * self.radius,
            )
            for px, py in self.SHAPE
        ]
        # Draw each edge in the next rainbow colour, instead of one solid
        # colour, so every unicorn is multicoloured all over.
        for i, start in enumerate(points):
            end = points[(i + 1) % len(points)]
            color = RAINBOW_COLORS[i % len(RAINBOW_COLORS)]
            pygame.draw.line(surface, color, start, end, LINE_WIDTH)

    def split(self):
        """Break into smaller unicorns. Smallest ones just vanish."""
        if self.size <= 1:
            return []
        return [Unicorn(self.x, self.y, self.size - 1) for _ in range(UNICORN_SPLIT_COUNT)]


class EnemyAsteroid:
    """A solid, filled-in asteroid that shoots chunks of itself at you."""

    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.radius = ENEMY_RADIUS

        angle = random.uniform(0, math.tau)
        speed = ENEMY_SPEED * random.uniform(0.7, 1.3)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.spin = random.uniform(-40, 40)
        self.angle = random.uniform(0, 360)
        self.fire_timer = random.uniform(0.5, ENEMY_FIRE_INTERVAL)   # stagger shots

        # A lumpy circle, same idea as a rock — but this one gets filled in.
        corners = random.randint(9, 12)
        self.shape = []
        for i in range(corners):
            theta = math.tau * i / corners
            jitter = random.uniform(0.78, 1.1)
            if random.random() < 0.25:
                jitter = random.uniform(0.42, 0.58)
            self.shape.append((math.cos(theta) * jitter, math.sin(theta) * jitter))

    def update(self, dt):
        self.x, self.y = wrap(self.x + self.vx * dt, self.y + self.vy * dt)
        self.angle += self.spin * dt
        self.fire_timer -= dt

    def points(self):
        radians = math.radians(self.angle)
        cos_a, sin_a = math.cos(radians), math.sin(radians)
        return [
            (
                self.x + (px * cos_a - py * sin_a) * self.radius,
                self.y + (px * sin_a + py * cos_a) * self.radius,
            )
            for px, py in self.shape
        ]

    def draw(self, surface):
        pygame.draw.polygon(surface, LINE_COLOR, self.points())

    def ready_to_fire(self):
        return self.fire_timer <= 0

    def fire_at(self, target_x, target_y):
        self.fire_timer = ENEMY_FIRE_INTERVAL
        return EnemyShot(self.x, self.y, target_x, target_y)


class EnemyShot:
    """A chunk that breaks off an enemy asteroid and flies at the player."""

    SHAPE = [(0.9, 0.1), (0.3, 0.9), (-0.7, 0.6), (-0.9, -0.4), (0.1, -0.9)]

    def __init__(self, x, y, target_x, target_y):
        self.x = x
        self.y = y
        angle = math.atan2(target_y - y, target_x - x)
        self.vx = math.cos(angle) * ENEMY_SHOT_SPEED
        self.vy = math.sin(angle) * ENEMY_SHOT_SPEED
        self.life = ENEMY_SHOT_LIFETIME
        self.radius = 6
        self.spin = random.uniform(-200, 200)
        self.angle = random.uniform(0, 360)

    def update(self, dt):
        self.x, self.y = wrap(self.x + self.vx * dt, self.y + self.vy * dt)
        self.angle += self.spin * dt
        self.life -= dt

    def draw(self, surface):
        radians = math.radians(self.angle)
        cos_a, sin_a = math.cos(radians), math.sin(radians)
        points = [
            (
                self.x + (px * cos_a - py * sin_a) * self.radius,
                self.y + (px * sin_a + py * cos_a) * self.radius,
            )
            for px, py in self.SHAPE
        ]
        pygame.draw.polygon(surface, LINE_COLOR, points)


class Debris:
    """A little burst of lines when something is destroyed."""

    def __init__(self, x, y, count=8):
        self.pieces = []
        for _ in range(count):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(40, 170)
            self.pieces.append(
                [x, y, math.cos(angle) * speed, math.sin(angle) * speed]
            )
        self.life = 0.6

    def update(self, dt):
        for piece in self.pieces:
            piece[0] += piece[2] * dt
            piece[1] += piece[3] * dt
        self.life -= dt

    def draw(self, surface):
        for x, y, vx, vy in self.pieces:
            scale = 0.03
            pygame.draw.line(
                surface, LINE_COLOR, (x, y), (x - vx * scale, y - vy * scale), 1
            )


# ─────────────────────────────────────────────────────────────────────────────
#  The game
# ─────────────────────────────────────────────────────────────────────────────


def collides(a, b):
    return math.hypot(a.x - b.x, a.y - b.y) < a.radius + b.radius


class Game:
    def __init__(self):
        self.start_new_game()

    def start_new_game(self):
        self.ship = Ship()
        self.bullets = []
        self.unicorns = []
        self.enemies = []
        self.enemy_shots = []
        self.debris = []
        self.score = 0
        self.lives = STARTING_LIVES
        self.wave = 0
        self.time_alive = 0.0
        self.fire_timer = 0.0
        self.over = False
        reset_score()
        submit_score(0)
        self.next_wave()
        self.spawn_enemies()

    def spawn_enemies(self):
        count = random.randint(ENEMY_COUNT_MIN, ENEMY_COUNT_MAX)
        for _ in range(count):
            # Spawn away from the middle so enemies don't appear on top of the ship.
            while True:
                x = random.uniform(0, WIDTH)
                y = random.uniform(0, HEIGHT)
                if math.hypot(x - WIDTH / 2, y - HEIGHT / 2) > 180:
                    break
            self.enemies.append(EnemyAsteroid(x, y))

    def next_wave(self):
        self.wave += 1
        count = STARTING_UNICORNS + self.wave - 1
        for _ in range(count):
            # Spawn away from the middle so unicorns don't appear on top of the ship.
            while True:
                x = random.uniform(0, WIDTH)
                y = random.uniform(0, HEIGHT)
                if math.hypot(x - WIDTH / 2, y - HEIGHT / 2) > 180:
                    break
            self.unicorns.append(Unicorn(x, y, 3))

    def shoot(self):
        if self.fire_timer > 0 or len(self.bullets) >= MAX_BULLETS:
            return
        nose_x, nose_y = self.ship.nose()
        self.bullets.append(Bullet(nose_x, nose_y, self.ship.angle))
        self.fire_timer = BULLET_COOLDOWN

    def add_score(self, points):
        self.score += points
        submit_score(self.score)

    def lose_a_life(self):
        self.debris.append(Debris(self.ship.x, self.ship.y, 12))
        self.lives -= 1
        if self.lives <= 0:
            self.over = True
            game_over(self.score)
        else:
            self.ship.reset()

    def update(self, dt, keys):
        self.time_alive += dt
        if self.over:
            for burst in self.debris:
                burst.update(dt)
            self.debris = [d for d in self.debris if d.life > 0]
            return

        self.fire_timer = max(0.0, self.fire_timer - dt)
        self.ship.update(dt, keys)
        if keys[pygame.K_SPACE]:
            self.shoot()

        for bullet in self.bullets:
            bullet.update(dt)
        self.bullets = [b for b in self.bullets if b.life > 0]

        for unicorn in self.unicorns:
            unicorn.update(dt)

        for enemy in self.enemies:
            enemy.update(dt)
            if enemy.ready_to_fire():
                self.enemy_shots.append(enemy.fire_at(self.ship.x, self.ship.y))

        for shot in self.enemy_shots:
            shot.update(dt)
        self.enemy_shots = [s for s in self.enemy_shots if s.life > 0]

        for burst in self.debris:
            burst.update(dt)
        self.debris = [d for d in self.debris if d.life > 0]

        # Bullets vs unicorns.
        surviving_unicorns = []
        for unicorn in self.unicorns:
            hit_by = None
            for bullet in self.bullets:
                if collides(unicorn, bullet):
                    hit_by = bullet
                    break
            if hit_by is None:
                surviving_unicorns.append(unicorn)
                continue
            self.bullets.remove(hit_by)
            self.add_score(UNICORN_POINTS[unicorn.size])
            self.debris.append(Debris(unicorn.x, unicorn.y))
            surviving_unicorns.extend(unicorn.split())
        self.unicorns = surviving_unicorns

        # Bullets vs enemy asteroids.
        surviving_enemies = []
        for enemy in self.enemies:
            hit_by = None
            for bullet in self.bullets:
                if collides(enemy, bullet):
                    hit_by = bullet
                    break
            if hit_by is None:
                surviving_enemies.append(enemy)
                continue
            self.bullets.remove(hit_by)
            self.add_score(ENEMY_POINTS)
            self.debris.append(Debris(enemy.x, enemy.y))
        self.enemies = surviving_enemies

        # Unicorns and enemy asteroids vs ship.
        if self.ship.invuln <= 0:
            for unicorn in self.unicorns:
                if collides(unicorn, self.ship):
                    self.lose_a_life()
                    break
            else:
                for enemy in self.enemies:
                    if collides(enemy, self.ship):
                        self.lose_a_life()
                        break

        # Enemy chunks vs ship — freezes you in place, no life lost.
        if self.ship.invuln <= 0:
            surviving_shots = []
            for shot in self.enemy_shots:
                if collides(shot, self.ship):
                    self.ship.freeze(ENEMY_FREEZE_TIME)
                else:
                    surviving_shots.append(shot)
            self.enemy_shots = surviving_shots

        if not self.unicorns:
            self.next_wave()

    def draw(self, surface):
        surface.fill(BACKGROUND)

        for unicorn in self.unicorns:
            unicorn.draw(surface)
        for enemy in self.enemies:
            enemy.draw(surface)
        for shot in self.enemy_shots:
            shot.draw(surface)
        for bullet in self.bullets:
            bullet.draw(surface)
        for burst in self.debris:
            burst.draw(surface)
        if not self.over:
            self.ship.draw(surface, self.time_alive)

        self.draw_hud(surface)

        if self.over:
            draw_text(surface, "GAME OVER", (WIDTH / 2, HEIGHT / 2 - 70), size=64, align="center")
            draw_text(surface, f"SCORE {self.score}", (WIDTH / 2, HEIGHT / 2 + 10),
                      size=34, align="center")
            draw_text(surface, "PRESS R TO PLAY AGAIN", (WIDTH / 2, HEIGHT / 2 + 60),
                      size=24, align="center")

    def draw_hud(self, surface):
        draw_text(surface, str(self.score), (28, 22), size=48)

        # Lives, drawn as little ships.
        for i in range(self.lives):
            x = 34 + i * 30
            y = 90
            points = [
                (x + (px * 0.0 - py * -1.0) * 11, y + (px * -1.0 + py * 0.0) * 11)
                for px, py in Ship.SHAPE
            ]
            draw_shape(surface, points, width=2)

        draw_text(surface, f"WAVE {self.wave}", (WIDTH - 28, 26), size=24, align="right")


async def main():
    pygame.init()
    pygame.display.set_caption(TITLE)
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()

    music_path = os.path.join(os.path.dirname(__file__), MUSIC_FILE)
    pygame.mixer.music.load(music_path)
    pygame.mixer.music.set_volume(MUSIC_VOLUME)
    pygame.mixer.music.play(loops=-1)

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
