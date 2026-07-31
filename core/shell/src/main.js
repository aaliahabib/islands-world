// Islands World — the overworld shell.
//
// This is the trusted client: it owns the WebSocket, draws the map, mounts
// island iframes, and submits the scores those islands report.

import { CONFIG } from "./config.js";
import { Hud } from "./hud.js";
import { Input } from "./input.js";
import { IslandHost } from "./island-host.js";
import { Net } from "./net.js";
import { World } from "./world.js";

const HANDLE_KEY = "islands-world.handle";

const el = (id) => document.getElementById(id);

const dom = {
  canvas: el("map"),
  connection: el("connection"),
  scores: el("scores"),
  worldTotal: el("world-total"),
  prompt: el("prompt"),
  emotes: el("emotes"),
  worldName: el("world-name"),
  gate: el("handle-gate"),
  gateForm: el("handle-form"),
  gateInput: el("handle-input"),
  stage: el("island-stage"),
  frameWrap: el("island-frame-wrap"),
  islandTitle: el("island-title"),
  islandStatus: el("island-status"),
  islandExit: el("island-exit"),
};

// ── Registry ───────────────────────────────────────────────────────────────

async function loadRegistry() {
  try {
    const response = await fetch("./registry.json", { cache: "no-cache" });
    if (!response.ok) throw new Error(String(response.status));
    const data = await response.json();
    const islands = Array.isArray(data) ? data : data.islands;
    if (!Array.isArray(islands)) throw new Error("registry is not a list");
    return islands.filter((entry) => entry && typeof entry.id === "string");
  } catch (error) {
    console.warn("[shell] could not load registry.json —", error);
    return [];
  }
}

