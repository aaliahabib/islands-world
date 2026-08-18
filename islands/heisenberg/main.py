"""GOD VALLEY — your island's game.

Fafa the Pirate King duels an old-generation haki master, one on one, on the
shores of God Valley.

    LEFT / RIGHT / UP / DOWN   (or WASD)   move
    SPACE                                  sword swing
    Q                                      Armament Haki — a harder swing
    E                                      Conqueror's Haki — stuns the rival
                                            once your meter (below your health
                                            bar) is full
    R                                      Observation Haki — see the rival's
                                            next attack coming, so it's easier
                                            to dodge
    R (after game over)                    restart

Land a hit to charge your Conqueror's Haki meter. Whoever's health hits zero
first loses the duel.

The fastest way to make it yours is the CUSTOMIZE block just below: colours,
damage, cooldowns, how tough the rival is.

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

TITLE = "God Valley"

WIDTH = 900                      # size of the game window
HEIGHT = 700

PAPER_COLOR = (250, 250, 245)     # the notebook-paper background
GRID_COLOR = (222, 222, 214)      # faint graph-paper grid
GRID_SPACING = 40

LINE_COLOR = (30, 30, 30)         # text, and the page border
HAKI_COLOR = (150, 60, 220)       # ordinary sword swing
ARMAMENT_COLOR = (25, 25, 30)     # Armament Haki, hardened and black
CONQUEROR_COLOR = (110, 20, 150)  # Conqueror's Haki
OBSERVATION_COLOR = (80, 210, 220)  # Observation Haki
SPARK_COLOR = (240, 130, 20)      # hit sparks
OUTLINE_COLOR = (40, 40, 40)

PLAYER_LINE_COLOR = (20, 20, 20)      # Fafa's stick figure
RIVAL_LINE_COLOR = (200, 40, 40)      # the rival haki master's stick figure

LINE_WIDTH = 2
STICK_LIMB_WIDTH = 4               # how thick the stick-figure lines are
FONT_NAME = None                   # None = pygame's built-in font

FIGHTER_SIZE = 26                 # how big Fafa and the rival are
ARENA_MARGIN = 70                 # how close to the edges either fighter can go
ARENA_TOP = 170

PLAYER_MAX_HEALTH = 100
PLAYER_SPEED = 210

SWORD_RANGE = 60
SWORD_ARC_DEGREES = 110            # how wide the swing is
SWORD_ACTIVE_TIME = 0.12           # how long the swing can hit for
SWORD_COOLDOWN = 0.4
SWORD_DAMAGE = 8
SWORD_METER_GAIN = 12               # conqueror's meter gained per hit

ARMAMENT_RANGE = 72
ARMAMENT_ARC_DEGREES = 130
ARMAMENT_COOLDOWN = 1.2
ARMAMENT_DAMAGE = 18
ARMAMENT_METER_GAIN = 22

CONQUEROR_METER_MAX = 100
CONQUEROR_STUN_TIME = 2.5

OBSERVATION_COOLDOWN = 6.0
OBSERVATION_DURATION = 3.0

CPU_MAX_HEALTH = 100
CPU_SPEED = 155
CPU_ENGAGE_RANGE = 80               # how close the rival closes in before attacking

# Easy/Medium/Hard scale the rival's health, speed, damage, and how often it
# picks the heavy swing over the jab. Change these to retune any difficulty.
DIFFICULTIES = {
    "easy": {"health": 0.8, "speed": 0.85, "damage": 0.7, "heavy_chance": 0.25},
    "medium": {"health": 1.0, "speed": 1.0, "damage": 1.0, "heavy_chance": 0.4},
    "hard": {"health": 1.25, "speed": 1.15, "damage": 1.3, "heavy_chance": 0.55},
}
DIFFICULTY_KEYS = {pygame.K_1: "easy", pygame.K_2: "medium", pygame.K_3: "hard"}

CPU_JAB_WINDUP = 0.28                # how long it telegraphs before swinging
CPU_JAB_RECOVER = 0.25
CPU_JAB_RANGE = 60
CPU_JAB_DAMAGE = 6

CPU_HEAVY_WINDUP = 0.75
CPU_HEAVY_RECOVER = 0.75
CPU_HEAVY_RANGE = 85
CPU_HEAVY_DAMAGE = 16

HIT_FLASH_TIME = 0.3
SHAKE_DURATION = 0.25
WIN_BONUS = 500

FPS = 60

# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────


def mirrored_points(x, y, flip_x, shape, scale):
    """Turn a shape's local (-1..1) points into real points, flipped left/right
    to face a direction — this is what keeps a stick figure standing upright
    instead of tipping over to point at whatever it's facing."""
    return [(x + px * scale * flip_x, y + py * scale) for px, py in shape]


