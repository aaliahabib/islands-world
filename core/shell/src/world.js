// The overworld: a white sheet of paper with black ink islands on it, and
// stick figures walking between them.
//
// Island shapes are generated deterministically from the island id, so an
// island always looks the same for everybody.

import { FAINT, INK, MID, PAPER, WORLD } from "./config.js";
import {
  DEFAULT_AVATAR,
  EMOTE_DURATION,
  avatarColour,
  drawFigure,
  poseFor,
  sanitizeAvatar,
} from "./avatar.js";

const UI_FONT = `ui-monospace, "SF Mono", Menlo, Consolas, monospace`;

/** All overworld text goes through here, so it's consistent and easy to change. */
function label(ctx, text, x, y, size, { align = "center", color = INK, bold = false } = {}) {
  ctx.save();
  ctx.font = `${bold ? "700 " : ""}${size}px ${UI_FONT}`;
  ctx.textAlign = align;
  ctx.textBaseline = "top";
  ctx.fillStyle = color;
  ctx.fillText(String(text).toUpperCase(), x, y);
  ctx.restore();
}

function measure(ctx, text, size, bold = false) {
  ctx.save();
  ctx.font = `${bold ? "700 " : ""}${size}px ${UI_FONT}`;
  const width = ctx.measureText(String(text).toUpperCase()).width;
  ctx.restore();
  return width;
}

// ── Deterministic randomness ───────────────────────────────────────────────

function hashString(str) {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h >>> 0;
}

