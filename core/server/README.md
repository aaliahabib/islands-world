# Islands World server

Presence and scores. Nothing else — no game logic, and it never executes student
code.

```bash
npm install
npm start          # http://localhost:8787, ws://localhost:8787/ws
```

## Environment

| Variable | Default | What it does |
|---|---|---|
| `PORT` | `8787` | HTTP + WebSocket port |
| `SITE_DIR` | unset | serve a built site from this directory (local dev, or a single-service deploy) |
| `DATABASE_URL` | unset | use Postgres; otherwise scores go to a JSON file |
| `SCORE_FILE` | `./data/scores.json` | where the JSON fallback writes |
| `PGSSL` | on | set to `off` for a local Postgres without TLS |

Scores are **persisted** either way — never in memory only, so a restart or a
redeploy mid-class doesn't wipe the scoreboard.

## Deploying on Render

- Root directory: `core/server`
- Build: `npm install`
- Start: `npm start`
- Add a Postgres instance; `DATABASE_URL` gets injected and the tables are
  created on boot.
- Scope auto-deploy to `core/server` so student pushes don't bounce the server.

Then set the `SERVER_URL` repository variable in GitHub to
`wss://<your-service>.onrender.com/ws`.

## Protocol

Client → server:

| Message | Meaning |
|---|---|
| `{t:"join", handle, avatar}` | announce yourself; replies with `welcome`. `avatar` is three small indices (colour, head, hat) for your stick figure — the server validates and relays them, and has no idea what they mean |
| `{t:"pos", x, y, a}` | where your avatar is (~15/s) |
| `{t:"emote", e}` | broadcast a short emote |
| `{t:"enter", island}` / `{t:"leave"}` | island occupancy counts |
| `{t:"score", island, value, final}` | a score; `final:true` commits it to the board |

Server → client:

| Message | Meaning |
|---|---|
| `{t:"welcome", id, handle, board, worldTotal}` | your id and the current board |
| `{t:"world", players, islands}` | roster (with each player's avatar) + island occupancy (~15/s) |
| `{t:"board", entries, worldTotal}` | scoreboard changed |
| `{t:"emote", id, e}` | someone emoted |

Only `final:true` scores land on the board — in-progress scores would just be
noise. There is **no clamping**: a score only has to be a finite safe integer.
Unfair is the point.

## Testing

```bash
node smoke-test.mjs            # needs the server running
```

Checks presence, occupancy, emotes, scoring, and that a stream of malformed
garbage is ignored rather than fatal.

⚠️ The smoke test submits **real** scores (ALICE and a deliberately absurd BO),
because that's the only honest way to test that scores persist. Wipe the board
before class:

```bash
rm -f core/server/data/scores.json     # JSON backend
# or, on Postgres:
psql "$DATABASE_URL" -c 'TRUNCATE scores, island_best;'
```
