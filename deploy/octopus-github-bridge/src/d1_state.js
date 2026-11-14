/** D1-backed drop-in key/value adapter for CI task metadata only.
 *
 * The canonical application database remains Supabase Postgres. This DB holds
 * only ephemeral Octopus bridge status, never chat, provider credentials or
 * model quota. D1's free tier has a much larger daily write budget than KV.
 */
const MAX_LIMIT = 1000;

export class D1BridgeState {
  constructor(database, { now = () => Date.now() } = {}) {
    if (!database?.prepare) throw new TypeError("D1 database binding required");
    this.database = database;
    this.now = now;
  }

  async get(name) {
    const record = await this.database
      .prepare("SELECT value FROM bridge_state WHERE name = ? AND expires_at > ?")
      .bind(name, Math.floor(this.now() / 1000))
      .first();
    return record?.value ?? null;
  }

  async put(name, value, { expirationTtl = 7 * 86400 } = {}) {
    if (!Number.isSafeInteger(expirationTtl) || expirationTtl < 60) {
      throw new RangeError("invalid bridge TTL");
    }
    const expiresAt = Math.floor(this.now() / 1000) + expirationTtl;
    await this.database.prepare(
      "INSERT INTO bridge_state(name, value, expires_at) VALUES(?, ?, ?) " +
      "ON CONFLICT(name) DO UPDATE SET value=excluded.value, expires_at=excluded.expires_at"
    ).bind(name, String(value), expiresAt).run();
  }

  async delete(name) {
    await this.database.prepare("DELETE FROM bridge_state WHERE name = ?")
      .bind(name).run();
  }

  async list({ prefix = "", limit = 1000, cursor } = {}) {
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > MAX_LIMIT) {
      throw new RangeError("invalid bridge page size");
    }
    if (typeof prefix !== "string" || (cursor && typeof cursor !== "string")) {
      throw new TypeError("invalid bridge list prefix or cursor");
    }
    // Upper bound is lexicographically after all keys beginning with prefix.
    // Named prefixes are internal ASCII keys: task:, result:, desired: etc.
    const query = (
      "SELECT name FROM bridge_state WHERE name >= ? AND name < ? " +
      "AND name > ? AND expires_at > ? ORDER BY name ASC LIMIT ?"
    );
    const response = await this.database.prepare(query).bind(
      prefix, prefix + "\uffff", cursor || "", Math.floor(this.now() / 1000), limit + 1
    ).all();
    if (!response?.success && response?.success !== undefined) {
      throw new Error("D1 bridge list failed");
    }
    const results = response?.results ?? [];
    const visible = results.slice(0, limit).map((row) => ({ name: row.name }));
    const done = results.length <= limit;
    return {
      keys: visible,
      list_complete: done,
      cursor: done ? undefined : visible.at(-1).name,
    };
  }

  async pruneExpired(limit = 250) {
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > MAX_LIMIT) {
      throw new RangeError("invalid bridge prune limit");
    }
    return this.database.prepare(
      "DELETE FROM bridge_state WHERE name IN (" +
      "SELECT name FROM bridge_state WHERE expires_at <= ? LIMIT ?)"
    ).bind(Math.floor(this.now() / 1000), limit).run();
  }
}

export function stateStoreEnv(env) {
  // Explicitly opt in after migrating pending task/result keys to D1.
  // A binding alone cannot cut over; this preserves KV while backfilling.
  if (env.STATE_BACKEND !== "d1") return env;
  if (!env.STATE_DB) return { ...env, TASKS: undefined };
  return { ...env, TASKS: new D1BridgeState(env.STATE_DB) };
}
