// Islands World — presence + scoreboard server.
//
// Deliberately tiny. It knows who is online, where their avatar is, and what
// everyone has scored. It runs no game logic and executes no student code.
//
// Every inbound message is parsed defensively: anything malformed is dropped,
// never trusted, never fatal. Scores are NOT clamped — an unfair scoreboard is
// part of the fun — they just have to be a finite integer.
//
//   PORT=8787 SITE_DIR=../../site node server.js

import { createServer } from "node:http";
import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { extname, join, normalize, resolve, sep } from "node:path";
import { WebSocketServer } from "ws";

import { createStore } from "./store.js";

const PORT = Number(process.env.PORT) || 8787;
const SITE_DIR = process.env.SITE_DIR ? resolve(process.env.SITE_DIR) : null;

const WORLD_TICK_MS = 1000 / 15; // how often we broadcast the roster
const BOARD_DEBOUNCE_MS = 400;
const HEARTBEAT_MS = 30000;

// A generous ceiling — this exists so a runaway loop in a student's game can't
// wedge the server, not to police anyone's score.
const MAX_MESSAGES_PER_SECOND = 60;
const MAX_MESSAGE_BYTES = 4096;

const store = await createStore();

// ── Validation helpers ─────────────────────────────────────────────────────

function cleanHandle(value) {
  if (typeof value !== "string") return null;
  const handle = value
    .toUpperCase()
    .replace(/[^A-Z0-9 _.'!?-]/g, "")
    .trim()
    .slice(0, 12);
  return handle || null;
}

function cleanId(value, max = 48) {
  if (typeof value !== "string") return null;
  const id = value.trim().slice(0, max);
  return /^[A-Za-z0-9._-]+$/.test(id) ? id : null;
}

function cleanNumber(value, limit) {
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return Math.max(-limit, Math.min(limit, Math.round(n)));
}

function cleanScore(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  // No clamping of magnitude — only a guard that keeps arithmetic exact and
  // JSON well-formed.
  const rounded = Math.trunc(n);
  if (!Number.isSafeInteger(rounded)) return null;
  return rounded;
}

// ── Static file serving (local dev + single-service deploys) ───────────────

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".wasm": "application/wasm",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".apk": "application/octet-stream",
  ".data": "application/octet-stream",
  ".zip": "application/zip",
  ".txt": "text/plain; charset=utf-8",
};

async function serveStatic(req, res) {
  if (!SITE_DIR) {
    res.writeHead(404, { "content-type": "text/plain" });
    res.end("Islands World server. No static site configured (set SITE_DIR).\n");
    return;
  }

  const requestPath = decodeURIComponent((req.url || "/").split("?")[0]);
  // Resolve inside SITE_DIR only — no climbing out with ../
  const safePath = normalize(requestPath).replace(/^(\.\.[/\\])+/, "");
  let filePath = join(SITE_DIR, safePath);
  if (!filePath.startsWith(SITE_DIR + sep) && filePath !== SITE_DIR) {
    res.writeHead(403).end("forbidden");
    return;
  }

  try {
    let info = await stat(filePath);
    if (info.isDirectory()) {
      filePath = join(filePath, "index.html");
      info = await stat(filePath);
    }
    res.writeHead(200, {
      "content-type": MIME[extname(filePath).toLowerCase()] || "application/octet-stream",
      "content-length": info.size,
      "cache-control": "no-cache",
      // NOTE: deliberately NO Cross-Origin-Embedder-Policy. pygbag's own dev
      // server sends `require-corp`, but islands load their Python runtime from
      // pygame-web.github.io, which does not send a CORP header — under
      // require-corp the browser blocks the runtime and islands never boot.
      "cross-origin-resource-policy": "cross-origin",
      "access-control-allow-origin": "*",
    });
    createReadStream(filePath).pipe(res);
  } catch {
    res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    res.end("not found\n");
  }
}

const httpServer = createServer((req, res) => {
  if (req.url === "/healthz") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ ok: true, players: clients.size }));
    return;
  }
  void serveStatic(req, res);
});

// ── Presence ───────────────────────────────────────────────────────────────

/** @type {Map<string, {socket: any, id: string, handle: string, x: number, y: number, a: number, island: string|null, alive: boolean, budget: number, budgetAt: number}>} */
const clients = new Map();
let nextId = 1;

const wss = new WebSocketServer({ server: httpServer, path: "/ws", maxPayload: MAX_MESSAGE_BYTES });

function broadcast(payload) {
  const text = JSON.stringify(payload);
  for (const client of clients.values()) {
    if (client.socket.readyState === client.socket.OPEN) {
      try {
        client.socket.send(text);
      } catch {
        /* socket is going away; the close handler will clean it up */
      }
    }
  }
}

function buildBoard() {
  const { totals } = store.snapshot();
  const entries = Object.entries(totals)
    .map(([handle, value]) => ({
      handle,
      total: Number(value?.total) || 0,
      runs: Number(value?.runs) || 0,
    }))
    .sort((a, b) => b.total - a.total);
  const worldTotal = entries.reduce((sum, entry) => sum + entry.total, 0);
  return { entries, worldTotal };
}

