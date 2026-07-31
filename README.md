# Islands World

A browser world made of islands. Each island is one student's pygame game.
Everyone walks a shared overworld and steps into each other's islands to play
them. One gloriously unfair scoreboard tracks the lot.

Built to teach ten high-schoolers to vibe-code with Claude across two one-hour
sessions.

```
overworld (white paper, black ink)          islands (black screen, white vectors)
┌──────────────────────────────┐            ┌──────────────────────────────┐
│  ╱‾‾‾‾╲          ╱‾‾╲        │            │ 20                           │
│ ╱ ROCK  ╲       ╱ BEN ╲      │   press E  │ ▲▲▲              WAVE 1      │
│ ╲HARBOR ╱       ╲____╱       │  ────────► │        ╱‾╲                   │
│  ╲____╱                      │            │       ╱   ╲      ◄▲          │
│      ▲ you                   │            │       ╲___╱                  │
└──────────────────────────────┘            └──────────────────────────────┘
```

---

## How it fits together

| Piece | What it is | Where it runs |
|---|---|---|
| `islands/<kid>/` | a student's pygame game | their laptop (PyCharm) **and** the browser as WASM |
| `islands_sdk/` | `submit_score()` / `game_over()` | bundled into every island |
| `core/shell/` | the overworld: map, avatars, iframe host, scoreboard | the browser — the one networked, trusted client |
| `core/server/` | presence + scores | a small always-on service |

Islands are **single-player**, one fresh instance per visitor, sandboxed in an
iframe with no network access. They `postMessage` their score to the shell, and
the shell submits it. That's the whole contract.

Everything deploys from git. Push to `main` → Actions builds changed islands →
GitHub Pages. **Your laptop only ever does git.**

---

## Run it locally

```bash
python3 -m venv .venv
.venv/bin/pip install pygame-ce pygbag
.venv/bin/python scripts/dev
```

Then open **<http://127.0.0.1:8787>**.

> ### ⚠️ Use `127.0.0.1`, not `localhost`
>
> pygbag's runtime special-cases the hostname `localhost`: it assumes it's
> behind pygbag's own dev proxy and rewrites its CDN to a server on port 8000
> that isn't running. Islands then hang on the loading screen forever.
> `127.0.0.1` sidesteps it. Deployed sites have a real hostname, so this only
> ever bites you locally.

`scripts/dev --fast` skips the pygbag builds when you're only touching the
overworld — much quicker, but islands won't be playable.

### Checks

```bash
.venv/bin/python scripts/check-island --all   # do all the games actually run?
node core/server/smoke-test.mjs               # does the protocol work? (needs the server up)
node scripts/check-bridge                     # does a score really get from WASM to the shell?
```

`check-bridge` is the one that matters. It drives a real Chrome, boots an island
to WASM in a sandboxed iframe, and waits for a score to arrive. If it passes,
the class works.

The server smoke test submits real scores, so clear the board before class with
`rm -f core/server/data/scores.json` (or truncate the Postgres tables).

---

## Before class: one-time setup

These are the bits a script can't do for you.

**1. GitHub repo + Pages**

```bash
git remote add origin https://github.com/YOUR-ORG/islands-world.git
git push -u origin main
```

Settings → Pages → Source: **GitHub Actions**.

**2. The server** (Render or Railway)

Point it at this repo with **root directory `core/server`**, build `npm install`,
start `npm start`. Set it to auto-deploy only on changes under `core/server` so
student pushes never bounce it. Add a Postgres instance and it'll pick up
`DATABASE_URL` on its own; without one it falls back to a JSON file on disk
(fine, but it needs a persistent volume to survive restarts).

Then in the repo: Settings → Secrets and variables → Actions → **Variables** →
add `SERVER_URL` = `wss://your-server.onrender.com/ws`. The deploy workflow
bakes it into the shell. Without it the world still renders and islands still
play — you just get no shared scoreboard.

**3. Hosting headers**

Whatever serves the site must send `Cross-Origin-Resource-Policy: cross-origin`
on the island bundles. GitHub Pages does this by default.

Do **not** set `Cross-Origin-Embedder-Policy: require-corp`. pygbag's own dev
server sends it, but islands load their Python runtime from
`pygame-web.github.io`, which sends no CORP header — under `require-corp` the
browser blocks the runtime and every island hangs on "Loading". This one cost an
afternoon; don't rediscover it.

**4. The islands**

```bash
for kid in alice bo cai dee eve finn gus hana ivy jo; do
  scripts/add-island $kid
done
```

Each one scaffolds `islands/<kid>/`, gives it a map slot, pushes to `main`
(which deploys it), and creates the student's branch.

The repo ships with `demo-01`…`demo-03` so the world isn't empty while you're
building. Delete them before class:

```bash
rm -rf islands/demo-0*
```

**5. Student machines**

Copy `setup.local.example.json` → `setup.local.json`, fill in the repo URL and a
**fine-grained PAT scoped to Contents:read+write on this one repo only**. It's
gitignored so it never reaches the repo. Hand it out inside each student's
pre-cloned repo folder.

Per machine, someone has to install by hand: **Python 3.11+, Git, PyCharm,
Claude Code**, and authenticate Claude Code. Then the student says *"set me up"*
and `scripts/setup` does the rest.

> **School laptops block installs.** Sort this out with IT *before* the sessions,
> and **run one real student machine end to end first** — install → "set me up"
> → run the game → share. Machine setup is the likeliest thing to eat your two
> hours.

---

## During class

Students only ever say three things to Claude: **"set me up"**, **"share my
island"**, **"update"**. `CLAUDE.md` pins Claude to those exact scripts and
forbids improvised git.

Your loop, roughly every ten minutes so you're not context-switching constantly:

```bash
git fetch origin
git diff --stat main origin/alice     # should touch ONLY islands/alice/
git merge origin/alice
git push origin main                  # Actions builds and deploys
```

The merge check is: does the diff touch anything outside `islands/<kid>/`? If
yes, look closer. The CI build is your smoke test — a broken island fails the
build and nothing deploys, so the world can't go down because of one student.

Undo is `git revert`. History is the safety net.

**Session 1** — demo the world (5 min), everyone gets the template running in
PyCharm, makes one small change, shares, sees it live. The goal is that every
single student ships once.
**Session 2** — deeper changes with Claude, then a play jam roaming each other's
islands chasing the scoreboard.

---

## Repo layout

```
core/shell/       overworld: map, avatars, iframe host, scoreboard, WS client
core/server/      presence + scores (Node + ws, Postgres or a JSON file)
islands/_template asteroids — the game every student starts from
islands/<kid>/    one student's island
islands_sdk/      submit_score / game_over
scripts/          add-island, setup, share, update, build-islands, dev, check-*
site/             build output (gitignored)
```

## Design decisions worth not re-litigating

- **Islands are single-player.** One fresh instance per visitor. Students can't
  test multiplayer locally, and running ten students' untrusted code on a shared
  server is not a thing you want to maintain during a class.
- **No score clamping, no anti-cheat.** Unfair is the point. The server still
  parses every message defensively — malformed input is dropped, never fatal.
- **The iframe is for isolation and teardown, not multiplayer.** One student's
  code runs in everyone else's browser; removing the iframe destroys the whole
  Python runtime cleanly between islands.
- **No accounts, no chat.** Kids pick a handle. Emotes only.
- **All building happens in CI.** Student machines need Python + pygame and
  nothing else — no pygbag, no Node.

The full design spec is in [`docs/islands-world-build-plan.md`](docs/islands-world-build-plan.md).
