#!/usr/bin/env node
/**
 * Cloudflare agent bootstrap for AyahOS, based on Cloudflare's agent-setup/prompt.md.
 *
 * Project MCP configs are already checked into Git. No credentials are stored.
 * Run from the canonical repo root. Skips the optional beta 'cf' CLI.
 */
import { spawnSync } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
const url = "https://mcp.cloudflare.com/mcp";
const configs = [
  ".codex/config.toml",
  ".mcp.json",
  ".cursor/mcp.json",
  ".vscode/mcp.json",
];
const args = process.argv.slice(2);
if (args.some((arg) => arg !== "--check" && arg !== "--agent=claude")) {
  console.error("Usage: node scripts/setup-cloudflare-agent.mjs [--check] [--agent=claude]");
  process.exit(2);
}
for (const file of configs) {
  const path = resolve(root, file);
  if (!existsSync(path)) {
    console.error(`Missing project MCP configuration: ${file}`);
    process.exit(1);
  }
  const source = readFileSync(path, "utf8");
  if (!source.includes(url)) {
    console.error(`Unexpected Cloudflare MCP endpoint: ${file}`);
    process.exit(1);
  }
  if (file.endsWith(".json")) JSON.parse(source);
}
console.log("Verified repository Cloudflare MCP definitions (Codex, Claude, Cursor, VS Code).");
if (args.includes("--check")) process.exit(0);

const claude = args.includes("--agent=claude");
const program = claude ? "claude" : "npx";
const cmd = process.platform === "win32" ? `${program}.cmd` : program;
const groups = claude
  ? [
      ["plugin", "marketplace", "add", "cloudflare/skills"],
      ["plugin", "install", "cloudflare@cloudflare"],
    ]
  : [["-y", "skills", "add", "cloudflare/skills", "--skill", "*", "--yes", "--global"]];
for (const installArgs of groups) {
  console.log("Installing official Cloudflare agent skills and MCP tooling...");
  const child = spawnSync(cmd, installArgs, {
    cwd: root,
    stdio: "inherit",
    shell: process.platform === "win32",
    env: process.env,
  });
  if (child.error || child.status !== 0) {
    console.error("Cloudflare agent tooling installation failed; check CLI/network access.");
    process.exit(child.status || 1);
  }
}
console.log(
  "Cloudflare agent setup commands succeeded. Restart your agent (Claude: /reload-plugins). " +
  "Authorize the Cloudflare MCP connection in your browser at first use " +
  "(Codex: codex mcp login cloudflare). Never paste credentials into chat.",
);
