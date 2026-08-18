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

ROBOT_SKIN = (214, 176, 150)
ROBOT_METAL = (140, 148, 158)
ROBOT_EYE = (220, 40, 40)

PLAYER_MAX_HEALTH = 100
ROBOT_MAX_HEALTH = 100

MOVE_SPEED = 230
JUMP_SPEED = 560
GRAVITY = 1500

PUNCH_DAMAGE = 6
KICK_DAMAGE = 10
ATTACK_RANGE = 82
ATTACK_ACTIVE_TIME = 0.12
ATTACK_COOLDOWN = 0.35

ROBOT_MOVE_SPEED = 170
ROBOT_ATTACK_COOLDOWN = 1.1

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


# ─────────────────────────────────────────────────────────────────────────────
#  Fighters
# ─────────────────────────────────────────────────────────────────────────────


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
        scale = 0.62 if self.crouching else 1.0
        body_h = 100 * scale
        top = GROUND_Y - body_h - self.air_height
        cx = self.x
        f = self.facing

        pygame.draw.rect(surface, PLAYER_SKIN, (cx - 16, top + body_h * 0.62, 12, body_h * 0.38))
        pygame.draw.rect(surface, PLAYER_SKIN, (cx + 4, top + body_h * 0.62, 12, body_h * 0.38))

        pygame.draw.rect(surface, PLAYER_SKIN, (cx - 17, top + body_h * 0.22, 34, body_h * 0.42))
        pygame.draw.rect(surface, PLAYER_SHORTS, (cx - 17, top + body_h * 0.58, 34, body_h * 0.14))

        arm_len = 34 if self.attack_timer > 0 and self.attack_type == "punch" else 16
        arm_y = top + body_h * 0.32
        pygame.draw.rect(surface, PLAYER_BANDAGE, (cx + f * 6, arm_y, f * arm_len, 9))

        if self.attack_timer > 0 and self.attack_type == "kick":
            pygame.draw.rect(surface, PLAYER_SKIN, (cx + f * 6, top + body_h * 0.74, f * 40, 10))

        head_r = body_h * 0.16
        head_center = (cx, top + head_r)
        pygame.draw.circle(surface, PLAYER_SKIN, head_center, head_r)
        pygame.draw.rect(surface, PLAYER_HAIR, (cx - head_r, top, head_r * 2, head_r * 1.1))
        pygame.draw.rect(
            surface, PLAYER_HEADBAND,
            (cx - head_r, top + head_r * 0.75, head_r * 2, head_r * 0.28),
        )


class Robot:
    def __init__(self):
        self.reset()

    def reset(self):
        self.x = WIDTH * 0.75
        self.facing = -1
        self.health = ROBOT_MAX_HEALTH
        self.attack_timer = 0.0
        self.attack_cooldown = 1.0
        self.attack_type = "punch"
        self.attack_registered = False
        self.stun_timer = 0.0

    def update(self, dt, player_x):
        self.facing = 1 if player_x >= self.x else -1

        if self.stun_timer > 0:
            self.stun_timer = max(0.0, self.stun_timer - dt)
        else:
            distance = abs(player_x - self.x)
            if distance > ATTACK_RANGE * 0.85:
                self.x += self.facing * ROBOT_MOVE_SPEED * dt
                self.x = max(ARENA_LEFT, min(ARENA_RIGHT, self.x))
            self.attack_cooldown = max(0.0, self.attack_cooldown - dt)
            if distance <= ATTACK_RANGE and self.attack_cooldown <= 0:
                self.attack_type = "punch"
                self.attack_timer = ATTACK_ACTIVE_TIME
                self.attack_cooldown = ROBOT_ATTACK_COOLDOWN
                self.attack_registered = False

        if self.attack_timer > 0:
            self.attack_timer -= dt
            if self.attack_timer <= 0:
                self.attack_registered = False

    def draw(self, surface):
        body_h = 105
        top = GROUND_Y - body_h
        cx = self.x
        f = self.facing
        flash = self.stun_timer > 0 and int(self.stun_timer * 10) % 2 == 0
        skin = ROBOT_METAL if flash else ROBOT_SKIN

        pygame.draw.rect(surface, skin, (cx - 16, top + body_h * 0.60, 12, body_h * 0.40))
        pygame.draw.rect(surface, skin, (cx + 4, top + body_h * 0.60, 12, body_h * 0.40))
        pygame.draw.rect(surface, skin, (cx - 18, top + body_h * 0.20, 36, body_h * 0.42))

        arm_len = 34 if self.attack_timer > 0 else 16
        pygame.draw.rect(surface, skin, (cx + f * 6, top + body_h * 0.30, f * arm_len, 10))

        head_r = body_h * 0.16
        head_center = (cx, top + head_r)
        pygame.draw.circle(surface, skin, head_center, head_r)
        pygame.draw.circle(
            surface, ROBOT_EYE, (head_center[0] + f * head_r * 0.4, head_center[1]), head_r * 0.22
        )


# ─────────────────────────────────────────────────────────────────────────────
#  The game
# ─────────────────────────────────────────────────────────────────────────────


class Game:
    def __init__(self):
        self.start_new_game()

    def start_new_game(self):
        self.player = Player()
        self.robot = Robot()
        self.score = 0
        self.over = False
        reset_score()
        submit_score(0)

    def add_score(self, points):
        self.score += points
        submit_score(self.score)

    def update(self, dt, keys):
        if self.over:
            return
        self.player.update(dt, keys, self.robot.x)
        self.robot.update(dt, self.player.x)
        self._resolve_attack(self.player, self.robot, scores=True)
        self._resolve_attack(self.robot, self.player, scores=False)

        if self.robot.health <= 0:
            self.add_score(SCORE_PER_ROBOT_DOWN)
            self.robot.reset()

        if self.player.health <= 0:
            self.over = True
            game_over(self.score)

    def _resolve_attack(self, attacker, defender, scores):
        if attacker.attack_timer > 0 and not attacker.attack_registered:
            if abs(attacker.x - defender.x) <= ATTACK_RANGE:
                damage = KICK_DAMAGE if attacker.attack_type == "kick" else PUNCH_DAMAGE
                defender.health = max(0, defender.health - damage)
                attacker.attack_registered = True
                if scores:
                    self.add_score(SCORE_PER_HIT)
                    self.player.special = min(SPECIAL_MAX, self.player.special + SPECIAL_PER_HIT)

    def use_special(self, kind):
        if self.over or not self.player.try_special():
            return
        if kind == "stun":
            self.robot.stun_timer = STUN_DURATION
        else:
            self.robot.health = max(0, self.robot.health - SPECIAL_DAMAGE)
            self.add_score(SCORE_PER_SPECIAL)

    def draw(self, surface):
        surface.fill(SKY_COLOR)
        pygame.draw.rect(surface, GROUND_COLOR, (0, GROUND_Y + 10, WIDTH, HEIGHT - GROUND_Y))

        self.robot.draw(surface)
        self.player.draw(surface)

        draw_bar(surface, 30, 24, 300, 22, self.player.health / PLAYER_MAX_HEALTH, (60, 200, 90))
        draw_bar(surface, 30, 52, 160, 12, self.player.special / SPECIAL_MAX, (80, 160, 230))
        draw_bar(surface, WIDTH - 330, 24, 300, 22, self.robot.health / ROBOT_MAX_HEALTH, (210, 60, 60))

        draw_text(surface, f"SCORE {self.score}", (WIDTH / 2, 20), size=28, align="center")
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
