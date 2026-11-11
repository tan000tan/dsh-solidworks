import os

dsh_server = r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\mcp-server-solidworks-main\adapters\dsh\server.py"
with open(dsh_server, "r", encoding="utf-8") as f:
    c = f.read()

old_imp = "from mcp.server import MCPServer"
new_imp = """try:
    from mcp.server.fastmcp import FastMCP as MCPServer
except ImportError:
    try:
        from mcp.server import MCPServer
    except ImportError:
        from mcp.server.lowlevel import Server as MCPServer"""

if old_imp in c:
    c = c.replace(old_imp, new_imp, 1)
    with open(dsh_server, "w", encoding="utf-8") as f:
        f.write(c)
    print("adapters/dsh/server.py patched!")

claude_server = r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\mcp-server-solidworks-main\adapters\claude\server.py"
with open(claude_server, "r", encoding="utf-8") as f:
    c2 = f.read()

old_c_imp = """from mcp.server import MCPServer
from mcp.server.caching import CacheHint
from mcp.server.mcpserver.exceptions import ResourceError"""

new_c_imp = """try:
    from mcp.server.fastmcp import FastMCP as MCPServer
except ImportError:
    from mcp.server import MCPServer
try:
    from mcp.server.caching import CacheHint
except ImportError:
    class CacheHint:
        pass
try:
    from mcp.server.mcpserver.exceptions import ResourceError
except ImportError:
    class ResourceError(Exception):
        pass"""

if old_c_imp in c2:
    c2 = c2.replace(old_c_imp, new_c_imp, 1)
    with open(claude_server, "w", encoding="utf-8") as f:
        f.write(c2)
    print("adapters/claude/server.py patched!")
