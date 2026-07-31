// Deployment configuration for the overworld shell.
//
// This is a plain script (not a module) loaded before the app, so it can be
// swapped at deploy time without rebuilding anything. CI overwrites it using
// the SERVER_URL repository variable — see .github/workflows/deploy.yml.

window.ISLANDS_CONFIG = {
  // WebSocket URL of the presence/score server, e.g.
  //   "wss://islands-world-server.onrender.com/ws"
  // Leave null to talk to whatever host is serving this page, which is what you
  // want for local development (`scripts/dev` serves the site and the server
  // together on one port).
  serverUrl: null,

  // The name of the world, drawn on the map.
  worldName: "ISLANDS WORLD",

  // Islands are untrusted code — one student's game runs in everyone else's
  // browser — so they are mounted in a sandboxed iframe.
  //
  //   false → sandbox="allow-scripts allow-same-origin"  (the default; pygbag
  //           needs same-origin for its storage, and this is what the build
  //           plan chose for simplicity)
  //   true  → sandbox="allow-scripts", an opaque origin. Stronger, but some
  //           pygbag builds fail to boot without storage access. Try it, and if
  //           islands still load, keep it.
  //
  // The genuinely strong option is serving islands from a separate subdomain —
  // see "Hardening the sandbox" in the README.
  strictSandbox: false,
};
