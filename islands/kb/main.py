"""ROCK VIBRAPHONE — your island's game.

Rocks drift across the screen in eight sizes. Every size is a different note of
the C major pentatonic scale — the biggest rock is the lowest note, the tiniest
is the highest. Click a rock to play its note. Higher notes are worth more
points, and they're the small ones, so they're the hardest to hit.

    MOUSE CLICK   play a rock
    P             hear your piece again, once it's over
    R             restart after you finish

Get to TARGET_SCORE and the piece is over — then the game plays your whole
melody back to you at a steady tempo.

This is YOUR game now. The fastest way to make it yours is the CUSTOMIZE block
just below — change the colours, the notes, how fast rocks arrive.
Then run it and see what happened. After that, ask Claude for bigger changes.

Two rules that keep your island working inside Islands World:
  1. keep `async def main()` and the `await asyncio.sleep(0)` at the end of the
     game loop — that's what lets the game run in a browser.
  2. keep calling `submit_score(...)` and `game_over(...)` — that's what puts
     your score on the world scoreboard.
"""

import array
import asyncio
import math
import random

import pygame

from islands_sdk import game_over, reset as reset_score, submit_score

# ─────────────────────────────────────────────────────────────────────────────
#  CUSTOMIZE ME — change these numbers and colours first. Nothing here can
#  break the game; the worst that happens is it gets silly.
# ─────────────────────────────────────────────────────────────────────────────

TITLE = "Rock Vibraphone"

WIDTH = 900                      # size of the game window
HEIGHT = 700

BACKGROUND = (0, 0, 0)           # colours are (RED, GREEN, BLUE), 0–255
LINE_COLOR = (255, 255, 255)     # text and the mouse ring are drawn in this
LINE_WIDTH = 2
FONT_NAME = None                 # None = pygame's built-in font

TARGET_SCORE = 1000              # reach this and the piece is finished

# The eight notes, lowest first: C major pentatonic over two octaves.
# Each line below is one note — its name, how big its rock is, what colour it
# is, and how many points it's worth. Low notes are big and slow and cheap;
# high notes are small and quick and worth a lot.
NOTE_NAMES  = ["C4", "D4", "E4", "G4", "A4", "C5", "D5", "E5"]
NOTE_FREQS  = [261.6, 293.7, 329.6, 392.0, 440.0, 523.3, 587.3, 659.3]  # pitch, in Hz
NOTE_RADIUS = [   54,   47,   41,   35,   30,   25,   21,   17]
NOTE_SPEED  = [   45,   55,   65,   78,   90,  105,  120,  138]
NOTE_POINTS = [   10,   20,   30,   40,   50,   60,   70,   80]
NOTE_COLORS = [
    (196,  64,  64),             # C4 — red
    (204, 116,  52),             # D4 — orange
    (198, 184,  60),             # E4 — yellow
    ( 96, 186,  92),             # G4 — green
    ( 66, 170, 178),             # A4 — teal
    ( 74, 126, 208),             # C5 — blue
    (140,  98, 206),             # D5 — violet
    (212,  96, 166),             # E5 — pink
]

NOTE_LENGTH = 1.4                # seconds a note rings for after you hit it
NOTE_VOLUME = 0.5                # 0.0 = silent, 1.0 = as loud as it goes
TREMOLO_HZ = 5.0                 # the wobble that makes a vibraphone a vibraphone
TREMOLO_DEPTH = 0.3              # how deep the wobble is (0.0 = none)

REPLAY_TEMPO = 0.28              # seconds between notes when your piece plays back
REPLAY_DELAY = 1.2               # pause after you finish, before the replay starts

SPAWN_EVERY = 0.65               # seconds between new rocks arriving
MAX_ROCKS = 14                   # how many can be on screen at once
ROCK_LIFETIME = 14.0             # seconds a rock lasts if you don't play it
ROCK_FADE = 1.2                  # it spends its last seconds fading out

FPS = 60

# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────


def wrap(x, y):
    """The screen has no edges — drift off one side, come back on the other."""
    return x % WIDTH, y % HEIGHT


def dim(color, amount):
    """The same colour, but darker. amount 1.0 = full, 0.0 = invisible."""
    return (int(color[0] * amount), int(color[1] * amount), int(color[2] * amount))


def lighten(color, by=70):
    """The same colour, but paler — used for the outline around each rock."""
    return (min(255, color[0] + by), min(255, color[1] + by), min(255, color[2] + by))


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
#  The sound
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_RATE = 22050              # how finely the sound is chopped up
_sounds = []                     # one tone per note, built when the game starts