let boardTimer = null;
function scheduleBoard() {
  if (boardTimer) return;
  boardTimer = setTimeout(() => {
    boardTimer = null;
    const { entries, worldTotal } = buildBoard();
    broadcast({ t: "board", entries: entries.slice(0, 30), worldTotal });
  }, BOARD_DEBOUNCE_MS);
}

function islandOccupancy() {
  const counts = Object.create(null);
  for (const client of clients.values()) {
    if (client.island) counts[client.island] = (counts[client.island] || 0) + 1;
  }
  return counts;
}

// ── Message handling ───────────────────────────────────────────────────────

function withinBudget(client) {
  const now = Date.now();
  if (now - client.budgetAt >= 1000) {
    client.budgetAt = now;
    client.budget = 0;
  }
  client.budget += 1;
  return client.budget <= MAX_MESSAGES_PER_SECOND;
}

function handleMessage(client, raw) {
  if (!withinBudget(client)) return;

  let message;
  try {
    message = JSON.parse(raw);
  } catch {
    return;
  }
  if (!message || typeof message !== "object" || typeof message.t !== "string") return;

  switch (message.t) {
    case "join": {
      const handle = cleanHandle(message.handle);
      if (handle) client.handle = handle;
      const { entries, worldTotal } = buildBoard();
      client.socket.send(
        JSON.stringify({
          t: "welcome",
          id: client.id,
          handle: client.handle,
          board: entries.slice(0, 30),
          worldTotal,
        })
      );
      break;
    }

    case "pos": {
      const x = cleanNumber(message.x, 100000);
      const y = cleanNumber(message.y, 100000);
      const a = cleanNumber(message.a, 100000);
      if (x === null || y === null) return;
      client.x = x;
      client.y = y;
      if (a !== null) client.a = a;
      break;
    }

    case "emote": {
      if (typeof message.e !== "string") return;
      const emote = message.e.slice(0, 6).toUpperCase();
      if (!emote) return;
      broadcast({ t: "emote", id: client.id, e: emote });
      break;
    }

    case "enter": {
      const island = cleanId(message.island);
      if (!island) return;
      client.island = island;
      break;
    }

    case "leave": {
      client.island = null;
      break;
    }

    case "score": {
      const score = cleanScore(message.value);
      if (score === null) return;
      const island = cleanId(message.island);
      if (message.final === true) {
        // A finished run is what actually lands on the scoreboard.
        store.commitRun(client.handle, island, score);
        scheduleBoard();
      }
      // Live in-progress scores are not persisted; they'd just be noise.
      break;
    }

    default:
      break; // unknown message types are ignored
  }
}

wss.on("connection", (socket, request) => {
  const id = `p${nextId++}`;
  const client = {
    socket,
    id,
    handle: `PLAYER${nextId - 1}`,
    x: 0,
    y: 0,
    a: -90,
    island: null,
    alive: true,
    budget: 0,
    budgetAt: Date.now(),
  };
  clients.set(id, client);
  console.log(`[ws] + ${id} (${clients.size} online)`);

  socket.on("message", (data) => {
    try {
      handleMessage(client, typeof data === "string" ? data : data.toString("utf8"));
    } catch (error) {
      // A bad message must never take the server down.
      console.warn(`[ws] error handling message from ${id} —`, error.message);
    }
  });

  socket.on("pong", () => {
    client.alive = true;
  });

  socket.on("close", () => {
    clients.delete(id);
    console.log(`[ws] - ${id} (${clients.size} online)`);
  });

  socket.on("error", () => {
    clients.delete(id);
  });

  request?.socket?.setKeepAlive?.(true);
});

// Roster broadcast.
setInterval(() => {
  if (clients.size === 0) return;
  const players = [];
  for (const client of clients.values()) {
    players.push({
      id: client.id,
      handle: client.handle,
      x: client.x,
      y: client.y,
      a: client.a,
      island: client.island,
    });
  }
  broadcast({ t: "world", players, islands: islandOccupancy() });
}, WORLD_TICK_MS).unref?.();

// Drop connections that stopped answering.
setInterval(() => {
  for (const client of clients.values()) {
    if (!client.alive) {
      try {
        client.socket.terminate();
      } catch {
        /* already gone */
      }
      clients.delete(client.id);
      continue;
    }
    client.alive = false;
    try {
      client.socket.ping();
    } catch {
      /* will be cleaned up next tick */
    }
  }
}, HEARTBEAT_MS).unref?.();

// ── Start / stop ───────────────────────────────────────────────────────────

httpServer.listen(PORT, () => {
  console.log(`[islands-world] listening on http://localhost:${PORT}`);
  console.log(`[islands-world] websocket at ws://localhost:${PORT}/ws`);
  if (SITE_DIR) console.log(`[islands-world] serving site from ${SITE_DIR}`);
});

async function shutdown(signal) {
  console.log(`\n[islands-world] ${signal} — saving scores…`);
  try {
    await store.close();
  } catch (error) {
    console.error("[islands-world] failed to save scores —", error.message);
  }
  httpServer.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 3000).unref();
}

process.on("SIGINT", () => void shutdown("SIGINT"));
process.on("SIGTERM", () => void shutdown("SIGTERM"));
