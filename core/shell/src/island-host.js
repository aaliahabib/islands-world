// Mounts an island in a sandboxed iframe and bridges its score out to the shell.
//
// One fresh instance per visit: entering builds a new iframe, leaving destroys
// it. That's both the teardown story (no state leaks between islands) and the
// security story (a student's game runs in everyone else's browser).

import { CONFIG } from "./config.js";

const LOAD_TIMEOUT_MS = 30000;

export class IslandHost {
  /**
   * @param {object} elements  stage / frameWrap / title / status / exit button
   * @param {object} handlers  { onScore, onGameOver, onExit }
   */
  constructor(elements, handlers) {
    this.stage = elements.stage;
    this.frameWrap = elements.frameWrap;
    this.titleEl = elements.title;
    this.statusEl = elements.status;
    this.exitButton = elements.exit;
    this.handlers = handlers;

    this.iframe = null;
    this.island = null;
    this.liveScore = 0;
    this.loadTimer = null;
    this.booted = false;

    this.onMessage = this.onMessage.bind(this);
    this.fitFrame = this.fitFrame.bind(this);
    window.addEventListener("message", this.onMessage);
    window.addEventListener("resize", this.fitFrame);

    this.exitButton.addEventListener("click", () => this.exit());
  }

  /**
   * Letterbox the iframe to the island's own aspect ratio. If we just let it
   * fill the stage, pygbag stretches the canvas and the edges of the play area
   * end up off-screen — which matters a lot in a game built on screen-wrap.
   */
  fitFrame() {
    if (!this.iframe || !this.island) return;
    const box = this.frameWrap.getBoundingClientRect();
    if (!box.width || !box.height) {
      // The stage was still hidden when we measured. Try again once it's laid
      // out; until then the CSS 100%/100% fallback keeps the iframe usable.
      requestAnimationFrame(this.fitFrame);
      return;
    }

    const ratio = (Number(this.island.width) || 900) / (Number(this.island.height) || 700);
    let width = box.width;
    let height = width / ratio;
    if (height > box.height) {
      height = box.height;
      width = height * ratio;
    }
    this.iframe.style.width = `${Math.floor(width)}px`;
    this.iframe.style.height = `${Math.floor(height)}px`;
  }

  get active() {
    return this.island !== null;
  }

  sandboxAttribute() {
    return CONFIG.strictSandbox ? "allow-scripts" : "allow-scripts allow-same-origin";
  }

  enter(island) {
    if (this.active) return;
    this.island = island;
    this.liveScore = 0;
    this.booted = false;

    this.titleEl.textContent = `${(island.name || island.id).toUpperCase()}${
      island.author ? ` · BY ${island.author.toUpperCase()}` : ""
    }`;

    // Show the stage BEFORE the iframe exists. An iframe inserted into a
    // display:none subtree boots its Python runtime against a zero-size
    // viewport and never recovers — it just sits on "Loading" forever.
    this.stage.hidden = false;
    this.showLoading();

    const iframe = document.createElement("iframe");
    iframe.setAttribute("sandbox", this.sandboxAttribute());
    iframe.setAttribute("title", island.name || island.id);
    iframe.setAttribute("allow", "autoplay; gamepad");

    iframe.addEventListener("error", () => this.showBroken());

    this.iframe = iframe;
    this.fitFrame();

    // Setting src last means the load starts with the frame already laid out.
    // Cache-busted by the version the build stamped into the registry, so a
    // student's change shows up the moment it deploys.
    const version = encodeURIComponent(island.version || "0");
    iframe.src = `${island.bundleUrl}${island.bundleUrl.includes("?") ? "&" : "?"}v=${version}`;
    this.frameWrap.replaceChildren(iframe);

    // pygbag builds take a moment to download and boot the Python runtime. If
    // nothing has happened well past that, the island is broken.
    this.loadTimer = setTimeout(() => {
      if (!this.booted) this.showBroken();
    }, LOAD_TIMEOUT_MS);

    iframe.addEventListener("load", () => {
      // The document loaded; the game may still be booting Python. Give the
      // island a chance to say hello, but hide the spinner once pixels can
      // plausibly be on screen.
      setTimeout(() => {
        if (this.island === island && !this.booted) this.hideStatus();
      }, 2500);
    });

    iframe.focus();
  }

