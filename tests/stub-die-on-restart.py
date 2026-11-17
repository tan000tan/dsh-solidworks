"""Minimal JSON-RPC MCP stdio server whose *second* start dies (exit 9).

Used by host.test.js to prove that a failed cross-session re-sync comes back
as a structured "unavailable" envelope instead of a thrown error (C-EXEC-01).

Deliberately dependency-free: it only needs the Python interpreter that discovery
already validated, so these tests never touch SolidWorks.

Behaviour switches (env):
  GC_STUB_MARK   append the pid to this file on every start (counts restarts)
  GC_STUB_DIE_ON_START  exit(9) immediately when the mark file already has a line
                        (simulates "the server cannot start a second time")
"""
import json
import os
import sys
import time

MARK = os.environ.get("GC_STUB_MARK")
LOG = os.environ.get("GC_STUB_LOG")
DIE_ON_START = os.environ.get("GC_STUB_DIE_ON_START") == "1"

if MARK:
    with open(MARK, "a", encoding="utf-8") as fh:
        fh.write("%d\n" % os.getpid())
    if DIE_ON_START:
        with open(MARK, encoding="utf-8") as fh:
            if len([x for x in fh.read().splitlines() if x.strip()]) > 1:
                sys.exit(9)

TOOLS = [
    {"name": "solidworks_sketch_and_extrude", "description": "sleep then echo",
     "inputSchema": {"type": "object", "properties": {"ms": {"type": "integer"}}, "required": ["ms"]}},
    {"name": "solidworks_mass_properties", "description": "echo",
     "inputSchema": {"type": "object", "properties": {"v": {"type": "string"}}, "required": ["v"]}},
]


def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if LOG:
            with open(LOG, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        try:
            msg = json.loads(line)
        except ValueError:
            sys.stdout.write("this is not json (diagnostics)\n")
            sys.stdout.flush()
            continue
        if msg.get("id") is None:
            continue
        method = msg.get("method")
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": msg["id"], "result": {
                "protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                "serverInfo": {"name": "gc-stub", "version": "1.0.0"}}})
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": TOOLS}})
        elif method == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name")
            args = params.get("arguments") or {}
            if name == "solidworks_sketch_and_extrude":
                time.sleep(max(0, int(args.get("ms", 0))) / 1000.0)
                send({"jsonrpc": "2.0", "id": msg["id"],
                      "result": {"content": [{"type": "text", "text": "slept %s" % args.get("ms")}]}})
            elif name == "solidworks_mass_properties":
                send({"jsonrpc": "2.0", "id": msg["id"],
                      "result": {"content": [{"type": "text", "text": "echo %s" % args.get("v")}]}})
            else:
                send({"jsonrpc": "2.0", "id": msg["id"],
                      "error": {"code": -32602, "message": "unknown tool %s" % name}})
        else:
            send({"jsonrpc": "2.0", "id": msg["id"],
                  "error": {"code": -32601, "message": "unknown method %s" % method}})


if __name__ == "__main__":
    main()
