---
name: remediate-plugin-compliance
description: Run audit-plugin-compliance, display the compliance report and suggested changes to the user, ask for explicit confirmation, and execute approved changes using the specialized compliance-remediator agent.
---

# Remediate Plugin Compliance (Agent Plugins v1.0.0)

Use this skill when the user wants to bring a plugin directory into full **Agent Plugins Specification v1.0.0** compliance with a human-in-the-loop approval gate before any files are modified.

## Specialized Agents Used

1. **`compliance-auditor`** (`modelTier: balanced`, `reasoningEffort: medium`, `read-only`) — invoked via the `audit-plugin-compliance` skill.
2. **`compliance-remediator`** (`modelTier: deep`, `reasoningEffort: high`, `read-write`) — defined in `io.github.monolith-inc.agents/templates/compliance-remediator.template.md`.

If the host has not yet hydrated the agent templates at install time and the user wants native host agent files materialized, you may run `bash scripts/hydrate-host-agents.sh --host <claude|codex|cursor|antigravity> --output <workspace>` (or call the `hydrate_agents` MCP tool).

## Required Workflow

### Step 1 — Run the Audit Skill
Invoke **`audit-plugin-compliance`** on the target plugin directory and consume its structured output (`status`, `counts`, `findings`, and `suggested_changes`).

### Step 2 — Present Report & Suggested Changes to the User
Display to the user:
1. The **Compliance Audit Report** (status, discovered components, and findings grouped by failure boundary).
2. The numbered **Suggested Changes** (`CHG-01`, `CHG-02`, ...) with exact file paths, spec sections, and actions.

If `status == "PASS"` and `suggested_changes` is empty, inform the user that the plugin is already 100% compliant and stop.

### Step 3 — Mandatory User Confirmation Gate
**NEVER modify files before the user confirms.** Explicitly ask the user:
- Whether they want to apply **all** suggested changes, a **subset** (by change ID), or **none**.
- If any finding involves a **hardcoded secret/credential** in `mcp.json`, explicitly warn that the secret will be removed and must be rotated / moved to client-managed auth.

### Step 4 — Delegate Execution to `compliance-remediator`
Once the user approves:
1. Invoke the hydrated **`compliance-remediator`** agent (or a write-enabled subagent loaded with `io.github.monolith-inc.agents/templates/compliance-remediator.template.md`), passing:
   - The target plugin directory path.
   - The exact list of user-approved `suggested_changes`.
2. Wait for `compliance-remediator` to apply the minimal targeted edits.

### Step 5 — Post-Remediation Verification
Re-run **`audit-plugin-compliance`** on the target plugin directory and present the final before/after summary to the user, confirming whether `status == "PASS"` with 0 errors and 0 warnings.
