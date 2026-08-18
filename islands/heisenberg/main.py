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

SKY_COLOR = (110, 140, 165)       # God Valley at dusk
GROUND_COLOR = (196, 172, 122)
PILLAR_COLOR = (150, 140, 128)
ROCK_COLOR = (95, 82, 66)

LINE_COLOR = (255, 255, 255)      # text
HAKI_COLOR = (150, 60, 220)       # ordinary sword swing
ARMAMENT_COLOR = (25, 25, 30)     # Armament Haki, hardened and black
CONQUEROR_COLOR = (110, 20, 150)  # Conqueror's Haki
OBSERVATION_COLOR = (80, 210, 220)  # Observation Haki
SPARK_COLOR = (255, 225, 90)      # hit sparks
HULL_OUTLINE = (30, 18, 10)

PLAYER_BODY_COLOR = (210, 170, 60)    # Fafa
PLAYER_SKIN_COLOR = (210, 160, 120)
RIVAL_BODY_COLOR = (110, 45, 45)      # the rival haki master
RIVAL_SKIN_COLOR = (200, 170, 150)

LINE_WIDTH = 2
FONT_NAME = None                  # None = pygame's built-in font

FIGHTER_SIZE = 20                 # how big Fafa and the rival are
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
CPU_ATTACK_RANGE = 72
CPU_WINDUP_TIME = 0.55             # how long the rival telegraphs before swinging
CPU_RECOVER_TIME = 0.5
CPU_DAMAGE = 10

HIT_FLASH_TIME = 0.3
SHAKE_DURATION = 0.25
WIN_BONUS = 500

FPS = 60

# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────


def rotated_points(x, y, angle, shape, scale):
    """Turn a shape's local (-1..1) points into real points on screen."""
    radians = math.radians(angle)
    cos_a, sin_a = math.cos(radians), math.sin(radians)
    return [
        (x + (px * cos_a - py * sin_a) * scale, y + (px * sin_a + py * cos_a) * scale)
        for px, py in shape
    ]


def draw_filled(surface, points, fill_color, outline_color=None, outline_width=2):
    """Draw a solid shape, with an optional darker outline on top for definition."""
    pygame.draw.polygon(surface, fill_color, points)
    if outline_color:
        pygame.draw.polygon(surface, outline_color, points, outline_width)


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
    pygame.draw.rect(surface, HULL_OUTLINE, (x, y, w, h), 2)


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
    """Shared bits between Fafa and the rival: a body, a health bar's worth of
    state, and a sword swing."""

    SHAPE = [(1.0, 0.0), (-0.7, 0.6), (-0.3, 0.0), (-0.7, -0.6)]

    def __init__(self, x, y, angle, max_health, body_color, skin_color):
        self.x = x
        self.y = y
        self.angle = angle
        self.max_health = max_health
        self.health = max_health
        self.radius = FIGHTER_SIZE * 0.6
        self.body_color = body_color
        self.skin_color = skin_color
        self.hit_flash = 0.0

    def face(self, target_x, target_y):
        self.angle = math.degrees(math.atan2(target_y - self.y, target_x - self.x))

    def clamp_to_arena(self):
        self.x = max(ARENA_MARGIN, min(WIDTH - ARENA_MARGIN, self.x))
        self.y = max(ARENA_TOP, min(HEIGHT - ARENA_MARGIN, self.y))

    def draw_body(self, surface, flash_color):
        color = flash_color if self.hit_flash > 0 and int(self.hit_flash * 20) % 2 == 0 else self.body_color
        body = rotated_points(self.x, self.y, self.angle, self.SHAPE, FIGHTER_SIZE)
        draw_filled(surface, body, color, HULL_OUTLINE, 1)
        head_x, head_y = rotated_points(self.x, self.y, self.angle, [(0.55, 0.0)], FIGHTER_SIZE)[0]
        pygame.draw.circle(surface, self.skin_color, (int(head_x), int(head_y)), 5)


