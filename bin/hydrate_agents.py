#!/usr/bin/env python3
"""Host-agnostic Agent Template hydrator for io.github.monolith-inc.agents v1.0.0.

Reads canonical agent templates from plugin.json#extensions["io.github.monolith-inc.agents"]
and io.github.monolith-inc.agents/host-profiles.json, then materializes native agent files
for the selected host (claude, codex, cursor, or antigravity).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

EXTENSION_NAMESPACE = "io.github.monolith-inc.agents"


def parse_template_markdown(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return {}, text
    end_idx = text.find("\n---", 3)
    if end_idx == -1:
        return {}, text
    raw_fm = text[4:end_idx]
    body = text[end_idx + 4:].lstrip("\r\n")
    fm: dict[str, str] = {}
    for line in raw_fm.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        fm[k.strip()] = v.strip()
    return fm, body


def load_extension(plugin_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads((plugin_root / "plugin.json").read_text(encoding="utf-8"))
    ext = (manifest.get("extensions") or {}).get(EXTENSION_NAMESPACE)
    if not isinstance(ext, dict):
        raise ValueError(f'Missing "{EXTENSION_NAMESPACE}" extension in {plugin_root / "plugin.json"}')
    profiles_rel = ext.get("hostProfiles", "./io.github.monolith-inc.agents/host-profiles.json")
    profiles = json.loads((plugin_root / profiles_rel).read_text(encoding="utf-8"))
    return ext, profiles


def toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def render_for_host(
    host: str,
    host_cfg: dict[str, Any],
    agent: dict[str, Any],
    template_fm: dict[str, str],
    body: str,
    model_override: str | None = None,
    effort_override: str | None = None,
) -> str:
    agent_id = agent["id"]
    description = template_fm.get("description") or agent.get("role", agent_id)
    tier = agent.get("modelTier", template_fm.get("modelTier", "balanced"))
    effort_key = agent.get("reasoningEffort", template_fm.get("reasoningEffort", "medium"))
    access = agent.get("access", template_fm.get("access", "read-only"))

    model = model_override or host_cfg["modelMap"].get(tier, tier)
    effort = effort_override or host_cfg["effortMap"].get(effort_key, effort_key)

    if host == "claude":
        tools = host_cfg["toolsMap"].get(access, ["Read"])
        tools_yaml = ", ".join(tools)
        return (
            "---\n"
            f"name: {agent_id}\n"
            f"description: {description}\n"
            f"model: {model}\n"
            f"effort: {effort}\n"
            f"tools: [{tools_yaml}]\n"
            "---\n\n"
            f"{body.rstrip()}\n"
        )

    if host == "codex":
        sandbox = host_cfg["sandboxMap"].get(access, "read-only")
        escaped_body = body.rstrip().replace('"""', '\\"\\"\\"')
        return (
            f'name = "{toml_escape(agent_id)}"\n'
            f'description = "{toml_escape(description)}"\n'
            f'model = "{toml_escape(model)}"\n'
            f'model_reasoning_effort = "{toml_escape(effort)}"\n'
            f'sandbox_mode = "{toml_escape(sandbox)}"\n'
            'developer_instructions = """\n'
            f"{escaped_body}\n"
            '"""\n'
        )

    if host == "cursor":
        readonly = "true" if host_cfg["readonlyMap"].get(access, True) else "false"
        return (
            "---\n"
            f"name: {agent_id}\n"
            f"description: {description}\n"
            f"model: {model}\n"
            f"reasoning_effort: {effort}\n"
            f"readonly: {readonly}\n"
            "---\n\n"
            f"{body.rstrip()}\n"
        )

    if host == "antigravity":
        write_tools = "true" if host_cfg["writeToolsMap"].get(access, False) else "false"
        return (
            "---\n"
            f"name: {agent_id}\n"
            f"description: {description}\n"
            f"model: {model}\n"
            f"reasoning_effort: {effort}\n"
            f"enable_write_tools: {write_tools}\n"
            "---\n\n"
            f"{body.rstrip()}\n"
        )

    raise ValueError(f"Unsupported host: {host}")


def hydrate_agents(
    plugin_root: Path,
    host: str,
    output_root: Path,
    dry_run: bool = False,
    model_override: str | None = None,
    effort_override: str | None = None,
) -> dict[str, Any]:
    ext, profiles = load_extension(plugin_root)
    hosts = profiles.get("hosts") or {}
    if host not in hosts:
        raise ValueError(f"Unsupported host '{host}'. Supported: {', '.join(sorted(hosts.keys()))}")

    host_cfg = hosts[host]
    out_dir = output_root / host_cfg["outputDir"]
    file_ext = host_cfg["fileExtension"]
    generated: list[dict[str, Any]] = []

    for agent in ext.get("agents", []):
        template_path = plugin_root / agent["template"]
        fm, body = parse_template_markdown(template_path.read_text(encoding="utf-8"))
        rendered = render_for_host(
            host=host,
            host_cfg=host_cfg,
            agent=agent,
            template_fm=fm,
            body=body,
            model_override=model_override,
            effort_override=effort_override,
        )
        dest = out_dir / f"{agent['id']}{file_ext}"
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(rendered, encoding="utf-8")
        generated.append(
            {
                "id": agent["id"],
                "host": host,
                "modelTier": agent["modelTier"],
                "reasoningEffort": agent["reasoningEffort"],
                "access": agent["access"],
                "destination": str(dest),
                "written": not dry_run,
            }
        )

    return {
        "ok": True,
        "host": host,
        "dry_run": dry_run,
        "agents": generated,
    }


def list_templates(plugin_root: Path) -> dict[str, Any]:
    ext, profiles = load_extension(plugin_root)
    return {
        "namespace": EXTENSION_NAMESPACE,
        "supported_hosts": sorted((profiles.get("hosts") or {}).keys()),
        "agents": ext.get("agents", []),
    }


def main() -> int:
    default_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Materialize host-agnostic agent templates for a target host.")
    parser.add_argument("--plugin-root", default=str(default_root), help="Path to plugin root.")
    parser.add_argument("--host", choices=("claude", "codex", "cursor", "antigravity"), help="Target host.")
    parser.add_argument("--output", default=".", help="Target workspace/project root where host agent files are written.")
    parser.add_argument("--dry-run", action="store_true", help="Render without writing files.")
    parser.add_argument("--list", action="store_true", help="List declared agent templates and supported hosts.")
    parser.add_argument("--override-model", default=None, help="Optional host model override.")
    parser.add_argument("--override-effort", default=None, help="Optional reasoning effort override.")
    args = parser.parse_args()

    plugin_root = Path(args.plugin_root).resolve()
    if args.list:
        print(json.dumps(list_templates(plugin_root), indent=2))
        return 0
    if not args.host:
        parser.error("--host is required unless --list is specified.")

    result = hydrate_agents(
        plugin_root=plugin_root,
        host=args.host,
        output_root=Path(args.output).resolve(),
        dry_run=args.dry_run,
        model_override=args.override_model,
        effort_override=args.override_effort,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
