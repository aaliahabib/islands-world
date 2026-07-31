// The overworld: a white sheet of paper with black ink islands on it.
//
// Everything is drawn as vector outlines to match the island games, just with
// the colours reversed. Island shapes are generated deterministically from the
// island id, so an island always looks the same for everybody.

import { FAINT, INK, MID, PAPER, WORLD } from "./config.js";
import { drawText, textWidth } from "./vecfont.js";

/**
 * Fit an island's name inside its shoreline: shrink it, and if it's still too
 * wide, break it across two lines at the most balanced space.
 */
function fitLabel(rawName, maxWidth) {
  const name = String(rawName).toUpperCase().slice(0, 28);
  const fits = (lines, size) => lines.every((line) => textWidth(line, size) <= maxWidth);

  // 1. One line at a comfortable size, if it fits.
  for (let size = 26; size >= 18; size -= 1) {
    if (fits([name], size)) return { lines: [name], size };
  }

  // 2. Otherwise break it in two rather than shrink it into illegibility.
  const words = name.split(/\s+/).filter(Boolean);
  if (words.length > 1) {
    let bestSplit = 1;
    let bestDelta = Infinity;
    for (let i = 1; i < words.length; i++) {
      const delta = Math.abs(
        words.slice(0, i).join(" ").length - words.slice(i).join(" ").length
      );
      if (delta < bestDelta) {
        bestDelta = delta;
        bestSplit = i;
      }
    }
    const lines = [words.slice(0, bestSplit).join(" "), words.slice(bestSplit).join(" ")];
    for (let size = 22; size >= 12; size -= 1) {
      if (fits(lines, size)) return { lines, size };
    }
    return { lines, size: 12 };
  }

  // 3. A single long word: no choice but to shrink it.
  for (let size = 17; size >= 10; size -= 1) {
    if (fits([name], size)) return { lines: [name], size };
  }
  return { lines: [name], size: 10 };
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

// ── Drawing helpers ────────────────────────────────────────────────────────

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

const AVATAR_SHAPE = [
  [1.0, 0.0],
  [-0.7, 0.65],
  [-0.4, 0.0],
  [-0.7, -0.65],
];

function drawAvatar(ctx, x, y, angleDeg, { color = INK, width = 2, scale = WORLD.playerRadius } = {}) {
  const a = (angleDeg * Math.PI) / 180;
  const cos = Math.cos(a);
  const sin = Math.sin(a);
  const points = AVATAR_SHAPE.map(([px, py]) => [
    (px * cos - py * sin) * scale,
    (px * sin + py * cos) * scale,
  ]);
  strokePolygon(ctx, points, { x, y, color, width });
}

// ── The world ──────────────────────────────────────────────────────────────

export class World {
  constructor(registry) {
    this.islands = buildIslands(registry);
    this.bounds = worldBounds(this.islands);

    // Start in the middle of the map so there's always something in view.
    this.player = {
      x: this.bounds.width / 2,
      y: this.bounds.height / 2,
      angle: -90,
      emote: null,
      emoteUntil: 0,
    };
    this.others = new Map();
    this.camera = { x: this.player.x, y: this.player.y };
    this.time = 0;
    this.nearest = null;
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
          angle: p.a ?? -90,
          renderAngle: p.a ?? -90,
          island: p.island ?? null,
          emote: null,
          emoteUntil: 0,
        };
        this.others.set(p.id, other);
      }
      other.handle = p.handle || other.handle;
      other.x = p.x;
      other.y = p.y;
      other.angle = p.a ?? other.angle;
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
    target.emoteUntil = this.time + WORLD.emoteDuration;
  }

  update(dt, input) {
    this.time += dt;

    let dx = 0;
    let dy = 0;
    if (input.left) dx -= 1;
    if (input.right) dx += 1;
    if (input.up) dy -= 1;
    if (input.down) dy += 1;

    if (dx || dy) {
      const len = Math.hypot(dx, dy);
      dx /= len;
      dy /= len;
      this.player.x += dx * WORLD.playerSpeed * dt;
      this.player.y += dy * WORLD.playerSpeed * dt;
      this.player.angle = (Math.atan2(dy, dx) * 180) / Math.PI;
    }

    // Stay on the map. Avatars pass through each other and through islands —
    // nobody gets to stand in a doorway and block it.
    this.player.x = Math.max(24, Math.min(this.bounds.width - 24, this.player.x));
    this.player.y = Math.max(24, Math.min(this.bounds.height - 24, this.player.y));

    // Smoothly ease everyone else toward their last reported position.
    const ease = 1 - Math.pow(0.0015, dt);
    for (const other of this.others.values()) {
      other.renderX += (other.x - other.renderX) * ease;
      other.renderY += (other.y - other.renderY) * ease;
      let delta = ((other.angle - other.renderAngle + 540) % 360) - 180;
      other.renderAngle += delta * ease;
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
    ctx.translate(Math.round(viewWidth / 2 - this.camera.x), Math.round(viewHeight / 2 - this.camera.y));

    this.drawSea(ctx, viewWidth, viewHeight);
    for (const island of this.islands) this.drawIsland(ctx, island);
    for (const other of this.others.values()) this.drawOther(ctx, other);
    this.drawPlayer(ctx);

    ctx.restore();

    this.drawCompass(ctx, viewWidth, viewHeight);
  }

  /** A sparse dot grid, so you can feel yourself moving across open water. */
  drawSea(ctx, viewWidth, viewHeight) {
    const step = 84;
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

    // Shoreline.
    strokePolygon(ctx, island.shape, {
      x: island.x,
      y: island.y,
      color: INK,
      width: active ? 4 : 2.5,
    });

    // A lighter inner contour, like a map's elevation line.
    const inner = island.shape.map(([x, y]) => [x * 0.76, y * 0.76]);
    strokePolygon(ctx, inner, { x: island.x, y: island.y, color: FAINT, width: 1.5 });

    // The island's name, shrunk (and wrapped) until it sits inside the shore.
    const { lines, size } = fitLabel(island.name || island.id || "ISLAND", island.radius * 1.05);
    const lineHeight = size * 1.35;
    const blockTop = island.y - (lines.length * lineHeight) / 2 - 6;

    lines.forEach((line, index) => {
      drawText(ctx, line, island.x, blockTop + index * lineHeight, size, {
        center: true,
        color: INK,
        width: active ? 3 : 2.5,
      });
    });

    let below = blockTop + lines.length * lineHeight + 4;

    if (island.author) {
      drawText(ctx, `BY ${island.author}`.slice(0, 18), island.x, below, 10, {
        center: true,
        color: MID,
        width: 1.5,
      });
      below += 20;
    }

    if (island.occupants > 0) {
      const label = island.occupants === 1 ? "1 PLAYING" : `${island.occupants} PLAYING`;
      drawText(ctx, label, island.x, below, 10, {
        center: true,
        color: INK,
        width: 1.5,
      });
    }

    if (active) {
      // A dashed ring showing you're in range.
      ctx.save();
      ctx.strokeStyle = MID;
      ctx.lineWidth = 1.5;
      ctx.setLineDash([7, 7]);
      ctx.lineDashOffset = -this.time * 22;
      ctx.beginPath();
      ctx.arc(island.x, island.y, island.reach, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }
  }

  drawPlayer(ctx) {
    const p = this.player;
    drawAvatar(ctx, p.x, p.y, p.angle, { width: 2.5 });
    drawText(ctx, "YOU", p.x, p.y - 34, 10, { center: true, color: MID, width: 1.5 });
    this.drawEmote(ctx, p);
  }

  drawOther(ctx, other) {
    drawAvatar(ctx, other.renderX, other.renderY, other.renderAngle, { width: 2 });
    drawText(ctx, other.handle.slice(0, 12), other.renderX, other.renderY - 34, 10, {
      center: true,
      color: INK,
      width: 1.5,
    });
    if (other.island) {
      // They're inside an island right now.
      drawText(ctx, "PLAYING", other.renderX, other.renderY + 22, 8, {
        center: true,
        color: MID,
        width: 1.5,
      });
    }
    this.drawEmote(ctx, other);
  }

  drawEmote(ctx, entity) {
    if (!entity.emote || this.time > entity.emoteUntil) return;
    const size = 15;
    const width = textWidth(entity.emote, size);
    const x = entity.x ?? entity.renderX;
    const y = (entity.y ?? entity.renderY) - 62;

    ctx.save();
    ctx.fillStyle = PAPER;
    ctx.strokeStyle = INK;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.rect(x - width / 2 - 9, y - 8, width + 18, size + 16);
    ctx.fill();
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(x - 5, y + size + 8);
    ctx.lineTo(x, y + size + 16);
    ctx.lineTo(x + 5, y + size + 8);
    ctx.stroke();
    ctx.restore();

    drawText(ctx, entity.emote, x, y, size, { center: true, color: INK, width: 2 });
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
    ctx.fillStyle = INK;
    ctx.fillRect(x + this.player.x * scaleX - 2.5, y + this.player.y * scaleY - 2.5, 5, 5);
    ctx.restore();
  }
}
