#!/usr/bin/env python3
"""Zero-dependency MCP stdio server for agent-plugins-compliance.

Exposes three portable tools over JSON-RPC 2.0 stdio:
- audit_plugin: Run the v1.0.0 compliance audit + suggested changes generator.
- list_agent_templates: List declared host-agnostic agent templates and supported hosts.
- hydrate_agents: Materialize agent templates for claude, codex, cursor, or antigravity.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent
if str(BIN_DIR) not in sys.path:
    sys.path.insert(0, str(BIN_DIR))

from audit_plugin import render_markdown, run_audit  # noqa: E402
from hydrate_agents import hydrate_agents, list_templates  # noqa: E402

PROTOCOL_VERSION = "2025-03-26"
SERVER_INFO = {"name": "agent-plugins-compliance", "version": "1.0.0"}

TOOLS = [
    {
        "name": "audit_plugin",
        "description": (
            "Audit a target plugin directory against Agent Plugins Specification v1.0.0 "
            "and return both findings and concrete suggested changes for compliance."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Absolute or relative path to the plugin directory."},
                "format": {"type": "string", "enum": ["json", "markdown"], "default": "json"},
            },
            "required": ["target"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_agent_templates",
        "description": "List the host-agnostic compliance agent templates, their modelTier/reasoningEffort, and supported hosts.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "hydrate_agents",
        "description": "Materialize the compliance-auditor and compliance-remediator agent templates for a target host.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {"type": "string", "enum": ["claude", "codex", "cursor", "antigravity"]},
                "output": {"type": "string", "description": "Target project/workspace root where host agent files will be written."},
                "dry_run": {"type": "boolean", "default": False},
            },
            "required": ["host", "output"],
            "additionalProperties": False,
        },
    },
]


def send(message: dict) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def handle_request(req: dict, plugin_root: Path) -> None:
    method = req.get("method")
    req_id = req.get("id")
    if method == "notifications/initialized" or req_id is None:
        return

    if method == "initialize":
        send(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": SERVER_INFO,
                },
            }
        )
    elif method == "ping":
        send({"jsonrpc": "2.0", "id": req_id, "result": {}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}})
    elif method == "tools/call":
        params = req.get("params") or {}
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            if tool_name == "audit_plugin":
                result = run_audit(arguments["target"])
                text = render_markdown(result) if arguments.get("format") == "markdown" else json.dumps(result, indent=2)
            elif tool_name == "list_agent_templates":
                text = json.dumps(list_templates(plugin_root), indent=2)
            elif tool_name == "hydrate_agents":
                res = hydrate_agents(
                    plugin_root=plugin_root,
                    host=arguments["host"],
                    output_root=Path(arguments["output"]).resolve(),
                    dry_run=bool(arguments.get("dry_run", False)),
                )
                text = json.dumps(res, indent=2)
            else:
                send(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32602, "message": f"Unknown tool: {tool_name}"},
                    }
                )
                return
            send(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": text}], "isError": False},
                }
            )
        except Exception as exc:  # noqa: BLE001
            send(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": f"Error: {exc}"}], "isError": True},
                }
            )
    else:
        send(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        )


def main() -> int:
    default_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="MCP stdio server for agent-plugins-compliance")
    parser.add_argument("--plugin-root", default=os.environ.get("PLUGIN_ROOT", str(default_root)))
    parser.add_argument("--data-dir", default=os.environ.get("PLUGIN_DATA", "."))
    args = parser.parse_args()

    plugin_root = Path(args.plugin_root).resolve()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {exc}"}})
            continue
        if isinstance(req, dict):
            handle_request(req, plugin_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