def draw_swing_arc(surface, x, y, angle, reach, arc_degrees, color, width=5):
    """The wedge-shaped haki flash a sword swing leaves behind."""
    radians = math.radians(angle)
    spread = math.radians(arc_degrees / 2)
    tip1 = (x + math.cos(radians - spread) * reach, y + math.sin(radians - spread) * reach)
    tip2 = (x + math.cos(radians + spread) * reach, y + math.sin(radians + spread) * reach)
    pygame.draw.lines(surface, color, False, [tip1, (x, y), tip2], width)
    pygame.draw.arc(
        surface, color, (x - reach, y - reach, reach * 2, reach * 2),
        radians - spread, radians + spread, max(2, width - 2),
    )


def draw_bar(surface, x, y, w, h, ratio, color, from_right=False):
    ratio = max(0.0, min(1.0, ratio))
    pygame.draw.rect(surface, (40, 40, 40), (x, y, w, h))
    fill_w = w * ratio
    fill_x = x + w - fill_w if from_right else x
    pygame.draw.rect(surface, color, (fill_x, y, fill_w, h))
    pygame.draw.rect(surface, OUTLINE_COLOR, (x, y, w, h), 2)


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
#  Little effects — sparks and haki shockwaves
# ─────────────────────────────────────────────────────────────────────────────


class Debris:
    """A little burst of lines — sword sparks, wherever a hit lands."""

    def __init__(self, x, y, count=8, color=None):
        self.color = color or LINE_COLOR
        self.pieces = []
        for _ in range(count):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(40, 170)
            self.pieces.append([x, y, math.cos(angle) * speed, math.sin(angle) * speed])
        self.life = 0.6

    def update(self, dt):
        for piece in self.pieces:
            piece[0] += piece[2] * dt
            piece[1] += piece[3] * dt
        self.life -= dt

    def draw(self, surface):
        for x, y, vx, vy in self.pieces:
            scale = 0.04
            pygame.draw.line(surface, self.color, (x, y), (x - vx * scale, y - vy * scale), 2)


class RingBurst:
    """An expanding, fading ring — used for the Conqueror's Haki shockwave."""

    def __init__(self, x, y, color, max_radius=150, life=0.5):
        self.x, self.y = x, y
        self.color = color
        self.max_radius = max_radius
        self.life = life
        self.total_life = life

    def update(self, dt):
        self.life -= dt

    def draw(self, surface):
        t = max(0.0, self.life / self.total_life)
        radius = int(self.max_radius * (1 - t))
        width = max(1, int(6 * t))
        if radius > 0:
            pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), radius, width)


# ─────────────────────────────────────────────────────────────────────────────
#  The fighters
# ─────────────────────────────────────────────────────────────────────────────