def build_sounds():
    """Make one vibraphone tone per note, from scratch. No sound files needed.

    A vibraphone is a struck metal bar, and three things make it sound like one:
    a clear note, a bright metallic ring on top that dies away almost at once,
    and a slow wobble in volume from the discs spinning under the bars.
    """
    if pygame.mixer.get_init() is None:
        return                   # no speakers on this machine — play silently
    pygame.mixer.set_num_channels(16)

    for freq in NOTE_FREQS:
        samples = array.array("h")
        for i in range(int(SAMPLE_RATE * NOTE_LENGTH)):
            t = i / SAMPLE_RATE
            bar = (
                math.sin(math.tau * freq * t)                                  # the note
                + 0.5 * math.sin(math.tau * freq * 4 * t) * math.exp(-7 * t)   # metallic ring
                + 0.2 * math.sin(math.tau * freq * 10 * t) * math.exp(-16 * t) # the strike
            )
            wobble = 1 - TREMOLO_DEPTH + TREMOLO_DEPTH * math.sin(math.tau * TREMOLO_HZ * t)
            fade_in = min(1.0, t / 0.005)      # a soft start, or you hear a click
            fade_out = math.exp(-3.0 * t)      # ring out and die away
            level = bar * wobble * fade_in * fade_out * NOTE_VOLUME * 0.45
            samples.append(int(max(-1.0, min(1.0, level)) * 32767))
        _sounds.append(pygame.mixer.Sound(buffer=samples.tobytes()))


def play_note(note):
    """Strike one bar. Notes overlap and ring together, like a real vibraphone."""
    if _sounds:
        _sounds[note].play()


# ─────────────────────────────────────────────────────────────────────────────
#  Things in the game
# ─────────────────────────────────────────────────────────────────────────────


class Rock:
    """One rock — which is to say, one note you can play."""

    def __init__(self, x, y, note, vx, vy):
        self.x = x
        self.y = y
        self.note = note                     # 0 = lowest note, 7 = highest
        self.radius = NOTE_RADIUS[note]
        self.color = NOTE_COLORS[note]
        self.points = NOTE_POINTS[note]
        self.vx = vx
        self.vy = vy
        self.spin = random.uniform(-60, 60)
        self.angle = random.uniform(0, 360)
        self.life = ROCK_LIFETIME

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
        self.life -= dt

    def brightness(self):
        """Full brightness most of its life, then fades out at the end."""
        return min(1.0, max(0.0, self.life / ROCK_FADE))

    def outline(self):
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
        fade = self.brightness()
        points = self.outline()
        pygame.draw.polygon(surface, dim(self.color, fade), points, 0)
        pygame.draw.polygon(surface, dim(lighten(self.color), fade), points, LINE_WIDTH)

    def contains(self, x, y):
        return math.hypot(self.x - x, self.y - y) <= self.radius


class Debris:
    """A little burst of lines when a rock is played."""

    def __init__(self, x, y, color, count=10):
        self.color = color
        self.pieces = []
        for _ in range(count):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(60, 200)
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
        fade = max(0.0, self.life / 0.6)
        color = dim(self.color, fade)
        for x, y, vx, vy in self.pieces:
            scale = 0.03
            pygame.draw.line(surface, color, (x, y), (x - vx * scale, y - vy * scale), 2)


# ─────────────────────────────────────────────────────────────────────────────
#  The game
# ─────────────────────────────────────────────────────────────────────────────


