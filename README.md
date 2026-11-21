# agent-plugins-compliance

An **Agent Plugins Specification v1.0.0** compliant plugin that audits any plugin directory for v1.0.0 conformance, generates an ordered list of concrete remediation changes, and executes user-approved fixes via specialized, host-agnostic agent templates.

## Components

| Component | Path | Purpose |
| --- | --- | --- |
| **Manifest** | `plugin.json` | Closed v1.0.0 manifest declaring `io.github.monolith-inc.agents` templates. |
| **Skill 1 (Audit)** | `skills/audit-plugin-compliance/SKILL.md` | Runs the deterministic v1.0.0 audit via `compliance-auditor` and produces the compliance report + suggested changes list. |
| **Skill 2 (Remediate)** | `skills/remediate-plugin-compliance/SKILL.md` | Calls `audit-plugin-compliance`, displays the report and remediation steps, asks for explicit user approval, and executes approved changes via `compliance-remediator`. |
| **MCP Server** | `mcp.json` → `./bin/compliance-mcp-server.py` | Zero-dependency `stdio` MCP server exposing `audit_plugin`, `list_agent_templates`, and `hydrate_agents`. |
| **Agent Templates** | `io.github.monolith-inc.agents/` | Host-agnostic templates (`compliance-auditor`, `compliance-remediator`) with abstract `modelTier` and `reasoningEffort`, plus `host-profiles.json` for `claude`, `codex`, `cursor`, and `antigravity`. |

## Quick CLI Usage

```bash
# 1. Audit any plugin directory (Markdown or JSON)
python3 bin/audit_plugin.py /path/to/my-plugin --format markdown
python3 bin/audit_plugin.py /path/to/my-plugin --format json

# 2. Hydrate specialized agent templates for a target host
python3 bin/hydrate_agents.py --host claude --output /path/to/project
python3 bin/hydrate_agents.py --host codex --output /path/to/project
python3 bin/hydrate_agents.py --host cursor --output /path/to/project
python3 bin/hydrate_agents.py --host antigravity --output /path/to/project
```
