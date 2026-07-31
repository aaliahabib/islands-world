# Islands World — Build Plan (handoff spec)

> This is a self-contained spec for a coding agent to build "Islands World." It was
> produced from a long design conversation; **the decisions below are settled — do not
> re-litigate them.** Where a decision has a rationale, it's given so you don't "improve"
> it into something that breaks a constraint. Sensible defaults are marked for anything
> left open.

---

## 0. What this is / who it's for

A browser-based multiplayer **"world of islands"** to teach **10 high-schoolers** (varied
technical experience) to **vibe-code with Claude**, across **two 1-hour sessions**.

- Each student owns **one island** = a **single-player pygame game** they customize.
- Players walk a shared **overworld** avatar and step into each other's islands to play them.
- A deliberately-**unfair global score total** tracks everyone (honor system, part of the fun).
- The **teacher is the maintainer** (low-resource laptop, not a web/devops expert). Kids edit
  **only their own island**, mostly by **talking to Claude**.

---

## 1. Hard constraints & non-goals (do not drift)

**Constraints**
- Kids write **Python/pygame only** (they know Python + HTML) and mostly **vibe-code via Claude**.
- Teacher's laptop is **low-resource** → the laptop must **only ever do git**; **all building
  happens in the cloud** (GitHub Actions). Never require the teacher to run heavy builds locally.
- **2 hours total** of class → optimize for **"everyone ships a live change fast."** The template
  must be **fully working** out of the box; keep art minimal.

**Non-goals (these were considered and explicitly rejected — do not add them)**
- ❌ **No shared-arena multiplayer inside islands.** Islands are strictly **single-player**, one
  **fresh instance per visitor**. (Rejected: kids can't test multiplayer locally; server
  maintenance; untrusted-code isolation on the server.)
- ❌ **No score clamping / anti-cheat.** Scores are honor-system ("unfair is fun"). *But* the
  server **must still parse messages defensively** so malformed input can't crash it.
- ❌ **No netcode inside islands** — no in-island real-time sync, no client prediction.
- ❌ **No elaborate overworld art.** Placeholder simple shapes or a free CC0 asset pack.
- ❌ **No accounts / auth / class-code gate.** Honor system; kids pick a handle.
- ❌ **No chat.** Emotes only.
- ❌ Kids must **not** be able to run the full app locally or edit outside their island.

---

## 2. Architecture (settled)

- **Islands:** single-player **pygame → WASM via [pygbag]**, run **client-side** in a **sandboxed
  iframe**. *Why:* kids know Python; the same code runs **natively in PyCharm** for instant local
  dev; the iframe gives **security** (one kid's code runs in another kid's browser) **and clean
  teardown** between islands. (The iframe is NOT about multiplayer.)
- **Overworld = a JS "shell":** the **one networked, trusted client**. Holds the WebSocket,
  renders the walkable map + avatars, mounts island iframes, shows the scoreboard. Islands are
  **sandboxed and network-less** — they `postMessage` their score to the shell, which submits it.
- **Server = a small always-on service** (Node pairs naturally with the JS shell; Python is fine):
  presence/roster, relays avatar positions, stores + broadcasts scores. **No game logic, no
  untrusted code.** Tiny.
- **Static assets** (shell + island WASM bundles) → **GitHub Pages/CDN**, built by **GitHub
  Actions**. **Server** → small **PaaS** (Render/Railway) with a tiny DB for score persistence.
- **Everything deploys from git.** Teacher merges to `main` → Actions builds changed islands →
  Pages. Server redeploys only on server-code changes.

```
GitHub repo (source of truth)
   │  push to main
   ├──► GitHub Actions ──► build changed island WASM ──► GitHub Pages / CDN   (free, static)
   └──► Render/Railway  ──► redeploy server (only if server code changed) ──► + tiny DB  (~$5–7/mo)

Player's browser  ──►  loads shell + island bundles from Pages/CDN
                  ──►  opens a WebSocket to the server (presence + scores)
                  ──►  islands run in a sandboxed iframe; score escapes via postMessage → shell → server
```

---

## 3. Repo layout

```
islands-world/
  core/
    shell/              # JS overworld shell: map, avatars, iframe host, scoreboard, emotes, WS client
    server/             # presence + scores WS server (+ tiny DB)
  islands/
    _template/          # fully-working template pygame game (copied for each kid)
      main.py
      island.json       # manifest: display name, author, thumbnail
    <kid>/              # created by scripts/add-island
  islands_sdk/          # kid-facing helper (NOT named "platform" — that shadows a Python stdlib module)
    __init__.py         # exposes submit_score(n), game_over(final)
  scripts/
    add-island          # TEACHER: scaffold + deploy a new island  (see §6 — explicitly requested)
    share               # KID (run by Claude): commit island folder + push their branch
    update              # KID (run by Claude): reset branch to latest main
    setup               # STUDENT (run by Claude): clone/checkout branch + venv + deps + git auth (see §13)
    build-islands       # CI: pygbag-build changed islands + assemble the site
  .github/workflows/
    deploy.yml          # build changed islands → publish to Pages (server deploy scoped separately)
  registry.json         # GENERATED at build time from islands/*/island.json
  CLAUDE.md             # per-kid guardrails (see §7)
  README.md             # teacher setup + run + workflow
```

