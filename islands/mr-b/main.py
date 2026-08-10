"""PLATFORM JUMPER — your island's game.

Run and jump across randomly placed platforms.

    LEFT / RIGHT  (or A / D)   run
    UP            (or W)       jump
    DOWN          (or S)       drop through the platform you're standing on
    R                          restart after game over

This is YOUR game now. The fastest way to make it yours is the CUSTOMIZE block
just below — change the colours, make the player faster, give yourself more
lives. Then run it and see what happened. After that, ask Claude for bigger
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

TITLE = "Platform Jumper"

WIDTH = 900                      # size of the game window
HEIGHT = 700

BACKGROUND = (12, 12, 32)
FLOOR_COLOR = (90, 65, 45)
PLATFORM_COLOR = (120, 95, 65)
PLAYER_COLOR = (255, 210, 70)
LINE_COLOR = (255, 255, 255)
FONT_NAME = None                 # None = pygame's built-in font

PLAYER_WIDTH = 28
PLAYER_HEIGHT = 40
RUN_SPEED = 280                  # how fast you run left/right
JUMP_SPEED = 780                 # how hard you push off when you jump
GRAVITY = 1500                   # how fast you fall back down

STARTING_LIVES = 3

FLOOR_HEIGHT = 40                # how tall the floor strip is

PLATFORM_ROWS = 4                # how many tiers of platforms above the floor
PLATFORMS_PER_ROW = (2, 3)       # min/max platforms in each tier
PLATFORM_WIDTH = (90, 160)       # min/max width of a platform
PLATFORM_THICKNESS = 18
ROW_GAP = 150                    # vertical space between tiers — must stay
                                  # smaller than how high you can jump!
RESERVED_WIDTH = 160             # a column on the right kept clear for the
                                  # bonus platform, so nothing else blocks it

ENEMY_SIZE = 26
ENEMY_COUNT = 4                  # how many enemies spawn each level
ENEMY_WANDER_SPEED = 60
ENEMY_CHASE_SPEED = 150
CHASE_RADIUS = 200               # how close you need to be before they chase
ENEMY_COLOR = (210, 60, 60)
ENEMY_VULNERABLE_COLOR = (90, 140, 255)   # colour while you can eat them

TOKEN_SIZE = 20
TOKEN_COLOR = (255, 255, 120)
TOKEN_POINTS = 10                # points for a regular token
POWER_TOKEN_COLOR = (110, 200, 255)
POWER_DURATION = 6.0             # seconds you can eat enemies for
BIGJUMP_TOKEN_COLOR = (255, 170, 60)
BIG_JUMP_MULTIPLIER = 1.35       # how much higher you jump once you have it

ENEMY_EAT_POINTS = 25            # points for eating a captured enemy
PLATFORM_POINTS = 10             # points the first time you jump to a platform
LEVEL_CLEAR_SCORE = 100          # points needed (this level) before a new one loads

BONUS_PLATFORM_COLOR = (200, 140, 255)
BONUS_WIDTH = 140
BONUS_GAP = 300                  # height above the floor — too high for a
                                  # normal jump, reachable with the big jump

PLAYER_INVULN_TIME = 1.2         # seconds of blinking safety after a hit

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


# ─────────────────────────────────────────────────────────────────────────────
#  Things in the game
# ─────────────────────────────────────────────────────────────────────────────


class Platform:
    def __init__(self, x, y, width, height, is_bonus=False):
        self.rect = pygame.Rect(x, y, width, height)
        self.is_bonus = is_bonus
        self.scored = False

    def draw(self, surface):
        color = BONUS_PLATFORM_COLOR if self.is_bonus else PLATFORM_COLOR
        pygame.draw.rect(surface, color, self.rect)
        pygame.draw.rect(surface, LINE_COLOR, self.rect, 2)


class Token:
    def __init__(self, x, y, kind):
        self.x = x
        self.y = y
        self.kind = kind  # "power" or "bigjump"

    def rect(self):
        return pygame.Rect(self.x - TOKEN_SIZE / 2, self.y - TOKEN_SIZE / 2, TOKEN_SIZE, TOKEN_SIZE)

    def draw(self, surface):
        color = {"point": TOKEN_COLOR, "power": POWER_TOKEN_COLOR, "bigjump": BIGJUMP_TOKEN_COLOR}[self.kind]
        pygame.draw.circle(surface, color, (int(self.x), int(self.y)), TOKEN_SIZE // 2)
        pygame.draw.circle(surface, LINE_COLOR, (int(self.x), int(self.y)), TOKEN_SIZE // 2, 2)


class Enemy:
    def __init__(self, platform):
        self.platform = platform
        self.x = platform.rect.centerx - ENEMY_SIZE / 2
        self.y = platform.rect.top - ENEMY_SIZE
        self.direction = random.choice((-1, 1))

    def rect(self):
        return pygame.Rect(self.x, self.y, ENEMY_SIZE, ENEMY_SIZE)

    def update(self, dt, player):
        left = self.platform.rect.left
        right = self.platform.rect.right - ENEMY_SIZE

        player_cx = player.x + PLAYER_WIDTH / 2
        player_cy = player.y + PLAYER_HEIGHT / 2
        my_cx = self.x + ENEMY_SIZE / 2
        my_cy = self.y + ENEMY_SIZE / 2
        near = math.hypot(player_cx - my_cx, player_cy - my_cy) < CHASE_RADIUS

        if near:
            self.direction = 1 if player_cx > my_cx else -1
            speed = ENEMY_CHASE_SPEED
        else:
            speed = ENEMY_WANDER_SPEED
            if random.random() < 0.5 * dt:
                self.direction *= -1

        self.x += self.direction * speed * dt
        if self.x <= left:
            self.x, self.direction = left, 1
        elif self.x >= right:
            self.x, self.direction = right, -1

    def draw(self, surface, vulnerable):
        color = ENEMY_VULNERABLE_COLOR if vulnerable else ENEMY_COLOR
        pygame.draw.rect(surface, color, self.rect())
        pygame.draw.rect(surface, LINE_COLOR, self.rect(), 2)


class Player:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False
        self.drop_timer = 0.0
        self.facing = 1
        self.power_timer = 0.0
        self.big_jump_active = False
        self.invuln = 0.0
        self.standing_on = None

    def rect(self):
        return pygame.Rect(self.x, self.y, PLAYER_WIDTH, PLAYER_HEIGHT)

    def update(self, dt, keys, platforms, floor_rect):
        self.power_timer = max(0.0, self.power_timer - dt)
        self.invuln = max(0.0, self.invuln - dt)

        moving = 0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            moving -= 1
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            moving += 1
        if moving:
            self.facing = moving
        self.vx = moving * RUN_SPEED

        jump_pressed = keys[pygame.K_UP] or keys[pygame.K_w]
        if jump_pressed and self.on_ground:
            jump_speed = JUMP_SPEED * (BIG_JUMP_MULTIPLIER if self.big_jump_active else 1.0)
            self.vy = -jump_speed
            self.on_ground = False

        drop_pressed = keys[pygame.K_DOWN] or keys[pygame.K_s]
        if drop_pressed and self.on_ground and self.y + PLAYER_HEIGHT < floor_rect.top:
            self.drop_timer = 0.25
            self.on_ground = False

        self.drop_timer = max(0.0, self.drop_timer - dt)

        old_bottom = self.y + PLAYER_HEIGHT
        self.vy += GRAVITY * dt
        self.x = max(0, min(WIDTH - PLAYER_WIDTH, self.x + self.vx * dt))
        self.y += self.vy * dt
        new_bottom = self.y + PLAYER_HEIGHT

        self.on_ground = False
        self.standing_on = None

        if self.vy >= 0:
            if (
                old_bottom <= floor_rect.top <= new_bottom
                and self.x + PLAYER_WIDTH > floor_rect.left
                and self.x < floor_rect.right
            ):
                self.y = floor_rect.top - PLAYER_HEIGHT
                self.vy = 0
                self.on_ground = True
            elif self.drop_timer <= 0:
                for platform in platforms:
                    prect = platform.rect
                    if (
                        old_bottom <= prect.top <= new_bottom
                        and self.x + PLAYER_WIDTH > prect.left
                        and self.x < prect.right
                    ):
                        self.y = prect.top - PLAYER_HEIGHT
                        self.vy = 0
                        self.on_ground = True
                        self.standing_on = platform
                        break

    def draw(self, surface):
        if self.invuln > 0 and int(self.invuln * 12) % 2 == 0:
            return
        color = PLAYER_COLOR
        if self.power_timer > 0:
            color = POWER_TOKEN_COLOR
        elif self.big_jump_active:
            color = BIGJUMP_TOKEN_COLOR
        pygame.draw.rect(surface, color, self.rect())
        pygame.draw.rect(surface, LINE_COLOR, self.rect(), 2)


# ─────────────────────────────────────────────────────────────────────────────
#  The game
# ─────────────────────────────────────────────────────────────────────────────


def make_platforms():
    """Random tiers of platforms above the floor, low enough to jump to, plus
    one bonus platform in its own clear column that only a big jump can reach."""
    platforms = []
    floor_top = HEIGHT - FLOOR_HEIGHT
    usable_width = WIDTH - RESERVED_WIDTH
    for row in range(1, PLATFORM_ROWS + 1):
        y = floor_top - ROW_GAP * row
        count = random.randint(*PLATFORMS_PER_ROW)
        slot_width = usable_width / count
        for i in range(count):
            width = min(random.uniform(*PLATFORM_WIDTH), slot_width - 20)
            slot_left = slot_width * i
            x = random.uniform(slot_left + 10, slot_left + slot_width - width - 10)
            platforms.append(Platform(x, y - PLATFORM_THICKNESS, width, PLATFORM_THICKNESS))

    bonus_x = random.uniform(usable_width + 10, WIDTH - BONUS_WIDTH - 10)
    bonus_y = floor_top - BONUS_GAP
    platforms.append(Platform(bonus_x, bonus_y, BONUS_WIDTH, PLATFORM_THICKNESS, is_bonus=True))
    return platforms


def make_enemies(platforms):
    regular = [p for p in platforms if not p.is_bonus]
    chosen = random.sample(regular, min(ENEMY_COUNT, len(regular)))
    return [Enemy(p) for p in chosen]


def make_tokens(platforms):
    regular = [p for p in platforms if not p.is_bonus]
    power_platform, bigjump_platform = random.sample(regular, min(2, len(regular)))
    tokens = [
        Token(power_platform.rect.centerx, power_platform.rect.top - TOKEN_SIZE, "power"),
        Token(bigjump_platform.rect.centerx, bigjump_platform.rect.top - TOKEN_SIZE, "bigjump"),
    ]
    for platform in regular:
        if platform is not power_platform and platform is not bigjump_platform:
            tokens.append(Token(platform.rect.centerx, platform.rect.top - TOKEN_SIZE, "point"))
    return tokens


class Game:
    def __init__(self):
        self.start_new_game()

    def start_new_game(self):
        self.floor = pygame.Rect(0, HEIGHT - FLOOR_HEIGHT, WIDTH, FLOOR_HEIGHT)
        self.score = 0
        self.lives = STARTING_LIVES
        self.level = 1
        self.over = False
        reset_score()
        submit_score(0)
        self.start_level()

    def start_level(self):
        self.platforms = make_platforms()
        self.enemies = make_enemies(self.platforms)
        self.tokens = make_tokens(self.platforms)
        self.player = Player(WIDTH / 2 - PLAYER_WIDTH / 2, self.floor.top - PLAYER_HEIGHT)
        self.level_progress = 0

    def next_level(self):
        self.level += 1
        self.start_level()

    def add_score(self, points):
        self.score += points
        self.level_progress += points
        submit_score(self.score)

    def lose_life(self):
        self.lives -= 1
        if self.lives <= 0:
            self.over = True
            game_over(self.score)
        else:
            self.player.x = WIDTH / 2 - PLAYER_WIDTH / 2
            self.player.y = self.floor.top - PLAYER_HEIGHT
            self.player.vx = 0
            self.player.vy = 0
            self.player.power_timer = 0.0
            self.player.big_jump_active = False
            self.player.invuln = PLAYER_INVULN_TIME

    def update(self, dt, keys):
        if self.over:
            return
        self.player.update(dt, keys, self.platforms, self.floor)

        if self.player.standing_on is not None and not self.player.standing_on.scored:
            self.player.standing_on.scored = True
            self.add_score(PLATFORM_POINTS)

        for enemy in self.enemies:
            enemy.update(dt, self.player)

        player_rect = self.player.rect()

        for token in self.tokens[:]:
            if player_rect.colliderect(token.rect()):
                if token.kind == "power":
                    self.player.power_timer = POWER_DURATION
                elif token.kind == "bigjump":
                    self.player.big_jump_active = True
                else:
                    self.add_score(TOKEN_POINTS)
                self.tokens.remove(token)

        if self.player.invuln <= 0:
            for enemy in self.enemies[:]:
                if player_rect.colliderect(enemy.rect()):
                    if self.player.power_timer > 0:
                        self.enemies.remove(enemy)
                        self.add_score(ENEMY_EAT_POINTS)
                    else:
                        self.lose_life()
                    break

        if not self.over and self.level_progress >= LEVEL_CLEAR_SCORE:
            self.next_level()

    def draw(self, surface):
        surface.fill(BACKGROUND)
        pygame.draw.rect(surface, FLOOR_COLOR, self.floor)
        for platform in self.platforms:
            platform.draw(surface)
        for token in self.tokens:
            token.draw(surface)
        for enemy in self.enemies:
            enemy.draw(surface, self.player.power_timer > 0)
        self.player.draw(surface)
        self.draw_hud(surface)

        if self.over:
            draw_text(surface, "GAME OVER", (WIDTH / 2, HEIGHT / 2 - 70), size=64, align="center")
            draw_text(surface, f"SCORE {self.score}", (WIDTH / 2, HEIGHT / 2 + 10),
                      size=34, align="center")
            draw_text(surface, "PRESS R TO PLAY AGAIN", (WIDTH / 2, HEIGHT / 2 + 60),
                      size=24, align="center")

    def draw_hud(self, surface):
        draw_text(surface, str(self.score), (28, 22), size=48)
        draw_text(surface, f"LIVES {self.lives}", (WIDTH - 28, 26), size=24, align="right")
        draw_text(surface, f"LEVEL {self.level}", (WIDTH - 28, 54), size=20, align="right")
        if self.player.power_timer > 0:
            draw_text(surface, "POWER!", (WIDTH / 2, 22), size=24, align="center",
                      color=POWER_TOKEN_COLOR)
        elif self.player.big_jump_active:
            draw_text(surface, "BIG JUMP!", (WIDTH / 2, 22), size=24, align="center",
                      color=BIGJUMP_TOKEN_COLOR)


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