function sanitizeHandle(raw) {
  return String(raw || "")
    .toUpperCase()
    .replace(/[^A-Z0-9 _.'!?-]/g, "")
    .trim()
    .slice(0, 12);
}

// ── Boot ───────────────────────────────────────────────────────────────────

async function boot() {
  dom.worldName.textContent = CONFIG.worldName;
  document.title = CONFIG.worldName.replace(/\b\w/g, (c) => c.toUpperCase());

  const registry = await loadRegistry();
  const world = new World(registry);

  if (!registry.length) {
    console.warn(
      "[shell] no islands in the registry — run scripts/build-islands to generate one"
    );
  }

  const handle = await askForHandle();
  const net = new Net(handle);

  const hud = new Hud(dom, {
    onEmote: (emote) => {
      world.showEmote(net.id, emote, net.id);
      world.player.emote = emote;
      world.player.emoteUntil = world.time + 2.6;
      net.sendEmote(emote);
    },
  });
  hud.setHandle(handle);
  hud.setWorldName(CONFIG.worldName);
  hud.setConnection(CONFIG.serverUrl ? "connecting" : "offline");

  // Scores that arrive while offline still show locally, so a kid always sees
  // their own run land somewhere.
  let localTotal = 0;

  const host = new IslandHost(
    {
      stage: dom.stage,
      frameWrap: dom.frameWrap,
      title: dom.islandTitle,
      status: dom.islandStatus,
      exit: dom.islandExit,
    },
    {
      onScore: (island, score) => {
        net.sendScore(island.id, score, false);
      },
      onGameOver: (island, score) => {
        localTotal += score;
        net.sendScore(island.id, score, true);
      },
      onExit: () => {
        input.setEnabled(true);
        net.sendLeave();
        dom.canvas.focus();
      },
    }
  );

  const input = new Input({
    onEnter: () => {
      if (host.active) return;
      const island = world.nearest;
      if (!island) return;
      input.setEnabled(false);
      net.sendEnter(island.id);
      host.enter(island);
    },
    onExit: () => {
      if (host.active) host.exit();
    },
    onEmote: (emote) => {
      if (host.active) return;
      world.player.emote = emote;
      world.player.emoteUntil = world.time + 2.6;
      net.sendEmote(emote);
    },
  });

  // ── Network events ───────────────────────────────────────────────────────

  net.addEventListener("state", (event) => {
    const state = event.detail;
    hud.setConnection(state);

    if (state === "online") {
      // Re-announce which island we're in after a reconnect.
      if (host.active && host.island) net.sendEnter(host.island.id);
    } else {
      // Disconnected: show at least our own total so a run never vanishes.
      world.others.clear();
      hud.setBoard(localTotal ? [{ handle, total: localTotal }] : [], localTotal);
    }
  });

  net.addEventListener("welcome", (event) => {
    const detail = event.detail;
    if (Array.isArray(detail.board)) {
      hud.setBoard(detail.board, detail.worldTotal);
    }
  });

  net.addEventListener("world", (event) => {
    const detail = event.detail;
    if (Array.isArray(detail.players)) world.updateOthers(detail.players, net.id);
    if (detail.islands && typeof detail.islands === "object") {
      world.setOccupancy(detail.islands);
    }
  });

  net.addEventListener("board", (event) => {
    const detail = event.detail;
    if (Array.isArray(detail.entries)) {
      hud.setBoard(detail.entries, detail.worldTotal);
    }
  });

  net.addEventListener("emote", (event) => {
    const detail = event.detail;
    if (typeof detail.id === "string" && typeof detail.e === "string") {
      world.showEmote(detail.id, detail.e.slice(0, 6), net.id);
    }
  });

  net.connect();

  // ── Canvas sizing ────────────────────────────────────────────────────────

  const ctx = dom.canvas.getContext("2d", { alpha: false });
  let viewWidth = 0;
  let viewHeight = 0;

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    viewWidth = window.innerWidth;
    viewHeight = window.innerHeight;
    dom.canvas.width = Math.floor(viewWidth * dpr);
    dom.canvas.height = Math.floor(viewHeight * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  window.addEventListener("resize", resize);
  resize();

  // ── Main loop ────────────────────────────────────────────────────────────

  let previous = performance.now();

  function frame(now) {
    // Cap dt so a backgrounded tab doesn't teleport everyone on return.
    const dt = Math.min((now - previous) / 1000, 0.05);
    previous = now;

    if (host.active) {
      // An island is on screen covering the whole map. Don't simulate or draw
      // the overworld underneath it — every frame we skip is a frame the
      // island's Python runtime gets instead, and it needs them while booting.
      hud.setPrompt(null);
    } else {
      const nearest = world.update(dt, input.state);
      world.focusCamera(viewWidth, viewHeight, dt);
      net.sendPosition(world.player.x, world.player.y, world.player.angle, now);
      hud.setPrompt(
        nearest ? `PRESS E TO PLAY ${(nearest.name || nearest.id).toUpperCase()}` : null
      );
      world.draw(ctx, viewWidth, viewHeight);
    }

    requestAnimationFrame(frame);
  }

  requestAnimationFrame(frame);

  // Be polite to the server when the tab goes away.
  window.addEventListener("pagehide", () => net.disconnect());
}

function askForHandle() {
  return new Promise((resolve) => {
    // ?handle=NAME skips the gate — handy for a demo screen or a kiosk.
    const fromUrl = sanitizeHandle(new URLSearchParams(location.search).get("handle"));
    if (fromUrl) {
      dom.gate.hidden = true;
      resolve(fromUrl);
      return;
    }

    const saved = sanitizeHandle(localStorage.getItem(HANDLE_KEY) || "");
    if (saved) dom.gateInput.value = saved;

    dom.gate.hidden = false;
    dom.gateInput.focus();
    dom.gateInput.select();

    dom.gateForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const handle = sanitizeHandle(dom.gateInput.value) || "PLAYER";
      try {
        localStorage.setItem(HANDLE_KEY, handle);
      } catch {
        /* private browsing — not important */
      }
      dom.gate.hidden = true;
      resolve(handle);
    });
  });
}

boot().catch((error) => {
  console.error("[shell] failed to start", error);
  document.body.innerHTML =
    '<pre style="padding:24px;font:14px ui-monospace,monospace">' +
    "Islands World failed to start.\n\n" +
    String(error && error.stack ? error.stack : error) +
    "</pre>";
});
