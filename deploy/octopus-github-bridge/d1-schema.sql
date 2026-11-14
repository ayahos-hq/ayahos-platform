-- Ephemeral Octopus verification metadata only.
-- Not the application database and not a model usage/quota ledger.
-- Apply to a dedicated Cloudflare D1 bridge database before STATE_BACKEND=d1.
CREATE TABLE IF NOT EXISTS bridge_state (
    name TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL,
    expires_at INTEGER NOT NULL CHECK (expires_at > 0)
);

CREATE INDEX IF NOT EXISTS bridge_state_expiration_idx
    ON bridge_state(expires_at);
