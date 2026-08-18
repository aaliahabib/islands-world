"""JUMPER — your island's game.

A goat jogs along the ground and jumps over obstacles rushing in from the
right. Clear one and score; hit one and it's game over.

    SPACE  (or UP)   jump
    R                restart after game over

This is YOUR game now. The fastest way to make it yours is the CUSTOMIZE block
just below — change the colours, how high you jump, how fast obstacles come at
you. Then run it and see what happened. After that, ask Claude for bigger
changes.

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

TITLE = "Jumper Island"

WIDTH = 900
HEIGHT = 700

BACKGROUND = (4, 4, 12)           # near-black so the glow colours pop
GOAT_COLOR = (57, 255, 20)        # neon green glow
GROUND_COLOR = (0, 255, 255)      # neon cyan glow
TEXT_COLOR = (255, 255, 0)        # neon yellow glow
LINE_WIDTH = 2
FONT_NAME = None

GROUND_Y = HEIGHT - 120          # how far up from the top the ground line sits
PLAYER_X = 140                   # how far from the left edge the goat stands
PLAYER_SIZE = 34                 # how big the goat is (scales the whole shape)
DUCK_HEIGHT = 16                 # how tall the goat's hitbox is while ducking

GRAVITY = 1800                   # how hard you're pulled back down
JUMP_SPEED = 780                 # how fast you launch upward when you jump

OBSTACLE_SPEED = 340              # how fast obstacles scroll toward you
OBSTACLE_MIN_GAP = 0.9            # seconds, shortest time between obstacles
OBSTACLE_MAX_GAP = 1.8            # seconds, longest time between obstacles

OBSTACLE_COLOR = (255, 20, 147)      # neon pink glow — jump over these
OBSTACLE_WIDTH = 30                  # how wide a jump obstacle is
OBSTACLE_HEIGHT = 46                 # how tall a jump obstacle is

TALL_OBSTACLE_COLOR = (191, 0, 255)  # neon purple glow — double-jump over these
TALL_OBSTACLE_HEIGHT = 210           # taller than one jump can clear on its own

DUCK_OBSTACLE_COLOR = (255, 140, 0)  # neon orange glow — duck under these
DUCK_OBSTACLE_WIDTH = 70             # duck obstacles are wide bars
DUCK_OBSTACLE_HEIGHT = 40            # how thick the floating bar is
DUCK_CLEARANCE = 20                  # gap between the ground and the bar

POINTS_PER_OBSTACLE = 67          # score for clearing one obstacle

LEAF_COLOR = (180, 255, 60)       # neon leaf-green glow
LEAF_ALTITUDE = 120               # how high above the ground the leaf floats
LEAF_MIN_GAP = 15                 # seconds, shortest time between leaves
LEAF_MAX_GAP = 20                 # seconds, longest time between leaves

FLIGHT_DURATION = 4.0             # seconds of flight after catching a leaf
FLIGHT_ALTITUDE = 250             # how high the goat soars while flying

# ─────────────────────────────────────────────────────────────────────────────
#  Player
# ─────────────────────────────────────────────────────────────────────────────

# The goat's outline, drawn as straight lines just like everything else in
# this game. Points are (x, y) offsets from the goat's feet, at PLAYER_SIZE 34
# — change PLAYER_SIZE above to scale the whole shape up or down.
GOAT_BODY = [
    (-16, -8), (-18, -16), (-10, -26), (4, -28), (10, -26), (14, -32),
    (18, -26), (23, -20), (25, -15), (20, -10), (16, -8),
]
GOAT_LEGS = [(-14, -8, -14, 0), (-6, -8, -6, 0), (8, -8, 8, 0), (15, -8, 15, 0)]
GOAT_TAIL = [(-18, -16), (-24, -10)]

# Airplane wings that appear while the goat is flying, same offset style as
# the goat's own shape above.
GOAT_WINGS = [
    [(-10, -20), (-42, -12), (-10, -12)],
    [(10, -20), (42, -12), (10, -12)],
]


class Player:
    def __init__(self):
        self.x = PLAYER_X
        self.y = GROUND_Y          # y of the goat's feet
        self.vy = 0.0
        self.on_ground = True
        self.can_double_jump = False
        self.ducking = False
        self.flying = False
        self.flight_timer = 0.0

    def jump(self):
        if self.on_ground:
            self.vy = -JUMP_SPEED
            self.on_ground = False
            self.can_double_jump = True
        elif self.can_double_jump:
            self.vy = -JUMP_SPEED
            self.can_double_jump = False

    def set_ducking(self, ducking):
        self.ducking = ducking

    def start_flying(self):
        self.flying = True
        self.flight_timer = FLIGHT_DURATION
        self.vy = 0.0
        self.on_ground = False

    def update(self, dt):
        if self.flying:
            self.flight_timer -= dt
            self.y = GROUND_Y - FLIGHT_ALTITUDE
            if self.flight_timer <= 0:
                self.flying = False
            return

        self.vy += GRAVITY * dt
        self.y += self.vy * dt
        if self.y >= GROUND_Y:
            self.y = GROUND_Y
            self.vy = 0.0
            self.on_ground = True

    def rect(self):
        scale = PLAYER_SIZE / 34
        height = (DUCK_HEIGHT if self.ducking else 32) * scale
        left = self.x - 24 * scale
        top = self.y - height
        return pygame.Rect(left, top, 49 * scale, height)

    def draw(self, surface):
        scale = PLAYER_SIZE / 34
        squash = 0.5 if self.ducking else 1.0

        def pt(dx, dy):
            return (self.x + dx * scale, self.y + dy * scale * squash)

        pygame.draw.polygon(surface, GOAT_COLOR, [pt(dx, dy) for dx, dy in GOAT_BODY], LINE_WIDTH)
        for x1, y1, x2, y2 in GOAT_LEGS:
            pygame.draw.line(surface, GOAT_COLOR, pt(x1, y1), pt(x2, y2), LINE_WIDTH)
        pygame.draw.line(surface, GOAT_COLOR, pt(*GOAT_TAIL[0]), pt(*GOAT_TAIL[1]), LINE_WIDTH)

        if self.flying:
            for wing in GOAT_WINGS:
                pygame.draw.polygon(surface, GOAT_COLOR, [pt(dx, dy) for dx, dy in wing], LINE_WIDTH)


# ─────────────────────────────────────────────────────────────────────────────
#  Obstacles
# ─────────────────────────────────────────────────────────────────────────────


class Obstacle:
    width = OBSTACLE_WIDTH
    color = OBSTACLE_COLOR

    def __init__(self):
        self.x = WIDTH + self.width
        self.scored = False

    def update(self, dt):
        self.x -= OBSTACLE_SPEED * dt

    def off_screen(self):
        return self.x + self.width < 0

    def draw(self, surface):
        pygame.draw.rect(surface, self.color, self.rect(), LINE_WIDTH)


class JumpObstacle(Obstacle):
    """A single jump clears these."""

    height = OBSTACLE_HEIGHT

    def rect(self):
        return pygame.Rect(self.x, GROUND_Y - self.height, self.width, self.height)


class DoubleJumpObstacle(JumpObstacle):
    """Taller than one jump can clear — needs a second jump mid-air."""

    height = TALL_OBSTACLE_HEIGHT
    color = TALL_OBSTACLE_COLOR


class DuckObstacle(Obstacle):
    """Floats above the ground — duck to shrink under the gap below it."""

    width = DUCK_OBSTACLE_WIDTH
    height = DUCK_OBSTACLE_HEIGHT
    color = DUCK_OBSTACLE_COLOR

    def rect(self):
        bottom = GROUND_Y - DUCK_CLEARANCE
        return pygame.Rect(self.x, bottom - self.height, self.width, self.height)


OBSTACLE_TYPES = [JumpObstacle, DoubleJumpObstacle, DuckObstacle]

# ─────────────────────────────────────────────────────────────────────────────
#  Leaf prize — catch it to fly for a while
# ─────────────────────────────────────────────────────────────────────────────

LEAF_SHAPE = [(0, -8), (10, 0), (0, 8), (-10, 0)]
LEAF_WIDTH = 20
LEAF_HEIGHT = 16


class Leaf:
    def __init__(self):
        self.x = WIDTH + LEAF_WIDTH
        self.caught = False

    def update(self, dt):
        self.x -= OBSTACLE_SPEED * dt

    def off_screen(self):
        return self.x + LEAF_WIDTH < 0

    def rect(self):
        top = GROUND_Y - LEAF_ALTITUDE - LEAF_HEIGHT / 2
        return pygame.Rect(self.x, top, LEAF_WIDTH, LEAF_HEIGHT)

    def draw(self, surface):
        cx = self.x + LEAF_WIDTH / 2
        cy = GROUND_Y - LEAF_ALTITUDE
        points = [(cx + dx, cy + dy) for dx, dy in LEAF_SHAPE]
        pygame.draw.polygon(surface, LEAF_COLOR, points, LINE_WIDTH)
        pygame.draw.line(surface, LEAF_COLOR, (cx, cy - 8), (cx, cy + 8), LINE_WIDTH)


# ─────────────────────────────────────────────────────────────────────────────
#  Game
# ─────────────────────────────────────────────────────────────────────────────


class Game:
    def __init__(self):
        self.player = Player()
        self.obstacles = []
        self.spawn_timer = random.uniform(OBSTACLE_MIN_GAP, OBSTACLE_MAX_GAP)
        self.leaves = []
        self.leaf_timer = random.uniform(LEAF_MIN_GAP, LEAF_MAX_GAP)
        self.score = 0
        self.over = False

    def spawn_obstacle(self):
        obstacle_cls = random.choice(OBSTACLE_TYPES)
        self.obstacles.append(obstacle_cls())
        self.spawn_timer = random.uniform(OBSTACLE_MIN_GAP, OBSTACLE_MAX_GAP)

    def spawn_leaf(self):
        self.leaves.append(Leaf())
        self.leaf_timer = random.uniform(LEAF_MIN_GAP, LEAF_MAX_GAP)

    def update(self, dt):
        if self.over:
            return

        self.player.update(dt)

        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            self.spawn_obstacle()

        self.leaf_timer -= dt
        if self.leaf_timer <= 0:
            self.spawn_leaf()

        player_rect = self.player.rect()
        for obstacle in self.obstacles:
            obstacle.update(dt)

            if not obstacle.scored and obstacle.x + obstacle.width < self.player.x:
                obstacle.scored = True
                self.score += POINTS_PER_OBSTACLE
                submit_score(self.score)

            if not self.player.flying and player_rect.colliderect(obstacle.rect()):
                self.over = True
                game_over(self.score)

        self.obstacles = [o for o in self.obstacles if not o.off_screen()]

        for leaf in self.leaves:
            leaf.update(dt)
            if not leaf.caught and player_rect.colliderect(leaf.rect()):
                leaf.caught = True
                self.player.start_flying()

        self.leaves = [leaf for leaf in self.leaves if not leaf.caught and not leaf.off_screen()]

    def draw(self, surface, font):
        surface.fill(BACKGROUND)

        pygame.draw.line(surface, GROUND_COLOR, (0, GROUND_Y), (WIDTH, GROUND_Y), LINE_WIDTH)

        self.player.draw(surface)
        for obstacle in self.obstacles:
            obstacle.draw(surface)
        for leaf in self.leaves:
            leaf.draw(surface)

        score_surf = font.render(f"Score: {self.score}", True, TEXT_COLOR)
        surface.blit(score_surf, (20, 20))

        if self.over:
            msg = font.render("GAME OVER — press R to restart", True, TEXT_COLOR)
            rect = msg.get_rect(center=(WIDTH / 2, HEIGHT / 2))
            surface.blit(msg, rect)


# ─────────────────────────────────────────────────────────────────────────────
#  Main loop
# ─────────────────────────────────────────────────────────────────────────────


async def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption(TITLE)
    clock = pygame.time.Clock()
    font = pygame.font.Font(FONT_NAME, 28)

    game = Game()

    running = True
    while running:
        dt = clock.tick(60) / 1000

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_SPACE, pygame.K_UP):
                    game.player.jump()
                elif event.key == pygame.K_r and game.over:
                    reset_score()
                    game = Game()

        game.player.set_ducking(pygame.key.get_pressed()[pygame.K_DOWN])

        game.update(dt)
        game.draw(screen, font)
        pygame.display.flip()

        await asyncio.sleep(0)

    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