---

## 4. The island contract ("Option A" — deliberately minimal)

A kid's island is a **normal pygame program** at `islands/<kid>/main.py`. The only platform
requirements:

```python
from islands_sdk import submit_score, game_over

# ... normal pygame ...
submit_score(n)        # call whenever the score changes
game_over(final_score) # call when a run ends → shell shows a consistent overlay + "return to world"
```

- `islands_sdk` is a **no-op stub when run natively** (so the game runs unchanged in PyCharm) and
  does the iframe `postMessage` when running in the browser.
- **Metadata** (display name, author, thumbnail) lives in `islands/<kid>/island.json`, **not in
  code**, so the map can render it without executing the game.
- **pygbag requirement:** the main loop must be **async-friendly** (an `async def main()` with
  `await asyncio.sleep(0)` each frame). The template already does this — kids shouldn't have to
  think about it.

---

## 5. Components to build

**5a. Template island (`islands/_template`) — the single most important artifact.**
A complete, **recolorable asteroids** (thrust / rotate / screen-wrap / shoot; rocks split; score
on destroy). Already calls `submit_score`/`game_over`; already async for pygbag; runs **both**
natively in PyCharm and via pygbag in the browser. Put color/speed **constants at the top** so the
easiest customization (recolor, change speed) is a 30-second win. Clean and readable — every kid
starts here.

**5b. `islands_sdk/__init__.py`.** Detect environment (browser via pygbag/Pyodide vs native).
Native → no-op (optionally print). Browser → `postMessage` to the parent shell:
`{type:'score', value:n}` / `{type:'game_over', value:n}`. Must be included in each island's build.

**5c. The shell (`core/shell`, JS).**
- Renders the overworld: top-down **fixed-slot map** from `registry.json`, avatars, labels
  (name / author / live player count), **scoreboard HUD**, **emote** buttons.
- **WS client:** send my position ~10–20 Hz + emotes; receive others' positions/emotes + score
  updates; **interpolate** others between updates. **Client-authoritative** movement.
  **Pass-through avatars** (no solid bodies — prevents entrance-blocking griefing).
- **Enter island:** on proximity + keypress, mount a **fresh sandboxed iframe** (`sandbox`
  attribute; ideally a separate origin) loading that island's bundle (URL + **cache-busted
  version** from the registry). Listen for `score`/`game_over` postMessages → forward to server.
  On exit / game-over overlay → **destroy the iframe**, return to the map at the prior position.
  Show a "🚧 this island looks broken — return to world" guard if it fails to load.

**5d. The server (`core/server`).**
WS handlers: `join(handle)`, position updates, emotes, score submit. In-memory **roster**;
**persist scores to a DB** (survives restarts/deploys — never in-memory only). Broadcast presence
+ score changes. **Parse every message defensively — ignore malformed; NO clamping.** Tiny load
(10 concurrent).

**5e. Registry (`registry.json`).** Generated by scanning `islands/*/island.json` at build time →
`[{ id, name, author, bundleUrl, version, slot }]`. The shell reads it to render the map and locate
each bundle.

**5f. GitHub Actions (`.github/workflows/deploy.yml`).** On push to `main`: detect **changed island
folders**, **pygbag-build only those**, assemble the site (shell + all island bundles + registry
with cache-busted versions), publish to Pages. **Fail the build (no deploy) if a changed island
fails to build** — this is the quality gate. Server deploy is **separate** (PaaS watches
`core/server` path or is its own service) so island pushes don't bounce the server.

---

## 6. `scripts/add-island` — detailed (explicitly requested)

**Purpose:** the teacher pre-provisions a kid's island and deploys it.

**Usage:** `scripts/add-island <kid-id> ["Display Name"]`
e.g. `scripts/add-island alice "Alice's Asteroids"`

**Steps:**
1. **Validate:** `<kid-id>` is a safe slug (lowercase, no spaces); `islands/<kid-id>` doesn't
   already exist (unless `--force`); git working tree is clean; on `main` and up to date
   (`git pull`).
2. **Scaffold:** copy `islands/_template/` → `islands/<kid-id>/`.
3. **Manifest:** write `islands/<kid-id>/island.json` with display name (arg or a default),
   `author = <kid-id>`, the **next free map slot**, and a placeholder thumbnail.
