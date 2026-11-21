# `io.github.monolith-inc.agents` Extension Specification (v1.0.0)

Agent Plugins Specification v1.0.0 standardizes **Skills** (`skills/`) and **MCP servers** (`mcp.json`), intentionally leaving custom subagents outside the v1.0.0 portable core because agent file formats, model identifiers, and reasoning controls differ across hosts.

This reverse-domain extension (`io.github.monolith-inc.agents`) provides a **host-agnostic agent template contract** that stays 100% compliant with Agent Plugins v1.0.0 (§8):

- Clients that do not implement `io.github.monolith-inc.agents` safely ignore it with zero errors and zero warnings.
- Installers/compilers that implement it (or users running `bin/hydrate_agents.py` / the `hydrate_agents` MCP tool) materialize each template into native host agent definitions at install time.

## Abstract Fields

Each entry in `plugin.json#extensions["io.github.monolith-inc.agents"].agents` declares:

| Field | Values | Meaning |
| --- | --- | --- |
| `id` | lowercase kebab-case | Stable identifier for the agent template. |
| `role` | string | Human-readable role title. |
| `template` | `./...` plugin-relative path | Markdown template with YAML frontmatter and host-agnostic prompt body. |
| `modelTier` | `"fast"` \| `"balanced"` \| `"deep"` | Abstract capability tier mapped to a host-native model by `host-profiles.json`. |
| `reasoningEffort` | `"low"` \| `"medium"` \| `"high"` | Abstract reasoning budget mapped to the host's native reasoning parameter. |
| `access` | `"read-only"` \| `"read-write"` | Tool/sandbox permission intent mapped to each host's native tool/sandbox fields. |

## Supported Hydration Targets

Run:

```bash
python3 bin/hydrate_agents.py --host <claude|codex|cursor|antigravity> --output <target-dir>
```

| Host | Output Path | Format |
| --- | --- | --- |
| `claude` | `<output>/.claude/agents/<id>.md` | Markdown + YAML frontmatter (`model`, `effort`, `tools`) |
| `codex` | `<output>/.codex/agents/<id>.toml` | TOML (`model`, `model_reasoning_effort`, `sandbox_mode`, `developer_instructions`) |
| `cursor` | `<output>/.cursor/agents/<id>.md` | Markdown + YAML frontmatter (`model`, `reasoning_effort`, `readonly`) |
| `antigravity` | `<output>/.gemini/agents/<id>.md` | Markdown + YAML frontmatter (`model`, `reasoning_effort`, `enable_write_tools`) |
