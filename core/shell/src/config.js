// Reads the deployment config that ../config.js put on `window`, and fills in
// sensible defaults so the shell also works when nothing has been configured.

const raw = (typeof window !== "undefined" && window.ISLANDS_CONFIG) || {};

function deriveServerUrl() {
  if (typeof raw.serverUrl === "string" && raw.serverUrl.trim()) {
    return raw.serverUrl.trim();
  }
  // No explicit URL: talk to whoever served this page. That's exactly right for
  // local development, where scripts/dev serves the site and the WebSocket
  // server on one port.
  if (typeof location === "undefined" || !location.host) return null;
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${location.host}/ws`;
}

export const CONFIG = {
  serverUrl: deriveServerUrl(),
  worldName: raw.worldName || "ISLANDS WORLD",
  strictSandbox: raw.strictSandbox === true,
};

// ── Palette ────────────────────────────────────────────────────────────────
// The island games are white-on-black. The overworld is the inverse.
export const INK = "#000";
export const PAPER = "#fff";
export const FAINT = "#d2d2d2";
export const MID = "#8a8a8a";

// ── World tuning ───────────────────────────────────────────────────────────
export const WORLD = {
  slotCols: 4,
  slotSpacingX: 660,
  slotSpacingY: 540,
  margin: 420,
  islandRadius: 168,
  playerSpeed: 320,
  playerRadius: 13,
  // How close you have to be to an island's edge before you can enter it.
  enterPadding: 46,
  // How often we tell the server where we are.
  positionHz: 15,
  emoteDuration: 2.6,
};

export const EMOTES = ["HI", "GG", "WOW", "?", "!"];
