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

BACKGROUND = (0, 0, 0)
LINE_COLOR = (255, 255, 255)
GROUND_COLOR = (120, 120, 120)
LINE_WIDTH = 2
FONT_NAME = None

GROUND_Y = HEIGHT - 120          # how far up from the top the ground line sits
PLAYER_X = 140                   # how far from the left edge the goat stands
PLAYER_SIZE = 34                 # how big the goat is (scales the whole shape)

GRAVITY = 1800                   # how hard you're pulled back down
JUMP_SPEED = 780                 # how fast you launch upward when you jump

OBSTACLE_SPEED = 340              # how fast obstacles scroll toward you
OBSTACLE_WIDTH = 30               # how wide an obstacle is
OBSTACLE_HEIGHT = 46              # how tall an obstacle is
OBSTACLE_MIN_GAP = 0.9            # seconds, shortest time between obstacles
OBSTACLE_MAX_GAP = 1.8            # seconds, longest time between obstacles

POINTS_PER_OBSTACLE = 67          # score for clearing one obstacle

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


class Player:
    def __init__(self):
        self.x = PLAYER_X
        self.y = GROUND_Y          # y of the goat's feet
        self.vy = 0.0
        self.on_ground = True

    def jump(self):
        if self.on_ground:
            self.vy = -JUMP_SPEED
            self.on_ground = False

    def update(self, dt):
        self.vy += GRAVITY * dt
        self.y += self.vy * dt
        if self.y >= GROUND_Y:
            self.y = GROUND_Y
            self.vy = 0.0
            self.on_ground = True

    def rect(self):
        scale = PLAYER_SIZE / 34
        left = self.x - 24 * scale
        top = self.y - 32 * scale
        return pygame.Rect(left, top, 49 * scale, 32 * scale)

    def draw(self, surface):
        scale = PLAYER_SIZE / 34

        def pt(dx, dy):
            return (self.x + dx * scale, self.y + dy * scale)

        pygame.draw.polygon(surface, LINE_COLOR, [pt(dx, dy) for dx, dy in GOAT_BODY], LINE_WIDTH)
        for x1, y1, x2, y2 in GOAT_LEGS:
            pygame.draw.line(surface, LINE_COLOR, pt(x1, y1), pt(x2, y2), LINE_WIDTH)
        pygame.draw.line(surface, LINE_COLOR, pt(*GOAT_TAIL[0]), pt(*GOAT_TAIL[1]), LINE_WIDTH)


# ─────────────────────────────────────────────────────────────────────────────
#  Obstacles
# ─────────────────────────────────────────────────────────────────────────────


class Obstacle:
    def __init__(self):
        self.width = OBSTACLE_WIDTH
        self.height = OBSTACLE_HEIGHT
        self.x = WIDTH + self.width
        self.scored = False

    def update(self, dt):
        self.x -= OBSTACLE_SPEED * dt

    def rect(self):
        return pygame.Rect(self.x, GROUND_Y - self.height, self.width, self.height)

    def off_screen(self):
        return self.x + self.width < 0

    def draw(self, surface):
        pygame.draw.rect(surface, LINE_COLOR, self.rect(), LINE_WIDTH)


# ─────────────────────────────────────────────────────────────────────────────
#  Game
# ─────────────────────────────────────────────────────────────────────────────


class Game:
    def __init__(self):
        self.player = Player()
        self.obstacles = []
        self.spawn_timer = random.uniform(OBSTACLE_MIN_GAP, OBSTACLE_MAX_GAP)
        self.score = 0
        self.over = False

    def spawn_obstacle(self):
        self.obstacles.append(Obstacle())
        self.spawn_timer = random.uniform(OBSTACLE_MIN_GAP, OBSTACLE_MAX_GAP)

    def update(self, dt):
        if self.over:
            return

        self.player.update(dt)

        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            self.spawn_obstacle()

        player_rect = self.player.rect()
        for obstacle in self.obstacles:
            obstacle.update(dt)

            if not obstacle.scored and obstacle.x + obstacle.width < self.player.x:
                obstacle.scored = True
                self.score += POINTS_PER_OBSTACLE
                submit_score(self.score)

            if player_rect.colliderect(obstacle.rect()):
                self.over = True
                game_over(self.score)

        self.obstacles = [o for o in self.obstacles if not o.off_screen()]

    def draw(self, surface, font):
        surface.fill(BACKGROUND)

        pygame.draw.line(surface, GROUND_COLOR, (0, GROUND_Y), (WIDTH, GROUND_Y), LINE_WIDTH)

        self.player.draw(surface)
        for obstacle in self.obstacles:
            obstacle.draw(surface)

        score_surf = font.render(f"Score: {self.score}", True, LINE_COLOR)
        surface.blit(score_surf, (20, 20))

        if self.over:
            msg = font.render("GAME OVER — press R to restart", True, LINE_COLOR)
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

        game.update(dt)
        game.draw(screen, font)
        pygame.display.flip()

        await asyncio.sleep(0)

    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
