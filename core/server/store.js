// Score persistence.
//
// Scores must survive a restart or a redeploy — never keep them in memory only.
// Two backends:
//
//   DATABASE_URL set  → Postgres (what you get on Render/Railway)
//   otherwise         → a JSON file on disk (what you get locally)
//
// Both expose the same tiny interface: load(), commitRun(), snapshot().

import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

/** Shape shared by both backends. */
function emptyState() {
  return {
    // handle → { total, runs }
    totals: Object.create(null),
    // islandId → { handle → best }
    best: Object.create(null),
  };
}

// ── JSON file backend ──────────────────────────────────────────────────────

class FileStore {
  constructor(path) {
    this.path = path;
    this.state = emptyState();
    this.writeTimer = null;
    this.writing = false;
    this.dirty = false;
  }

  async load() {
    try {
      const text = await readFile(this.path, "utf8");
      const parsed = JSON.parse(text);
      if (parsed && typeof parsed === "object") {
        this.state.totals = Object.assign(Object.create(null), parsed.totals || {});
        this.state.best = Object.assign(Object.create(null), parsed.best || {});
      }
      console.log(`[store] loaded ${Object.keys(this.state.totals).length} player(s) from ${this.path}`);
    } catch (error) {
      if (error.code !== "ENOENT") {
        console.warn("[store] could not read score file, starting fresh —", error.message);
      }
    }
    return this;
  }

  scheduleWrite() {
    this.dirty = true;
    if (this.writeTimer) return;
    this.writeTimer = setTimeout(() => {
      this.writeTimer = null;
      void this.flush();
    }, 800);
  }

  async flush() {
    if (this.writing || !this.dirty) return;
    this.writing = true;
    this.dirty = false;
    try {
      await mkdir(dirname(this.path), { recursive: true });
      const temp = `${this.path}.tmp`;
      await writeFile(temp, JSON.stringify(this.state, null, 2), "utf8");
      await rename(temp, this.path); // atomic-ish: never leave a half-written file
    } catch (error) {
      console.error("[store] write failed —", error.message);
      this.dirty = true;
    } finally {
      this.writing = false;
    }
  }

  commitRun(handle, islandId, score) {
    const entry = (this.state.totals[handle] ??= { total: 0, runs: 0 });
    entry.total += score;
    entry.runs += 1;

    if (islandId) {
      const island = (this.state.best[islandId] ??= Object.create(null));
      if (!(handle in island) || score > island[handle]) island[handle] = score;
    }
    this.scheduleWrite();
  }

  snapshot() {
    return this.state;
  }

  async close() {
    clearTimeout(this.writeTimer);
    this.writeTimer = null;
    await this.flush();
  }
}

// ── Postgres backend ───────────────────────────────────────────────────────

class PostgresStore {
  constructor(pool) {
    this.pool = pool;
    this.state = emptyState();
    this.queue = Promise.resolve();
  }

  async load() {
    await this.pool.query(`
      CREATE TABLE IF NOT EXISTS scores (
        handle      TEXT PRIMARY KEY,
        total       BIGINT NOT NULL DEFAULT 0,
        runs        INTEGER NOT NULL DEFAULT 0,
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
      );
    `);
    await this.pool.query(`
      CREATE TABLE IF NOT EXISTS island_best (
        island  TEXT NOT NULL,
        handle  TEXT NOT NULL,
        best    BIGINT NOT NULL DEFAULT 0,
        PRIMARY KEY (island, handle)
      );
    `);

    const totals = await this.pool.query("SELECT handle, total, runs FROM scores");
    for (const row of totals.rows) {
      this.state.totals[row.handle] = { total: Number(row.total), runs: Number(row.runs) };
    }
    const best = await this.pool.query("SELECT island, handle, best FROM island_best");
    for (const row of best.rows) {
      const island = (this.state.best[row.island] ??= Object.create(null));
      island[row.handle] = Number(row.best);
    }
    console.log(`[store] loaded ${totals.rowCount} player(s) from Postgres`);
    return this;
  }

  commitRun(handle, islandId, score) {
    // Update the in-memory view immediately so broadcasts are instant, then
    // persist in the background. Writes are serialised through `queue` so two
    // fast runs can't race.
    const entry = (this.state.totals[handle] ??= { total: 0, runs: 0 });
    entry.total += score;
    entry.runs += 1;
    if (islandId) {
      const island = (this.state.best[islandId] ??= Object.create(null));
      if (!(handle in island) || score > island[handle]) island[handle] = score;
    }

    this.queue = this.queue
      .then(async () => {
        await this.pool.query(
          `INSERT INTO scores (handle, total, runs, updated_at)
           VALUES ($1, $2, 1, NOW())
           ON CONFLICT (handle) DO UPDATE
             SET total = scores.total + $2,
                 runs = scores.runs + 1,
                 updated_at = NOW()`,
          [handle, score]
        );
        if (islandId) {
          await this.pool.query(
            `INSERT INTO island_best (island, handle, best)
             VALUES ($1, $2, $3)
             ON CONFLICT (island, handle) DO UPDATE
               SET best = GREATEST(island_best.best, EXCLUDED.best)`,
            [islandId, handle, score]
          );
        }
      })
      .catch((error) => {
        console.error("[store] postgres write failed —", error.message);
      });
  }

  snapshot() {
    return this.state;
  }

  async close() {
    await this.queue;
    await this.pool.end();
  }
}

// ── Factory ────────────────────────────────────────────────────────────────

export async function createStore() {
  const url = process.env.DATABASE_URL;
  if (!url) {
    const path = process.env.SCORE_FILE || join(HERE, "data", "scores.json");
    console.log("[store] no DATABASE_URL — persisting scores to", path);
    return new FileStore(path).load();
  }

  let pg;
  try {
    ({ default: pg } = await import("pg"));
  } catch {
    throw new Error(
      "DATABASE_URL is set but the 'pg' package is not installed. Run `npm install` in core/server."
    );
  }

  const pool = new pg.Pool({
    connectionString: url,
    // Managed Postgres on Render/Railway terminates TLS with its own cert.
    ssl: process.env.PGSSL === "off" ? false : { rejectUnauthorized: false },
    max: 4,
  });
  return new PostgresStore(pool).load();
}
