// End-to-end check of the presence + score protocol.
//
//   node core/server/smoke-test.mjs [ws://localhost:8787/ws]
//
// Connects two players, walks them around, submits a score, and throws garbage
// at the server to prove malformed input is ignored rather than fatal.

import { WebSocket } from "ws";

const URL = process.argv[2] || "ws://localhost:8787/ws";

let failures = 0;

function check(label, condition, detail = "") {
  if (condition) {
    console.log(`  ✓ ${label}`);
  } else {
    failures += 1;
    console.log(`  ✗ ${label}${detail ? ` — ${detail}` : ""}`);
  }
}

function connect(handle) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(URL);
    const player = { socket, handle, messages: [], id: null };

    socket.on("message", (data) => {
      let message;
      try {
        message = JSON.parse(data.toString());
      } catch {
        return;
      }
      player.messages.push(message);
      if (message.t === "welcome") player.id = message.id;
    });
    socket.on("open", () => {
      socket.send(JSON.stringify({ t: "join", handle }));
      resolve(player);
    });
    socket.on("error", reject);
    setTimeout(() => reject(new Error(`timed out connecting to ${URL}`)), 5000);
  });
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const latest = (player, type) => [...player.messages].reverse().find((m) => m.t === type);

async function run() {
  console.log(`smoke-testing ${URL}\n`);

  const alice = await connect("ALICE");
  const bo = await connect("BO");
  await wait(300);

  check("both clients got a welcome", !!alice.id && !!bo.id, `alice=${alice.id} bo=${bo.id}`);
  check("ids are distinct", alice.id !== bo.id);

  // ── presence
  alice.socket.send(JSON.stringify({ t: "pos", x: 120, y: 340, a: 45 }));
  bo.socket.send(JSON.stringify({ t: "pos", x: 900, y: 200, a: -90 }));
  await wait(400);

  const world = latest(bo, "world");
  check("world broadcast arrives", !!world);
  const seenAlice = world?.players?.find((p) => p.id === alice.id);
  check("alice appears in the roster with her handle", seenAlice?.handle === "ALICE");
  check(
    "alice's position propagated",
    seenAlice?.x === 120 && seenAlice?.y === 340,
    JSON.stringify(seenAlice)
  );

  // ── island occupancy
  alice.socket.send(JSON.stringify({ t: "enter", island: "demo-01" }));
  await wait(300);
  check("island occupancy is counted", latest(bo, "world")?.islands?.["demo-01"] === 1);

  alice.socket.send(JSON.stringify({ t: "leave" }));
  await wait(300);
  check("leaving clears occupancy", !latest(bo, "world")?.islands?.["demo-01"]);

  // ── emotes
  bo.socket.send(JSON.stringify({ t: "emote", e: "GG" }));
  await wait(250);
  const emote = latest(alice, "emote");
  check("emotes relay to other players", emote?.e === "GG" && emote?.id === bo.id);

  // ── scores
  const before = latest(alice, "welcome")?.worldTotal ?? 0;
  const aliceBefore =
    latest(alice, "welcome")?.board?.find((e) => e.handle === "ALICE")?.total ?? 0;

  alice.socket.send(JSON.stringify({ t: "score", island: "demo-01", value: 250, final: false }));
  await wait(300);
  check(
    "in-progress scores do NOT hit the board",
    (latest(alice, "board")?.entries?.find((e) => e.handle === "ALICE")?.total ?? aliceBefore) ===
      aliceBefore
  );

  alice.socket.send(JSON.stringify({ t: "score", island: "demo-01", value: 1337, final: true }));
  await wait(700);
  const board = latest(alice, "board");
  check("finished runs land on the board", !!board);
  check(
    "alice's total went up by 1337",
    board?.entries?.find((e) => e.handle === "ALICE")?.total === aliceBefore + 1337,
    JSON.stringify(board?.entries)
  );
  check("world total went up too", (board?.worldTotal ?? 0) === before + 1337);

  // ── absurd scores are allowed: unfair is the point, there is no clamping
  bo.socket.send(JSON.stringify({ t: "score", island: "demo-01", value: 999999999, final: true }));
  await wait(700);
  check(
    "huge scores are accepted, not clamped",
    latest(bo, "board")?.entries?.find((e) => e.handle === "BO")?.total >= 999999999
  );

  // ── malformed input must be ignored, never fatal
  const garbage = [
    "not json at all",
    "{}",
    '{"t":123}',
    '{"t":"pos","x":"NaN","y":null}',
    '{"t":"score","value":"1e999","final":true}',
    '{"t":"score","value":null,"final":true}',
    '{"t":"emote","e":null}',
    '{"t":"enter","island":"../../etc/passwd"}',
    '{"t":"nonsense","payload":[1,2,3]}',
    JSON.stringify({ t: "join", handle: "<script>alert(1)</script>" }),
  ];
  for (const junk of garbage) bo.socket.send(junk);
  await wait(600);

  check("server survived malformed input", bo.socket.readyState === WebSocket.OPEN);
  const afterGarbage = latest(bo, "board") ?? board;
  check(
    "garbage did not corrupt the board",
    Number.isFinite(afterGarbage?.worldTotal),
    JSON.stringify(afterGarbage?.worldTotal)
  );
  const sanitized = latest(bo, "world")?.players?.find((p) => p.id === bo.id)?.handle;
  check("handles are sanitized", sanitized && !sanitized.includes("<"), sanitized);

  // ── disconnect
  alice.socket.close();
  await wait(500);
  check(
    "leaving removes you from the roster",
    !latest(bo, "world")?.players?.some((p) => p.id === alice.id)
  );

  bo.socket.close();
  await wait(100);

  console.log(failures === 0 ? "\nall server checks passed ✅" : `\n${failures} check(s) failed ❌`);
  process.exit(failures === 0 ? 0 : 1);
}

run().catch((error) => {
  console.error("\nsmoke test could not run —", error.message);
  console.error("Is the server running? Try: scripts/dev");
  process.exit(1);
});
