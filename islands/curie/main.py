"""KARATEKA VS ROBOT — your island's game.

A one-on-one fight against a robot that gets tougher every time you beat it.

    LEFT / RIGHT      move
    UP                jump
    DOWN              crouch
    SPACE             attack (punch standing, kick crouched)
    Z                 special: stun the robot (needs a full special bar)
    X                 special: big damage hit (needs a full special bar)
    R                 restart after game over

This is YOUR game now. The fastest way to make it yours is the CUSTOMIZE block
just below — change the colours, health, damage, speeds. Then run it and see
what happened. After that, ask Claude for bigger changes.

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

TITLE = "Karateka vs Robot"

WIDTH = 900
HEIGHT = 700
FPS = 60

SKY_COLOR = (135, 206, 250)
GROUND_COLOR = (76, 153, 74)
LINE_COLOR = (255, 255, 255)
FONT_NAME = None

GROUND_Y = HEIGHT - 130
ARENA_LEFT = 90
ARENA_RIGHT = WIDTH - 90

PLAYER_SKIN = (224, 172, 132)
PLAYER_SHORTS = (30, 30, 35)
PLAYER_HAIR = (15, 15, 15)
PLAYER_HEADBAND = (200, 30, 30)
PLAYER_BANDAGE = (235, 227, 210)
PLAYER_SHOES = (40, 40, 40)

ROBOT_SKIN = (214, 176, 150)
ROBOT_METAL = (140, 148, 158)
ROBOT_EYE = (220, 40, 40)
ROBOT_CLOTHING = (92, 68, 52)      # the vest it wears over its chest
ROBOT_PANTS = (55, 58, 66)
ROBOT_BOOTS = (25, 25, 28)

PIXEL_SIZE = 5                     # size of one "pixel" block in the sprites

SUN_COLOR = (255, 221, 89)
CLOUD_COLOR = (255, 255, 255)
GRASS_DARK = (54, 122, 54)

PLAYER_MAX_HEALTH = 100

PHASE_COUNT = 5
ROBOT_MAX_HEALTH_BY_PHASE = [100, 120, 145, 175, 220]
SCORE_MULTIPLIER_BY_PHASE = [1.0, 1.3, 1.6, 2.0, 2.5]

MOVE_SPEED = 230
JUMP_SPEED = 560
GRAVITY = 1500

PUNCH_DAMAGE = 6
KICK_DAMAGE = 10
ATTACK_RANGE = 82
ATTACK_ACTIVE_TIME = 0.12
ATTACK_COOLDOWN = 0.35

SPECIAL_MAX = 100
SPECIAL_PER_SECOND = 3
SPECIAL_PER_HIT = 18
STUN_DURATION = 1.4
SPECIAL_DAMAGE = 30

SCORE_PER_HIT = 10
SCORE_PER_SPECIAL = 30
SCORE_PER_ROBOT_DOWN = 200

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


def draw_bar(surface, x, y, width, height, ratio, color, back_color=(40, 40, 40)):
    pygame.draw.rect(surface, back_color, (x, y, width, height))
    pygame.draw.rect(surface, color, (x, y, width * max(0.0, min(1.0, ratio)), height))
    pygame.draw.rect(surface, LINE_COLOR, (x, y, width, height), 2)


def draw_pixel_sprite(surface, blocks, palette, cx, top_y, facing, total_w_units, v_scale=1.0):
    """Draw a little pixel-art character. `blocks` is a list of
    (grid_x, grid_y, grid_width, grid_height, palette_key) rectangles, all
    measured in PIXEL_SIZE units and assuming the character faces right."""
    for gx, gy, gw, gh, key in blocks:
        if facing == -1:
            gx = total_w_units - gx - gw
        x = cx - (total_w_units * PIXEL_SIZE) / 2 + gx * PIXEL_SIZE
        y = top_y + gy * PIXEL_SIZE * v_scale
        pygame.draw.rect(surface, palette[key], (x, y, gw * PIXEL_SIZE, gh * PIXEL_SIZE * v_scale))


def draw_cloud(surface, x, y, color=None):
    for dx, dy, r in [(-24, 4, 20), (0, -6, 26), (26, 4, 20), (50, 6, 16)]:
        pygame.draw.circle(surface, color or CLOUD_COLOR, (x + dx, y + dy), r)


def draw_flame(surface, base_x, base_y, scale=1.0):
    """A little flame standing on its base point, tip pointing up."""
    pygame.draw.polygon(surface, (200, 60, 20), [
        (base_x, base_y - 26 * scale), (base_x - 10 * scale, base_y), (base_x + 10 * scale, base_y),
    ])
    pygame.draw.polygon(surface, (240, 150, 40), [
        (base_x, base_y - 14 * scale), (base_x - 5 * scale, base_y), (base_x + 5 * scale, base_y),
    ])


STAR_SPOTS = [(60, 40), (140, 90), (300, 30), (500, 70), (650, 40), (800, 90), (380, 120), (200, 150), (720, 140)]
NIGHT_FIRE_SPOTS = [220, 520, 760]
HELL_FIRE_SPOTS = [150, 320, 480, 640, 800]


def draw_background(surface, phase):
    """Each phase is a later hour of the same fight — day, evening, night,
    night with fire creeping in, then the inferno."""
    if phase == 1:
        surface.fill(SKY_COLOR)
        pygame.draw.circle(surface, SUN_COLOR, (WIDTH - 120, 100), 46)
        for cx, cy in [(150, 90), (420, 60), (650, 110)]:
            draw_cloud(surface, cx, cy)
        pygame.draw.rect(surface, GROUND_COLOR, (0, GROUND_Y + 10, WIDTH, HEIGHT - GROUND_Y))
        for gx in range(10, WIDTH, 16):
            pygame.draw.line(surface, GRASS_DARK, (gx, GROUND_Y + 10), (gx - 4, GROUND_Y), 2)
    elif phase == 2:
        surface.fill((255, 170, 95))
        pygame.draw.circle(surface, (255, 130, 60), (WIDTH - 150, 190), 56)
        for cx, cy in [(150, 90), (420, 60), (650, 110)]:
            draw_cloud(surface, cx, cy, (255, 205, 160))
        pygame.draw.rect(surface, (120, 108, 58), (0, GROUND_Y + 10, WIDTH, HEIGHT - GROUND_Y))
        for gx in range(10, WIDTH, 16):
            pygame.draw.line(surface, (80, 70, 35), (gx, GROUND_Y + 10), (gx - 4, GROUND_Y), 2)
    elif phase == 3:
        surface.fill((16, 16, 42))
        pygame.draw.circle(surface, (225, 225, 210), (WIDTH - 130, 90), 34)
        for sx, sy in STAR_SPOTS:
            pygame.draw.circle(surface, (230, 230, 230), (sx, sy), 2)
        pygame.draw.rect(surface, (35, 48, 38), (0, GROUND_Y + 10, WIDTH, HEIGHT - GROUND_Y))
    elif phase == 4:
        surface.fill((34, 16, 24))
        pygame.draw.circle(surface, (200, 190, 180), (WIDTH - 130, 90), 30)
        for sx, sy in STAR_SPOTS:
            pygame.draw.circle(surface, (210, 190, 190), (sx, sy), 2)
        pygame.draw.rect(surface, (44, 32, 28), (0, GROUND_Y + 10, WIDTH, HEIGHT - GROUND_Y))
        for fx in NIGHT_FIRE_SPOTS:
            draw_flame(surface, fx, GROUND_Y + 10, scale=0.8)
    else:
        surface.fill((120, 20, 20))
        pygame.draw.rect(surface, (70, 10, 10), (0, GROUND_Y - 90, WIDTH, 90))
        pygame.draw.rect(surface, (18, 12, 12), (0, GROUND_Y + 10, WIDTH, HEIGHT - GROUND_Y))
        for fx in HELL_FIRE_SPOTS:
            draw_flame(surface, fx, GROUND_Y + 10, scale=1.1)


# ─────────────────────────────────────────────────────────────────────────────
#  Fighters
# ─────────────────────────────────────────────────────────────────────────────


PLAYER_UNITS_W = 14
PLAYER_UNITS_H = 20

PLAYER_PALETTE = {
    "hair": PLAYER_HAIR,
    "skin": PLAYER_SKIN,
    "band": PLAYER_HEADBAND,
    "shorts": PLAYER_SHORTS,
    "bandage": PLAYER_BANDAGE,
    "shoes": PLAYER_SHOES,
}


def build_player_blocks(attacking, attack_type):
    front_arm_w = 8 if attacking and attack_type == "punch" else 2
    front_leg_w = 9 if attacking and attack_type == "kick" else 3
    return [
        (4, 0, 6, 2, "hair"),
        (4, 2, 6, 3, "skin"),
        (4, 3, 6, 1, "band"),
        (3, 5, 8, 1, "skin"),
        (3, 6, 8, 5, "skin"),
        (3, 11, 8, 2, "shorts"),
        (1, 7, 2, 4, "bandage"),
        (11, 7, front_arm_w, 4, "bandage"),
        (3, 13, 3, 6, "skin"),
        (8, 13, front_leg_w, 6, "skin"),
        (3, 19, 3, 1, "shoes"),
        (8, 19, 3, 1, "shoes"),
    ]


class Player:
    def __init__(self):
        self.reset()

    def reset(self):
        self.x = WIDTH * 0.25
        self.facing = 1
        self.air_height = 0.0
        self.vy = 0.0
        self.on_ground = True
        self.crouching = False
        self.health = PLAYER_MAX_HEALTH
        self.special = 0.0
        self.attack_timer = 0.0
        self.attack_cooldown = 0.0
        self.attack_type = None
        self.attack_registered = False
        self.stun_timer = 0.0

    def update(self, dt, keys, opponent_x):
        self.facing = 1 if opponent_x >= self.x else -1

        if self.stun_timer > 0:
            self.stun_timer = max(0.0, self.stun_timer - dt)
        else:
            self.crouching = self.on_ground and keys[pygame.K_DOWN]
            if not self.crouching:
                moving = 0
                if keys[pygame.K_LEFT]:
                    moving -= 1
                if keys[pygame.K_RIGHT]:
                    moving += 1
                self.x += moving * MOVE_SPEED * dt
                self.x = max(ARENA_LEFT, min(ARENA_RIGHT, self.x))
                if keys[pygame.K_UP] and self.on_ground:
                    self.vy = JUMP_SPEED
                    self.on_ground = False

        if not self.on_ground:
            self.vy -= GRAVITY * dt
            self.air_height += self.vy * dt
            if self.air_height <= 0:
                self.air_height = 0.0
                self.vy = 0.0
                self.on_ground = True

        self.attack_cooldown = max(0.0, self.attack_cooldown - dt)
        if self.attack_timer > 0:
            self.attack_timer -= dt
            if self.attack_timer <= 0:
                self.attack_registered = False

        self.special = min(SPECIAL_MAX, self.special + SPECIAL_PER_SECOND * dt)

    def reset_for_new_phase(self):
        """New phase: your health is fully restored, but your special bar
        keeps whatever charge it already had."""
        self.health = PLAYER_MAX_HEALTH

    def try_attack(self):
        if self.attack_cooldown <= 0 and self.stun_timer <= 0:
            self.attack_type = "kick" if self.crouching else "punch"
            self.attack_timer = ATTACK_ACTIVE_TIME
            self.attack_cooldown = ATTACK_COOLDOWN
            self.attack_registered = False

    def try_special(self):
        if self.special >= SPECIAL_MAX and self.stun_timer <= 0:
            self.special = 0.0
            return True
        return False

    def draw(self, surface):
        v_scale = 0.62 if self.crouching else 1.0
        top_y = GROUND_Y - PLAYER_UNITS_H * PIXEL_SIZE * v_scale - self.air_height
        blocks = build_player_blocks(self.attack_timer > 0, self.attack_type)
        draw_pixel_sprite(surface, blocks, PLAYER_PALETTE, self.x, top_y, self.facing, PLAYER_UNITS_W, v_scale)


ROBOT_UNITS_W = 14
ROBOT_UNITS_H = 20

ROBOT_PALETTE_BASE = {
    "head": ROBOT_SKIN,
    "torso_peek": ROBOT_SKIN,
    "arm_l": ROBOT_SKIN,
    "arm_r": ROBOT_SKIN,
    "clothing": ROBOT_CLOTHING,
    "pants": ROBOT_PANTS,
    "leg_l": ROBOT_PANTS,
    "leg_r": ROBOT_PANTS,
    "boot_l": ROBOT_BOOTS,
    "boot_r": ROBOT_BOOTS,
}

# Which body parts have lost their skin and show bare metal, one phase's
# worth added on top of the last — by phase 5 it's a walking skeleton.
DEGRADE_PARTS_BY_PHASE = [
    [],
    ["arm_r"],
    ["arm_r", "arm_l"],
    ["arm_r", "arm_l", "leg_r"],
    ["arm_r", "arm_l", "leg_r", "leg_l", "head", "torso_peek"],
]

# Five phases, five fighting styles. `low_kick` styles can be dodged by
# jumping; `guard_chance` styles mostly block unless you catch them right
# after their own attack (recovery_window); `dash` styles rush in fast and
# are wide open for a moment right after. `symbol_color` is a small, easy to
# miss marking that changes with the style — the only outward clue.
STYLES = [
    {
        "name": "boxeador",
        "move_speed": 170,
        "attack_type": "punch",
        "attack_cooldown": 1.0,
        "damage": PUNCH_DAMAGE,
        "low_kick": False,
        "guard_chance": 0.0,
        "dash": False,
        "symbol_color": (230, 200, 40),
    },
    {
        "name": "patadas bajas",
        "move_speed": 190,
        "attack_type": "kick",
        "attack_cooldown": 1.15,
        "damage": KICK_DAMAGE + 4,
        "low_kick": True,
        "guard_chance": 0.0,
        "dash": False,
        "symbol_color": (230, 130, 40),
    },
    {
        "name": "guardia",
        "move_speed": 150,
        "attack_type": "punch",
        "attack_cooldown": 1.3,
        "damage": PUNCH_DAMAGE + 6,
        "low_kick": False,
        "guard_chance": 0.65,
        "dash": False,
        "symbol_color": (90, 170, 230),
    },
    {
        "name": "embestida",
        "move_speed": 150,
        "attack_type": "punch",
        "attack_cooldown": 1.6,
        "damage": PUNCH_DAMAGE + 8,
        "low_kick": False,
        "guard_chance": 0.0,
        "dash": True,
        "symbol_color": (220, 60, 60),
    },
    {
        "name": "mixto",
        "move_speed": 210,
        "attack_type": "mixed",
        "attack_cooldown": 0.8,
        "damage": KICK_DAMAGE + 10,
        "low_kick": True,
        "guard_chance": 0.3,
        "dash": True,
        "symbol_color": (200, 90, 220),
    },
]


def build_robot_blocks(attacking, attack_type):
    attacking_punch = attacking and attack_type == "punch"
    attacking_kick = attacking and attack_type == "kick"
    front_arm_w = 8 if attacking_punch else 2
    front_leg_w = 9 if attacking_kick else 3
    return [
        (4, 0, 6, 4, "head"),
        (5, 4, 4, 1, "head"),
        (2, 6, 10, 5, "clothing"),
        (3, 5, 8, 1, "torso_peek"),
        (1, 6, 2, 5, "arm_l"),
        (11, 6, front_arm_w, 5, "arm_r"),
        (3, 11, 8, 2, "pants"),
        (3, 13, 3, 5, "leg_l"),
        (8, 13, front_leg_w, 5, "leg_r"),
        (3, 18, 3, 2, "boot_l"),
        (8, 18, 3, 2, "boot_r"),
    ]


class Robot:
    def __init__(self, phase):
        self.phase = phase
        self.style = STYLES[phase - 1]
        self.reset()

    def reset(self):
        self.x = WIDTH * 0.75
        self.facing = -1
        self.max_health = ROBOT_MAX_HEALTH_BY_PHASE[self.phase - 1]
        self.health = self.max_health
        self.attack_timer = 0.0
        self.attack_cooldown = 1.0
        self.attack_type = "punch"
        self.attack_registered = False
        self.stun_timer = 0.0
        self.dash_cooldown = 0.0
        self.recovery_timer = 0.0
        self.attack_cycle = 0

    def update(self, dt, player_x):
        self.facing = 1 if player_x >= self.x else -1

        if self.stun_timer > 0:
            self.stun_timer = max(0.0, self.stun_timer - dt)
        else:
            distance = abs(player_x - self.x)
            dashing = self.style["dash"] and distance > ATTACK_RANGE * 1.3 and self.dash_cooldown <= 0
            speed = self.style["move_speed"] * (3.0 if dashing else 1.0)
            if distance > ATTACK_RANGE * 0.85:
                self.x += self.facing * speed * dt
                self.x = max(ARENA_LEFT, min(ARENA_RIGHT, self.x))

            self.attack_cooldown = max(0.0, self.attack_cooldown - dt)
            distance = abs(player_x - self.x)
            if distance <= ATTACK_RANGE and self.attack_cooldown <= 0:
                self._start_attack()

        self.dash_cooldown = max(0.0, self.dash_cooldown - dt)
        self.recovery_timer = max(0.0, self.recovery_timer - dt)
        if self.attack_timer > 0:
            self.attack_timer -= dt
            if self.attack_timer <= 0:
                self.attack_registered = False

    def _start_attack(self):
        attack_type = self.style["attack_type"]
        if attack_type == "mixed":
            attack_type = "kick" if self.attack_cycle % 2 == 0 else "punch"
            self.attack_cycle += 1
        self.attack_type = attack_type
        self.attack_timer = ATTACK_ACTIVE_TIME
        self.attack_cooldown = self.style["attack_cooldown"]
        self.attack_registered = False
        if self.style["dash"]:
            self.dash_cooldown = 0.5
            self.recovery_timer = 0.6   # wide open right after a dash-attack

    def draw(self, surface):
        top_y = GROUND_Y - ROBOT_UNITS_H * PIXEL_SIZE
        blocks = build_robot_blocks(self.attack_timer > 0, self.attack_type)

        palette = dict(ROBOT_PALETTE_BASE)
        for key in DEGRADE_PARTS_BY_PHASE[self.phase - 1]:
            palette[key] = ROBOT_METAL
        flash = self.stun_timer > 0 and int(self.stun_timer * 10) % 2 == 0
        if flash:
            palette = {key: ROBOT_METAL for key in palette}

        draw_pixel_sprite(surface, blocks, palette, self.x, top_y, self.facing, ROBOT_UNITS_W)

        eye_x = self.x + self.facing * 8
        eye_y = top_y + PIXEL_SIZE * 2
        pygame.draw.circle(surface, ROBOT_EYE, (eye_x, eye_y), 5)

        # The one clue to its fighting style — small enough that you have to
        # be paying attention to notice it changed.
        symbol_x = self.x - self.facing * 10
        symbol_y = top_y + PIXEL_SIZE * 7
        pygame.draw.rect(surface, self.style["symbol_color"], (symbol_x - 3, symbol_y - 3, 6, 6))

        if self.phase == PHASE_COUNT:
            flicker = (pygame.time.get_ticks() // 150) % 2
            for dx in (-14, 0, 16):
                draw_flame(surface, self.x + dx, top_y + PIXEL_SIZE * (7 + flicker), scale=0.55)


# ─────────────────────────────────────────────────────────────────────────────
#  The game
# ─────────────────────────────────────────────────────────────────────────────


class Game:
    def __init__(self):
        self.start_new_game()

    def start_new_game(self):
        self.phase = 1
        self.player = Player()
        self.robot = Robot(self.phase)
        self.score = 0
        self.over = False
        reset_score()
        submit_score(0)

    def add_score(self, points):
        multiplier = SCORE_MULTIPLIER_BY_PHASE[self.phase - 1]
        self.score += round(points * multiplier)
        submit_score(self.score)

    def update(self, dt, keys):
        if self.over:
            return
        self.player.update(dt, keys, self.robot.x)
        self.robot.update(dt, self.player.x)
        self._resolve_attack(self.player, self.robot, scores=True)
        self._resolve_attack(self.robot, self.player, scores=False)

        if self.robot.health <= 0:
            self._advance_phase()

        if self.player.health <= 0:
            self.over = True
            game_over(self.score)

    def _advance_phase(self):
        self.add_score(SCORE_PER_ROBOT_DOWN)
        self.phase = min(PHASE_COUNT, self.phase + 1)
        self.player.reset_for_new_phase()
        self.robot = Robot(self.phase)

    def _resolve_attack(self, attacker, defender, scores):
        if not (attacker.attack_timer > 0 and not attacker.attack_registered):
            return
        if abs(attacker.x - defender.x) > ATTACK_RANGE:
            return
        attacker.attack_registered = True

        robot_style = attacker.style if attacker is self.robot else None
        if robot_style and robot_style["low_kick"] and attacker.attack_type == "kick" and defender.air_height > 0:
            return   # dodged by jumping over the low kick

        if robot_style:
            damage = robot_style["damage"]
        else:
            damage = KICK_DAMAGE if attacker.attack_type == "kick" else PUNCH_DAMAGE

        if defender is self.robot:
            damage = self._through_guard(damage)

        defender.health = max(0, defender.health - damage)
        if scores:
            self.add_score(SCORE_PER_HIT)
            self.player.special = min(SPECIAL_MAX, self.player.special + SPECIAL_PER_HIT)

    def _through_guard(self, damage):
        robot = self.robot
        if robot.recovery_timer > 0:
            return round(damage * 1.5)   # caught it right after its own attack
        if robot.style["guard_chance"] > 0 and random.random() < robot.style["guard_chance"]:
            return 1   # blocked — just a chip of damage gets through
        return damage

    def use_special(self, kind):
        if self.over or not self.player.try_special():
            return
        if kind == "stun":
            self.robot.stun_timer = STUN_DURATION
        else:
            self.robot.health = max(0, self.robot.health - SPECIAL_DAMAGE)
            self.add_score(SCORE_PER_SPECIAL)

    def draw(self, surface):
        draw_background(surface, self.phase)

        self.robot.draw(surface)
        self.player.draw(surface)

        draw_bar(surface, 30, 24, 300, 22, self.player.health / PLAYER_MAX_HEALTH, (60, 200, 90))
        draw_bar(surface, 30, 52, 160, 12, self.player.special / SPECIAL_MAX, (80, 160, 230))
        draw_bar(surface, WIDTH - 330, 24, 300, 22, self.robot.health / self.robot.max_health, (210, 60, 60))

        draw_text(surface, f"FASE {self.phase}/{PHASE_COUNT}", (WIDTH / 2, 20), size=26, align="center")
        draw_text(surface, f"SCORE {self.score}", (WIDTH / 2, 54), size=18, align="center")
        draw_text(surface, "Z: ATURDIR   X: DAÑO", (WIDTH - 20, HEIGHT - 30), size=16, align="right")

        if self.over:
            draw_text(surface, "GAME OVER", (WIDTH / 2, HEIGHT / 2 - 60), size=60, align="center")
            draw_text(surface, f"SCORE {self.score}", (WIDTH / 2, HEIGHT / 2 + 8), size=30, align="center")
            draw_text(surface, "PRESS R TO PLAY AGAIN", (WIDTH / 2, HEIGHT / 2 + 54), size=22, align="center")


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
                if event.key == pygame.K_SPACE:
                    game.player.try_attack()
                elif event.key == pygame.K_z:
                    game.use_special("stun")
                elif event.key == pygame.K_x:
                    game.use_special("damage")
                elif event.key == pygame.K_r and game.over:
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
