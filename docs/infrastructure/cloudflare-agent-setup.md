# Cloudflare AI agent setup (project-scoped)

Source: https://developers.cloudflare.com/agent-setup/prompt.md (fetched 2026-10-21). The Cloudflare CLI `cf` is optional and **not** installed here. This setup does not require a paid Cloudflare plan.

## Applied to this repository

The following Cloudflare remote MCP registrations are project-local, checked into this repository, and contain no credentials:

| Agent | Configuration |
| --- | --- |
| Codex CLI/IDE | `.codex/config.toml` |
| Claude Code | `.mcp.json` |
| Cursor | `.cursor/mcp.json` |
| VS Code Copilot agent | `.vscode/mcp.json` |

All use the official **Code Mode MCP server** at `https://mcp.cloudflare.com/mcp`. For VS Code the root property is `servers` (not `mcpServers`); this follows its current configuration format. Codex must trust the cloned project before project config can load.

The remote server prompts for interactive Cloudflare OAuth on first use. Configuration **does not authenticate the user or create an AI Gateway by itself**.

## Finish installing Cloudflare Skills on your own development computer

From this repository's root, with Node.js and internet access:

```bash
# Installs Cloudflare's official skills globally for Codex/other compatible agents
node scripts/setup-cloudflare-agent.mjs

# If the target agent is Claude Code, use Cloudflare's official plugin commands
node scripts/setup-cloudflare-agent.mjs --agent=claude

# Offline / CI-safe syntax/config check, no installations or network calls
node scripts/setup-cloudflare-agent.mjs --check
```

The script uses the exact Cloudflare-recommended commands, `npx -y skills add cloudflare/skills --skill '*' --yes --global`, or the two `claude plugin` commands. The **current ChatGPT execution container is not your connected development computer**, so executing an installer here would not install into your Codex or Claude installation. The repo-level MCP configs *are* committed on the feature branch.

After successful installation, restart the target agent. For Codex, run `codex mcp login cloudflare` locally and finish browser OAuth. For Claude Code, `/reload-plugins`, then authorize when prompted. In VS Code/Cursor, enable the MCP server and authorize its login prompt.

## Verification

Codex:
```bash
codex mcp list
# cloudflare server should point to https://mcp.cloudflare.com/mcp
```

Once authenticated, use the agent to inspect the Cloudflare account and confirm the AI Gateway plan and settings. Do not share OAuth tokens, API keys, or saved cookies in Git or chat.

This config/setup is **distinct from enabling paid TypeSafe Jev model inference**. Cloudflare AI Gateway's basic gateway is free but TypeSafe inference is not made free by transport routing. Keep Jev's paid-request flag disabled under the owner's $0 spending rule.

## Not completed by repository configuration alone

Cloudflare OAuth, installing global Skills on the owner's machine, provisioning `ayahos-undermind` in the live Cloudflare account, connecting encrypted secrets, executing an inference request, and Octopus CI acceptance require separate verified actions. Do not claim those steps passed based on checked-in files.
