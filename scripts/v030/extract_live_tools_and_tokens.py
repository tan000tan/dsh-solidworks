import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Set up paths
PLUGIN_ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SERVER_PATH = PLUGIN_ROOT / "vendor" / "solidworks-automation-skill" / "mcp-server" / "server.py"
SERVER_CWD = SERVER_PATH.parent.parent
EVIDENCE_DIR = PLUGIN_ROOT / "v0.3.0-phase1-6-delivery" / "evidence_raw" / "A-Audit"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

# Add site-packages / paths if needed
sys.path.insert(0, str(SERVER_PATH.parent))

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

async def main():
    start_time = time.time()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SERVER_CWD) + os.pathsep + str(PLUGIN_ROOT)
    
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_PATH)],
        env=env,
        cwd=str(SERVER_CWD)
    )
    
    print(f"Connecting to live MCP server at {SERVER_PATH}...")
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("Session initialized successfully.")
            
            tools_response = await session.list_tools()
            tools = tools_response.tools
            print(f"Live MCP server returned {len(tools)} tools.")
            
            # Serialize tools to dictionary
            tool_data = []
            total_chars = 0
            for t in tools:
                schema_dict = {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.inputSchema
                }
                serialized = json.dumps(schema_dict, ensure_ascii=False)
                total_chars += len(serialized)
                
                # Check required fields and properties count
                props = t.inputSchema.get("properties", {}) if t.inputSchema else {}
                reqs = t.inputSchema.get("required", []) if t.inputSchema else []
                
                tool_data.append({
                    "name": t.name,
                    "description": t.description,
                    "param_count": len(props),
                    "required_params": reqs,
                    "properties": list(props.keys()),
                    "schema_char_len": len(serialized)
                })
    
    duration = time.time() - start_time
    
    # Calculate Token count
    # Let's see if tiktoken is available, or use cl100k estimation (avg 3.5 - 4 chars per token in json)
    token_count_cl100k = None
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        full_json = json.dumps([{"name": t["name"], "description": t["description"], "parameters": t["inputSchema"]} for t in tools], ensure_ascii=False)
        token_count_cl100k = len(enc.encode(full_json))
        print(f"Precise tiktoken cl100k_base token count: {token_count_cl100k}")
    except Exception as e:
        print(f"tiktoken not installed or failed: {e}. Calculating standard heuristic...")
        # standard fallback
        token_count_cl100k = int(total_chars / 3.7)
    
    result = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_tools": len(tools),
        "total_characters": total_chars,
        "token_count_cl100k": token_count_cl100k,
        "elapsed_seconds": round(duration, 3),
        "tools": tool_data
    }
    
    out_file = EVIDENCE_DIR / "live_mcp_tools_list.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"Saved live tool listing and token analysis to {out_file} (Duration: {duration:.3f}s)")

if __name__ == "__main__":
    asyncio.run(main())
