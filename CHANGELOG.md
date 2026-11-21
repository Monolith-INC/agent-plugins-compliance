# Changelog

All notable changes to `agent-plugins-compliance` will be documented in this file.
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-20

### Added
- Agent Plugins v1.0.0 compliant manifest (`plugin.json`) and `stdio` MCP server (`mcp.json`).
- `audit-plugin-compliance` skill and `bin/audit_plugin.py` engine with structured suggested-changes output.
- `remediate-plugin-compliance` skill with user confirmation gate and post-fix verification.
- Host-agnostic agent templates (`compliance-auditor`, `compliance-remediator`) under `io.github.monolith-inc.agents/` with `modelTier` / `reasoningEffort` hydration for Claude Code, Codex, Cursor, and Google Antigravity (`bin/hydrate_agents.py`).
