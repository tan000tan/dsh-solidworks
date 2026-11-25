"""MCP tool-registry integrity regression test (BUG-0005 / C1).

Why this suite exists
---------------------
During the promotion-phase audit, `solidworks_add_coincident_mate` was registered
through FastMCP while its `@mcp.tool(...)` decorator had been attached to the
private helper `_mate_delta_payload(before_mates, after_mates)`. The tool name was
therefore published, but every call reached the helper and failed with a
signature/AttributeError instead of running the mate operation. Nothing in the
existing suites looked at the *shape* of the decorator bindings, so the defect
survived a green test run.

This suite is a static (no COM, no SolidWorks, no network) guard:
  R1  every `@mcp.tool(...)` decorator must decorate a function whose name is
      either the explicit tool name or `<tool name>_tool`;
  R2  no decorated function may be private (leading underscore) — that is the
      exact shape of the BUG-0005 misbinding;
  R3  published tool names must be unique;
  R4  published tool names must use a known namespace prefix;
  R5  the decorator count must stay in a plausible range (guards against a
      truncated/merged file silently losing tools).

Run: python -B tests/tool_registry_integrity_test.py
"""
from __future__ import annotations

import os
import re
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# DSH_SOLIDWORKS_SERVER_PY lets the audit re-point this suite at a saved snapshot
# (used to prove the suite actually fails on the pre-fix file).
SERVER_PY = os.environ.get("DSH_SOLIDWORKS_SERVER_PY") or os.path.join(
    PROJECT_ROOT, "vendor", "solidworks-automation-skill", "mcp-server", "server.py"
)

NAME_RE = re.compile(r'name\s*=\s*"([^"]+)"')
DEF_RE = re.compile(r"^def\s+([A-Za-z0-9_]+)\s*\(")
ALLOWED_PREFIXES = ("solidworks_", "cadstudio_", "design_spec_")


def _read_server_source() -> str:
    with open(SERVER_PY, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read().replace("\r\n", "\n").replace("\r", "\n")


def _collect_bindings(source: str) -> list[dict]:
    """Return one record per `@mcp.tool(...)` decorator found in server.py."""
    lines = source.split("\n")
    bindings: list[dict] = []
    for index, line in enumerate(lines):
        if not line.startswith("@mcp.tool("):
            continue
        tool_name = None
        cursor = index + 1
        while cursor < len(lines) and not lines[cursor].startswith("def "):
            found = NAME_RE.search(lines[cursor])
            if found and tool_name is None:
                tool_name = found.group(1)
            cursor += 1
        func_name = DEF_RE.match(lines[cursor]).group(1) if cursor < len(lines) else None
        bindings.append(
            {
                "line": index + 1,
                "tool_name": tool_name or func_name,
                "explicit_name": tool_name is not None,
                "function": func_name,
            }
        )
    return bindings


class ToolRegistryIntegrityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = _read_server_source()
        cls.bindings = _collect_bindings(cls.source)

    def test_r0_source_present(self) -> None:
        """The vendored server must exist and expose at least one decorated tool."""
        self.assertTrue(os.path.isfile(SERVER_PY), f"missing {SERVER_PY}")
        self.assertGreater(len(self.bindings), 0, "no @mcp.tool decorators found")
        print(f"[R0] decorators parsed: {len(self.bindings)}")

    def test_r1_decorator_binds_matching_function(self) -> None:
        """R1: explicit tool name must match the decorated function name."""
        problems = []
        for item in self.bindings:
            if not item["explicit_name"]:
                continue
            function = item["function"] or ""
            if function != item["tool_name"] and function != f"{item['tool_name']}_tool":
                problems.append(
                    f"line {item['line']}: name={item['tool_name']} bound to def {function}()"
                )
        self.assertEqual(problems, [], "decorator/function name mismatches: " + "; ".join(problems))
        print(f"[R1] {len(self.bindings)} decorators bind to matching functions")

    def test_r2_no_private_function_registered(self) -> None:
        """R2: a private helper must never be published as an MCP tool (BUG-0005)."""
        bad = [
            f"line {item['line']}: {item['tool_name']} -> def {item['function']}()"
            for item in self.bindings
            if item["function"] and item["function"].startswith("_")
        ]
        self.assertEqual(bad, [], "private functions registered as tools: " + "; ".join(bad))
        print("[R2] no private helper is registered as a tool")

    def test_r3_tool_names_unique(self) -> None:
        """R3: duplicate tool names would shadow each other at registration time."""
        names = [item["tool_name"] for item in self.bindings if item["tool_name"]]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        self.assertEqual(duplicates, [], f"duplicate tool names: {duplicates}")
        print(f"[R3] {len(names)} unique tool names")

    def test_r4_namespace_prefix(self) -> None:
        """R4: every published tool must live in an expected namespace."""
        bad = [
            item["tool_name"]
            for item in self.bindings
            if item["tool_name"] and not item["tool_name"].startswith(ALLOWED_PREFIXES)
        ]
        self.assertEqual(bad, [], f"unexpected tool namespaces: {bad}")
        print("[R4] all tool names use solidworks_/cadstudio_ namespaces")

    def test_r5_decorator_count_plausible(self) -> None:
        """R5: guard against a truncated or double-spaced merge losing tools."""
        self.assertGreaterEqual(len(self.bindings), 60, "suspiciously few decorators")
        self.assertLessEqual(len(self.bindings), 80, "suspiciously many decorators")
        print(f"[R5] decorator count within expected band: {len(self.bindings)}")


if __name__ == "__main__":
    unittest.main(verbosity=2)