class Game:
    def __init__(self):
        self.start_new_game()

    def start_new_game(self):
        self.rocks = []
        self.debris = []
        self.score = 0
        self.melody = []             # every note you play, in order — your piece
        self.playback_index = None   # which note the replay is up to (None = not playing)
        self.playback_timer = 0.0
        self.time_alive = 0.0
        self.spawn_timer = 0.0
        self.over = False
        reset_score()
        submit_score(0)
        # Start with a few already drifting so there's something to play at once.
        for _ in range(5):
            self.spawn_rock()

    def spawn_rock(self):
        """Send one new rock drifting in from a random edge."""
        if len(self.rocks) >= MAX_ROCKS:
            return
        note = random.randrange(len(NOTE_NAMES))
        speed = NOTE_SPEED[note] * random.uniform(0.8, 1.2)
        edge = random.choice(["top", "bottom", "left", "right"])
        if edge == "top":
            x, y, heading = random.uniform(0, WIDTH), -40, random.uniform(20, 160)
        elif edge == "bottom":
            x, y, heading = random.uniform(0, WIDTH), HEIGHT + 40, random.uniform(200, 340)
        elif edge == "left":
            x, y, heading = -40, random.uniform(0, HEIGHT), random.uniform(-70, 70)
        else:
            x, y, heading = WIDTH + 40, random.uniform(0, HEIGHT), random.uniform(110, 250)
        radians = math.radians(heading)
        self.rocks.append(
            Rock(x, y, note, math.cos(radians) * speed, math.sin(radians) * speed)
        )

    def play(self, x, y):
        """The mouse was clicked at (x, y). Play the rock under it, if any."""
        if self.over:
            return
        # If rocks overlap, the one whose middle is nearest the click wins.
        hits = [r for r in self.rocks if r.contains(x, y)]
        if not hits:
            return
        rock = min(hits, key=lambda r: math.hypot(r.x - x, r.y - y))
        play_note(rock.note)
        self.rocks.remove(rock)
        self.debris.append(Debris(rock.x, rock.y, lighten(rock.color)))
        self.melody.append(rock.note)          # remember it for the replay
        self.add_score(rock.points)

    def add_score(self, points):
        self.score += points
        submit_score(self.score)
        if self.score >= TARGET_SCORE:
            self.over = True
            game_over(self.score)
            self.start_playback()

    def start_playback(self):
        """Play the whole piece back from the beginning, one note per beat."""
        self.playback_index = 0
        self.playback_timer = REPLAY_DELAY

    def update_playback(self, dt):
        if self.playback_index is None:
            return
        self.playback_timer -= dt
        if self.playback_timer > 0:
            return
        if self.playback_index >= len(self.melody):
            self.playback_index = None         # the piece has finished playing
            return
        play_note(self.melody[self.playback_index])
        self.playback_index += 1
        self.playback_timer = REPLAY_TEMPO

    def update(self, dt):
        self.time_alive += dt

        for burst in self.debris:
            burst.update(dt)
        self.debris = [d for d in self.debris if d.life > 0]

        if self.over:
            self.update_playback(dt)
            return

        for rock in self.rocks:
            rock.update(dt)
        self.rocks = [r for r in self.rocks if r.life > 0]

        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            self.spawn_rock()
            self.spawn_timer = SPAWN_EVERY

    def draw(self, surface, mouse_pos):
        surface.fill(BACKGROUND)

        for rock in self.rocks:
            rock.draw(surface)
        for burst in self.debris:
            burst.draw(surface)

        self.draw_hud(surface)

        if self.over:
            draw_text(surface, "FINISHED", (WIDTH / 2, HEIGHT / 2 - 190), size=64, align="center")
            draw_text(surface, f"SCORE {self.score} IN {len(self.melody)} NOTES",
                      (WIDTH / 2, HEIGHT / 2 - 120), size=34, align="center")
            draw_text(surface, "YOUR PIECE", (WIDTH / 2, HEIGHT / 2 - 70), size=20, align="center")
            self.draw_melody(surface, HEIGHT / 2 + 40)
            draw_text(surface, "P TO HEAR IT AGAIN    R TO PLAY AGAIN",
                      (WIDTH / 2, HEIGHT / 2 + 80), size=24, align="center")
        else:
            self.draw_pointer(surface, mouse_pos)

    def draw_melody(self, surface, baseline):
        """Your piece, drawn as bars sitting on a line: one bar per note, taller
        for higher notes. The bar currently sounding goes white."""
        if not self.melody:
            return
        spacing = min(20.0, (WIDTH - 140) / len(self.melody))
        width = max(3, int(spacing * 0.7))
        left = WIDTH / 2 - spacing * len(self.melody) / 2
        for i, note in enumerate(self.melody):
            sounding = self.playback_index is not None and i == self.playback_index - 1
            color = LINE_COLOR if sounding else NOTE_COLORS[note]
            height = 10 + note * 7
            pygame.draw.rect(
                surface, color, (left + i * spacing, baseline - height, width, height), 0
            )
        pygame.draw.line(
            surface, dim(LINE_COLOR, 0.35),
            (left - 8, baseline + 1), (left + spacing * len(self.melody) + 4, baseline + 1), 1,
        )

    def draw_pointer(self, surface, mouse_pos):
        """A little ring where the mouse is, so you can find it against black."""
        x, y = mouse_pos
        pygame.draw.circle(surface, LINE_COLOR, (x, y), 9, 1)
        pygame.draw.circle(surface, LINE_COLOR, (x, y), 1, 0)

    def draw_hud(self, surface):
        draw_text(surface, str(self.score), (28, 22), size=48)
        draw_text(surface, f"OF {TARGET_SCORE}", (30, 78), size=20)

        # A little swatch of every note, low to high, so you can see the scale.
        for i, color in enumerate(NOTE_COLORS):
            pygame.draw.rect(surface, color, (WIDTH - 28 - (8 - i) * 22, 26, 16, 16), 0)
        draw_text(surface, "LOW → HIGH", (WIDTH - 28, 50), size=16, align="right")


async def main():
    # Ask for mono sound at our sample rate BEFORE pygame starts, so the tones
    # we build are in the format the mixer expects.
    pygame.mixer.pre_init(SAMPLE_RATE, -16, 1, 512)
    pygame.init()
    build_sounds()
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
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                game.play(*event.pos)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r and game.over:
                    game.start_new_game()
                elif event.key == pygame.K_p and game.over:
                    game.start_playback()
                # ESC is not handled here on purpose — in Islands World it means
                # "leave this island", and the world itself takes care of that.

        game.update(dt)
        game.draw(screen, pygame.mouse.get_pos())
        pygame.display.flip()

        # Required for the browser build — hands control back to the page each
        # frame. Do not remove this line.
        await asyncio.sleep(0)

    pygame.quit()


# pygbag needs the program to start with asyncio.run(main()) at the top level.
asyncio.run(main())
