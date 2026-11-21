# Changelog

All notable changes to `agent-plugins-compliance` will be documented in this file.
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2026-11-21

### Fixed
- Wire Google Antigravity workspace skills and hydrated agents into `.agents/skills/` and `.agents/agents/` instead of `.gemini/` so Antigravity discovers them automatically.
- Clean up both `.agents/` and legacy `.gemini/` paths during `--uninstall`.
- Support comma-separated numeric/mixed host selections (e.g. `1,4`) in `scripts/install.sh`.
- Always check for `tar` during installation (including offline `AGENT_PLUGINS_COMPLIANCE_ARCHIVE` installs) and validate required values for `--dest`, `--host`, and `--version`.

## [1.0.0] - 2026-11-20

### Added
- Agent Plugins v1.0.0 compliant manifest (`plugin.json`) and `stdio` MCP server (`mcp.json`).
- `audit-plugin-compliance` skill and `bin/audit_plugin.py` engine with structured suggested-changes output.
- `remediate-plugin-compliance` skill with user confirmation gate and post-fix verification.
- Host-agnostic agent templates (`compliance-auditor`, `compliance-remediator`) under `io.github.monolith-inc.agents/` with `modelTier` / `reasoningEffort` hydration for Claude Code, Codex, Cursor, and Google Antigravity (`bin/hydrate_agents.py`).