class Fighter:
    """Shared bits between Fafa and the rival: a stick-figure body, a health
    bar's worth of state, and a sword swing."""

    # A stick figure, standing upright with its head up (-y) and feet down
    # (+y). Change these to reshape it — each pair is a line segment, as
    # (start, end) local points.
    HEAD = (0.0, -0.85)
    LIMBS = [
        [(0.0, -0.55), (0.0, 0.3)],        # spine
        [(0.0, -0.35), (0.55, -0.05)],     # front arm, toward whoever it's facing
        [(0.0, -0.35), (-0.45, 0.05)],     # back arm
        [(0.0, 0.3), (0.4, 1.0)],          # front leg
        [(0.0, 0.3), (-0.4, 1.0)],         # back leg
    ]

    def __init__(self, x, y, angle, max_health, line_color):
        self.x = x
        self.y = y
        self.angle = angle
        self.max_health = max_health
        self.health = max_health
        self.radius = FIGHTER_SIZE * 0.6
        self.line_color = line_color
        self.hit_flash = 0.0

    def face(self, target_x, target_y):
        self.angle = math.degrees(math.atan2(target_y - self.y, target_x - self.x))

    def clamp_to_arena(self):
        self.x = max(ARENA_MARGIN, min(WIDTH - ARENA_MARGIN, self.x))
        self.y = max(ARENA_TOP, min(HEIGHT - ARENA_MARGIN, self.y))

    def draw_body(self, surface, flash_color):
        color = flash_color if self.hit_flash > 0 and int(self.hit_flash * 20) % 2 == 0 else self.line_color
        flip = 1 if math.cos(math.radians(self.angle)) >= 0 else -1
        for limb in self.LIMBS:
            p1, p2 = mirrored_points(self.x, self.y, flip, limb, FIGHTER_SIZE)
            pygame.draw.line(surface, color, p1, p2, STICK_LIMB_WIDTH)
        head_x, head_y = mirrored_points(self.x, self.y, flip, [self.HEAD], FIGHTER_SIZE)[0]
        pygame.draw.circle(surface, color, (int(head_x), int(head_y)),
                            int(FIGHTER_SIZE * 0.3), STICK_LIMB_WIDTH)


class Player(Fighter):
    def __init__(self):
        super().__init__(ARENA_MARGIN + 130, HEIGHT / 2, 0.0, PLAYER_MAX_HEALTH, PLAYER_LINE_COLOR)
        self.attack_timer = 0.0
        self.armament_timer = 0.0
        self.observation_timer = 0.0
        self.observation_active = 0.0
        self.conqueror_meter = 0.0
        self.swing_active = 0.0
        self.swing_kind = None
        self.swing_hit_landed = False

    def try_sword(self):
        if self.attack_timer <= 0:
            self.attack_timer = SWORD_COOLDOWN
            self.swing_active = SWORD_ACTIVE_TIME
            self.swing_kind = "sword"
            self.swing_hit_landed = False

    def try_armament(self):
        if self.armament_timer <= 0:
            self.armament_timer = ARMAMENT_COOLDOWN
            self.swing_active = SWORD_ACTIVE_TIME
            self.swing_kind = "armament"
            self.swing_hit_landed = False

    def try_observation(self):
        if self.observation_timer <= 0:
            self.observation_timer = OBSERVATION_COOLDOWN
            self.observation_active = OBSERVATION_DURATION

    def try_conqueror(self):
        if self.conqueror_meter >= CONQUEROR_METER_MAX:
            self.conqueror_meter = 0.0
            return True
        return False

    def update(self, dt, keys, rival_x, rival_y):
        dx = dy = 0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            dx -= 1
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            dx += 1
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            dy -= 1
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            dy += 1
        if dx or dy:
            length = math.hypot(dx, dy)
            self.x += dx / length * PLAYER_SPEED * dt
            self.y += dy / length * PLAYER_SPEED * dt
            self.clamp_to_arena()
        self.face(rival_x, rival_y)

        self.attack_timer = max(0.0, self.attack_timer - dt)
        self.armament_timer = max(0.0, self.armament_timer - dt)
        self.observation_timer = max(0.0, self.observation_timer - dt)
        self.observation_active = max(0.0, self.observation_active - dt)
        self.swing_active = max(0.0, self.swing_active - dt)
        self.hit_flash = max(0.0, self.hit_flash - dt)

    def draw(self, surface):
        self.draw_body(surface, (255, 90, 90))
        if self.observation_active > 0:
            pygame.draw.circle(surface, OBSERVATION_COLOR, (int(self.x), int(self.y)), FIGHTER_SIZE + 12, 2)
        if self.swing_active > 0:
            armament = self.swing_kind == "armament"
            draw_swing_arc(
                surface, self.x, self.y, self.angle,
                ARMAMENT_RANGE if armament else SWORD_RANGE,
                ARMAMENT_ARC_DEGREES if armament else SWORD_ARC_DEGREES,
                ARMAMENT_COLOR if armament else HAKI_COLOR,
            )


