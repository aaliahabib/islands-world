// Islands World — the overworld shell.
//
// This is the trusted client: it owns the WebSocket, draws the map, mounts
// island iframes, and submits the scores those islands report.

import {
  COLOURS,
  EMOTE_DURATION,
  HATS,
  HEADS,
  drawFigure,
  poseFor,
  sanitizeAvatar,
} from "./avatar.js";
import { CONFIG } from "./config.js";
import { Hud } from "./hud.js";
import { Input } from "./input.js";
import { IslandHost } from "./island-host.js";
import { Net } from "./net.js";
import { World } from "./world.js";

const HANDLE_KEY = "islands-world.handle";
const AVATAR_KEY = "islands-world.avatar";

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
  avatarPreview: el("avatar-preview"),
  avatarPicker: el("avatar-picker"),
};

// ── Registry ───────────────────────────────────────────────────────────────

async function loadRegistry() {
  try {
    const response = await fetch("./registry.json", { cache: "no-cache" });
    if (!response.ok) throw new Error(String(response.status));
    const data = await response.json();
    const islands = Array.isArray(data) ? data : data.islands;
    if (!Array.isArray(islands)) throw new Error("registry is not a list");
    return {
      islands: islands.filter((entry) => entry && typeof entry.id === "string"),
      runtime: (!Array.isArray(data) && data.runtime) || null,
    };
  } catch (error) {
    console.warn("[shell] could not load registry.json —", error);
    return { islands: [], runtime: null };
  }
}

/**
 * Pull the Python runtime into the browser cache while the player is still
 * walking around.
 *
 * It's ~21 MB (main.wasm 13.4, main.data 6.7, main.js 0.9) and it's the entire
 * reason the first island a browser opens takes about a minute. Every island
 * shares it, so paying for it once, early, in the background, is the difference
 * between "press E and wait a minute" and "press E and play".
 *
 * Failures are ignored on purpose — this is an optimisation, and the island
 * will fetch whatever's missing itself.
 */
function prewarmRuntime(runtime) {
  const assets = runtime?.assets;
  if (!Array.isArray(assets) || !assets.length) return;

  // A beat after boot, so this never competes with the shell's own load.
  setTimeout(() => {
    for (const url of assets) {
      if (typeof url !== "string") continue;
      // no-cors: we don't need to read these, only to get them into the cache.
      fetch(url, { mode: "no-cors", credentials: "omit" }).catch(() => {});
    }
    console.info(`[shell] preloading ${assets.length} runtime asset(s) in the background`);
  }, 1200);
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

  const { islands, runtime } = await loadRegistry();
  const world = new World(islands);

  if (!islands.length) {
    console.warn(
      "[shell] no islands in the registry — run scripts/build-islands to generate one"
    );
  }
  prewarmRuntime(runtime);

  const { handle, avatar } = await askForHandle();
  world.setAvatar(avatar);
  const net = new Net(handle, avatar);

  const hud = new Hud(dom, {
    onEmote: (emote) => {
      world.playEmote(emote);
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
      world.playEmote(emote);
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

function loadAvatar() {
  try {
    return sanitizeAvatar(JSON.parse(localStorage.getItem(AVATAR_KEY) || "null"));
  } catch {
    return sanitizeAvatar(null);
  }
}

/** Build the three ‹ › rows and keep the preview in step with them. */
function buildAvatarPicker(avatar, onChange) {
  const axes = [
    { key: "c", label: "COLOUR", options: COLOURS.map((c) => c.name) },
    { key: "h", label: "HEAD", options: HEADS },
    { key: "t", label: "HAT", options: HATS },
  ];

  dom.avatarPicker.replaceChildren();
  const valueEls = {};

  for (const axis of axes) {
    const row = document.createElement("div");
    row.className = "avatar-row";

    const name = document.createElement("span");
    name.className = "avatar-label";
    name.textContent = axis.label;

    const step = (delta) => {
      const n = axis.options.length;
      avatar[axis.key] = (avatar[axis.key] + delta + n) % n;
      valueEls[axis.key].textContent = axis.options[avatar[axis.key]];
      onChange();
    };

    const prev = document.createElement("button");
    prev.type = "button";
    prev.textContent = "‹";
    prev.setAttribute("aria-label", `previous ${axis.label.toLowerCase()}`);
    prev.addEventListener("click", () => step(-1));

    const value = document.createElement("span");
    value.className = "avatar-value";
    value.textContent = axis.options[avatar[axis.key]];
    valueEls[axis.key] = value;

    const next = document.createElement("button");
    next.type = "button";
    next.textContent = "›";
    next.setAttribute("aria-label", `next ${axis.label.toLowerCase()}`);
    next.addEventListener("click", () => step(1));

    row.append(name, prev, value, next);
    dom.avatarPicker.append(row);
  }
}

function askForHandle() {
  return new Promise((resolve) => {
    const avatar = loadAvatar();

    // ?handle=NAME skips the gate — handy for a demo screen or a kiosk.
    const fromUrl = sanitizeHandle(new URLSearchParams(location.search).get("handle"));
    if (fromUrl) {
      dom.gate.hidden = true;
      resolve({ handle: fromUrl, avatar });
      return;
    }

    const saved = sanitizeHandle(localStorage.getItem(HANDLE_KEY) || "");
    if (saved) dom.gateInput.value = saved;

    // Preview: the figure waves at you while you pick.
    const previewCtx = dom.avatarPreview.getContext("2d");
    const start = performance.now();
    let previewing = true;
    function drawPreview(now) {
      if (!previewing) return;
      previewCtx.clearRect(0, 0, 120, 120);
      const t = ((now - start) / 1000 / EMOTE_DURATION) % 1;
      drawFigure(previewCtx, 60, 108, avatar, poseFor({ emote: "WAVE", emoteT: t }), 1, 1.7);
      requestAnimationFrame(drawPreview);
    }
    requestAnimationFrame(drawPreview);

    buildAvatarPicker(avatar, () => {});

    dom.gate.hidden = false;
    dom.gateInput.focus();
    dom.gateInput.select();

    dom.gateForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const handle = sanitizeHandle(dom.gateInput.value) || "PLAYER";
      try {
        localStorage.setItem(HANDLE_KEY, handle);
        localStorage.setItem(AVATAR_KEY, JSON.stringify(avatar));
      } catch {
        /* private browsing — not important */
      }
      previewing = false;
      dom.gate.hidden = true;
      resolve({ handle, avatar });
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