4. **Deploy:** `git add islands/<kid-id>` → commit `"add island: <kid-id>"` → `git push origin
   main`. This triggers Actions to build + publish → the island goes **live in the world** (as the
   template until the kid customizes it).
5. **Kid's branch:** `git branch <kid-id> main` and `git push -u origin <kid-id>`, so the kid's
   pre-provisioned workspace can check it out.
6. **Report:** print confirmation, the kid's branch name, the local island path, and (optionally)
   the URL where the island will appear.

**Behavior notes:**
- **Safety:** refuse if the island already exists (support `--force` to re-scaffold). Never touch
  other islands or `core/`.
- **Deployment gating (environmental):** steps 4–5 need the git **remote + Actions/host wired**
  (see §9). If no remote is configured yet, do the **local** scaffold + branch and print a clear
  *"remote not configured — connect it (see README) and re-run to push/deploy"* message — don't
  fail silently.
- Keep it a simple **bash or Python** script run from the repo root.
- **Pre-class use:** the teacher loops it over the 10 kids (a roster file, or a shell loop).

---

## 7. `CLAUDE.md` (per-kid guardrails)

Must encode:
- **Scope:** *"You are helping `<student>` build THEIR island. You may ONLY edit files in
  `islands/<student>/`. Never touch `core/`, other islands, `islands_sdk/`, `scripts/`, or the
  registry."*
- **Contract:** `main.py` must keep an **async pygame loop** and call `submit_score(n)` /
  `game_over(final)`. Metadata goes in `island.json`.
- **Sharing (pin Claude to the exact script — no improvised git):** *"When the student says
  'share' / 'share my island' / 'publish' / 'save my game', run exactly `scripts/share`. When they
  say 'update', run exactly `scripts/update`. Never run any other git commands."*
- **Setup:** *"When the student says 'set me up' / 'get me started', run exactly `scripts/setup`."*
- **Encouragement:** the customization ladder — colors/speed → weapons/how rocks split → new
  mechanics; keep it runnable; small steps.

---

## 8. `scripts/share` and `scripts/update` (kid-facing, run by Claude)

- **share:** verify only `islands/<kid>/` changed; `git add islands/<kid>`; commit; `git push
  origin HEAD:<their-branch>`. **Always succeeds** (own branch). Friendly output ("Shared! ✅"),
  "try again in a sec" on error.
- **update:** `git fetch`; reset their branch to `origin/main` (pulls template fixes + others'
  merged islands). Rarely needed in a 2-hour class — **Share is the main loop.**
- Both dead-simple, **scoped to the kid's folder/branch**.

---

## 9. External one-time setup (teacher — environmental prereqs a script can't create)

1. Create the **GitHub repo**; push the scaffold. Enable **GitHub Pages** (or chosen static host).
2. Configure Actions permissions/secrets for the Pages deploy.
3. Create the **server on Render/Railway**; connect the repo (deploy-on-push, **scoped to
   `core/server`**); add a small **DB** (managed Postgres, or SQLite on a persistent volume); note
   the server URL.
4. Point the shell at the server URL (env/config).
5. *(Optional, stronger sandbox)* serve island iframes from a **separate origin/subdomain**.
6. **Pre-provision the 10 islands** (`add-island` per kid) and set up each kid's **PyCharm
   workspace** checked out on their branch with `CLAUDE.md` present.

**Cost:** Pages free; always-on server ~**$5–7/mo**; DB free tier. Tear it all down after the course.

---

## 10. Teacher workflow during class

