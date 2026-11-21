# Agent Plugins v1.0.0 Normative Audit Reference

Quick reference for the `compliance-auditor` and `compliance-remediator` agents:

1. **Package Boundary (§4.1):** Single filesystem directory; all package files and symlinks MUST resolve within the plugin root. Plugin-relative paths begin with `./`.
2. **Root Manifest `plugin.json` (§5):**
   - Required closed top-level object with `$schema: "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"` and `name` (`1–64` chars, `^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$`).
   - Permitted optional fields: `version`, `description`, `author` (closed object: `name`, `email`, `url` strings), `homepage`, `repository`, `license`, `keywords` (`string[]`), `extensions` (reverse-domain object map).
   - Unknown top-level fields and non-object `extensions` are **non-fatal warnings** (report and ignore). All other manifest violations are **fatal**.
3. **Skills `skills/` (§6, §7.1):**
   - Immediate child directories containing a regular file named `SKILL.md` with valid Agent Skills YAML frontmatter (`name`, `description`). No recursive discovery.
4. **MCP Servers `mcp.json` (§7.2, §9, §10.1):**
   - Closed top-level object: `$schema: "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"` (matching `plugin.json` version) and `mcpServers`.
   - Closed server variants with explicit `type`: `stdio` (`command`, `args`, `env`, `cwd`), `streamable-http` (`url`, `headers`), `sse` (`url`, `headers`, deprecated/optional).
   - `stdio`: single-token `command` (bare or `./`, no placeholder expansion), no `PLUGIN_ROOT`/`PLUGIN_DATA` keys in `env`, `cwd` starts with `./`, `${PLUGIN_ROOT}`, or `${PLUGIN_DATA}`, no secrets in `env`.
   - Remote: absolute `https://` URL (`http://` allowed only for `localhost` or loopback IP literals), no userinfo or fragment, no case-insensitive duplicate headers, no secrets in `headers`.
5. **Client Extensions (§8):** Reverse-domain namespaces in `plugin.json#extensions` and/or top-level `<namespace>/` directories.
