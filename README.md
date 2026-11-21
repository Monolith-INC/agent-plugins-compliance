# Agent Plugins Compliance

[![CI](https://github.com/Monolith-INC/agent-plugins-compliance/actions/workflows/ci.yml/badge.svg)](https://github.com/Monolith-INC/agent-plugins-compliance/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Monolith-INC/agent-plugins-compliance?sort=semver)](https://github.com/Monolith-INC/agent-plugins-compliance/releases)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Agent Plugins](https://img.shields.io/badge/Agent%20Plugins-v1.0.0-8A2BE2)](https://agent-plugins.org/specification)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.10-brightgreen)](https://www.python.org/)
[![Hosts](https://img.shields.io/badge/hosts-claude%20%7C%20codex%20%7C%20cursor%20%7C%20antigravity-informational)](#install)

An **Agent Plugins Specification v1.0.0** compliant plugin that audits any plugin directory against the published v1.0.0 standard, produces an ordered list of concrete suggested changes, and executes user-approved remediations through specialized, host-agnostic agent templates.

---

## Install

**One command.** Run it from a terminal in the project where you want to install the plugin (or pass `--dest` in CI). You do **not** need to clone this repository.

### Interactive (recommended)

```bash
bash <(curl -fsSL https://github.com/Monolith-INC/agent-plugins-compliance/releases/latest/download/install.sh)
```

The interactive installer will:

1. Confirm the target project directory (defaults to your current directory).
2. Ask which host(s) to wire: **Claude Code**, **Codex**, **Cursor**, **Google Antigravity**, or **all**.
3. Download the latest release tarball and verify its `SHA256SUMS` digest.
4. Install the portable plugin under `<project>/.agent-plugins/agent-plugins-compliance/`.
5. Materialize/hydrate the specialized `compliance-auditor` and `compliance-remediator` agent templates into each selected host's native format and copy the skills into the host's skills directory.

### Non-interactive / CI

```bash
curl -fsSL https://github.com/Monolith-INC/agent-plugins-compliance/releases/latest/download/install.sh \
  | bash -s -- --non-interactive --dest /absolute/path/to/your-project --host claude,codex
```

Optional flags: `--host claude|codex|cursor|antigravity|all`, `--version v1.0.0`, `--uninstall`.

Pin a release with `AGENT_PLUGINS_COMPLIANCE_VERSION=v1.0.0`, or install offline from a local tarball with `AGENT_PLUGINS_COMPLIANCE_ARCHIVE=/path/to/agent-plugins-compliance.tar.gz`.

### Requirements

- **Python 3.10+** (zero external dependencies)
- **Bash**, **curl**, and **tar**
- Network access to GitHub Releases (or a local archive via `AGENT_PLUGINS_COMPLIANCE_ARCHIVE`)

After install, **restart your agent session** so the newly installed skills and hydrated agents reload.

---

## Skills & Specialized Agents

| Skill | Specialized Agent | Model Tier / Effort | What it does |
| --- | --- | --- | --- |
| `audit-plugin-compliance` | `compliance-auditor` *(read-only)* | `balanced` / `medium` | Runs the deterministic v1.0.0 audit (`bin/audit_plugin.py` or `audit_plugin` MCP tool) and returns findings grouped by failure boundary plus an ordered list of suggested changes (`CHG-01`, `CHG-02`, ...). |
| `remediate-plugin-compliance` | `compliance-remediator` *(read-write)* | `deep` / `high` | Calls `audit-plugin-compliance`, displays the report and suggested changes, asks for explicit user confirmation, executes approved fixes, and re-audits to verify `PASS`. |

## Components

| Component | Path | Purpose |
| --- | --- | --- |
| **Manifest** | `plugin.json` | Closed v1.0.0 manifest declaring `io.github.monolith-inc.agents` templates. |
| **Skills** | `skills/audit-plugin-compliance/`, `skills/remediate-plugin-compliance/` | Composable audit and guided remediation skills. |
| **MCP Server** | `mcp.json` → `./bin/compliance-mcp-server.py` | Zero-dependency `stdio` MCP server exposing `audit_plugin`, `list_agent_templates`, and `hydrate_agents`. |
| **Agent Templates** | `io.github.monolith-inc.agents/` | Host-agnostic templates and `host-profiles.json` hydrated into native formats for Claude Code (`.claude/agents/*.md`), Codex (`.codex/agents/*.toml`), Cursor (`.cursor/agents/*.md`), and Google Antigravity (`.gemini/agents/*.md`). |

## Direct CLI Usage

```bash
# Audit any plugin directory (Markdown or JSON)
python3 bin/audit_plugin.py /path/to/my-plugin --format markdown
python3 bin/audit_plugin.py /path/to/my-plugin --format json

# Hydrate specialized agent templates for a target host
python3 bin/hydrate_agents.py --host claude --output /path/to/project
python3 bin/hydrate_agents.py --host codex --output /path/to/project
python3 bin/hydrate_agents.py --host cursor --output /path/to/project
python3 bin/hydrate_agents.py --host antigravity --output /path/to/project
```

## License

Licensed under the [Apache License 2.0](LICENSE).
