#!/usr/bin/env python3
"""Zero-dependency Agent Plugins Specification v1.0.0 compliance auditor.

Audits a target plugin directory against all normative v1.0.0 requirements and
emits both structured findings and an ordered list of concrete suggested changes
to bring the plugin into 100% compliance.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

PLUGIN_SCHEMA_1_0_0 = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA_1_0_0 = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"

PLUGIN_NAME_RE = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
CWD_RE = re.compile(r"^(?:\./|\$\{PLUGIN_ROOT\}(?:/|$)|\$\{PLUGIN_DATA\}(?:/|$))")
HEADER_NAME_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
LEGACY_PLACEHOLDER_RE = re.compile(r"\$\{(?:CLAUDE_PLUGIN_ROOT|workspaceFolder|HOME|ENV:[^}]+)\}")

ALLOWED_MANIFEST_KEYS = {
    "$schema",
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "extensions",
}
ALLOWED_AUTHOR_KEYS = {"name", "email", "url"}
RESERVED_ENV_KEYS = {"PLUGIN_ROOT", "PLUGIN_DATA"}
SENSITIVE_KEY_HINTS = ("authorization", "proxy-authorization", "api_key", "apikey", "secret", "token", "password")


def is_within(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve(strict=False)
        root_resolved = root.resolve(strict=True)
        resolved.relative_to(root_resolved)
        return True
    except (ValueError, OSError):
        return False


def is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def sanitize_plugin_name(raw: str) -> str:
    candidate = raw.strip().lower()
    if "/" in candidate:
        candidate = candidate.rsplit("/", 1)[-1]
    candidate = re.sub(r"[^a-z0-9.-]+", "-", candidate)
    candidate = re.sub(r"-{2,}", "-", candidate)
    candidate = re.sub(r"\.{2,}", ".", candidate)
    candidate = candidate.strip(".-")[:64].strip(".-")
    return candidate or "my-plugin"


class AuditContext:
    def __init__(self, target: Path) -> None:
        self.target = target
        self.findings: list[dict[str, Any]] = []
        self.suggested_changes: list[dict[str, Any]] = []
        self.summary: dict[str, Any] = {
            "manifest": None,
            "skills": [],
            "mcpServers": [],
            "extensions": [],
        }

    def add_finding(
        self,
        severity: str,
        boundary: str,
        code: str,
        path: str,
        section: str,
        message: str,
        action: str | None = None,
        patch_hint: str | None = None,
    ) -> None:
        self.findings.append(
            {
                "severity": severity,
                "boundary": boundary,
                "code": code,
                "path": path,
                "spec_section": section,
                "message": message,
            }
        )
        if action is not None:
            priority = "P0-fatal" if severity == "fatal" else ("P1-error" if severity == "error" else "P2-warning")
            self.suggested_changes.append(
                {
                    "id": f"CHG-{len(self.suggested_changes) + 1:02d}",
                    "priority": priority,
                    "file": path,
                    "spec_section": section,
                    "issue": message,
                    "action": action,
                    **({"patch_hint": patch_hint} if patch_hint else {}),
                }
            )


def audit_manifest(ctx: AuditContext) -> dict[str, Any] | None:
    manifest_path = ctx.target / "plugin.json"
    if not manifest_path.exists() and not manifest_path.is_symlink():
        legacy_locations = [
            p
            for p in (".claude-plugin/plugin.json", ".cursor-plugin/plugin.json", ".codex-plugin/plugin.json", "manifest.json")
            if (ctx.target / p).is_file()
        ]
        hint = (
            f"Migrate fields from {legacy_locations[0]} to root plugin.json"
            if legacy_locations
            else f'Create root plugin.json with "$schema": "{PLUGIN_SCHEMA_1_0_0}" and a valid "name".'
        )
        ctx.add_finding(
            "fatal",
            "plugin",
            "manifest.missing",
            "plugin.json",
            "§5.1",
            "Missing required root manifest plugin.json.",
            action=hint,
            patch_hint=json.dumps({"$schema": PLUGIN_SCHEMA_1_0_0, "name": sanitize_plugin_name(ctx.target.name)}, indent=2),
        )
        return None

    if not is_within(manifest_path, ctx.target):
        ctx.add_finding(
            "fatal",
            "plugin",
            "manifest.path_escape",
            "plugin.json",
            "§4.1",
            "plugin.json resolves outside the plugin root.",
            action="Replace the escaping symlink with a regular file inside the plugin root.",
        )
        return None

    if not manifest_path.is_file():
        ctx.add_finding(
            "fatal",
            "plugin",
            "manifest.not_a_file",
            "plugin.json",
            "§5.1",
            "plugin.json exists but is not a regular file.",
            action="Replace plugin.json with a regular JSON object file.",
        )
        return None

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        ctx.add_finding(
            "fatal",
            "plugin",
            "manifest.invalid_json",
            "plugin.json",
            "§5.2",
            f"plugin.json is not valid JSON: {exc}.",
            action="Fix JSON syntax errors in plugin.json.",
        )
        return None

    if not isinstance(data, dict):
        ctx.add_finding(
            "fatal",
            "plugin",
            "manifest.not_an_object",
            "plugin.json",
            "§5.2",
            "plugin.json top-level value must be a JSON object.",
            action="Rewrite plugin.json as a JSON object with '$schema' and 'name'.",
        )
        return None

    # $schema
    schema_val = data.get("$schema")
    if schema_val != PLUGIN_SCHEMA_1_0_0:
        ctx.add_finding(
            "fatal",
            "plugin",
            "manifest.schema.invalid",
            "plugin.json",
            "§5.2, §5.3",
            f'Manifest "$schema" must be "{PLUGIN_SCHEMA_1_0_0}", got {schema_val!r}.',
            action=f'Set "$schema": "{PLUGIN_SCHEMA_1_0_0}" at the top level of plugin.json.',
            patch_hint=f'"$schema": "{PLUGIN_SCHEMA_1_0_0}"',
        )

    # name
    name_val = data.get("name")
    if not isinstance(name_val, str) or not (1 <= len(name_val) <= 64) or not PLUGIN_NAME_RE.match(name_val):
        suggested = sanitize_plugin_name(str(name_val or ctx.target.name))
        ctx.add_finding(
            "fatal",
            "plugin",
            "manifest.name.invalid",
            "plugin.json",
            "§5.3, §5.5",
            f"Manifest 'name' ({name_val!r}) violates v1.0.0 constraints (1-64 lowercase a-z/0-9/-/. without -- or ..).",
            action=f'Rename plugin.json#name to a v1.0.0-compliant identifier such as "{suggested}".',
            patch_hint=f'"name": "{suggested}"',
        )

    # Unknown top-level fields (non-fatal warning)
    for key in sorted(set(data.keys()) - ALLOWED_MANIFEST_KEYS):
        if key == "schemaVersion":
            action = 'Remove legacy "schemaVersion" from plugin.json (versioning is declared exclusively by "$schema").'
        elif key == "mcpServers":
            action = 'Move inline "mcpServers" out of plugin.json into a root mcp.json file with "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json".'
        elif key == "skills":
            action = 'Remove "skills" from plugin.json; skills are discovered automatically from fixed root skills/<name>/SKILL.md.'
        else:
            action = f'Move unknown top-level field "{key}" into plugin.json#extensions["<your-reverse-domain>"] or remove it.'
        ctx.add_finding(
            "warning",
            "manifest-field",
            "manifest.unknown_field",
            "plugin.json",
            "§5.2",
            f'Unknown top-level field "{key}" is a non-fatal schema violation (clients report and ignore it).',
            action=action,
        )

    # Metadata types
    for field in ("version", "description", "homepage", "repository", "license"):
        if field in data and not isinstance(data[field], str):
            ctx.add_finding(
                "fatal",
                "plugin",
                f"manifest.{field}.invalid_type",
                "plugin.json",
                "§5.4",
                f'Manifest field "{field}" must be a JSON string.',
                action=f'Convert plugin.json#{field} to a string value or remove it.',
            )

    if "keywords" in data:
        kw = data["keywords"]
        if not isinstance(kw, list) or not all(isinstance(item, str) for item in kw):
            ctx.add_finding(
                "fatal",
                "plugin",
                "manifest.keywords.invalid_type",
                "plugin.json",
                "§5.4",
                'Manifest field "keywords" must be an array of strings.',
                action="Update plugin.json#keywords to be an array of strings.",
            )

    if "author" in data:
        author = data["author"]
        if not isinstance(author, dict):
            ctx.add_finding(
                "fatal",
                "plugin",
                "manifest.author.invalid_type",
                "plugin.json",
                "§5.4",
                'Manifest field "author" must be an object with optional string fields name, email, url.',
                action='Convert plugin.json#author to an object, e.g. {"name": "..."}.',
            )
        else:
            extra_author = sorted(set(author.keys()) - ALLOWED_AUTHOR_KEYS)
            if extra_author:
                ctx.add_finding(
                    "fatal",
                    "plugin",
                    "manifest.author.unknown_field",
                    "plugin.json",
                    "§5.4",
                    f'Manifest "author" contains disallowed fields: {extra_author}.',
                    action=f'Remove {extra_author} from plugin.json#author (only "name", "email", "url" are allowed).',
                )
            for ak, av in author.items():
                if ak in ALLOWED_AUTHOR_KEYS and not isinstance(av, str):
                    ctx.add_finding(
                        "fatal",
                        "plugin",
                        f"manifest.author.{ak}.invalid_type",
                        "plugin.json",
                        "§5.4",
                        f'Manifest "author.{ak}" must be a string.',
                        action=f'Change plugin.json#author.{ak} to a string.',
                    )

    if "extensions" in data:
        ext = data["extensions"]
        if not isinstance(ext, dict):
            ctx.add_finding(
                "warning",
                "manifest-field",
                "manifest.extensions.invalid_type",
                "plugin.json",
                "§8.1",
                'Manifest "extensions" is not a JSON object (non-fatal; clients report and ignore it).',
                action='Change plugin.json#extensions to an object keyed by reverse-domain namespaces, or remove it.',
            )
        else:
            ctx.summary["extensions"] = sorted(ext.keys())
            for ns, val in ext.items():
                if not isinstance(val, dict):
                    ctx.add_finding(
                        "error",
                        "manifest-field",
                        "manifest.extensions.namespace_not_object",
                        "plugin.json",
                        "§8.1",
                        f'Extension namespace "{ns}" value must be a JSON object.',
                        action=f'Wrap plugin.json#extensions["{ns}"] value in a JSON object.',
                    )

    ctx.summary["manifest"] = {"name": name_val, "version": data.get("version"), "$schema": schema_val}
    return data


def audit_symlinks(ctx: AuditContext) -> None:
    for dirpath, dirnames, filenames in os.walk(ctx.target, followlinks=False):
        base = Path(dirpath)
        for entry in list(dirnames) + list(filenames):
            p = base / entry
            if p.is_symlink() and not is_within(p, ctx.target):
                rel = str(p.relative_to(ctx.target))
                ctx.add_finding(
                    "error",
                    "path",
                    "path.symlink_escape",
                    rel,
                    "§4.1",
                    f"Symlink '{rel}' resolves outside the plugin root.",
                    action=f"Replace escaping symlink '{rel}' with a real file copied inside the plugin root or a target within the plugin root.",
                )


def audit_skills(ctx: AuditContext) -> None:
    skills_dir = ctx.target / "skills"
    if not skills_dir.exists() and not skills_dir.is_symlink():
        return
    if not is_within(skills_dir, ctx.target):
        ctx.add_finding(
            "error",
            "component-type:skills",
            "skills.path_escape",
            "skills",
            "§4.1, §6.2",
            "skills/ resolves outside the plugin root.",
            action="Replace escaping skills/ symlink with a real directory inside the plugin root.",
        )
        return
    if not skills_dir.is_dir():
        ctx.add_finding(
            "error",
            "component-type:skills",
            "skills.not_a_directory",
            "skills",
            "§6.2",
            "Fixed component location 'skills' exists but is not a directory.",
            action="Replace 'skills' with a directory containing immediate child skill folders.",
        )
        return

    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir():
            continue
        skill_md = child / "SKILL.md"
        rel = f"skills/{child.name}/SKILL.md"
        if not skill_md.exists() and not skill_md.is_symlink():
            nested = list(child.rglob("SKILL.md"))
            if nested:
                nested_rels = [str(p.relative_to(ctx.target)) for p in nested]
                ctx.add_finding(
                    "warning",
                    f"skill:{child.name}",
                    "skill.nested_ignored",
                    f"skills/{child.name}",
                    "§7.1",
                    f"Nested SKILL.md files ({nested_rels}) will not be discovered; only immediate children of skills/ are discovered.",
                    action=f"Flatten nested skills under skills/{child.name}/ into immediate child directories of skills/<skill-name>/SKILL.md.",
                )
            continue
        if not is_within(skill_md, ctx.target):
            ctx.add_finding(
                "error",
                f"skill:{child.name}",
                "skill.path_escape",
                rel,
                "§4.1, §7.1",
                f"{rel} resolves outside the plugin root.",
                action=f"Replace escaping symlink at {rel} with a regular file inside the plugin root.",
            )
            continue
        if not skill_md.is_file():
            ctx.add_finding(
                "error",
                f"skill:{child.name}",
                "skill.not_a_file",
                rel,
                "§7.1",
                f"{rel} is not a regular file.",
                action=f"Replace {rel} with a regular Markdown file.",
            )
            continue
        text = skill_md.read_text(encoding="utf-8")
        if not text.startswith("---\n") and not text.startswith("---\r\n"):
            ctx.add_finding(
                "error",
                f"skill:{child.name}",
                "skill.missing_frontmatter",
                rel,
                "§7.1",
                f"{rel} is missing YAML frontmatter.",
                action=f'Add YAML frontmatter with "name: {child.name}" and "description: ..." at the top of {rel}.',
            )
            continue
        end_idx = text.find("\n---", 3)
        if end_idx == -1:
            ctx.add_finding(
                "error",
                f"skill:{child.name}",
                "skill.unterminated_frontmatter",
                rel,
                "§7.1",
                f"{rel} has unterminated YAML frontmatter.",
                action=f"Close the YAML frontmatter block with '---' in {rel}.",
            )
            continue
        fm = text[4:end_idx]
        if not re.search(r"^name:\s*\S+", fm, re.MULTILINE) or not re.search(r"^description:\s*\S+", fm, re.MULTILINE):
            ctx.add_finding(
                "error",
                f"skill:{child.name}",
                "skill.incomplete_frontmatter",
                rel,
                "§7.1",
                f"{rel} frontmatter must include non-empty 'name' and 'description'.",
                action=f"Ensure {rel} YAML frontmatter declares both 'name' and 'description'.",
            )
            continue
        ctx.summary["skills"].append(rel)


def audit_stdio_server(ctx: AuditContext, name: str, cfg: dict[str, Any]) -> None:
    allowed = {"type", "command", "args", "env", "cwd"}
    extra = sorted(set(cfg.keys()) - allowed)
    if extra:
        ctx.add_finding(
            "error",
            f"mcp:{name}",
            "mcpServer.unknown_field",
            "mcp.json",
            "§7.2.1",
            f"stdio server '{name}' contains disallowed fields: {extra}.",
            action=f"Remove disallowed fields {extra} from mcp.json#mcpServers.{name}.",
        )

    cmd = cfg.get("command")
    if not isinstance(cmd, str) or not cmd:
        ctx.add_finding(
            "error",
            f"mcp:{name}",
            "mcpServer.command.required",
            "mcp.json",
            "§7.2.1",
            f"stdio server '{name}' requires a non-empty string 'command'.",
            action=f"Add a single-token executable 'command' to mcp.json#mcpServers.{name}.",
        )
    else:
        if "${PLUGIN_ROOT}" in cmd or "${PLUGIN_DATA}" in cmd or LEGACY_PLACEHOLDER_RE.search(cmd):
            ctx.add_finding(
                "error",
                f"mcp:{name}",
                "mcpServer.command.placeholder",
                "mcp.json",
                "§7.2.1, §9.2",
                f"stdio server '{name}' command '{cmd}' contains a placeholder (forbidden in command).",
                action=f"Replace placeholder in command with a './'-prefixed plugin-relative path (e.g. './bin/server') or bare executable name.",
            )
        if any(ch.isspace() for ch in cmd):
            ctx.add_finding(
                "warning",
                f"mcp:{name}",
                "mcpServer.command.shell_string",
                "mcp.json",
                "§7.2.1",
                f"stdio server '{name}' command '{cmd}' contains whitespace; command must be a single executable token, not a shell string.",
                action=f"Split '{cmd}' into a single executable token in 'command' and move flags/arguments into 'args'.",
            )
        if cmd.startswith("./"):
            resolved = ctx.target / cmd
            if not is_within(resolved, ctx.target):
                ctx.add_finding(
                    "error",
                    f"mcp:{name}",
                    "mcpServer.command.escape",
                    "mcp.json",
                    "§4.1, §7.2.1",
                    f"stdio server '{name}' command '{cmd}' escapes the plugin root.",
                    action=f"Point mcp.json#mcpServers.{name}.command to an executable strictly within the plugin root.",
                )
            elif not resolved.exists():
                ctx.add_finding(
                    "warning",
                    f"mcp:{name}",
                    "mcpServer.command.missing",
                    "mcp.json",
                    "§7.2.1",
                    f"Bundled executable '{cmd}' for server '{name}' does not exist on disk.",
                    action=f"Create '{cmd}' (with executable permissions) or update mcp.json#mcpServers.{name}.command.",
                )
        elif "/" in cmd or "\\" in cmd:
            ctx.add_finding(
                "error",
                f"mcp:{name}",
                "mcpServer.command.invalid_path",
                "mcp.json",
                "§7.2.1",
                f"stdio server '{name}' command '{cmd}' must be a bare executable name or './'-prefixed plugin-relative path.",
                action=f"Change command '{cmd}' to start with './' (for bundled executables) or use a bare executable name.",
            )

    if "args" in cfg:
        args = cfg["args"]
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            ctx.add_finding(
                "error",
                f"mcp:{name}",
                "mcpServer.args.invalid_type",
                "mcp.json",
                "§7.2.1",
                f"stdio server '{name}' 'args' must be an array of strings.",
                action=f"Convert mcp.json#mcpServers.{name}.args to an array of strings.",
            )
        else:
            for arg in args:
                if LEGACY_PLACEHOLDER_RE.search(arg):
                    ctx.add_finding(
                        "warning",
                        f"mcp:{name}",
                        "mcpServer.args.legacy_placeholder",
                        "mcp.json",
                        "§9.2",
                        f"stdio server '{name}' arg '{arg}' uses a non-portable placeholder; only ${{PLUGIN_ROOT}} and ${{PLUGIN_DATA}} are expanded.",
                        action=f"Replace legacy placeholder in '{arg}' with '${{PLUGIN_ROOT}}' or '${{PLUGIN_DATA}}'.",
                    )

    if "env" in cfg:
        env = cfg["env"]
        if not isinstance(env, dict):
            ctx.add_finding(
                "error",
                f"mcp:{name}",
                "mcpServer.env.invalid_type",
                "mcp.json",
                "§7.2.1",
                f"stdio server '{name}' 'env' must be an object of string values.",
                action=f"Convert mcp.json#mcpServers.{name}.env to a JSON object mapping string keys to string values.",
            )
        else:
            for k, v in env.items():
                if k in RESERVED_ENV_KEYS:
                    ctx.add_finding(
                        "error",
                        f"mcp:{name}",
                        "mcpServer.env.reserved_key",
                        "mcp.json",
                        "§9.2",
                        f"stdio server '{name}' env must not declare reserved variable '{k}'.",
                        action=f"Remove '{k}' from mcp.json#mcpServers.{name}.env (clients inject it automatically).",
                    )
                if not isinstance(v, str):
                    ctx.add_finding(
                        "error",
                        f"mcp:{name}",
                        "mcpServer.env.value_type",
                        "mcp.json",
                        "§7.2.1",
                        f"stdio server '{name}' env.{k} must be a string.",
                        action=f"Convert mcp.json#mcpServers.{name}.env.{k} to a string.",
                    )
                elif any(hint in k.lower() for hint in SENSITIVE_KEY_HINTS) and v.strip():
                    ctx.add_finding(
                        "warning",
                        f"mcp:{name}",
                        "mcpServer.env.possible_secret",
                        "mcp.json",
                        "§9.2",
                        f"stdio server '{name}' env.{k} appears to hold a secret/credential (visible package data must not embed secrets).",
                        action=f"Remove secret value from mcp.json#mcpServers.{name}.env.{k} and use client-managed auth.",
                    )

    if "cwd" in cfg:
        cwd = cfg["cwd"]
        if not isinstance(cwd, str) or not CWD_RE.match(cwd):
            ctx.add_finding(
                "error",
                f"mcp:{name}",
                "mcpServer.cwd.invalid",
                "mcp.json",
                "§7.2.1",
                f"stdio server '{name}' cwd '{cwd}' must start with './', '${{PLUGIN_ROOT}}', or '${{PLUGIN_DATA}}'.",
                action=f"Prefix mcp.json#mcpServers.{name}.cwd with './', '${{PLUGIN_ROOT}}', or '${{PLUGIN_DATA}}'.",
            )
        else:
            if cwd.startswith("./") and not is_within(ctx.target / cwd, ctx.target):
                ctx.add_finding(
                    "error",
                    f"mcp:{name}",
                    "mcpServer.cwd.escape",
                    "mcp.json",
                    "§7.2.1",
                    f"stdio server '{name}' cwd '{cwd}' escapes plugin root.",
                    action=f"Ensure mcp.json#mcpServers.{name}.cwd resolves inside the plugin root.",
                )
            elif cwd.startswith("${PLUGIN_ROOT}"):
                sub = cwd[len("${PLUGIN_ROOT}"):].lstrip("/")
                if not is_within(ctx.target / sub, ctx.target):
                    ctx.add_finding(
                        "error",
                        f"mcp:{name}",
                        "mcpServer.cwd.escape",
                        "mcp.json",
                        "§7.2.1",
                        f"stdio server '{name}' cwd '{cwd}' escapes PLUGIN_ROOT.",
                        action=f"Ensure mcp.json#mcpServers.{name}.cwd stays inside ${{PLUGIN_ROOT}}.",
                    )
            elif cwd.startswith("${PLUGIN_DATA}"):
                fake_data = Path("/tmp/__agent_plugins_fake_data__")
                sub = cwd[len("${PLUGIN_DATA}"):].lstrip("/")
                norm = Path(os.path.normpath(str(fake_data / sub)))
                try:
                    norm.relative_to(fake_data)
                except ValueError:
                    ctx.add_finding(
                        "error",
                        f"mcp:{name}",
                        "mcpServer.cwd.escape",
                        "mcp.json",
                        "§7.2.1",
                        f"stdio server '{name}' cwd '{cwd}' escapes PLUGIN_DATA.",
                        action=f"Ensure mcp.json#mcpServers.{name}.cwd stays inside ${{PLUGIN_DATA}}.",
                    )


def audit_remote_server(ctx: AuditContext, name: str, cfg: dict[str, Any]) -> None:
    allowed = {"type", "url", "headers"}
    extra = sorted(set(cfg.keys()) - allowed)
    if extra:
        ctx.add_finding(
            "error",
            f"mcp:{name}",
            "mcpServer.unknown_field",
            "mcp.json",
            "§7.2.1",
            f"Remote server '{name}' contains disallowed fields: {extra}.",
            action=f"Remove disallowed fields {extra} from mcp.json#mcpServers.{name}.",
        )

    url = cfg.get("url")
    if not isinstance(url, str) or not url:
        ctx.add_finding(
            "error",
            f"mcp:{name}",
            "mcpServer.url.required",
            "mcp.json",
            "§7.2.1",
            f"Remote server '{name}' requires a non-empty string 'url'.",
            action=f"Set a valid HTTPS 'url' on mcp.json#mcpServers.{name}.",
        )
    else:
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            ctx.add_finding(
                "error",
                f"mcp:{name}",
                "mcpServer.url.invalid",
                "mcp.json",
                "§7.2.1",
                f"Remote server '{name}' url '{url}' must be an absolute HTTP or HTTPS URL.",
                action=f"Update mcp.json#mcpServers.{name}.url to a valid absolute https:// URL.",
            )
        if parsed.username is not None or parsed.password is not None:
            ctx.add_finding(
                "error",
                f"mcp:{name}",
                "mcpServer.url.userinfo",
                "mcp.json",
                "§7.2.1",
                f"Remote server '{name}' url must not contain userinfo.",
                action=f"Strip username/password from mcp.json#mcpServers.{name}.url.",
            )
        if parsed.fragment:
            ctx.add_finding(
                "error",
                f"mcp:{name}",
                "mcpServer.url.fragment",
                "mcp.json",
                "§7.2.1",
                f"Remote server '{name}' url must not contain a fragment (#...).",
                action=f"Remove the '#...' fragment from mcp.json#mcpServers.{name}.url.",
            )
        if parsed.scheme == "http" and not is_loopback_host(parsed.hostname):
            ctx.add_finding(
                "error",
                f"mcp:{name}",
                "mcpServer.url.insecure_http",
                "mcp.json",
                "§7.2.1",
                f"Non-loopback endpoint '{url}' for server '{name}' must use HTTPS.",
                action=f"Upgrade mcp.json#mcpServers.{name}.url from http:// to https://.",
            )

    if "headers" in cfg:
        headers = cfg["headers"]
        if not isinstance(headers, dict):
            ctx.add_finding(
                "error",
                f"mcp:{name}",
                "mcpServer.headers.invalid_type",
                "mcp.json",
                "§7.2.1",
                f"Remote server '{name}' 'headers' must be an object of strings.",
                action=f"Convert mcp.json#mcpServers.{name}.headers to a string-to-string object.",
            )
        else:
            seen: set[str] = set()
            for hk, hv in headers.items():
                if not isinstance(hv, str):
                    ctx.add_finding(
                        "error",
                        f"mcp:{name}",
                        "mcpServer.headers.value_type",
                        "mcp.json",
                        "§7.2.1",
                        f"Header '{hk}' on server '{name}' must be a string.",
                        action=f"Convert header '{hk}' value to a string.",
                    )
                if not HEADER_NAME_RE.match(hk):
                    ctx.add_finding(
                        "error",
                        f"mcp:{name}",
                        "mcpServer.headers.invalid_name",
                        "mcp.json",
                        "§7.2.1",
                        f"Header name '{hk}' on server '{name}' is not a valid HTTP header token.",
                        action=f"Fix or remove invalid header name '{hk}'.",
                    )
                low = hk.lower()
                if low in seen:
                    ctx.add_finding(
                        "error",
                        f"mcp:{name}",
                        "mcpServer.headers.duplicate",
                        "mcp.json",
                        "§7.2.1",
                        f"Duplicate case-insensitive header '{hk}' on server '{name}'.",
                        action=f"Deduplicate case-insensitive header '{hk}' in mcp.json#mcpServers.{name}.headers.",
                    )
                seen.add(low)
                if any(hint in low for hint in SENSITIVE_KEY_HINTS):
                    ctx.add_finding(
                        "warning",
                        f"mcp:{name}",
                        "mcpServer.headers.possible_secret",
                        "mcp.json",
                        "§7.2.1",
                        f"Header '{hk}' on server '{name}' looks like a credential; plugins must not embed secrets in headers.",
                        action=f"Remove credential header '{hk}' from mcp.json#mcpServers.{name}.headers and rely on client-managed MCP authorization.",
                    )


def audit_mcp(ctx: AuditContext) -> None:
    mcp_path = ctx.target / "mcp.json"
    if not mcp_path.exists() and not mcp_path.is_symlink():
        legacy_mcp = ctx.target / ".mcp.json"
        if legacy_mcp.is_file():
            ctx.add_finding(
                "warning",
                "component-type:mcp",
                "mcp.legacy_location",
                ".mcp.json",
                "§7.2.1",
                "Found legacy '.mcp.json'; Agent Plugins v1.0.0 discovers MCP configuration only from root 'mcp.json'.",
                action=f'Move ".mcp.json" to root "mcp.json" with "$schema": "{MCP_SCHEMA_1_0_0}" and explicit server "type" fields.',
            )
        return

    if not is_within(mcp_path, ctx.target):
        ctx.add_finding(
            "error",
            "component-type:mcp",
            "mcp.path_escape",
            "mcp.json",
            "§4.1, §6.2",
            "mcp.json resolves outside the plugin root.",
            action="Replace escaping mcp.json symlink with a regular file inside the plugin root.",
        )
        return
    if not mcp_path.is_file():
        ctx.add_finding(
            "error",
            "component-type:mcp",
            "mcp.not_a_file",
            "mcp.json",
            "§6.2",
            "mcp.json exists but is not a regular file.",
            action="Replace mcp.json with a regular JSON object file.",
        )
        return

    try:
        data = json.loads(mcp_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        ctx.add_finding(
            "error",
            "component-type:mcp",
            "mcp.invalid_json",
            "mcp.json",
            "§7.2.2",
            f"mcp.json is not valid JSON: {exc}.",
            action="Fix JSON syntax errors in mcp.json.",
        )
        return

    if not isinstance(data, dict):
        ctx.add_finding(
            "error",
            "component-type:mcp",
            "mcp.not_an_object",
            "mcp.json",
            "§7.2.1",
            "mcp.json top-level value must be a JSON object.",
            action=f'Wrap mcp.json as {{"$schema": "{MCP_SCHEMA_1_0_0}", "mcpServers": {{...}}}}.',
        )
        return

    if "mcpServers" not in data:
        ctx.add_finding(
            "error",
            "component-type:mcp",
            "mcp.missing_wrapper",
            "mcp.json",
            "§7.2.1",
            'mcp.json is missing required top-level "mcpServers" object (looks like a legacy bare server map).',
            action=f'Wrap servers inside {{"$schema": "{MCP_SCHEMA_1_0_0}", "mcpServers": {{...}}}} and add explicit "type" on every server.',
        )
        return

    extra_top = sorted(set(data.keys()) - {"$schema", "mcpServers"})
    if extra_top:
        ctx.add_finding(
            "error",
            "component-type:mcp",
            "mcp.unknown_top_level_field",
            "mcp.json",
            "§7.2.1",
            f"mcp.json contains disallowed top-level fields: {extra_top}.",
            action=f'Remove {extra_top} from mcp.json (only "$schema" and "mcpServers" are allowed).',
        )

    if data.get("$schema") != MCP_SCHEMA_1_0_0:
        ctx.add_finding(
            "error",
            "component-type:mcp",
            "mcp.schema.invalid",
            "mcp.json",
            "§7.2.1, §10.1",
            f'mcp.json "$schema" must be "{MCP_SCHEMA_1_0_0}", got {data.get("$schema")!r}.',
            action=f'Set "$schema": "{MCP_SCHEMA_1_0_0}" in mcp.json.',
            patch_hint=f'"$schema": "{MCP_SCHEMA_1_0_0}"',
        )

    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        ctx.add_finding(
            "error",
            "component-type:mcp",
            "mcp.mcpServers.invalid_type",
            "mcp.json",
            "§7.2.1",
            'mcp.json "mcpServers" must be a JSON object.',
            action='Convert mcp.json#mcpServers to a JSON object keyed by server name.',
        )
        return

    for srv_name, srv_cfg in servers.items():
        if not isinstance(srv_cfg, dict):
            ctx.add_finding(
                "error",
                f"mcp:{srv_name}",
                "mcpServer.not_an_object",
                "mcp.json",
                "§7.2.1",
                f"MCP server '{srv_name}' must be a JSON object.",
                action=f"Convert mcp.json#mcpServers.{srv_name} to a valid server object with explicit 'type'.",
            )
            continue
        stype = srv_cfg.get("type")
        if stype == "stdio":
            audit_stdio_server(ctx, srv_name, srv_cfg)
            ctx.summary["mcpServers"].append({"name": srv_name, "type": "stdio"})
        elif stype in ("streamable-http", "sse"):
            audit_remote_server(ctx, srv_name, srv_cfg)
            ctx.summary["mcpServers"].append({"name": srv_name, "type": stype})
        else:
            inferred = "stdio" if "command" in srv_cfg else ("streamable-http" if "url" in srv_cfg else "stdio")
            ctx.add_finding(
                "error",
                f"mcp:{srv_name}",
                "mcpServer.type.invalid",
                "mcp.json",
                "§7.2.1",
                f"MCP server '{srv_name}' has missing or unsupported 'type': {stype!r}.",
                action=f'Add explicit "type": "{inferred}" (valid values: "stdio", "streamable-http", "sse") to mcp.json#mcpServers.{srv_name}.',
            )


def run_audit(target_dir: str | Path) -> dict[str, Any]:
    target = Path(target_dir).resolve()
    if not target.is_dir():
        return {
            "target": str(target),
            "spec_version": "1.0.0",
            "status": "FAIL",
            "counts": {"fatal": 1, "error": 0, "warning": 0},
            "summary": {},
            "findings": [
                {
                    "severity": "fatal",
                    "boundary": "plugin",
                    "code": "target.not_a_directory",
                    "path": str(target),
                    "spec_section": "§4.1",
                    "message": f"Target path '{target}' does not exist or is not a directory.",
                }
            ],
            "suggested_changes": [],
        }

    ctx = AuditContext(target)
    audit_manifest(ctx)
    audit_symlinks(ctx)
    audit_skills(ctx)
    audit_mcp(ctx)

    fatal_count = sum(1 for f in ctx.findings if f["severity"] == "fatal")
    error_count = sum(1 for f in ctx.findings if f["severity"] == "error")
    warn_count = sum(1 for f in ctx.findings if f["severity"] == "warning")

    if fatal_count > 0 or error_count > 0:
        status = "FAIL"
    elif warn_count > 0:
        status = "PASS_WITH_WARNINGS"
    else:
        status = "PASS"

    return {
        "target": str(target),
        "spec_version": "1.0.0",
        "status": status,
        "counts": {"fatal": fatal_count, "error": error_count, "warning": warn_count},
        "summary": ctx.summary,
        "findings": ctx.findings,
        "suggested_changes": ctx.suggested_changes,
    }


def render_markdown(result: dict[str, Any]) -> str:
    counts = result["counts"]
    lines = [
        f"# Agent Plugins v1.0.0 Compliance Audit",
        "",
        f"- **Target:** `{result['target']}`",
        f"- **Spec Version:** `{result['spec_version']}`",
        f"- **Status:** **{result['status']}** (fatal: {counts['fatal']}, errors: {counts['error']}, warnings: {counts['warning']})",
        "",
    ]
    summary = result.get("summary") or {}
    if summary:
        lines.extend(
            [
                "## Discovered Package Summary",
                f"- **Manifest:** `{summary.get('manifest')}`",
                f"- **Skills ({len(summary.get('skills', []))}):** {', '.join(summary.get('skills', [])) or 'none'}",
                f"- **MCP Servers ({len(summary.get('mcpServers', []))}):** "
                + (", ".join(f"{s['name']} ({s['type']})" for s in summary.get("mcpServers", [])) or "none"),
                f"- **Extensions ({len(summary.get('extensions', []))}):** {', '.join(summary.get('extensions', [])) or 'none'}",
                "",
            ]
        )

    findings = result.get("findings") or []
    if not findings:
        lines.append("## Findings\n\nNo compliance issues found. This plugin is 100% compliant with Agent Plugins v1.0.0.\n")
    else:
        lines.append("## Findings\n")
        lines.append("| Severity | Boundary | Spec | Path | Code | Message |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for f in findings:
            lines.append(
                f"| `{f['severity']}` | `{f['boundary']}` | {f['spec_section']} | `{f['path']}` | `{f['code']}` | {f['message']} |"
            )
        lines.append("")

    changes = result.get("suggested_changes") or []
    if changes:
        lines.append("## Suggested Changes for Compliance\n")
        for c in changes:
            lines.append(f"### {c['id']} [{c['priority']}] — `{c['file']}` ({c['spec_section']})")
            lines.append(f"- **Issue:** {c['issue']}")
            lines.append(f"- **Action:** {c['action']}")
            if "patch_hint" in c:
                lines.append(f"- **Hint:** `{c['patch_hint']}`")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a plugin directory against Agent Plugins Specification v1.0.0.")
    parser.add_argument("target", help="Path to the plugin directory to audit.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown", help="Output format.")
    args = parser.parse_args()

    result = run_audit(args.target)
    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        print(render_markdown(result), end="")
    return 0 if result["status"] in ("PASS", "PASS_WITH_WARNINGS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