class Rival(Fighter):
    def __init__(self, difficulty="medium"):
        preset = DIFFICULTIES[difficulty]
        max_health = round(CPU_MAX_HEALTH * preset["health"])
        super().__init__(WIDTH - ARENA_MARGIN - 130, HEIGHT / 2, 180.0, max_health, RIVAL_LINE_COLOR)
        self.speed = CPU_SPEED * preset["speed"]
        self.damage_mult = preset["damage"]
        self.heavy_chance = preset["heavy_chance"]
        self.state = "approach"
        self.state_timer = 0.0
        self.stun_timer = 0.0
        self.attack_kind = None

    def stun(self, duration):
        self.stun_timer = duration
        self.state = "approach"
        self.state_timer = 0.0

    def update(self, dt, player_x, player_y, observation_active):
        self.hit_flash = max(0.0, self.hit_flash - dt)
        self.face(player_x, player_y)

        if self.stun_timer > 0:
            self.stun_timer = max(0.0, self.stun_timer - dt)
            return None

        dist = math.hypot(player_x - self.x, player_y - self.y)

        if self.state == "approach":
            if dist > CPU_ENGAGE_RANGE:
                radians = math.radians(self.angle)
                self.x += math.cos(radians) * self.speed * dt
                self.y += math.sin(radians) * self.speed * dt
                self.clamp_to_arena()
            else:
                self.attack_kind = "heavy" if random.random() < self.heavy_chance else "jab"
                windup = CPU_HEAVY_WINDUP if self.attack_kind == "heavy" else CPU_JAB_WINDUP
                # Getting hurt makes it fight faster and meaner, not slower.
                aggression = 0.75 + 0.25 * (self.health / self.max_health)
                self.state = "windup"
                self.state_timer = windup * aggression * (2.2 if observation_active else 1.0)
        elif self.state == "windup":
            self.state_timer -= dt
            if self.state_timer <= 0:
                self.state = "recover"
                self.state_timer = CPU_HEAVY_RECOVER if self.attack_kind == "heavy" else CPU_JAB_RECOVER
                return self.attack_kind
        elif self.state == "recover":
            self.state_timer -= dt
            if self.state_timer <= 0:
                self.state = "approach"
        return None

    def draw(self, surface):
        self.draw_body(surface, (255, 190, 190))
        if self.state == "windup":
            heavy = self.attack_kind == "heavy"
            warn_x, warn_y = self.x, self.y - FIGHTER_SIZE - 26
            size = 11 if heavy else 8
            color = (200, 40, 40) if heavy else (255, 170, 40)
            pygame.draw.polygon(
                surface, color,
                [(warn_x - size, warn_y + size + 6), (warn_x + size, warn_y + size + 6), (warn_x, warn_y - 6)],
            )
            draw_text(surface, "!!" if heavy else "!", (warn_x, warn_y - 4), size=18, align="center", color=(30, 20, 0))
        if self.stun_timer > 0:
            draw_text(surface, "STUNNED", (self.x, self.y - FIGHTER_SIZE - 30),
                      size=16, align="center", color=CONQUEROR_COLOR)


# ─────────────────────────────────────────────────────────────────────────────
#  The game
# ─────────────────────────────────────────────────────────────────────────────


