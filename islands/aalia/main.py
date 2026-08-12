"""BALANCE TREE — your island's game.

Grow a tree by drawing branches. Every branch ends in a heavy coloured disc,
and the tree topples the moment its weight leans further out than its roots
can hold.

    DRAG from the trunk or any branch   grow a new branch
    R                                   start again after it falls

The disc you're about to grow is shown at the end of the branch while you
drag, so you always know how heavy it will be before you let go.

This is YOUR game now. The fastest way to make it yours is the CUSTOMIZE block
just below — change the colours, make the trunk heavier, allow bigger discs.
Then run it and see what happened.

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

TITLE = "Balance Tree"

WIDTH = 900                      # size of the game window
HEIGHT = 700
FPS = 60

BACKGROUND = (244, 243, 240)     # colours are (RED, GREEN, BLUE), 0–255
GROUND_COLOR = (60, 58, 54)
WOOD = (176, 150, 84)            # the gold of the trunk and branches
PENDING = (220, 212, 186)        # a branch you haven't closed a loop on yet
WOOD_SPECKLE = (192, 168, 108)   # flecks up the trunk — keep this close to
TRUNK_SPECKLES = 70              # WOOD, and the count low, or it gets noisy

GROUND_Y = 640                   # how far down the ground line sits
TRUNK_X = 450                    # the trunk stands here
TRUNK_TOP_Y = 430                # and reaches up to here
TRUNK_BASE_HALF = 24             # half its width at the ground
TRUNK_TOP_HALF = 6               # and at the top

BASE_HALF_WIDTH = 36             # how far the weight can sit off-centre before
                                 # the tree starts tipping. Smaller = harder.
TRUNK_MASS = 900                 # the trunk's own weight — the other difficulty
                                 # dial. Bigger = steadier tree = easier game.

# Once the weight goes past the base the tree starts to fall — but you can save
# it. Hang something on the other side fast enough and it swings back upright.
TIP_ACCELERATION = 1.0           # how hard an overbalanced tree tips over
RIGHTING_STRENGTH = 9.0          # how eagerly a supported tree stands back up
TILT_DAMPING = 5.0               # slows the lean down — this is what gives you
                                 # time to react. Lower = falls faster.
POINT_OF_NO_RETURN = 40          # degrees of tilt you cannot come back from

BRANCH_WIDTH_START = 9           # branches taper from this…
BRANCH_WIDTH_END = 3             # …down to this at the tip

GRAB_DISTANCE = 26               # how near a branch you must click to grab it
MIN_BRANCH_LENGTH = 45           # shorter drags than this are ignored

SCORE_SCALE = 5000               # a branch scores its disc's weight times how
                                 # far out you hung it, divided by this. Make
                                 # it smaller for bigger, showier numbers.

FALL_ACCELERATION = 7.0          # how fast a doomed tree tips over
TEXT_COLOR = (60, 58, 54)
FONT_NAME = None                 # None = pygame's built-in font
FONT_SIZE = 26

SHOW_BALANCE = False             # True draws the centre of mass and the safe
                                 # footprint, which makes the game much easier

# The discs you can grow. Each one is (radius, rings), and the rings are drawn
# biggest first — (colour, size) where size is a fraction of the radius.
#
# They're listed smallest to largest ON PURPOSE: colour tells you weight, so
# after a few goes you know the little pink one is safe and the big peach one
# is trouble. Add your own, or change a radius to make a colour heavier.
DISC_TYPES = [
    (12, [((240, 180, 154), 1.0), ((122, 84, 66), 0.42)]),
    (15, [((193, 80, 46), 1.0), ((222, 216, 206), 0.60)]),
    (17, [((44, 42, 60), 1.0), ((90, 74, 158), 0.62)]),
    (20, [((36, 34, 40), 1.0), ((205, 95, 122), 0.70), ((30, 28, 26), 0.28)]),
    (23, [((232, 216, 168), 1.0), ((246, 240, 220), 0.72), ((74, 70, 58), 0.24)]),
    (26, [((58, 36, 24), 1.0), ((91, 143, 168), 0.80), ((26, 24, 22), 0.34)]),
    (30, [((193, 80, 46), 1.0), ((222, 216, 206), 0.66), ((26, 24, 22), 0.34)]),
    (34, [((26, 24, 30), 1.0), ((72, 92, 112), 0.66)]),
]

# ─────────────────────────────────────────────────────────────────────────────
#  The tree
# ─────────────────────────────────────────────────────────────────────────────


def curve(start, control_a, control_b, end, steps=30):
    """A smooth line from start to end, pulled toward two control points.

    This is a cubic Bézier. The two controls are what let a branch change its
    mind halfway along — bend left, then right, like an S. (With only one
    control point you get a plain arc that can bend one way and no more.)

    Drag the controls further from the line for a sharper bend, or put them on
    opposite sides of it for a wiggle. We sample the curve into a list of
    points so we can draw it as a tapered stroke.
    """
    points = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        x = (
            u * u * u * start[0]
            + 3 * u * u * t * control_a[0]
            + 3 * u * t * t * control_b[0]
            + t * t * t * end[0]
        )
        y = (
            u * u * u * start[1]
            + 3 * u * u * t * control_a[1]
            + 3 * u * t * t * control_b[1]
            + t * t * t * end[1]
        )
        points.append((x, y))
    return points


def s_curve(start, end, bend_a, bend_b, steps=30):
    """An S-shaped branch from start to end.

    Rather than placing the two control points by hand, this pushes them
    sideways off the straight line between the ends — `bend_a` a third of the
    way along, `bend_b` two thirds. Give the two bends OPPOSITE signs and the
    branch curves one way and then the other, which is the S. Same sign and
    you get a plain arc; bigger numbers bend harder.
    """
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length  # across the line, not along it

    control_a = (start[0] + dx / 3 + nx * bend_a, start[1] + dy / 3 + ny * bend_a)
    control_b = (start[0] + dx * 2 / 3 + nx * bend_b, start[1] + dy * 2 / 3 + ny * bend_b)
    return curve(start, control_a, control_b, end, steps)


def rotate(points, pivot, angle):
    """Swing a list of points around a pivot — how the whole tree falls over."""
    if angle == 0:
        return points
    sin_a, cos_a = math.sin(angle), math.cos(angle)
    turned = []
    for x, y in points:
        dx, dy = x - pivot[0], y - pivot[1]
        turned.append(
            (pivot[0] + dx * cos_a - dy * sin_a, pivot[1] + dx * sin_a + dy * cos_a)
        )
    return turned


def closest_point_on_segment(point, a, b):
    """The point on line segment a→b that sits nearest to `point`."""
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return a
    # How far along the segment the perpendicular lands, clamped to the ends.
    t = ((point[0] - ax) * dx + (point[1] - ay) * dy) / length_squared
    t = max(0.0, min(1.0, t))
    return (ax + dx * t, ay + dy * t)


def path_length(points):
    return sum(
        math.dist(points[i], points[i + 1]) for i in range(len(points) - 1)
    )


def point_at_fraction(points, fraction):
    """Walk `fraction` of the way along a path and return the point there."""
    target = path_length(points) * fraction
    travelled = 0.0
    for i in range(len(points) - 1):
        step = math.dist(points[i], points[i + 1])
        if travelled + step >= target and step > 0:
            t = (target - travelled) / step
            return (
                points[i][0] + (points[i + 1][0] - points[i][0]) * t,
                points[i][1] + (points[i + 1][1] - points[i][1]) * t,
            )
        travelled += step
    return points[-1]


def tidy(points, steps=30):
    """Redraw a hand-drawn line as a smooth branch in the tree's own style.

    We keep where the line starts, where it ends, and how far it bows out to
    the side at a third and two thirds of the way along. Those two sideways
    distances are exactly what `s_curve` takes, so a drawn branch is built by
    the same function as the ones the tree started with — which is why they
    look like they belong together.
    """
    start, end = points[0], points[-1]
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 1:
        return [start, end]
    nx, ny = -dy / length, dx / length

    def sideways(fraction):
        px, py = point_at_fraction(points, fraction)
        return (px - start[0]) * nx + (py - start[1]) * ny

    first, second = sideways(1 / 3), sideways(2 / 3)

    # A cubic Bézier doesn't pass through its control points, so bending by
    # `first` at a third of the way along needs a slightly larger push than
    # `first` itself. This undoes that shrinkage so the curve lands on the
    # line you actually drew.
    bend_a = 3 * first - 1.5 * second
    bend_b = 3 * second - 1.5 * first
    return s_curve(start, end, bend_a, bend_b, steps)


class Disc:
    """A coloured disc at the end of a branch. This is where the weight is.

    Its size comes from its kind, so the colour and the weight always agree.
    """

    def __init__(self, x, y, kind):
        self.x = x
        self.y = y
        self.radius, self.rings = DISC_TYPES[kind % len(DISC_TYPES)]

    @property
    def mass(self):
        """Weight goes up with area, so looping twice as wide is 4x as heavy."""
        return math.pi * self.radius * self.radius

    def draw(self, surface, at=None):
        x, y = at if at is not None else (self.x, self.y)
        for colour, size in self.rings:
            r = max(1, int(self.radius * size))
            pygame.draw.circle(surface, colour, (int(x), int(y)), r)


def risk_points(x, kind):
    """What a disc of this kind, hung at this x, is worth.

    It's the same sum that decides whether the tree falls over: how heavy the
    disc is, times how far from the trunk you hung it. A heavy disc out on a
    limb is worth many times a small one tucked in beside the trunk — and it's
    exactly as much more likely to kill you.
    """
    radius = DISC_TYPES[kind % len(DISC_TYPES)][0]
    mass = math.pi * radius * radius
    return max(1, round(mass * abs(x - TRUNK_X) / SCORE_SCALE))


class Branch:
    """A drawn stroke of wood, with a disc on the end.

    The path is only ever art — the physics cares about the disc alone, so a
    long curly branch costs nothing until you loop a disc onto it.
    """

    def __init__(self, path, disc):
        self.path = path
        self.disc = disc

    def draw(self, surface):
        stroke(surface, self.path, BRANCH_WIDTH_START, BRANCH_WIDTH_END, WOOD)


def stroke(surface, points, width_start, width_end, colour):
    """Draw a list of points as a stroke that tapers from one width to another.

    We walk the line, and at each point step sideways by half the width to
    build up the left and right edges. Joining those two edges gives a polygon
    we can fill — which is what makes a branch look drawn rather than wiry.
    """
    if len(points) < 2:
        return

    left, right = [], []
    for i, (x, y) in enumerate(points):
        # Which way is the line heading here? Look at the neighbours.
        prev_point = points[max(i - 1, 0)]
        next_point = points[min(i + 1, len(points) - 1)]
        dx = next_point[0] - prev_point[0]
        dy = next_point[1] - prev_point[1]
        length = math.hypot(dx, dy) or 1.0

        # The normal is the tangent turned 90°, so it points across the line.
        nx, ny = -dy / length, dx / length

        t = i / (len(points) - 1)
        half = (width_start + (width_end - width_start) * t) / 2
        left.append((x + nx * half, y + ny * half))
        right.append((x - nx * half, y - ny * half))

    pygame.draw.polygon(surface, colour, left + right[::-1])


class Tree:
    def __init__(self):
        self.branches = []
        self.speckles = []
        self.build_starting_tree()

    def trunk_half_width(self, y):
        """How wide the trunk is at a given height — wide at the base, thin up top."""
        t = (y - TRUNK_TOP_Y) / (GROUND_Y - TRUNK_TOP_Y)
        t = max(0.0, min(1.0, t))
        return TRUNK_TOP_HALF + (TRUNK_BASE_HALF - TRUNK_TOP_HALF) * t

    def build_starting_tree(self):
        """A small version of the tree the game is based on."""
        # Each branch leaves the trunk one way and arrives at its disc the
        # other — that's the S. Flip the sign of either bend to mirror it.
        self.branches = [
            Branch(s_curve((TRUNK_X, 545), (344, 508), 30, -30), Disc(344, 508, 5)),
            Branch(s_curve((TRUNK_X, 508), (578, 472), 34, -34), Disc(578, 472, 6)),
            Branch(s_curve((TRUNK_X, 470), (376, 424), 24, -24), Disc(376, 424, 3)),
            Branch(s_curve((TRUNK_X, 434), (466, 392), 18, -18), Disc(466, 392, 1)),
        ]

        # Flecks on the trunk. Seeded, so the tree looks the same every run.
        rng = random.Random(7)
        self.speckles = []
        for _ in range(TRUNK_SPECKLES):
            y = rng.uniform(TRUNK_TOP_Y, GROUND_Y)
            half = self.trunk_half_width(y) - 3
            if half <= 1:
                continue
            x = TRUNK_X + rng.uniform(-half, half)
            self.speckles.append((x, y))

    # ── growing ──────────────────────────────────────────────────────────────

    def anchor_near(self, point):
        """Find somewhere on the tree to grow from, or None if you missed.

        You can start a branch anywhere on the trunk or on any branch already
        drawn — so we check every stretch of wood and keep the nearest.
        """
        best = None
        best_distance = GRAB_DISTANCE

        trunk_point = closest_point_on_segment(
            point, (TRUNK_X, TRUNK_TOP_Y), (TRUNK_X, GROUND_Y)
        )
        if math.dist(point, trunk_point) <= best_distance:
            best, best_distance = trunk_point, math.dist(point, trunk_point)

        for branch in self.branches:
            for i in range(len(branch.path) - 1):
                candidate = closest_point_on_segment(
                    point, branch.path[i], branch.path[i + 1]
                )
                distance = math.dist(point, candidate)
                if distance <= best_distance:
                    best, best_distance = candidate, distance
        return best

    def grow(self, path, kind):
        """Add a finished branch, with its disc sitting at the tip."""
        tip = path[-1]
        branch = Branch(path, Disc(tip[0], tip[1], kind))
        self.branches.append(branch)
        return branch

    # ── physics ──────────────────────────────────────────────────────────────

    def centre_of_mass(self):
        """Where the tree's weight sits — both across AND up.

        Height matters as much as sideways position: weight hung high swings
        much further out when the tree starts to lean, which is why a top-heavy
        tree tips so much faster than a wide low one.

        The trunk counts as a lump of weight halfway up itself — that's what
        stops the very first disc from tipping everything over.
        """
        trunk_middle = (TRUNK_TOP_Y + GROUND_Y) / 2
        total = TRUNK_MASS
        moment_x = TRUNK_MASS * TRUNK_X
        moment_y = TRUNK_MASS * trunk_middle
        for branch in self.branches:
            mass = branch.disc.mass
            total += mass
            moment_x += mass * branch.disc.x
            moment_y += mass * branch.disc.y
        return moment_x / total, moment_y / total

    def lean_offset(self, tilt):
        """How far past the base the weight is, with the tree tilted this far.

        This is the whole game in one line: as the tree leans, its weight
        swings out sideways, which makes it lean further. Positive means the
        weight has gone off to the right.
        """
        cx, cy = self.centre_of_mass()
        dx = cx - TRUNK_X
        dy = cy - GROUND_Y                     # negative, because up is less y
        return dx * math.cos(tilt) - dy * math.sin(tilt)

    def is_balanced(self, tilt=0.0):
        return abs(self.lean_offset(tilt)) <= BASE_HALF_WIDTH

    # ── drawing ──────────────────────────────────────────────────────────────

    def draw(self, surface, angle=0.0):
        """Draw the tree, optionally tipped over by `angle` about its base."""
        pivot = (TRUNK_X, GROUND_Y)

        def swing(points):
            return rotate(points, pivot, angle)

        self.draw_roots(surface, swing)
        self.draw_trunk(surface, swing)
        for branch in self.branches:
            stroke(
                surface,
                swing(branch.path),
                BRANCH_WIDTH_START,
                BRANCH_WIDTH_END,
                WOOD,
            )
        for branch in self.branches:
            branch.disc.draw(surface, swing([(branch.disc.x, branch.disc.y)])[0])

    def draw_roots(self, surface, swing):
        """Little legs splaying out to the ground, like the reference tree."""
        for direction in (-1, 1):
            for reach, start_y in ((34, 596), (18, 612)):
                stroke(
                    surface,
                    swing(
                        curve(
                            (TRUNK_X, start_y),
                            (TRUNK_X + direction * reach * 0.3, start_y + 10),
                            (TRUNK_X + direction * reach * 0.8, start_y + 18),
                            (TRUNK_X + direction * reach, GROUND_Y),
                        )
                    ),
                    8,
                    3,
                    WOOD,
                )

    def draw_trunk(self, surface, swing):
        left, right = [], []
        y = TRUNK_TOP_Y
        while y <= GROUND_Y:
            half = self.trunk_half_width(y)
            left.append((TRUNK_X - half, y))
            right.append((TRUNK_X + half, y))
            y += 6
        pygame.draw.polygon(surface, WOOD, swing(left) + swing(right)[::-1])

        for x, y in swing(self.speckles):
            pygame.draw.circle(surface, WOOD_SPECKLE, (int(x), int(y)), 1)


# ─────────────────────────────────────────────────────────────────────────────
#  The game
# ─────────────────────────────────────────────────────────────────────────────


class Game:
    def __init__(self):
        self.start_new_game()

    def start_new_game(self):
        self.tree = Tree()
        self.score = 0
        self.branches = 0
        self.over = False
        self.drawing = None          # the line you're dragging out right now
        self.next_disc = random.randrange(len(DISC_TYPES))
        self.tilt = 0.0              # which way, and how far, the tree is leaning
        self.tilt_speed = 0.0
        self.fall_direction = 1      # +1 fell right, -1 fell left
        reset_score()

    def update(self, dt):
        """Lean the tree, and decide whether it's saveable or finished."""
        if self.over:
            # Past saving. Keep going until it's flat on the ground.
            self.tilt_speed += FALL_ACCELERATION * dt * self.fall_direction
            self.tilt += self.tilt_speed * dt
            limit = math.pi / 2
            self.tilt = max(-limit, min(limit, self.tilt))
            return

        offset = self.tree.lean_offset(self.tilt)

        if abs(offset) > BASE_HALF_WIDTH:
            # The weight has walked off the end of the base. Down it goes —
            # and the further it goes, the harder it pulls.
            past = (abs(offset) - BASE_HALF_WIDTH) / BASE_HALF_WIDTH
            direction = 1 if offset > 0 else -1
            self.tilt_speed += TIP_ACCELERATION * past * direction * dt
        else:
            # The base is holding it up, so it swings back toward standing.
            self.tilt_speed -= RIGHTING_STRENGTH * self.tilt * dt

        # Damping either way: it stops a rescued tree rocking forever, and it
        # stops a doomed one accelerating out of reach before you can respond.
        self.tilt_speed -= TILT_DAMPING * self.tilt_speed * dt
        self.tilt += self.tilt_speed * dt

        if abs(self.tilt) >= math.radians(POINT_OF_NO_RETURN):
            self.over = True
            self.fall_direction = 1 if self.tilt > 0 else -1
            game_over(self.score)

    # ── drawing a branch ─────────────────────────────────────────────────────

    def in_tree_space(self, position):
        """Undo the tree's lean, so a click lands where the tree thinks it is.

        Everything about the tree is stored upright and only tilted when drawn.
        So when it's leaning we have to swing the mouse the other way before
        asking which branch you clicked.
        """
        return rotate([position], (TRUNK_X, GROUND_Y), -self.tilt)[0]

    def begin_drag(self, position):
        """Start a branch, but only if you grabbed the tree somewhere."""
        if self.over:
            return
        anchor = self.tree.anchor_near(self.in_tree_space(position))
        if anchor is not None:
            self.drawing = [anchor]

    def extend_drag(self, position):
        if self.drawing is None:
            return
        point = self.in_tree_space(position)
        # Skip points that barely moved — they add jitter and nothing else.
        if math.dist(self.drawing[-1], point) >= 3:
            self.drawing.append(point)

    def finish_drag(self):
        """Let go: keep the branch if the drag was long enough to mean it."""
        if self.drawing is None:
            return
        drawn, self.drawing = self.drawing, None
        if len(drawn) < 2 or path_length(drawn) < MIN_BRANCH_LENGTH:
            return
        path = tidy(drawn)
        self.tree.grow(path, self.next_disc)
        self.branches += 1
        self.score += risk_points(path[-1][0], self.next_disc)
        submit_score(self.score)
        # Roll the next one now, so the preview can always show what's coming.
        self.next_disc = random.randrange(len(DISC_TYPES))

    # ── drawing to the screen ────────────────────────────────────────────────

    def draw(self, surface, font):
        surface.fill(BACKGROUND)
        pygame.draw.line(
            surface, GROUND_COLOR, (110, GROUND_Y), (WIDTH - 110, GROUND_Y), 2
        )
        self.tree.draw(surface, self.tilt)
        self.draw_preview(surface, font)

        if SHOW_BALANCE:
            self.draw_balance(surface)

        surface.blit(font.render(f"SCORE {self.score}", True, TEXT_COLOR), (28, 24))
        surface.blit(
            font.render(f"BRANCHES {self.branches}", True, TEXT_COLOR), (28, 54)
        )
        if self.over:
            message = font.render("IT FELL OVER — PRESS R TO GROW AGAIN", True, TEXT_COLOR)
            surface.blit(message, (WIDTH // 2 - message.get_width() // 2, 24))

    def draw_preview(self, surface, font):
        """Show the branch you'd get if you let go now, disc and all.

        The disc is the one already rolled for this branch, so the weight you
        can see is the weight you'll get — the only thing you're choosing is
        where to put it.
        """
        if self.drawing is None:
            return

        # Drawn upright like the rest of the tree, then leaned to match it.
        path = rotate(tidy(self.drawing), (TRUNK_X, GROUND_Y), self.tilt)
        if path_length(self.drawing) < MIN_BRANCH_LENGTH:
            # Too short to plant — show it faintly so you know it won't take.
            stroke(surface, path, BRANCH_WIDTH_START, BRANCH_WIDTH_END, PENDING)
            return

        stroke(surface, path, BRANCH_WIDTH_START, BRANCH_WIDTH_END, WOOD)
        tip = path[-1]
        Disc(tip[0], tip[1], self.next_disc).draw(surface)

        # What this branch is worth, so you can see the reward growing as you
        # drag further out — and feel the risk growing with it.
        points = risk_points(tidy(self.drawing)[-1][0], self.next_disc)
        label = font.render(f"+{points}", True, TEXT_COLOR)
        radius = DISC_TYPES[self.next_disc % len(DISC_TYPES)][0]
        surface.blit(label, (tip[0] - label.get_width() / 2, tip[1] - radius - 30))

    def draw_balance(self, surface):
        """Only drawn when SHOW_BALANCE is on — the game is much easier with it."""
        y = GROUND_Y + 16
        pygame.draw.line(
            surface,
            (150, 150, 150),
            (TRUNK_X - BASE_HALF_WIDTH, y),
            (TRUNK_X + BASE_HALF_WIDTH, y),
            3,
        )
        offset = self.tree.lean_offset(self.tilt)
        colour = (40, 140, 60) if abs(offset) <= BASE_HALF_WIDTH else (200, 50, 40)
        pygame.draw.circle(surface, colour, (int(TRUNK_X + offset), y), 6)


async def main():
    pygame.init()
    pygame.display.set_caption(TITLE)
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    font = pygame.font.Font(FONT_NAME, FONT_SIZE)

    game = Game()
    running = True

    while running:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)   # cap dt so lag can't jump the fall

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                game.begin_drag(event.pos)
            elif event.type == pygame.MOUSEMOTION:
                game.extend_drag(event.pos)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                game.finish_drag()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    game.start_new_game()
                # ESC is not handled here on purpose — in Islands World it means
                # "leave this island", and the world itself takes care of that.

        game.update(dt)
        game.draw(screen, font)
        pygame.display.flip()

        # Required for the browser build — hands control back to the page each
        # frame. Do not remove this line.
        await asyncio.sleep(0)

    pygame.quit()


# pygbag needs the program to start with asyncio.run(main()) at the top level.
asyncio.run(main())