function mulberry32(seed) {
  let a = seed >>> 0;
  return function next() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ── Island geometry ────────────────────────────────────────────────────────

/** A lumpy closed polygon — the same idea as an asteroid, but it's land. */
function islandShape(rand, radius) {
  const corners = 11 + Math.floor(rand() * 5);
  const points = [];
  for (let i = 0; i < corners; i++) {
    const theta = (Math.PI * 2 * i) / corners;
    let jitter = 0.78 + rand() * 0.32;
    if (rand() < 0.22) jitter = 0.52 + rand() * 0.12; // a bay
    points.push([Math.cos(theta) * jitter * radius, Math.sin(theta) * jitter * radius]);
  }
  return points;
}

function maxExtent(points) {
  let m = 0;
  for (const [x, y] of points) m = Math.max(m, Math.hypot(x, y));
  return m;
}

export function buildIslands(registry) {
  const { slotCols, slotSpacingX, slotSpacingY, margin, islandRadius } = WORLD;

  return registry.map((entry, index) => {
    const slot = Number.isInteger(entry.slot) ? entry.slot : index;
    const col = slot % slotCols;
    const row = Math.floor(slot / slotCols);

    const rand = mulberry32(hashString(entry.id || `island-${slot}`));
    // A stable per-island wobble so the grid doesn't read as a grid.
    const jitterX = (rand() - 0.5) * slotSpacingX * 0.26;
    const jitterY = (rand() - 0.5) * slotSpacingY * 0.26;
    const radius = islandRadius * (0.82 + rand() * 0.4);
    const shape = islandShape(rand, radius);

    return {
      ...entry,
      slot,
      x: margin + col * slotSpacingX + jitterX,
      y: margin + row * slotSpacingY + jitterY,
      radius,
      reach: maxExtent(shape) + WORLD.enterPadding,
      shape,
      occupants: 0,
    };
  });
}

export function worldBounds(islands) {
  const { margin } = WORLD;
  let maxX = 0;
  let maxY = 0;
  for (const island of islands) {
    maxX = Math.max(maxX, island.x + island.radius);
    maxY = Math.max(maxY, island.y + island.radius);
  }
  return { width: maxX + margin, height: maxY + margin };
}

function strokePolygon(ctx, points, { x = 0, y = 0, color = INK, width = 2 } = {}) {
  if (points.length < 2) return;
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineJoin = "round";
  ctx.beginPath();
  ctx.moveTo(x + points[0][0], y + points[0][1]);
  for (let i = 1; i < points.length; i++) {
    ctx.lineTo(x + points[i][0], y + points[i][1]);
  }
  ctx.closePath();
  ctx.stroke();
  ctx.restore();
}

// ── The world ──────────────────────────────────────────────────────────────

export class World {
  constructor(registry, avatar = DEFAULT_AVATAR) {
    this.islands = buildIslands(registry);
    this.bounds = worldBounds(this.islands);

    this.player = {
      handle: "YOU",
      x: this.bounds.width / 2,
      y: this.bounds.height / 2,
      avatar: sanitizeAvatar(avatar),
      facing: 1,
      moving: false,
      walkPhase: 0,
      emote: null,
      emoteUntil: 0,
    };
    this.others = new Map();
    this.camera = { x: this.player.x, y: this.player.y };
    this.time = 0;
    this.nearest = null;
  }

  setAvatar(avatar) {
    this.player.avatar = sanitizeAvatar(avatar);
  }

  setOccupancy(counts) {
    for (const island of this.islands) {
      island.occupants = Number(counts?.[island.id]) || 0;
    }
  }

  /** Merge a roster snapshot from the server into our interpolation buffers. */
  updateOthers(players, myId) {
    const seen = new Set();
    for (const p of players) {
      if (!p || p.id === myId) continue;
      seen.add(p.id);
      let other = this.others.get(p.id);
      if (!other) {
        other = {
          id: p.id,
          handle: p.handle || "?",
          x: p.x,
          y: p.y,
          renderX: p.x,
          renderY: p.y,
          avatar: sanitizeAvatar(p.avatar),
          facing: 1,
          moving: false,
          walkPhase: Math.random(),
          island: p.island ?? null,
          emote: null,
          emoteUntil: 0,
        };
        this.others.set(p.id, other);
      }

      const dx = p.x - other.x;
      other.moving = Math.hypot(dx, p.y - other.y) > 1;
      if (Math.abs(dx) > 0.5) other.facing = dx > 0 ? 1 : -1;

      other.handle = p.handle || other.handle;
      other.x = p.x;
      other.y = p.y;
      if (p.avatar) other.avatar = sanitizeAvatar(p.avatar);
      other.island = p.island ?? null;
    }
    for (const id of [...this.others.keys()]) {
      if (!seen.has(id)) this.others.delete(id);
    }
  }

  showEmote(id, emote, myId) {
    const target = id === myId ? this.player : this.others.get(id);
    if (!target) return;
    target.emote = emote;
    target.emoteUntil = this.time + EMOTE_DURATION;
  }

  playEmote(emote) {
    this.player.emote = emote;
    this.player.emoteUntil = this.time + EMOTE_DURATION;
  }

  update(dt, input) {
    this.time += dt;

    let dx = 0;
    let dy = 0;
    if (input.left) dx -= 1;
    if (input.right) dx += 1;
    if (input.up) dy -= 1;
    if (input.down) dy += 1;

    const moving = dx !== 0 || dy !== 0;
    this.player.moving = moving;
    if (moving) {
      const len = Math.hypot(dx, dy);
      dx /= len;
      dy /= len;
      this.player.x += dx * WORLD.playerSpeed * dt;
      this.player.y += dy * WORLD.playerSpeed * dt;
      if (Math.abs(dx) > 0.01) this.player.facing = dx > 0 ? 1 : -1;
      this.player.walkPhase = (this.player.walkPhase + dt * 2.2) % 1;
    }

    // Stay on the map. Figures pass through each other and through islands —
    // nobody gets to stand in a doorway and block it.
    this.player.x = Math.max(24, Math.min(this.bounds.width - 24, this.player.x));
    this.player.y = Math.max(24, Math.min(this.bounds.height - 24, this.player.y));

    // Smoothly ease everyone else toward their last reported position.
    const ease = 1 - Math.pow(0.0015, dt);
    for (const other of this.others.values()) {
      other.renderX += (other.x - other.renderX) * ease;
      other.renderY += (other.y - other.renderY) * ease;
      if (other.moving) other.walkPhase = (other.walkPhase + dt * 2.2) % 1;
    }

    this.nearest = this.findEnterable();
    return this.nearest;
  }

  findEnterable() {
    let best = null;
    let bestDistance = Infinity;
    for (const island of this.islands) {
      const distance = Math.hypot(island.x - this.player.x, island.y - this.player.y);
      if (distance < island.reach && distance < bestDistance) {
        best = island;
        bestDistance = distance;
      }
    }
    return best;
  }

  focusCamera(viewWidth, viewHeight, dt) {
    const halfW = viewWidth / 2;
    const halfH = viewHeight / 2;
    let targetX = this.player.x;
    let targetY = this.player.y;

    if (this.bounds.width > viewWidth) {
      targetX = Math.max(halfW, Math.min(this.bounds.width - halfW, targetX));
    } else {
      targetX = this.bounds.width / 2;
    }
    if (this.bounds.height > viewHeight) {
      targetY = Math.max(halfH, Math.min(this.bounds.height - halfH, targetY));
    } else {
      targetY = this.bounds.height / 2;
    }

    const ease = 1 - Math.pow(0.0005, dt);
    this.camera.x += (targetX - this.camera.x) * ease;
    this.camera.y += (targetY - this.camera.y) * ease;
  }

  draw(ctx, viewWidth, viewHeight) {
    ctx.fillStyle = PAPER;
    ctx.fillRect(0, 0, viewWidth, viewHeight);

    ctx.save();
    ctx.translate(
      Math.round(viewWidth / 2 - this.camera.x),
      Math.round(viewHeight / 2 - this.camera.y)
    );

    this.drawSea(ctx, viewWidth, viewHeight);
    for (const island of this.islands) this.drawIsland(ctx, island);

    // Draw figures back-to-front so the nearer ones overlap correctly.
    const figures = [...this.others.values(), this.player].sort(
      (a, b) => (a.renderY ?? a.y) - (b.renderY ?? b.y)
    );
    for (const figure of figures) this.drawPerson(ctx, figure, figure === this.player);

    ctx.restore();

    this.drawCompass(ctx, viewWidth, viewHeight);
  }

  /** A sparse dot grid, so you can feel yourself moving across open water. */
  drawSea(ctx, viewWidth, viewHeight) {
    const step = 96;
    const left = this.camera.x - viewWidth / 2;
    const top = this.camera.y - viewHeight / 2;
    const startX = Math.floor(left / step) * step;
    const startY = Math.floor(top / step) * step;

    ctx.save();
    ctx.fillStyle = FAINT;
    for (let x = startX; x < left + viewWidth + step; x += step) {
      for (let y = startY; y < top + viewHeight + step; y += step) {
        ctx.fillRect(x, y, 2, 2);
      }
    }
    ctx.restore();
  }

  drawIsland(ctx, island) {
    const active = this.nearest === island;

    // One outline. That's the whole island.
    strokePolygon(ctx, island.shape, {
      x: island.x,
      y: island.y,
      color: INK,
      width: active ? 4 : 2.5,
    });

    const { lines, size } = this.fitLabel(ctx, island.name || island.id, island.radius * 1.1);
    const lineHeight = size * 1.25;
    let y = island.y - (lines.length * lineHeight) / 2 - 6;

    for (const line of lines) {
      label(ctx, line, island.x, y, size, { bold: true });
      y += lineHeight;
    }

    y += 4;
    if (island.author) {
      label(ctx, `by ${island.author}`.slice(0, 20), island.x, y, 11, { color: MID });
      y += 16;
    }
    if (island.occupants > 0) {
      label(ctx, island.occupants === 1 ? "1 playing" : `${island.occupants} playing`,
        island.x, y, 11);
    }
  }

  /** Shrink a name, then wrap it, until it fits inside the shoreline. */
  fitLabel(ctx, rawName, maxWidth) {
    const name = String(rawName).slice(0, 28);
    const fits = (lines, size) => lines.every((l) => measure(ctx, l, size, true) <= maxWidth);

    for (let size = 22; size >= 15; size -= 1) {
      if (fits([name], size)) return { lines: [name], size };
    }
    const words = name.split(/\s+/).filter(Boolean);
    if (words.length > 1) {
      let best = 1;
      let bestDelta = Infinity;
      for (let i = 1; i < words.length; i++) {
        const delta = Math.abs(
          words.slice(0, i).join(" ").length - words.slice(i).join(" ").length
        );
        if (delta < bestDelta) {
          bestDelta = delta;
          best = i;
        }
      }
      const lines = [words.slice(0, best).join(" "), words.slice(best).join(" ")];
      for (let size = 19; size >= 11; size -= 1) {
        if (fits(lines, size)) return { lines, size };
      }
      return { lines, size: 11 };
    }
    for (let size = 14; size >= 9; size -= 1) {
      if (fits([name], size)) return { lines: [name], size };
    }
    return { lines: [name], size: 9 };
  }

  drawPerson(ctx, person, isMe) {
    const x = person.renderX ?? person.x;
    const y = person.renderY ?? person.y;

    const active = person.emote && this.time < person.emoteUntil;
    const pose = poseFor({
      emote: active ? person.emote : null,
      emoteT: active ? 1 - (person.emoteUntil - this.time) / EMOTE_DURATION : 0,
      walkPhase: person.walkPhase,
      moving: person.moving,
    });
    if (!active) person.emote = null;

    drawFigure(ctx, x, y, person.avatar, pose, person.facing);

    // Ride the bob, or the name lands on the figure's chest mid-jump. -70 clears
    // the head plus the tallest hat.
    const name = isMe ? "you" : person.handle.slice(0, 12);
    label(ctx, name, x, y + (pose.bob || 0) - 70, 11, {
      color: isMe ? MID : avatarColour(person.avatar),
      bold: !isMe,
    });

    if (person.island) label(ctx, "playing", x, y + 8, 9, { color: MID });
  }

  /** Top-left minimap: every island, and where you are among them. */
  drawCompass(ctx, viewWidth, viewHeight) {
    const boxW = 96;
    const boxH = Math.max(46, Math.round((96 * this.bounds.height) / this.bounds.width));
    const x = 20;
    const y = 54;
    const scaleX = boxW / this.bounds.width;
    const scaleY = boxH / this.bounds.height;

    ctx.save();
    ctx.strokeStyle = INK;
    ctx.lineWidth = 2;
    ctx.fillStyle = PAPER;
    ctx.fillRect(x, y, boxW, boxH);
    ctx.strokeRect(x, y, boxW, boxH);

    ctx.fillStyle = FAINT;
    for (const island of this.islands) {
      ctx.fillRect(x + island.x * scaleX - 2, y + island.y * scaleY - 2, 4, 4);
    }
    ctx.fillStyle = avatarColour(this.player.avatar);
    ctx.fillRect(x + this.player.x * scaleX - 2.5, y + this.player.y * scaleY - 2.5, 5, 5);
    ctx.restore();
  }
}