  onMessage(event) {
    if (!this.iframe || event.source !== this.iframe.contentWindow) return;

    const data = event.data;
    if (!data || typeof data !== "object") return;

    // Everything from an island is untrusted input. Parse defensively; a
    // malformed message is dropped, never thrown.
    const type = typeof data.type === "string" ? data.type : null;
    if (!type) return;

    const value = Number(data.value);
    if (!Number.isFinite(value)) return;
    const score = Math.trunc(value);

    this.booted = true;
    clearTimeout(this.loadTimer);
    this.loadTimer = null;

    if (type === "score") {
      this.hideStatus();
      this.liveScore = score;
      this.handlers.onScore?.(this.island, score);
    } else if (type === "game_over") {
      this.liveScore = score;
      this.handlers.onGameOver?.(this.island, score);
      this.showGameOver(score);
    }
  }

  // ── Overlays ─────────────────────────────────────────────────────────────

  showStatus(node) {
    this.statusEl.replaceChildren(node);
    this.statusEl.hidden = false;
  }

  hideStatus() {
    this.statusEl.hidden = true;
    this.statusEl.replaceChildren();
  }

  showLoading() {
    const box = document.createElement("div");
    box.className = "box";
    const spinner = document.createElement("div");
    spinner.className = "spinner";
    const headline = document.createElement("div");
    headline.className = "detail";
    headline.textContent = "LOADING ISLAND…";
    box.append(spinner, headline);
    this.showStatus(box);
  }

  showGameOver(score) {
    const box = document.createElement("div");
    box.className = "box";

    const headline = document.createElement("div");
    headline.className = "headline";
    headline.textContent = "GAME OVER";

    const final = document.createElement("div");
    final.className = "final";
    final.textContent = score.toLocaleString();

    const detail = document.createElement("div");
    detail.className = "detail";
    detail.textContent = "ADDED TO THE WORLD SCOREBOARD";

    const actions = document.createElement("div");
    actions.className = "actions";

    const again = document.createElement("button");
    again.type = "button";
    again.textContent = "PLAY AGAIN";
    again.addEventListener("click", () => this.restart());

    const back = document.createElement("button");
    back.type = "button";
    back.textContent = "← BACK TO WORLD";
    back.addEventListener("click", () => this.exit());

    actions.append(again, back);
    box.append(headline, final, detail, actions);
    this.showStatus(box);
    back.focus();
  }

  showBroken() {
    const box = document.createElement("div");
    box.className = "box";

    const headline = document.createElement("div");
    headline.className = "headline";
    headline.textContent = "🚧 THIS ISLAND LOOKS BROKEN";

    const detail = document.createElement("div");
    detail.className = "detail";
    detail.textContent =
      "It didn't finish loading. That's on the island, not on you — go tell whoever owns it.";

    const actions = document.createElement("div");
    actions.className = "actions";

    const retry = document.createElement("button");
    retry.type = "button";
    retry.textContent = "TRY AGAIN";
    retry.addEventListener("click", () => this.restart());

    const back = document.createElement("button");
    back.type = "button";
    back.textContent = "← BACK TO WORLD";
    back.addEventListener("click", () => this.exit());

    actions.append(retry, back);
    box.append(headline, detail, actions);
    this.showStatus(box);
    back.focus();
  }

  // ── Lifecycle ────────────────────────────────────────────────────────────

  restart() {
    const island = this.island;
    if (!island) return;
    this.teardown();
    this.enter(island);
  }

  teardown() {
    clearTimeout(this.loadTimer);
    this.loadTimer = null;
    // Removing the iframe destroys the whole Python runtime with it — no
    // leftover timers, audio, or state bleeding into the next island.
    this.frameWrap.replaceChildren();
    this.iframe = null;
    this.island = null;
    this.booted = false;
    this.hideStatus();
  }

  exit() {
    if (!this.active) return;
    const island = this.island;
    this.teardown();
    this.stage.hidden = true;
    this.handlers.onExit?.(island);
  }

  destroy() {
    window.removeEventListener("message", this.onMessage);
    window.removeEventListener("resize", this.fitFrame);
    this.teardown();
  }
}