- **Rolling integration (NOT formal rounds):** when a kid Shares (pushes their branch), the teacher
  merges their branch → `main` (trivial + conflict-free, since it's folder-per-kid) → Actions
  deploys. **Batch merges every ~10 min** to avoid constant context-switching while teaching.
- **Gate:** the merge check = the diff touches **only** `islands/<kid>/` (flag anything outside);
  the **CI build is the smoke test** (a broken island won't deploy).
- **Undo:** `git revert` / re-merge; history is the safety net. (Optional: auto-snapshot on the
  server, invisible to kids.)
- **Two-session shape:** *Session 1* — 5-min world demo, everyone gets the template running in
  PyCharm, makes one small change, Shares, sees it live (goal: everyone ships once). *Session 2* —
  deeper changes with Claude + a **play jam** roaming each other's islands, chasing the leaderboard.

---

## 11. Suggested build order (walking skeleton first — get a demo early)

1. Repo + **template island that runs natively in PyCharm** (no web yet). ← immediate visible value.
2. `islands_sdk` stub + **pygbag build** of the template → runs in a browser standalone.
3. Minimal shell: load **one** island in an iframe + the **score bridge** (no map/multiplayer yet).
4. Server: presence + scores; shell shows the **scoreboard + other avatars** (the multiplayer overworld).
5. Registry + **fixed-slot map** + enter/leave transitions.
6. **GitHub Actions** build/deploy + Pages; **server on PaaS**.
7. `add-island` + `share` + `update` + `setup` scripts + `CLAUDE.md`.
8. Emotes, polish, pre-provision the class.

**Before class: verify the full student onboarding on one real student laptop end-to-end** (install
prereqs → "Claude, set me up" → run the template natively → Share). Machine setup is the
**highest-risk part** of a fixed 2-hour window — see §13.

Build the **vertical slice** (template → iframe → score on the board) first so there's a working
demo before the full breadth exists.

---

## 12. Open decisions (defaults chosen; builder may swap)

| Decision | Default | Alt |
|---|---|---|
| Server language | **Node** (pairs with JS shell) | Python |
| Static host | **GitHub Pages** | Netlify / Cloudflare Pages |
| PaaS | **Render** | Railway |
| DB | **Managed Postgres** | SQLite on a volume |
| Overworld art | **Simple shapes / free CC0 top-down pack** — don't invest | — |
| Iframe origin | **Same-origin sandboxed** (simplest) | Separate subdomain (stronger) |

---

## 13. Student environment setup (`scripts/setup` + machine prereqs)

**Assumption:** students are on **their own laptops** (Mac *or* Windows, varied experience), so each
machine needs setup. *(If they're actually shared/lab machines the teacher controls, pre-image them
instead and this becomes much easier.)* Split the work into what a script can automate vs. what is
an unavoidable manual per-machine prerequisite.

### 13a. Minimum to RUN an island (local dev)
Running the template natively in PyCharm needs only **Python** + **pygame-ce** + the repo. **No
pygbag locally** — the WASM build happens in CI, so student machines stay light.

### 13b. Additional to SHARE
Sharing also needs **git** installed and a **push credential** for the repo (see 13d).

### 13c. `scripts/setup` — the scriptable part (write it in **Python**, for cross-platform)
Python is a prerequisite anyway and must run on Mac + Windows, so write setup as a **Python script**
(not bash). Given a student id + a teacher-provided config (13d), it:
1. Clones the repo (no-op if already inside it) and **checks out the student's branch**.
2. Configures **git identity** and the **pre-baked push remote** (13d).
3. Creates a **virtualenv** and `pip install pygame-ce`.
4. Ensures `from islands_sdk import ...` resolves (repo root on the venv path / editable install).
5. **Smoke check** (headless-safe): `import pygame`, `import islands_sdk`, confirm
   `islands/<id>/main.py` exists → print `✅ ready — open islands/<id>/main.py and Run it`.
   *(Don't launch a window in setup — an import check avoids display/headless issues.)*
Idempotent; safe to re-run.

**Claude integration (matches share/update):** in `CLAUDE.md` — *"When the student says 'set me up'
/ 'get me started', run exactly `scripts/setup`."* Onboarding becomes one sentence to Claude.

### 13d. Git push auth — the one real decision here
Students should **not** manage GitHub accounts in a 2-hour class. Bake a **fine-grained,
repo-scoped Personal Access Token** (contents: read/write on *this one repo only*) into the push
remote, handed out via the setup config:
`https://x-access-token:<TOKEN>@github.com/<org>/<repo>.git`
- ✅ Students never authenticate; `share` just works.
- ⚠️ It's a shared-ish secret, but scoped to push to a single repo. Fine for a trusted class —
  **revoke it after the course.** Never use a broad/personal token.

### 13e. Manual per-machine prerequisites (NOT scriptable — instructions, possibly IT)
A script can't install system tools or authenticate accounts. Provide a short checklist:
1. Install **Python (3.11+)**, **Git**, **PyCharm**, and **Claude Code**.
2. **Authenticate Claude Code** (so "set me up" / "share" work at all).
3. Run **"Claude, set me up"** (or `scripts/setup`) — the script does the rest.

⚠️ **School-managed laptops often block installs.** Sort out permissions / IT **before** the
sessions, or use machines with the four tools pre-installed. **Verify one real student machine
end-to-end before class** — this is the likeliest thing to eat your 2 hours.

### 13f. Chicken-and-egg ordering
"Claude, set me up" presupposes Claude Code is already installed + authenticated and the repo is
present. So the true first steps are manual (13e §1–2 + getting the repo onto the machine); the
script takes over from there. For **zero terminal**, the teacher can hand each student a
**pre-cloned repo folder** so step one is just "open it in PyCharm, then tell Claude 'set me up'."

[pygbag]: https://github.com/pygame-web/pygbag
