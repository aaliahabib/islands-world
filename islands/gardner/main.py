"""ASTEROIDS — your island's game.

Fly the ship, shoot the rocks, don't get hit. Big rocks split into smaller ones.

    LEFT / RIGHT  (or A / D)   turn
    UP            (or W)       thrust
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

SHIP_COLOR = (255, 230, 0)       # colour of your ship
SHIP_SIZE = 22                   # how big the ship is
SHIP_TURN_SPEED = 220            # degrees per second
SHIP_THRUST = 340                # how hard the engine pushes
SHIP_MAX_SPEED = 430             # top speed
SHIP_DRAG = 0.45                 # how fast you coast to a stop (0 = never)
SHIP_INVULN_TIME = 2.0           # seconds of blinking safety after respawning

BULLET_SPEED = 560
BULLET_LIFETIME = 0.85           # seconds before a bullet fizzles out
BULLET_COOLDOWN = 0.20           # seconds between shots
MAX_BULLETS = 5

STARTING_LIVES = 4
STARTING_ROCKS = 4               # rocks in wave 1; each wave adds one more

# Rocks come in 3 sizes. size 3 = big, 2 = medium, 1 = small.
ROCK_RADIUS = {3: 54, 2: 30, 1: 16}
ROCK_SPEED = {3: 55, 2: 90, 1: 140}
ROCK_POINTS = {3: 20, 2: 50, 1: 100}   # points for shooting one
ROCK_SPLIT_COUNT = 2                   # how many pieces a rock breaks into

ENEMY_START_WAVE = 2              # the enemy ship starts showing up on this wave
ENEMY_SPEED = 260                 # how fast it chases you (faster than your ship's SHIP_MAX_SPEED)
ENEMY_TURN_SPEED = 150            # how quickly it turns to face you, degrees per second
ENEMY_HITS_TO_DESTROY = 3         # how many bullets it takes to destroy it
ENEMY_POINTS = 200                # points for destroying it
ENEMY_SIZE = 22
ENEMY_COLOR = (255, 40, 40)       # colour of the enemy ship

POWERUP_DURATION = 5.0            # how long a power-up's effect lasts, in seconds
POWERUP_MIN_INTERVAL = 6.0        # a new power-up appears every 6-12 seconds
POWERUP_MAX_INTERVAL = 12.0
POWERUP_RADIUS = 14
SPEED_BOOST_COLOR = (60, 200, 255)     # cyan
SPEED_BOOST_MULTIPLIER = 1.6           # how much faster your ship gets
RAPID_FIRE_COLOR = (255, 220, 40)      # yellow
RAPID_FIRE_COOLDOWN_MULTIPLIER = 0.35  # shot cooldown is multiplied by this (smaller = faster firing)

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

    def update(self, dt, keys, speed_multiplier=1.0):
        turning = 0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            turning -= 1
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            turning += 1
        self.angle += turning * SHIP_TURN_SPEED * dt

        self.thrusting = keys[pygame.K_UP] or keys[pygame.K_w]
        if self.thrusting:
            radians = math.radians(self.angle)
            self.vx += math.cos(radians) * SHIP_THRUST * speed_multiplier * dt
            self.vy += math.sin(radians) * SHIP_THRUST * speed_multiplier * dt

        # Drag, then speed limit.
        damping = max(0.0, 1.0 - SHIP_DRAG * dt)
        self.vx *= damping
        self.vy *= damping
        speed = math.hypot(self.vx, self.vy)
        max_speed = SHIP_MAX_SPEED * speed_multiplier
        if speed > max_speed:
            self.vx = self.vx / speed * max_speed
            self.vy = self.vy / speed * max_speed

        self.x, self.y = wrap(self.x + self.vx * dt, self.y + self.vy * dt)
        self.invuln = max(0.0, self.invuln - dt)

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
        draw_shape(surface, self.points(self.SHAPE), color=SHIP_COLOR)
        if self.thrusting and random.random() < 0.7:
            draw_shape(surface, self.points(self.FLAME), color=SHIP_COLOR)

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


class Rock:
    def __init__(self, x, y, size):
        self.x = x
        self.y = y
        self.size = size
        self.radius = ROCK_RADIUS[size]

        angle = random.uniform(0, math.tau)
        speed = ROCK_SPEED[size] * random.uniform(0.7, 1.3)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.spin = random.uniform(-60, 60)
        self.angle = random.uniform(0, 360)

        # A lumpy circle with a few deep notches — this is what makes rocks look
        # like rocks instead of like blobs.
        corners = random.randint(9, 12)
        self.shape = []
        for i in range(corners):
            theta = math.tau * i / corners
            jitter = random.uniform(0.78, 1.1)
            if random.random() < 0.25:
                jitter = random.uniform(0.42, 0.58)   # a chunk taken out
            self.shape.append((math.cos(theta) * jitter, math.sin(theta) * jitter))

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
            for px, py in self.shape
        ]
        draw_shape(surface, points)

    def split(self):
        """Break into smaller rocks. Smallest rocks just vanish."""
        if self.size <= 1:
            return []
        return [Rock(self.x, self.y, self.size - 1) for _ in range(ROCK_SPLIT_COUNT)]


class EnemyShip:
    # Same outline as your ship, drawn nose-first.
    SHAPE = Ship.SHAPE

    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.angle = 0.0
        self.radius = ENEMY_SIZE * 0.7
        self.hits_left = ENEMY_HITS_TO_DESTROY

    def update(self, dt, target):
        # Turn to face the ship, then fly straight at it.
        dx, dy = target.x - self.x, target.y - self.y
        desired_angle = math.degrees(math.atan2(dy, dx))
        diff = (desired_angle - self.angle + 180) % 360 - 180
        max_turn = ENEMY_TURN_SPEED * dt
        self.angle += max(-max_turn, min(max_turn, diff))

        radians = math.radians(self.angle)
        self.x, self.y = wrap(
            self.x + math.cos(radians) * ENEMY_SPEED * dt,
            self.y + math.sin(radians) * ENEMY_SPEED * dt,
        )

    def points(self, shape, scale=ENEMY_SIZE):
        radians = math.radians(self.angle)
        cos_a, sin_a = math.cos(radians), math.sin(radians)
        return [
            (
                self.x + (px * cos_a - py * sin_a) * scale,
                self.y + (px * sin_a + py * cos_a) * scale,
            )
            for px, py in shape
        ]

    def draw(self, surface):
        draw_shape(surface, self.points(self.SHAPE), color=ENEMY_COLOR)


class PowerUp:
    # Drawn as a little filled diamond in the colour of whichever effect it
    # grants, with an icon on top: an arrow for speed, a bullet for rapid fire.
    SHAPE = [(1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0)]
    ARROW_ICON = [
        (-0.45, -0.3), (0.1, -0.3), (0.1, -0.55),
        (0.6, 0.0), (0.1, 0.55), (0.1, 0.3), (-0.45, 0.3),
    ]
    BULLET_ICON = [
        (0.0, -0.55), (0.4, -0.15), (0.4, 0.55), (-0.4, 0.55), (-0.4, -0.15),
    ]

    def __init__(self, x, y, kind):
        self.x = x
        self.y = y
        self.kind = kind    # "speed" or "rapid"
        self.radius = POWERUP_RADIUS
        self.color = SPEED_BOOST_COLOR if kind == "speed" else RAPID_FIRE_COLOR
        self.icon = self.ARROW_ICON if kind == "speed" else self.BULLET_ICON

    def draw(self, surface):
        points = [(self.x + px * self.radius, self.y + py * self.radius) for px, py in self.SHAPE]
        pygame.draw.polygon(surface, self.color, points)
        icon_points = [
            (self.x + px * self.radius, self.y + py * self.radius) for px, py in self.icon
        ]
        pygame.draw.polygon(surface, BACKGROUND, icon_points)


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
        self.rocks = []
        self.enemy = None
        self.debris = []
        self.powerups = []
        self.powerup_timer = random.uniform(POWERUP_MIN_INTERVAL, POWERUP_MAX_INTERVAL)
        self.speed_timer = 0.0
        self.rapid_timer = 0.0
        self.score = 0
        self.lives = STARTING_LIVES
        self.wave = 0
        self.time_alive = 0.0
        self.fire_timer = 0.0
        self.banner_timer = 0.0
        self.over = False
        reset_score()
        submit_score(0)
        self.next_wave()

    def next_wave(self):
        self.wave += 1
        self.lives = STARTING_LIVES

        if self.wave == ENEMY_START_WAVE:
            self.banner_timer = 2.0    # flash "BOSS" briefly
        else:
            count = STARTING_ROCKS + self.wave - 1
            for _ in range(count):
                # Spawn away from the middle so rocks don't appear on top of the ship.
                while True:
                    x = random.uniform(0, WIDTH)
                    y = random.uniform(0, HEIGHT)
                    if math.hypot(x - WIDTH / 2, y - HEIGHT / 2) > 180:
                        break
                self.rocks.append(Rock(x, y, 3))

        if self.wave == ENEMY_START_WAVE:
            while True:
                x = random.uniform(0, WIDTH)
                y = random.uniform(0, HEIGHT)
                if math.hypot(x - WIDTH / 2, y - HEIGHT / 2) > 180:
                    break
            self.enemy = EnemyShip(x, y)

    def shoot(self):
        if self.fire_timer > 0 or len(self.bullets) >= MAX_BULLETS:
            return
        nose_x, nose_y = self.ship.nose()
        self.bullets.append(Bullet(nose_x, nose_y, self.ship.angle))
        cooldown = BULLET_COOLDOWN
        if self.rapid_timer > 0:
            cooldown *= RAPID_FIRE_COOLDOWN_MULTIPLIER
        self.fire_timer = cooldown

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
        self.speed_timer = max(0.0, self.speed_timer - dt)
        self.rapid_timer = max(0.0, self.rapid_timer - dt)
        speed_multiplier = SPEED_BOOST_MULTIPLIER if self.speed_timer > 0 else 1.0
        self.ship.update(dt, keys, speed_multiplier)
        if keys[pygame.K_SPACE]:
            self.shoot()

        for bullet in self.bullets:
            bullet.update(dt)
        self.bullets = [b for b in self.bullets if b.life > 0]

        for rock in self.rocks:
            rock.update(dt)

        if self.enemy:
            self.enemy.update(dt, self.ship)

        self.powerup_timer -= dt
        if self.powerup_timer <= 0:
            self.powerup_timer = random.uniform(POWERUP_MIN_INTERVAL, POWERUP_MAX_INTERVAL)
            while True:
                x = random.uniform(0, WIDTH)
                y = random.uniform(0, HEIGHT)
                if math.hypot(x - WIDTH / 2, y - HEIGHT / 2) > 180:
                    break
            kind = random.choice(["speed", "rapid"])
            self.powerups.append(PowerUp(x, y, kind))

        for burst in self.debris:
            burst.update(dt)
        self.debris = [d for d in self.debris if d.life > 0]

        # Bullets vs rocks.
        surviving_rocks = []
        for rock in self.rocks:
            hit_by = None
            for bullet in self.bullets:
                if collides(rock, bullet):
                    hit_by = bullet
                    break
            if hit_by is None:
                surviving_rocks.append(rock)
                continue
            self.bullets.remove(hit_by)
            self.add_score(ROCK_POINTS[rock.size])
            self.debris.append(Debris(rock.x, rock.y))
            surviving_rocks.extend(rock.split())
        self.rocks = surviving_rocks

        # Rocks vs ship.
        if self.ship.invuln <= 0:
            for rock in self.rocks:
                if collides(rock, self.ship):
                    self.lose_a_life()
                    break

        # Power-ups vs ship — only the ship picks these up.
        picked_up = [p for p in self.powerups if collides(p, self.ship)]
        for powerup in picked_up:
            if powerup.kind == "speed":
                self.speed_timer = POWERUP_DURATION
            else:
                self.rapid_timer = POWERUP_DURATION
        if picked_up:
            self.powerups = [p for p in self.powerups if p not in picked_up]

        # Bullets vs enemy.
        if self.enemy:
            hit_by = None
            for bullet in self.bullets:
                if collides(self.enemy, bullet):
                    hit_by = bullet
                    break
            if hit_by is not None:
                self.bullets.remove(hit_by)
                self.enemy.hits_left -= 1
                if self.enemy.hits_left <= 0:
                    self.add_score(ENEMY_POINTS)
                    self.enemy = None

        # Enemy ship vs ship.
        if self.ship.invuln <= 0 and self.enemy and collides(self.enemy, self.ship):
            self.lose_a_life()

        self.banner_timer = max(0.0, self.banner_timer - dt)

        boss_wave_clear = self.wave != ENEMY_START_WAVE or self.enemy is None
        if not self.rocks and boss_wave_clear:
            self.next_wave()

    def draw(self, surface):
        surface.fill(BACKGROUND)

        for rock in self.rocks:
            rock.draw(surface)
        if self.enemy:
            self.enemy.draw(surface)
        for powerup in self.powerups:
            powerup.draw(surface)
        for bullet in self.bullets:
            bullet.draw(surface)
        for burst in self.debris:
            burst.draw(surface)
        if not self.over:
            self.ship.draw(surface, self.time_alive)

        self.draw_hud(surface)

        if self.banner_timer > 0:
            draw_text(surface, "BOSS", (WIDTH / 2, 40), size=90, color=ENEMY_COLOR, align="center")

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

        # Boss's remaining hits, drawn as little red ships on the opposite side.
        if self.enemy:
            for i in range(self.enemy.hits_left):
                x = WIDTH - 34 - i * 30
                y = 90
                points = [
                    (x + (px * 0.0 - py * -1.0) * 11, y + (px * -1.0 + py * 0.0) * 11)
                    for px, py in Ship.SHAPE
                ]
                draw_shape(surface, points, color=ENEMY_COLOR, width=2)

        # Active power-up effects, shown below the score.
        effect_y = 120
        if self.speed_timer > 0:
            draw_text(surface, f"SPEED {self.speed_timer:.1f}", (28, effect_y),
                      size=20, color=SPEED_BOOST_COLOR)
            effect_y += 26
        if self.rapid_timer > 0:
            draw_text(surface, f"RAPID FIRE {self.rapid_timer:.1f}", (28, effect_y),
                      size=20, color=RAPID_FIRE_COLOR)


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