class Player(Fighter):
    def __init__(self):
        super().__init__(ARENA_MARGIN + 130, HEIGHT / 2, 0.0, PLAYER_MAX_HEALTH,
                          PLAYER_BODY_COLOR, PLAYER_SKIN_COLOR)
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
    def __init__(self):
        super().__init__(WIDTH - ARENA_MARGIN - 130, HEIGHT / 2, 180.0, CPU_MAX_HEALTH,
                          RIVAL_BODY_COLOR, RIVAL_SKIN_COLOR)
        self.state = "approach"
        self.state_timer = 0.0
        self.stun_timer = 0.0

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
            if dist > CPU_ATTACK_RANGE * 0.8:
                radians = math.radians(self.angle)
                self.x += math.cos(radians) * CPU_SPEED * dt
                self.y += math.sin(radians) * CPU_SPEED * dt
                self.clamp_to_arena()
            else:
                self.state = "windup"
                self.state_timer = CPU_WINDUP_TIME * (2.2 if observation_active else 1.0)
        elif self.state == "windup":
            self.state_timer -= dt
            if self.state_timer <= 0:
                self.state = "recover"
                self.state_timer = CPU_RECOVER_TIME
                return "swing"
        elif self.state == "recover":
            self.state_timer -= dt
            if self.state_timer <= 0:
                self.state = "approach"
        return None

    def draw(self, surface):
        self.draw_body(surface, (255, 190, 190))
        if self.state == "windup":
            warn_x, warn_y = self.x, self.y - FIGHTER_SIZE - 26
            pygame.draw.polygon(
                surface, (255, 170, 40),
                [(warn_x - 9, warn_y + 15), (warn_x + 9, warn_y + 15), (warn_x, warn_y - 6)],
            )
            draw_text(surface, "!", (warn_x, warn_y - 4), size=18, align="center", color=(40, 25, 0))
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
        self.rival = Rival()
        self.effects = []
        self.bursts = []
        self.shake_timer = 0.0
        self.shake_magnitude = 0.0
        self.score = 0
        self.over = False
        self.result = None
        self.rocks = [
            (random.uniform(ARENA_MARGIN, WIDTH - ARENA_MARGIN),
             random.uniform(ARENA_TOP, HEIGHT - ARENA_MARGIN),
             random.uniform(14, 30))
            for _ in range(6)
        ]
        reset_score()
        submit_score(0)

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
        if swing_event == "swing":
            dist = math.hypot(self.rival.x - self.player.x, self.rival.y - self.player.y)
            if dist <= CPU_ATTACK_RANGE * 1.3:
                self.player.health = max(0, self.player.health - CPU_DAMAGE)
                self.player.hit_flash = HIT_FLASH_TIME
                self.effects.append(Debris(self.player.x, self.player.y, 10, SPARK_COLOR))
                self.trigger_shake(8)
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
        surface.fill(SKY_COLOR)
        pygame.draw.rect(surface, GROUND_COLOR, (0, ARENA_TOP - 40, WIDTH, HEIGHT - ARENA_TOP + 40))
        for i in range(5):
            px = WIDTH * (i + 0.5) / 5
            pygame.draw.rect(surface, PILLAR_COLOR, (px - 14, ARENA_TOP - 100, 28, 100))
        for x, y, size in self.rocks:
            pygame.draw.circle(surface, ROCK_COLOR, (int(x), int(y)), int(size))
            pygame.draw.circle(surface, HULL_OUTLINE, (int(x), int(y)), int(size), 2)

        self.rival.draw(surface)
        self.player.draw(surface)
        for burst in self.bursts:
            burst.draw(surface)
        for effect in self.effects:
            effect.draw(surface)

        self.draw_hud(surface)

        if self.over:
            if self.result == "win":
                draw_text(surface, "VICTORY", (WIDTH / 2, HEIGHT / 2 - 40), size=64, align="center", color=HAKI_COLOR)
            else:
                draw_text(surface, "DEFEATED", (WIDTH / 2, HEIGHT / 2 - 40), size=64, align="center", color=RIVAL_BODY_COLOR)
            draw_text(surface, f"SCORE {self.score}", (WIDTH / 2, HEIGHT / 2 + 30), size=34, align="center")
            draw_text(surface, "PRESS R TO PLAY AGAIN", (WIDTH / 2, HEIGHT / 2 + 80), size=24, align="center")

    def draw_hud(self, surface):
        draw_bar(surface, 28, 22, 260, 22, self.player.health / PLAYER_MAX_HEALTH, HAKI_COLOR)
        draw_text(surface, "FAFA", (28, 48), size=16)
        draw_bar(surface, WIDTH - 28 - 260, 22, 260, 22, self.rival.health / CPU_MAX_HEALTH,
                  RIVAL_BODY_COLOR, from_right=True)
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
                # ESC is not handled here on purpose — in Islands World it means
                # "leave this island", and the world itself takes care of that.

        game.update(dt, pygame.key.get_pressed())
        game.draw(render_surface)

        # A little screen shake on big hits — draw to an offscreen surface, then
        # blit it onto the real screen with a small random offset.
        screen.fill(SKY_COLOR)
        screen.blit(render_surface, game.shake_offset())
        pygame.display.flip()

        # Required for the browser build — hands control back to the page each
        # frame. Do not remove this line.
        await asyncio.sleep(0)

    pygame.quit()


# pygbag needs the program to start with asyncio.run(main()) at the top level.
asyncio.run(main())
