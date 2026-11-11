path = "mcp-server-solidworks-main/adapters/claude/server.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

target = """mcp = MCPServer(
    "solidworks-execution-adapter",
    cache_hints={
        "resources/read": _RECIPE_CACHE,
        "resources/list": _RECIPE_CACHE,
        "resources/templates/list": _RECIPE_CACHE,
    },
)"""

replacement = """try:
    mcp = MCPServer(
        "solidworks-execution-adapter",
        cache_hints={
            "resources/read": _RECIPE_CACHE,
            "resources/list": _RECIPE_CACHE,
            "resources/templates/list": _RECIPE_CACHE,
        },
    )
except TypeError:
    mcp = MCPServer("solidworks-execution-adapter")"""

if target in content:
    content = content.replace(target, replacement, 1)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    print("Updated mcp initialization successfully!")
else:
    print("Target not found!")