class Game:
    def __init__(self):
        self.start_new_game()

    def start_new_game(self):
        self.player = Player()
        self.rival = Rival()          # a default rival just to stand there on the start screen
        self.effects = []
        self.bursts = []
        self.shake_timer = 0.0
        self.shake_magnitude = 0.0
        self.score = 0
        self.started = False
        self.over = False
        self.result = None
        reset_score()
        submit_score(0)

    def choose_difficulty(self, difficulty):
        self.rival = Rival(difficulty)
        self.started = True

    def trigger_shake(self, magnitude):
        self.shake_timer = SHAKE_DURATION
        self.shake_magnitude = magnitude

    def shake_offset(self):
        if self.shake_timer <= 0:
            return (0, 0)
        strength = self.shake_magnitude * (self.shake_timer / SHAKE_DURATION)
        return (random.uniform(-strength, strength), random.uniform(-strength, strength))

    def add_score(self, points):
        self.score += points
        submit_score(self.score)

    def end_duel(self, result):
        self.result = result
        self.over = True
        if result == "win":
            self.add_score(WIN_BONUS)
        game_over(self.score)

    def update(self, dt, keys):
        if not self.started:
            return

        self.shake_timer = max(0.0, self.shake_timer - dt)
        for effect in self.effects:
            effect.update(dt)
        self.effects = [e for e in self.effects if e.life > 0]
        for burst in self.bursts:
            burst.update(dt)
        self.bursts = [b for b in self.bursts if b.life > 0]

        if self.over:
            return

        self.player.update(dt, keys, self.rival.x, self.rival.y)
        if keys[pygame.K_SPACE]:
            self.player.try_sword()
        if keys[pygame.K_q]:
            self.player.try_armament()
        if keys[pygame.K_r]:
            self.player.try_observation()
        if keys[pygame.K_e] and self.player.try_conqueror():
            self.rival.stun(CONQUEROR_STUN_TIME)
            self.bursts.append(RingBurst(self.rival.x, self.rival.y, CONQUEROR_COLOR, 160, 0.5))
            self.trigger_shake(10)

        swing_event = self.rival.update(dt, self.player.x, self.player.y, self.player.observation_active > 0)
        if swing_event:
            heavy = swing_event == "heavy"
            reach = CPU_HEAVY_RANGE if heavy else CPU_JAB_RANGE
            damage = round((CPU_HEAVY_DAMAGE if heavy else CPU_JAB_DAMAGE) * self.rival.damage_mult)
            dist = math.hypot(self.rival.x - self.player.x, self.rival.y - self.player.y)
            if dist <= reach * 1.3:
                self.player.health = max(0, self.player.health - damage)
                self.player.hit_flash = HIT_FLASH_TIME
                self.effects.append(Debris(self.player.x, self.player.y, 14 if heavy else 8, SPARK_COLOR))
                self.trigger_shake(11 if heavy else 6)
                if self.player.health <= 0:
                    self.end_duel("lose")
                    return

        if self.player.swing_active > 0 and not self.player.swing_hit_landed:
            armament = self.player.swing_kind == "armament"
            reach = ARMAMENT_RANGE if armament else SWORD_RANGE
            arc = ARMAMENT_ARC_DEGREES if armament else SWORD_ARC_DEGREES
            dist = math.hypot(self.rival.x - self.player.x, self.rival.y - self.player.y)
            bearing = math.degrees(math.atan2(self.rival.y - self.player.y, self.rival.x - self.player.x))
            diff = abs((bearing - self.player.angle + 180) % 360 - 180)
            if dist < reach and diff < arc / 2:
                damage = ARMAMENT_DAMAGE if armament else SWORD_DAMAGE
                gain = ARMAMENT_METER_GAIN if armament else SWORD_METER_GAIN
                self.player.swing_hit_landed = True
                self.rival.health = max(0, self.rival.health - damage)
                self.rival.hit_flash = HIT_FLASH_TIME
                self.player.conqueror_meter = min(CONQUEROR_METER_MAX, self.player.conqueror_meter + gain)
                self.add_score(damage)
                self.effects.append(
                    Debris(self.rival.x, self.rival.y, 10, ARMAMENT_COLOR if armament else HAKI_COLOR)
                )
                self.trigger_shake(8 if armament else 5)
                if self.rival.health <= 0:
                    self.end_duel("win")
                    return

    def draw(self, surface):
        # A sheet of graph paper for the fight to happen on.
        surface.fill(PAPER_COLOR)
        for grid_x in range(0, WIDTH, GRID_SPACING):
            pygame.draw.line(surface, GRID_COLOR, (grid_x, 0), (grid_x, HEIGHT), 1)
        for grid_y in range(0, HEIGHT, GRID_SPACING):
            pygame.draw.line(surface, GRID_COLOR, (0, grid_y), (WIDTH, grid_y), 1)
        pygame.draw.rect(
            surface, OUTLINE_COLOR,
            (ARENA_MARGIN - 20, ARENA_TOP - 20, WIDTH - 2 * (ARENA_MARGIN - 20), HEIGHT - ARENA_TOP - ARENA_MARGIN + 40),
            3,
        )

        self.rival.draw(surface)
        self.player.draw(surface)
        for burst in self.bursts:
            burst.draw(surface)
        for effect in self.effects:
            effect.draw(surface)

        self.draw_hud(surface)

        if not self.started:
            draw_text(surface, "GOD VALLEY", (WIDTH / 2, HEIGHT / 2 - 150), size=54, align="center", color=HAKI_COLOR)
            draw_text(surface, "MOVE: WASD OR ARROW KEYS", (WIDTH / 2, HEIGHT / 2 - 60), size=18, align="center")
            draw_text(surface, "SWORD: SPACE     ARMAMENT HAKI: Q", (WIDTH / 2, HEIGHT / 2 - 30), size=18, align="center")
            draw_text(surface, "CONQUEROR'S HAKI: E     OBSERVATION HAKI: R", (WIDTH / 2, HEIGHT / 2), size=18, align="center")
            draw_text(surface, "PICK A DIFFICULTY — 1 EASY   2 MEDIUM   3 HARD",
                      (WIDTH / 2, HEIGHT / 2 + 60), size=26, align="center")
        elif self.over:
            if self.result == "win":
                draw_text(surface, "VICTORY", (WIDTH / 2, HEIGHT / 2 - 40), size=64, align="center", color=HAKI_COLOR)
            else:
                draw_text(surface, "DEFEATED", (WIDTH / 2, HEIGHT / 2 - 40), size=64, align="center", color=RIVAL_LINE_COLOR)
            draw_text(surface, f"SCORE {self.score}", (WIDTH / 2, HEIGHT / 2 + 30), size=34, align="center")
            draw_text(surface, "PRESS R TO PLAY AGAIN", (WIDTH / 2, HEIGHT / 2 + 80), size=24, align="center")

    def draw_hud(self, surface):
        draw_bar(surface, 28, 22, 260, 22, self.player.health / PLAYER_MAX_HEALTH, HAKI_COLOR)
        draw_text(surface, "FAFA", (28, 48), size=16)
        draw_bar(surface, WIDTH - 28 - 260, 22, 260, 22, self.rival.health / self.rival.max_health,
                  RIVAL_LINE_COLOR, from_right=True)
        draw_text(surface, "RIVAL", (WIDTH - 28, 48), size=16, align="right")

        draw_bar(surface, 28, 68, 180, 12, self.player.conqueror_meter / CONQUEROR_METER_MAX, CONQUEROR_COLOR)
        draw_text(surface, "CONQUEROR'S HAKI (E)", (28, 84), size=13)

        draw_text(surface, str(self.score), (WIDTH / 2, 22), size=32, align="center")
        draw_text(surface, "SWORD SPACE   ARMAMENT Q   OBSERVATION R", (WIDTH / 2, HEIGHT - 34),
                  size=15, align="center")


async def main():
    pygame.init()
    pygame.display.set_caption(TITLE)
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    render_surface = pygame.Surface((WIDTH, HEIGHT))
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
                elif not game.started and event.key in DIFFICULTY_KEYS:
                    game.choose_difficulty(DIFFICULTY_KEYS[event.key])
                # ESC is not handled here on purpose — in Islands World it means
                # "leave this island", and the world itself takes care of that.

        game.update(dt, pygame.key.get_pressed())
        game.draw(render_surface)

        # A little screen shake on big hits — draw to an offscreen surface, then
        # blit it onto the real screen with a small random offset.
        screen.fill(PAPER_COLOR)
        screen.blit(render_surface, game.shake_offset())
        pygame.display.flip()

        # Required for the browser build — hands control back to the page each
        # frame. Do not remove this line.
        await asyncio.sleep(0)

    pygame.quit()


# pygbag needs the program to start with asyncio.run(main()) at the top level.
asyncio.run(main())
