---
name: audit-plugin-compliance
description: Audit a plugin directory against Agent Plugins Specification v1.0.0 using the specialized compliance-auditor agent and return the full compliance report plus an ordered list of suggested changes.
---

# Audit Plugin Compliance (Agent Plugins v1.0.0)

Use this skill whenever the user (or another skill such as `remediate-plugin-compliance`) needs a thorough, normative **Agent Plugins Specification v1.0.0** compliance audit of a plugin directory, including concrete suggested changes for every finding.

## Specialized Agent

This skill delegates read-only analysis to the **`compliance-auditor`** agent template (`io.github.monolith-inc.agents/templates/compliance-auditor.template.md`):
- **Model tier:** `balanced`
- **Reasoning effort:** `medium`
- **Access:** `read-only` (never modifies files)

If the host has hydrated `compliance-auditor` (e.g., via `io.github.monolith-inc.agents` install-time hydration or `bin/hydrate_agents.py`), invoke that hydrated agent. Otherwise, load `io.github.monolith-inc.agents/templates/compliance-auditor.template.md` and run a read-only subagent (or follow its instructions directly if subagents are unavailable).

## Execution Steps

1. **Identify the target plugin directory** from the user's request (or current working directory if omitted).
2. **Run the deterministic v1.0.0 audit engine** using whichever interface is available on the host:
   - **MCP tool (preferred when MCP is active):** Call `audit_plugin` with `{ "target": "<plugin-dir>", "format": "json" }`.
   - **Bundled script (works on all clients):** Run `bash scripts/run-audit.sh "<plugin-dir>" --format json` (or `python3 ../../bin/audit_plugin.py "<plugin-dir>" --format json`).
3. **Review context** against `references/compliance-rules-v1.0.0.md`:
   - Confirm whether any bundled executables referenced via `./` in `mcp.json` have executable permissions.
   - Check whether non-v1 client features (hooks, custom agents, rules, commands) are properly isolated under reverse-domain extension directories (`<reverse-domain>/`).
4. **Return the complete structured report** containing:
   - **Status:** `PASS`, `PASS_WITH_WARNINGS`, or `FAIL` with exact fatal/error/warning counts.
   - **Discovered Package Summary:** manifest identity, skills, MCP servers, and extensions.
   - **Findings Table:** severity, failure boundary, spec section, file path, code, and message.
   - **Ordered Suggested Changes (`CHG-01`, `CHG-02`, ...):** priority, exact file path, spec section, issue, concrete remediation action, and patch hint.
