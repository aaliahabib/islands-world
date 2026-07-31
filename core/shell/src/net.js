// WebSocket client for the presence + score server.
//
// The shell is the only networked, trusted client in the system. Islands never
// touch the network — they postMessage their score to us and we submit it.
//
// Everything here degrades: if the server is down the world still works, you
// just play alone and scores don't persist.

import { CONFIG, WORLD } from "./config.js";

const RECONNECT_BASE_MS = 900;
const RECONNECT_MAX_MS = 12000;

export class Net extends EventTarget {
  constructor(handle) {
    super();
    this.handle = handle;
    this.socket = null;
    this.id = null;
    this.state = "offline";
    this.attempts = 0;
    this.reconnectTimer = null;
    this.lastSent = 0;
    this.closedByUs = false;
  }

  get online() {
    return this.socket && this.socket.readyState === WebSocket.OPEN;
  }

  setState(state) {
    if (this.state === state) return;
    this.state = state;
    this.dispatchEvent(new CustomEvent("state", { detail: state }));
  }

  connect() {
    if (!CONFIG.serverUrl) {
      // Opened straight off the filesystem, or no server configured.
      this.setState("offline");
      return;
    }
    this.closedByUs = false;
    this.setState(this.attempts === 0 ? "connecting" : "reconnecting");

    let socket;
    try {
      socket = new WebSocket(CONFIG.serverUrl);
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.socket = socket;

    socket.addEventListener("open", () => {
      this.attempts = 0;
      this.setState("online");
      this.send({ t: "join", handle: this.handle });
    });

    socket.addEventListener("message", (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return; // Malformed frames are ignored, never fatal.
      }
      if (!message || typeof message.t !== "string") return;
      this.dispatchEvent(new CustomEvent(message.t, { detail: message }));
      if (message.t === "welcome" && typeof message.id === "string") {
        this.id = message.id;
      }
    });

    socket.addEventListener("close", () => {
      this.socket = null;
      if (this.closedByUs) return;
      this.setState("offline");
      this.scheduleReconnect();
    });

    socket.addEventListener("error", () => {
      // 'close' always follows; nothing to do but let it.
    });
  }

  scheduleReconnect() {
    if (this.reconnectTimer || this.closedByUs) return;
    this.attempts += 1;
    const delay = Math.min(RECONNECT_BASE_MS * 2 ** (this.attempts - 1), RECONNECT_MAX_MS);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  send(payload) {
    if (!this.online) return false;
    try {
      this.socket.send(JSON.stringify(payload));
      return true;
    } catch {
      return false;
    }
  }

  /** Rate-limited position update. Call every frame; it throttles itself. */
  sendPosition(x, y, angle, now) {
    const interval = 1000 / WORLD.positionHz;
    if (now - this.lastSent < interval) return;
    this.lastSent = now;
    this.send({
      t: "pos",
      x: Math.round(x),
      y: Math.round(y),
      a: Math.round(angle),
    });
  }

  sendEmote(emote) {
    this.send({ t: "emote", e: emote });
  }

  sendEnter(islandId) {
    this.send({ t: "enter", island: islandId });
  }

  sendLeave() {
    this.send({ t: "leave" });
  }

  /**
   * Forward a score from an island.
   * `final` marks the end of a run — that's what gets added to the world total.
   */
  sendScore(islandId, value, final) {
    this.send({ t: "score", island: islandId, value, final: !!final });
  }

  disconnect() {
    this.closedByUs = true;
    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    if (this.socket) {
      try {
        this.socket.close();
      } catch {
        /* already gone */
      }
    }
    this.socket = null;
    this.setState("offline");
  }
}
