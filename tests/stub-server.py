"""Minimal MCP server used by host.test.js to prove the plugin's argument wrapper.

It speaks the same newline-delimited JSON-RPC that the real server does, and it
exposes one tool shaped the way FastMCP shapes every tool: a single `params`
object holding the real inputs. `stub_wrapped` echoes back exactly what it
received, so the test can tell whether the plugin re-wrapped the arguments or
sent them flat.
"""
import json
import sys

TOOLS = [
    {
        "name": "stub_wrapped",
        "description": "a FastMCP-shaped tool whose inputs live in one params object",
        "inputSchema": {
            "type": "object",
            "properties": {"params": {"$ref": "#/$defs/StubInput"}},
            "required": ["params"],
            "$defs": {
                "StubInput": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "width_mm": {"type": "number", "default": 80},
                        "shape": {"type": "string", "enum": ["box", "cylinder"], "default": "cylinder"},
                    },
                    "required": [],
                }
            },
        },
    },
    {
        "name": "stub_plain",
        "description": "a tool with flat arguments, to prove nothing is wrapped twice",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
            "additionalProperties": False,
        },
    },
{
        "name": "stub_export",
        "description": "a write-shaped tool with a path argument, for the path gate",
        "inputSchema": {
            "type": "object",
            "properties": {"params": {"$ref": "#/$defs/StubExport"}},
            "required": ["params"],
            "$defs": {
                "StubExport": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"output_path": {"type": "string"}},
                    "required": ["output_path"],
                }
            },
        },
    },
]


def send(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def handle(message):
    if "id" not in message:
        return
    method = message.get("method")
    if method == "initialize":
        send({
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "stub-py", "version": "0.0.1"},
            },
        })
        return
    if method == "tools/list":
        send({"jsonrpc": "2.0", "id": message["id"], "result": {"tools": TOOLS}})
        return
    if method == "tools/call":
        name = message.get("params", {}).get("name")
        arguments = message.get("params", {}).get("arguments") or {}
        if name == "stub_wrapped":
            # Echo the exact wire arguments so the test can assert the wrapper.
            send({"jsonrpc": "2.0", "id": message["id"], "result": {"content": [{"type": "text", "text": json.dumps(arguments)}]}})
            return
        if name == "stub_plain":
            send({"jsonrpc": "2.0", "id": message["id"], "result": {"content": [{"type": "text", "text": json.dumps(arguments)}]}})
            return
        send({"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32602, "message": "unknown tool %s" % name}})
        return
    send({"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": "unknown method %s" % method}})


for line in sys.stdin:
    line = line.strip()
    if line:
        handle(json.loads(line))